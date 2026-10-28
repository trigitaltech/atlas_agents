import asyncio
import hashlib
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from app.core.policies import NetworkPolicy, PolicyError, normalize
from app.core.tool_registry import registry
from app.core.llm_gateway import LLMGateway
from app.agents.web_scraper.fetcher import Fetcher
from app.agents.web_scraper.extractor import deterministic
from app.agents.web_scraper.validator import fingerprint
from app.agents.web_scraper.planner import plan
from app.agents.web_scraper.access import check_access


class JobCancelled(Exception):
    pass


class State(TypedDict, total=False):
    plan: dict
    pages: int
    records: int
    stop_reason: str


class ScraperAgent:
    def __init__(
        self, request, config, checkpoint=lambda *args: None, cancelled=lambda: False
    ):
        self.request, self.config = request, config
        self.checkpoint, self.cancelled = checkpoint, cancelled
        self.policy = NetworkPolicy.for_execution(request)
        self.fetcher = Fetcher(self.policy)
        self.gateway = LLMGateway(config)
        self.queue = [(normalize(request.url), 0)]
        self.seen, self.hashes = set(), set()
        self.processed_urls: set[str] = set()
        self.attempts = 0
        self.pages, self.records = 0, 0
        self.started = time.monotonic()
        self.enabled = set(config.tools)
        self.stop_reason = "frontier_exhausted"

    async def tool(self, name, *args):
        return await registry[name].execute(list(args), self.enabled)

    def check_cancel(self):
        if self.cancelled():
            raise JobCancelled("Job cancelled")

    async def initialize(self, state):
        self.check_cancel()
        self.policy.check(self.request.url)
        p = plan(self.request).model_dump()
        self.checkpoint("planning", {"plan": p})
        return {"plan": p, "pages": 0, "records": 0}

    async def visit(self, state):
        self.check_cancel()
        start = time.monotonic()
        url, depth = self.queue.pop(0)
        self.seen.add(url)
        self.attempts += 1
        self.checkpoint("fetching", {"url": url})
        page = await self.tool("http_fetch", self.fetcher, url)
        check_access(page.html, page.status_code)
        if "html" not in page.content_type:
            raise PolicyError("Target is not HTML")
        page.url = normalize(page.url)
        if page.url in self.processed_urls:
            return {"pages": self.pages, "records": self.records}
        self.processed_urls.add(page.url)
        self.seen.add(page.url)
        title, text = await self.tool("html_parser", page.html)
        if self.request.render_js or (
            len(text) < 80
            and "<script" in page.html
            and "browser_navigation" in self.enabled
        ):
            page = await self.tool("browser_navigation", page.url, self.fetcher)
            check_access(page.html, page.status_code)
            title, text = await self.tool("html_parser", page.html)
        self.check_cancel()
        self.checkpoint("extracting", {"url": page.url})
        if self.config.provider == "deterministic":
            extracted = deterministic(text, title, self.request.fields)
        else:
            remaining = self.request.token_budget - self.gateway.tokens
            # Trim conservatively, retaining a bounded output reserve.
            usable = max(0, remaining - 4000)
            bounded = text.encode()[:usable].decode(errors="ignore")
            extracted = await self.tool(
                "ai_extraction",
                self.gateway,
                bounded,
                self.request.fields,
                self.request.instruction,
                remaining,
            )
        record = await self.tool(
            "validation", extracted, self.request.fields, text, page.url
        )
        key = fingerprint(record)
        payload = {
            "url": page.url,
            "title": title,
            "status_code": page.status_code,
            "content_hash": hashlib.sha256(page.html.encode()).hexdigest(),
        }
        self.check_cancel()
        if key not in self.hashes:
            self.hashes.add(key)
            payload["record"] = record
            self.records += 1
        self.pages += 1
        payload.update(
            pages=self.pages,
            records=self.records,
            tokens=self.gateway.tokens,
            approximate_cost=self.gateway.cost,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        await self.tool(
            "database_storage", lambda data: self.checkpoint("stored", data), payload
        )
        if depth < self.request.max_depth:
            for link in await self.tool(
                "link_discovery", page.html, page.url, self.policy
            ):
                if link not in self.seen and all(link != u for u, _ in self.queue):
                    self.queue.append((link, depth + 1))
                if len(self.queue) >= self.request.max_pages:
                    break
        return {"pages": self.pages, "records": self.records}

    def route(self, state):
        self.check_cancel()
        self.queue = [(url, depth) for url, depth in self.queue if url not in self.seen]
        if self.attempts >= self.request.max_pages:
            self.stop_reason = "page_limit"
            return END
        if self.gateway.tokens >= self.request.token_budget:
            self.stop_reason = "token_budget"
            return END
        return "visit" if self.queue else END

    async def run(self):
        graph = StateGraph(State)
        graph.add_node("initialize", self.initialize)
        graph.add_node("visit", self.visit)
        graph.add_edge(START, "initialize")
        graph.add_edge("initialize", "visit")
        graph.add_conditional_edges("visit", self.route)
        compiled = graph.compile()
        try:
            async with asyncio.timeout(self.request.timeout):
                result = await compiled.ainvoke(
                    {}, {"recursion_limit": self.request.max_pages + 5}
                )
                result["stop_reason"] = self.stop_reason
                return result
        finally:
            await self.fetcher.close()

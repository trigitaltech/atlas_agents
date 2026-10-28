import asyncio
from unittest.mock import AsyncMock
import httpx
import pytest
from app.core.config import settings
from app.core.policies import NetworkPolicy, PolicyError
from app.agents.web_scraper.schemas import ScrapeRequest, AgentConfiguration, Extraction
from app.agents.web_scraper.fetcher import Fetcher, Page
from app.agents.web_scraper.extractor import parse, deterministic
from app.agents.web_scraper.validator import validate, fingerprint
from app.agents.web_scraper.crawler import discover
from app.agents.web_scraper.agent import ScraperAgent, JobCancelled
from app.agents.web_scraper.exporter import export


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:password@example.com",
        "http://example.com:9000",
    ],
)
def test_invalid_url(url):
    with pytest.raises(ValueError):
        ScrapeRequest(
            authorization_confirmed=True,
            url=url,
            instruction="Extract",
            fields=["title"],
        )


def test_valid_url():
    assert (
        ScrapeRequest(
            authorization_confirmed=True,
            url="https://example.com",
            instruction="Extract",
            fields=["title"],
        ).max_pages
        == 5
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://169.254.169.254",
        "https://evil.test",
        "http://[::1]",
    ],
)
def test_ssrf(url):
    with pytest.raises(PolicyError):
        NetworkPolicy(["example.com"]).check(url)


async def test_dns_rebinding(monkeypatch):
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop, "getaddrinfo", AsyncMock(return_value=[(2, 1, 6, "", ("127.0.0.1", 443))])
    )
    with pytest.raises(PolicyError):
        await NetworkPolicy(["example.com"]).resolve("https://example.com")


async def test_mixed_dns(monkeypatch):
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop,
        "getaddrinfo",
        AsyncMock(
            return_value=[
                (2, 1, 6, "", ("93.184.216.34", 443)),
                (2, 1, 6, "", ("10.0.0.1", 443)),
            ]
        ),
    )
    with pytest.raises(PolicyError):
        await NetworkPolicy(["example.com"]).resolve("https://example.com")


async def mock_fetcher(monkeypatch, handler):
    fetcher = Fetcher(NetworkPolicy(["example.com"]))
    await fetcher.client.aclose()
    fetcher.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        fetcher.policy,
        "resolve",
        AsyncMock(return_value=("example.com", "93.184.216.34")),
    )
    monkeypatch.setattr(fetcher, "throttle", AsyncMock())
    return fetcher


async def test_redirect_restriction(monkeypatch):
    fetcher = await mock_fetcher(
        monkeypatch,
        lambda r: httpx.Response(302, headers={"location": "http://127.0.0.1/"}),
    )
    with pytest.raises(PolicyError):
        await fetcher.request("https://example.com", robots_check=False)
    await fetcher.close()


async def test_pinned_transport(monkeypatch):
    def handler(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(200, text="ok")

    fetcher = await mock_fetcher(monkeypatch, handler)
    assert (await fetcher.request("https://example.com", False)).html == "ok"
    await fetcher.close()


async def test_robots_disallow(monkeypatch):
    fetcher = Fetcher(NetworkPolicy(["example.com"]))
    monkeypatch.setattr(
        fetcher,
        "request",
        AsyncMock(
            return_value=Page(
                "https://example.com/robots.txt",
                "User-agent: *\nDisallow: /private",
                200,
            )
        ),
    )
    with pytest.raises(PolicyError):
        await fetcher.check_robots("https://example.com/private")
    await fetcher.check_robots("https://example.com/public")
    await fetcher.close()


async def test_robots_unavailable_fails_closed(monkeypatch):
    fetcher = Fetcher(NetworkPolicy(["example.com"]))
    monkeypatch.setattr(fetcher, "request", AsyncMock(return_value=Page("", "", 503)))
    with pytest.raises(PolicyError):
        await fetcher.check_robots("https://example.com")
    await fetcher.close()


async def test_response_limit(monkeypatch):
    fetcher = await mock_fetcher(
        monkeypatch, lambda r: httpx.Response(200, text="x" * 200)
    )
    monkeypatch.setattr(settings(), "max_response_bytes", 100)
    with pytest.raises(PolicyError):
        await fetcher.request("https://example.com", False)
    await fetcher.close()


def test_parse_extract_validate(html):
    title, text = parse(html)
    assert "ignore previous" not in text
    fields = ["company_name", "business_email", "location", "source_url"]
    output = validate(
        deterministic(text, title, fields), fields, text, "https://example.com"
    )
    assert output["extracted_data"] == {
        "company_name": "Acme Labs",
        "business_email": "hello@acme.test",
        "location": None,
        "source_url": "https://example.com",
    }


def test_evidence_rejects_hallucination():
    raw = Extraction.model_validate(
        {"fields": {"location": {"value": "Paris", "evidence": "Paris"}}}
    )
    assert (
        validate(raw, ["location"], "London", "https://example.com")["extracted_data"][
            "location"
        ]
        is None
    )


def test_discovery(html):
    assert discover(html, "https://example.com", NetworkPolicy(["example.com"])) == [
        "https://example.com/about"
    ]


def test_duplicate_sources():
    assert fingerprint(
        {"extracted_data": {"title": "Acme", "source_url": "a"}}
    ) == fingerprint({"extracted_data": {"title": "Acme", "source_url": "b"}})


def test_exports():
    assert "'=HYPERLINK" in export([{"name": "=HYPERLINK(1)"}], "csv")
    assert '"name": null' in export([{"name": None}], "json")


async def test_page_limit_and_duplicates(html, monkeypatch):
    request = ScrapeRequest(
        authorization_confirmed=True,
        url="https://example.com",
        instruction="Extract",
        fields=["title"],
        max_pages=2,
    )
    saved = []
    agent = ScraperAgent(
        request,
        AgentConfiguration(),
        lambda step, payload: saved.append((step, payload)),
    )
    monkeypatch.setattr(
        agent.fetcher,
        "request",
        AsyncMock(side_effect=lambda url: Page(url, html, 200)),
    )
    result = await agent.run()
    assert result["pages"] == 2 and result["records"] == 1
    assert result["stop_reason"] == "page_limit"
    assert len([s for s, p in saved if s == "stored"]) == 2


async def test_depth_limit(html, monkeypatch):
    agent = ScraperAgent(
        ScrapeRequest(
            authorization_confirmed=True,
            url="https://example.com",
            instruction="Extract",
            fields=["title"],
            max_depth=0,
        ),
        AgentConfiguration(),
    )
    monkeypatch.setattr(
        agent.fetcher,
        "request",
        AsyncMock(return_value=Page("https://example.com", html, 200)),
    )
    assert (await agent.run())["pages"] == 1


async def test_cancellation():
    agent = ScraperAgent(
        ScrapeRequest(
            authorization_confirmed=True,
            url="https://example.com",
            instruction="Extract",
            fields=["title"],
        ),
        AgentConfiguration(),
        cancelled=lambda: True,
    )
    with pytest.raises(JobCancelled):
        await agent.run()


async def test_execution_timeout(monkeypatch):
    request = ScrapeRequest(
        authorization_confirmed=True,
        url="https://example.com",
        instruction="Extract",
        fields=["title"],
    )
    request.timeout = 0.01
    agent = ScraperAgent(request, AgentConfiguration())

    async def slow(url):
        await asyncio.sleep(1)

    monkeypatch.setattr(agent.fetcher, "request", slow)
    with pytest.raises(TimeoutError):
        await agent.run()


async def test_browser_disabled():
    from app.agents.web_scraper.browser import render

    fetcher = Fetcher(NetworkPolicy(["example.com"]))
    with pytest.raises(PolicyError):
        await render("https://example.com", fetcher)
    await fetcher.close()


async def test_redirect_alias_deduplication(html, monkeypatch):
    agent = ScraperAgent(
        ScrapeRequest(
            authorization_confirmed=True,
            url="https://example.com",
            instruction="Extract",
            fields=["title"],
            max_pages=3,
        ),
        AgentConfiguration(),
    )
    monkeypatch.setattr(
        agent.fetcher,
        "request",
        AsyncMock(return_value=Page("https://example.com/canonical", html, 200)),
    )
    result = await agent.run()
    assert result["pages"] == 1
    assert result["records"] == 1


async def test_robots_delay_is_applied_to_shared_throttle(monkeypatch):
    fetcher = Fetcher(NetworkPolicy(["example.com"]))
    monkeypatch.setattr(
        fetcher,
        "request",
        AsyncMock(
            return_value=Page(
                "https://example.com/robots.txt",
                "User-agent: *\nCrawl-delay: 5\nRequest-rate: 1/8",
                200,
            )
        ),
    )
    await fetcher.check_robots("https://example.com/public")
    assert fetcher.delays["example.com"] == 8
    await fetcher.close()


async def test_tool_input_schema_and_permission():
    from app.core.tool_registry import registry

    assert (
        "url" in registry["http_fetch"].input_schema.model_json_schema()["properties"]
    )
    with pytest.raises(PermissionError):
        await registry["html_parser"].execute(["<html></html>"], set())
    with pytest.raises(ValueError):
        await registry["html_parser"].execute([], {"html_parser"})


@pytest.mark.parametrize(
    "ip",
    [
        "224.0.0.1",
        "ff02::1",
        "2002:7f00:1::",
        "::ffff:127.0.0.1",
        "0.0.0.0",
        "100.64.0.1",
    ],
)
async def test_non_public_address_classes(ip, monkeypatch):
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop, "getaddrinfo", AsyncMock(return_value=[(2, 1, 6, "", (ip, 443))])
    )
    with pytest.raises(PolicyError):
        await NetworkPolicy(["example.com"]).resolve("https://example.com")

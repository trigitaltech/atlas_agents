"""Typed, permission-checked tool contracts shared by all agent implementations."""

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, create_model


@dataclass
class Tool:
    name: str
    description: str
    permission: str
    function: Callable
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    timeout: float = 45

    async def execute(self, args: list, enabled: set[str]) -> Any:
        if self.name not in enabled:
            raise PermissionError(f"Tool {self.name} is disabled")
        names = list(self.input_schema.model_fields)
        if len(args) != len(names):
            raise ValueError(f"Incorrect argument count for {self.name}")
        payload = self.input_schema.model_validate(dict(zip(names, args)))
        async with asyncio.timeout(self.timeout):
            value = self.function(*(getattr(payload, key) for key in names))
            if inspect.isawaitable(value):
                value = await value
            return self.output_schema(result=value).result


registry: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    if tool.name in registry:
        raise ValueError("Duplicate tool name")
    registry[tool.name] = tool


def initialize() -> None:
    if registry:
        return
    from app.agents.web_scraper.extractor import parse
    from app.agents.web_scraper.crawler import discover
    from app.agents.web_scraper.validator import validate
    from app.agents.web_scraper.exporter import export
    from app.agents.web_scraper.browser import render
    from app.agents.web_scraper.fetcher import Page
    from app.agents.web_scraper.schemas import Extraction

    async def fetch(fetcher, url):
        return await fetcher.request(url)

    async def extract(gateway, text, fields, instruction, budget):
        return await gateway.extract(text, fields, instruction, budget)

    def store(callback, payload):
        return callback(payload)

    # Context handles stay backend-only. Network and LLM access also enforce independent server policy.
    specs = [
        (
            "http_fetch",
            "Fetch an authorized public URL",
            "network",
            fetch,
            {"fetcher": Any, "url": str},
            Page,
        ),
        (
            "browser_navigation",
            "Render with restricted resources",
            "browser",
            render,
            {"url": str, "fetcher": Any},
            Page,
        ),
        (
            "html_parser",
            "Remove executable markup and extract text",
            "read",
            parse,
            {"html": str},
            tuple[str, str],
        ),
        (
            "link_discovery",
            "Discover authorized internal links",
            "read",
            discover,
            {"html": str, "url": str, "policy": Any},
            list[str],
        ),
        (
            "ai_extraction",
            "Extract evidence-backed structured fields",
            "llm",
            extract,
            {
                "gateway": Any,
                "text": str,
                "fields": list[str],
                "instruction": str,
                "budget": int,
            },
            Extraction,
        ),
        (
            "validation",
            "Validate source evidence",
            "read",
            validate,
            {"extraction": Extraction, "fields": list[str], "text": str, "url": str},
            dict,
        ),
        (
            "database_storage",
            "Persist job output",
            "database",
            store,
            {"callback": Any, "payload": dict},
            Any,
        ),
        (
            "csv_export",
            "Export formula-safe CSV",
            "export",
            lambda records: export(records, "csv"),
            {"records": list[dict]},
            str,
        ),
        (
            "json_export",
            "Export JSON",
            "export",
            lambda records: export(records, "json"),
            {"records": list[dict]},
            str,
        ),
    ]
    for name, description, permission, function, inputs, output in specs:
        input_schema = create_model(
            name + "Input",
            __config__=ConfigDict(extra="forbid"),
            **{key: (annotation, ...) for key, annotation in inputs.items()},
        )
        output_schema = create_model(name + "Output", result=(output, ...))
        register(
            Tool(name, description, permission, function, input_schema, output_schema)
        )


initialize()

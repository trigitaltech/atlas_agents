"""Credential-safe diagnostics. Sends no website traffic and downloads no models."""

import argparse
import asyncio
import sys

import httpx
from pydantic import ValidationError

from app.agents.web_scraper.schemas import AgentConfiguration
from app.agents.web_scraper.validator import validate
from app.core.config import settings
from app.core.llm_gateway import LLMGateway, LLMProviderError, ollama_connection


async def check(model: str | None = None) -> int:
    try:
        endpoint, headers = ollama_connection(settings())
        async with httpx.AsyncClient(
            timeout=5, trust_env=False, follow_redirects=False
        ) as client:
            response = await client.get(
                endpoint.removesuffix("/api/chat") + "/api/tags", headers=headers
            )
        if response.status_code == 200:
            models = response.json().get("models", [])
            if not isinstance(models, list):
                raise ValueError("Invalid model list")
            print("Ollama reachable; model count:", len(models))
            if model is not None:
                installed = any(
                    isinstance(item, dict)
                    and model in {item.get("name"), item.get("model")}
                    for item in models
                )
                if not installed:
                    print("Selected model is not listed; no model was downloaded.")
                    return 1
        elif response.status_code == 404 and model is not None:
            print("Model listing unavailable; checking the explicitly selected model.")
        else:
            print("Ollama connection check failed; HTTP status:", response.status_code)
            return 1
        if model is None:
            print(
                "Use --model with an available model ID to test schema extraction on a static fixture."
            )
            return 0
        text = "Company: Atlas Fixture. Office: Test City."
        fields = ["company_name", "location", "phone"]
        output = await LLMGateway(
            AgentConfiguration(provider="ollama", model=model)
        ).extract(
            text,
            fields,
            "Extract the company name and office city verbatim. Missing phone must be null.",
            10000,
        )
        record = validate(output, fields, text, "urn:atlas:diagnostic")
        if record["extracted_data"] != {
            "company_name": "Atlas Fixture",
            "location": "Test City",
            "phone": None,
        }:
            print(
                "Schema response received, but fixture values or evidence did not validate."
            )
            return 1
        print("Structured extraction, missing null and source evidence: passed.")
        return 0
    except LLMProviderError as exc:
        print(str(exc))  # Only static, sanitized gateway messages.
    except httpx.HTTPError as exc:
        print("Ollama network check failed; error type:", type(exc).__name__)
    except (ValueError, TypeError, AttributeError, ValidationError):
        print("Ollama configuration or model-list response is invalid.")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        help="An available model ID. Sends only a small static extraction fixture.",
    )
    sys.exit(asyncio.run(check(parser.parse_args().model)))


if __name__ == "__main__":
    main()

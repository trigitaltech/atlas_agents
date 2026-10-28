"""Structured model calls with backend-only credentials and safe provider errors."""

import asyncio
import json
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings, settings
from app.agents.web_scraper.schemas import (
    AgentConfiguration,
    Extraction,
    extraction_schema,
)
from app.agents.web_scraper.prompts import SYSTEM_PROMPT, CLOUD_JSON_INSTRUCTION
from app.agents.web_scraper.extractor import parse_cloud_extraction


class LLMProviderError(RuntimeError):
    """Only static, credential-free messages may cross the provider boundary."""


def ollama_connection(cfg: Settings) -> tuple[str, dict[str, str]]:
    """Resolve a native Ollama endpoint; never follow redirects with its credential."""
    parsed = urlsplit(cfg.ollama_url)
    if cfg.ollama_mode == "cloud":
        if cfg.ollama_url.rstrip("/") != "https://ollama.com":
            raise LLMProviderError(
                "Cloud mode requires OLLAMA_URL=https://ollama.com without /api or /api/chat"
            )
        if not cfg.ollama_api_key.get_secret_value():
            raise LLMProviderError(
                "OLLAMA_API_KEY is required for Ollama Cloud; configure it on the backend"
            )
    elif parsed.hostname in {"ollama.com", "www.ollama.com"}:
        raise LLMProviderError(
            "Set OLLAMA_MODE=cloud to use prompt JSON extraction with Ollama Cloud"
        )
    key = cfg.ollama_api_key.get_secret_value()
    headers: dict[str, str] = {}
    if key:
        if parsed.scheme != "https":
            raise LLMProviderError("Ollama API credentials require an HTTPS endpoint")
        if any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise LLMProviderError("Ollama API credential has an invalid format")
        headers["Authorization"] = f"Bearer {key}"
    return cfg.ollama_url.rstrip("/") + "/api/chat", headers


class LLMGateway:
    def __init__(self, configuration: AgentConfiguration):
        self.config = configuration
        self.tokens = 0
        self.cost = 0.0

    async def extract(
        self, text: str, fields: list[str], instruction: str, budget: int
    ) -> Extraction:
        cfg = settings()
        cloud = self.config.provider == "ollama" and cfg.ollama_mode == "cloud"
        system_prompt = (
            SYSTEM_PROMPT + CLOUD_JSON_INSTRUCTION if cloud else SYSTEM_PROMPT
        )
        schema = extraction_schema(fields)
        payload = json.dumps(
            {
                "instruction": instruction,
                "requested_fields": fields,
                "output_schema": schema,
                "untrusted_website_text": text,
            },
            ensure_ascii=False,
        )
        # Conservative budget includes the prompt schema and any provider schema contract.
        estimate = (
            len(payload.encode())
            + len(system_prompt.encode())
            + len(json.dumps(schema).encode())
            + 100
        )
        output_tokens = min(2048, budget // 3)
        if estimate + output_tokens > budget:
            raise ValueError(
                "Token budget exhausted; reduce pages/content or increase budget"
            )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ]
        if self.config.provider == "ollama":
            endpoint, headers = ollama_connection(cfg)
            credential = cfg.ollama_api_key.get_secret_value()
            body = {
                "model": self.config.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.config.temperature,
                    "num_predict": output_tokens,
                },
            }
            if not cloud:
                body["format"] = schema
        elif self.config.provider == "openai":
            if not cfg.openai_api_key:
                raise LLMProviderError("OPENAI_API_KEY is not configured")
            endpoint = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {cfg.openai_api_key}"}
            credential = cfg.openai_api_key
            body = {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_completion_tokens": output_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "extraction",
                        "strict": True,
                        "schema": schema,
                    },
                },
            }
        else:
            raise LLMProviderError("This provider does not support model extraction")

        consumed_before = self.tokens
        async with httpx.AsyncClient(
            timeout=30, trust_env=False, follow_redirects=False
        ) as client:
            for attempt in range(3):
                try:
                    response = await client.post(endpoint, headers=headers, json=body)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    status = (
                        exc.response.status_code
                        if isinstance(exc, httpx.HTTPStatusError)
                        else None
                    )
                    retryable = isinstance(
                        exc, (httpx.TimeoutException, httpx.NetworkError)
                    ) or status in {429, 502, 503, 504}
                    # Failed requests may have been billable. Never repeat their raw errors/bodies.
                    self.tokens += estimate + output_tokens
                    if not retryable or attempt == 2:
                        if status in {401, 403}:
                            message = "LLM provider rejected authentication or access; check backend credentials and model permissions"
                        elif status is not None and 300 <= status < 400:
                            message = "LLM provider redirected the request; configure its final endpoint directly"
                        else:
                            message = "LLM provider request failed; check service availability, model ID and request compatibility"
                        raise LLMProviderError(message) from None
                    if (
                        self.tokens - consumed_before + estimate + output_tokens
                        > budget
                    ):
                        raise LLMProviderError(
                            "Insufficient token budget for provider retry"
                        ) from None
                    await asyncio.sleep(2**attempt)
                    continue
                except (ValueError, httpx.InvalidURL):
                    raise LLMProviderError(
                        "LLM provider request configuration is invalid"
                    ) from None

                try:
                    result = response.json()
                    if self.config.provider == "openai":
                        usage = result.get("usage", {})
                        self.tokens += usage.get(
                            "total_tokens", estimate + output_tokens
                        )
                        self.cost += (
                            usage.get("prompt_tokens", 0) * cfg.input_cost_per_million
                            + usage.get("completion_tokens", 0)
                            * cfg.output_cost_per_million
                        ) / 1_000_000
                        content = result["choices"][0]["message"]["content"]
                    else:
                        self.tokens += result.get(
                            "prompt_eval_count", estimate
                        ) + result.get("eval_count", output_tokens)
                        content = result["message"]["content"]
                    if not isinstance(content, str) or (
                        credential and credential in content
                    ):
                        raise ValueError("Unsafe provider content")
                    if cloud:
                        return parse_cloud_extraction(content, fields, text)
                    return Extraction.model_validate_json(content)
                except (ValueError, KeyError, TypeError, IndexError, AttributeError):
                    # Pydantic and JSON errors may include raw upstream content, including echoed keys.
                    raise LLMProviderError(
                        "LLM provider returned invalid or unsafe structured extraction output"
                    ) from None
        raise LLMProviderError("Extraction failed")

"""Cloud extraction is tested with fictional pages and mocked provider responses only."""

import hashlib
import json
import logging
import secrets
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from app.agents.web_scraper.extractor import parse_cloud_extraction
from app.agents.web_scraper.fetcher import Fetcher, Page
from app.agents.web_scraper.schemas import AgentConfiguration
from app.core.config import settings
from app.core.llm_gateway import LLMGateway, LLMProviderError, ollama_connection


@pytest.fixture
def cloud(monkeypatch):
    key = SecretStr(secrets.token_urlsafe(24))
    monkeypatch.setattr(settings(), "ollama_mode", "cloud")
    monkeypatch.setattr(settings(), "ollama_url", "https://ollama.com")
    monkeypatch.setattr(settings(), "ollama_api_key", key)
    return key


def contains_secret(value, key):
    return key.get_secret_value() in str(value)


def header_valid(headers, key):
    expected = hashlib.sha256(("Bearer " + key.get_secret_value()).encode()).digest()
    return (
        hashlib.sha256(headers.get("Authorization", "").encode()).digest() == expected
    )


def chat_response(fields):
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://ollama.com/api/chat"),
        json={
            "message": {"content": json.dumps({"fields": fields})},
            "prompt_eval_count": 100,
            "eval_count": 50,
        },
    )


async def test_cloud_native_endpoint_bearer_and_prompt_json(monkeypatch, cloud):
    async def post(_client, url, **kwargs):
        assert url == "https://ollama.com/api/chat"
        assert header_valid(kwargs["headers"], cloud)
        body = kwargs["json"]
        assert body["stream"] is False
        assert body["model"] == "available-cloud-model"
        assert "format" not in body and "response_format" not in body
        assert not contains_secret(json.dumps(body), cloud)
        assert "exactly one JSON object" in body["messages"][0]["content"]
        user = json.loads(body["messages"][1]["content"])
        assert user["instruction"] == "Extract the office city; do not infer phone."
        assert user["requested_fields"] == ["location", "phone"]
        assert user["output_schema"]["properties"]["fields"]["required"] == [
            "location",
            "phone",
        ]
        return chat_response(
            {"location": {"value": "Test City", "evidence": "Office: Test City."}}
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    output = await LLMGateway(
        AgentConfiguration(provider="ollama", model="available-cloud-model")
    ).extract(
        "Office: Test City.",
        ["location", "phone"],
        "Extract the office city; do not infer phone.",
        10000,
    )
    assert output.fields["location"].value == "Test City"
    assert output.fields["location"].evidence == "Office: Test City."
    assert (
        output.fields["phone"].value is None and output.fields["phone"].evidence is None
    )


@pytest.mark.parametrize(
    "base",
    [
        "https://ollama.com/api",
        "https://ollama.com/api/chat",
        "http://ollama.com",
        "https://different.invalid",
    ],
)
def test_cloud_rejects_incorrect_base_url(cloud, monkeypatch, base):
    monkeypatch.setattr(settings(), "ollama_url", base)
    with pytest.raises(LLMProviderError, match="OLLAMA_URL=https://ollama.com"):
        ollama_connection(settings())


def test_cloud_requires_backend_key(cloud, monkeypatch):
    monkeypatch.setattr(settings(), "ollama_api_key", SecretStr(""))
    with pytest.raises(LLMProviderError, match="OLLAMA_API_KEY is required"):
        ollama_connection(settings())


@pytest.mark.parametrize("wrapped", [False, True])
def test_cloud_values_need_exact_evidence_and_expected_types(wrapped):
    payload = {
        "fields": {
            "location": {"value": "Test City", "evidence": "Office: Test City."},
            "invented": {"value": "Invented CEO", "evidence": "Invented CEO"},
            "unquoted": {"value": "Test City", "evidence": None},
            "wrong_quote": {"value": "Test City", "evidence": "Office:"},
            "array": {"value": ["Test City"], "evidence": "Test City"},
            "number": {"value": 42, "evidence": "42"},
            "extra": {
                "value": "Test City",
                "evidence": "Test City",
                "unsupported": True,
            },
            "not_requested": {"value": "Test City", "evidence": "Test City"},
        }
    }
    text = json.dumps(payload)
    if wrapped:
        text = "```json\n" + text + "\n```"
    fields = [
        "location",
        "invented",
        "unquoted",
        "wrong_quote",
        "array",
        "number",
        "extra",
        "missing",
    ]
    parsed = parse_cloud_extraction(text, fields, "Office: Test City.")
    assert list(parsed.fields) == fields
    assert parsed.fields["location"].value == "Test City"
    for name in fields[1:]:
        assert parsed.fields[name].value is None
        assert parsed.fields[name].evidence is None


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"location":"Test City"}',
        '{"fields":[]}',
        '{"fields":{},"extra":true}',
        '{"fields":{"location":null,"location":null}}',
        '{"fields":{"location":{"value":NaN}}}',
        'Explanation: {"fields":{}}',
    ],
)
def test_cloud_rejects_ambiguous_or_invalid_json(content):
    with pytest.raises(ValueError):
        parse_cloud_extraction(content, ["location"], "Office: Test City.")


@pytest.mark.parametrize("failure", ["auth", "malformed", "echo", "transport"])
async def test_cloud_errors_never_expose_credentials(
    monkeypatch, cloud, caplog, failure
):
    async def post(_client, url, **kwargs):
        key = cloud.get_secret_value()
        if failure == "transport":
            raise httpx.ConnectError(key, request=httpx.Request("POST", url))
        if failure == "auth":
            return httpx.Response(
                401, request=httpx.Request("POST", url), json={"error": key}
            )
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "message": {
                    "content": key
                    if failure == "malformed"
                    else json.dumps(
                        {"fields": {"location": {"value": key, "evidence": key}}}
                    )
                }
            },
        )

    async def no_wait(_seconds):
        pass

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr("app.core.llm_gateway.asyncio.sleep", no_wait)
    with caplog.at_level(logging.INFO), pytest.raises(LLMProviderError) as caught:
        await LLMGateway(AgentConfiguration(provider="ollama")).extract(
            "Office: Test City.", ["location"], "Extract", 20000
        )
    assert not contains_secret(str(caught.value), cloud)
    assert not contains_secret(caplog.text, cloud)


def test_cloud_job_validates_then_persists_source_facts(client, monkeypatch, cloud):
    html = "<html><head><title>Atlas Fiction</title></head><body>Office: Test City.</body></html>"
    monkeypatch.setattr(
        Fetcher,
        "request",
        AsyncMock(return_value=Page("https://cloud-scrape-fixture.test/", html, 200)),
    )

    async def post(_client, url, **kwargs):
        assert url == "https://ollama.com/api/chat"
        assert "format" not in kwargs["json"]
        return chat_response(
            {
                "location": {"value": "Test City", "evidence": "Office: Test City."},
                "phone": {"value": "invented", "evidence": "invented"},
            }
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    created = client.post(
        "/api/agents",
        json={
            "name": "Cloud fixture",
            "configuration": {"provider": "ollama", "model": "available-cloud-model"},
        },
    )
    assert created.status_code == 201
    job = client.post(
        "/api/scraping/jobs",
        json={
            "authorization_confirmed": True,
            "agent_id": created.json()["id"],
            "url": "https://cloud-scrape-fixture.test/",
            "instruction": "Extract the office city and published phone.",
            "fields": ["location", "phone", "source_url"],
            "max_pages": 1,
            "max_depth": 0,
        },
    ).json()
    detail = client.get(f"/api/scraping/jobs/{job['id']}").json()
    assert detail["status"] == "completed"
    assert detail["context"]["authorized_hostnames"] == ["cloud-scrape-fixture.test"]
    assert "cloud-scrape-fixture.test" not in settings().domains
    results = client.get(f"/api/scraping/jobs/{job['id']}/results").json()
    assert results[0]["extracted_data"] == {
        "location": "Test City",
        "phone": None,
        "source_url": "https://cloud-scrape-fixture.test/",
    }
    assert results[0]["evidence"] == {
        "location": "Office: Test City.",
        "source_url": "https://cloud-scrape-fixture.test/",
    }
    for path in [
        "/api/agents",
        "/api/models",
        "/api/settings",
        f"/api/scraping/jobs/{job['id']}",
        f"/api/scraping/jobs/{job['id']}/results",
    ]:
        assert not contains_secret(client.get(path).text, cloud)


def test_cloud_error_not_persisted_in_history(client, monkeypatch, cloud, caplog, html):
    monkeypatch.setattr(
        Fetcher,
        "request",
        AsyncMock(return_value=Page("https://example.com/", html, 200)),
    )

    async def post(_client, url, **kwargs):
        return httpx.Response(
            401,
            request=httpx.Request("POST", url),
            json={"error": cloud.get_secret_value()},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    agent = client.post(
        "/api/agents",
        json={
            "name": "Denied cloud",
            "configuration": {"provider": "ollama", "model": "available-cloud-model"},
        },
    ).json()
    job = client.post(
        "/api/scraping/jobs",
        json={
            "authorization_confirmed": True,
            "agent_id": agent["id"],
            "url": "https://example.com/",
            "instruction": "Extract",
            "fields": ["title"],
            "max_pages": 1,
        },
    ).json()
    detail = client.get(f"/api/scraping/jobs/{job['id']}").json()
    assert detail["status"] == "failed" and "authentication" in detail["error_message"]
    assert not contains_secret(json.dumps(detail), cloud)
    assert not contains_secret(caplog.text, cloud)

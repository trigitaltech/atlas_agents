import httpx
import pytest
from app.core.llm_gateway import LLMGateway, LLMProviderError
from app.agents.web_scraper.schemas import AgentConfiguration


async def test_structured_ollama(monkeypatch):
    async def post(*args, **kwargs):
        assert "untrusted_website_text" in kwargs["json"]["messages"][1]["content"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", "http://local"),
            json={
                "message": {
                    "content": '{"fields":{"title":{"value":"Acme","evidence":"Acme"}}}'
                },
                "prompt_eval_count": 120,
                "eval_count": 30,
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    gateway = LLMGateway(AgentConfiguration(provider="ollama", model="local"))
    assert (await gateway.extract("Acme", ["title"], "Extract", 10000)).fields[
        "title"
    ].value == "Acme"
    assert gateway.tokens == 150


async def test_budget_no_request(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No paid call expected")

    monkeypatch.setattr(httpx.AsyncClient, "post", forbidden)
    with pytest.raises(ValueError, match="budget"):
        await LLMGateway(AgentConfiguration(provider="ollama")).extract(
            "x" * 10000, ["title"], "Extract", 100
        )


async def test_openai_strict_schema_and_usage(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings(), "openai_api_key", "test-key")

    async def post(*args, **kwargs):
        payload = kwargs["json"]
        contract = payload["response_format"]["json_schema"]
        assert contract["strict"] is True
        assert contract["schema"]["additionalProperties"] is False
        assert contract["schema"]["properties"]["fields"]["required"] == ["title"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"fields":{"title":{"value":"Acme","evidence":"Acme"}}}'
                        }
                    }
                ],
                "usage": {
                    "total_tokens": 120,
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                },
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    gateway = LLMGateway(AgentConfiguration(provider="openai"))
    assert (await gateway.extract("Acme", ["title"], "Extract", 10000)).fields[
        "title"
    ].value == "Acme"
    assert gateway.tokens == 120


async def test_invalid_llm_schema(monkeypatch):
    async def post(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", "http://local"),
            json={"message": {"content": '{"fields":{"title":"invented scalar"}}'}},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with pytest.raises(LLMProviderError):
        await LLMGateway(AgentConfiguration(provider="ollama")).extract(
            "Acme", ["title"], "Extract", 10000
        )

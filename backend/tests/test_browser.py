"""Optional real Chromium coverage: RUN_BROWSER_TESTS=1 pytest -q."""

import os
from unittest.mock import AsyncMock
import pytest
from app.core.config import settings
from app.core.policies import NetworkPolicy
from app.agents.web_scraper.fetcher import Fetcher, Page
from app.agents.web_scraper.browser import render


@pytest.mark.skipif(
    os.getenv("RUN_BROWSER_TESTS") != "1",
    reason="Enable real Chromium tests explicitly",
)
async def test_js_rendering_and_resource_permissions(monkeypatch):
    monkeypatch.setattr(settings(), "browser_enabled", True)
    fetcher = Fetcher(NetworkPolicy(["example.com"]))
    html = """<html><body><h1 id="result">Loading</h1><script>
    document.getElementById('result').textContent = 'Rendered company';
    fetch('http://127.0.0.1/internal').catch(()=>{});
    fetch('https://evil.test/secret').catch(()=>{});
    </script></body></html>"""
    requests = []

    async def safe_request(url):
        requests.append(url)
        fetcher.policy.check(url)
        return Page(url, html, 200)

    monkeypatch.setattr(fetcher, "request", safe_request)
    page = await render("https://example.com/", fetcher)
    assert "Rendered company</h1>" in page.html
    assert "http://127.0.0.1/internal" in requests
    assert "https://evil.test/secret" in requests
    await fetcher.close()


@pytest.mark.skipif(
    os.getenv("RUN_BROWSER_TESTS") != "1",
    reason="Enable real Chromium tests explicitly",
)
async def test_browser_redirect_retains_authorization_reason(monkeypatch):
    from app.agents.web_scraper.schemas import ScrapeRequest
    from app.core.policies import RedirectAuthorizationRequired

    monkeypatch.setattr(settings(), "browser_enabled", True)
    policy = NetworkPolicy.for_execution(
        ScrapeRequest(
            url="https://render-fixture.test/",
            instruction="Extract",
            fields=["title"],
            authorization_confirmed=True,
        )
    )
    fetcher = Fetcher(policy)

    async def blocked(url):
        policy.redirect_url("https://www.render-fixture.test/")

    monkeypatch.setattr(fetcher, "request", blocked)
    try:
        with pytest.raises(RedirectAuthorizationRequired) as caught:
            await render("https://render-fixture.test/", fetcher)
        assert caught.value.hostname == "www.render-fixture.test"
    finally:
        await fetcher.close()

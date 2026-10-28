"""Deterministic full-stack browser smoke test. Run from backend after npm ci."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]


def ready(url: str) -> None:
    for _ in range(100):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Server did not start: {url}")


async def exercise(artifacts: Path) -> dict:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1080})
        page.set_default_timeout(10000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        # Tests need neither external websites nor a paid LLM.
        await page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
        await page.goto("http://127.0.0.1:15173", wait_until="networkidle")
        await page.get_by_role("heading", name="Intelligence, in motion.").wait_for()
        await page.get_by_role("link", name="Agent builder", exact=True).click()
        await page.get_by_label("LLM provider", exact=True).select_option("ollama")
        await page.get_by_text("Enter a model available", exact=False).wait_for()
        await page.get_by_label("Model", exact=True).fill("installed-model")
        # This UI check does not require or contact an Ollama service.
        await page.get_by_label("LLM provider", exact=True).select_option(
            "deterministic"
        )
        await page.get_by_label("Agent name", exact=True).fill("Company intelligence")
        await page.get_by_role("button", name="Create agent", exact=True).click()
        await page.get_by_role("heading", name="Company intelligence").wait_for()
        await page.locator('nav a[href="/scrape"]').click()
        await page.get_by_label("Website URL", exact=True).fill("https://example.com")
        assert await page.get_by_role(
            "button", name="Run agent", exact=True
        ).is_disabled()
        await page.get_by_role(
            "checkbox", name="I confirm crawl authorization", exact=True
        ).check()
        await page.get_by_label("Website URL", exact=True).fill("https://example.com/")
        assert not await page.get_by_role(
            "checkbox", name="I confirm crawl authorization", exact=True
        ).is_checked()
        await page.get_by_label("Maximum pages", exact=True).fill("1")
        await page.get_by_role(
            "checkbox", name="I confirm crawl authorization", exact=True
        ).check()
        await page.get_by_role("button", name="Run agent", exact=True).click()
        await page.get_by_role("link", name="View results", exact=True).wait_for()
        await page.screenshot(
            path=str(artifacts / "execution-desktop.png"), full_page=True
        )
        await page.get_by_role("link", name="View results", exact=True).click()
        await page.get_by_role("cell", name="Acme Labs", exact=True).wait_for()
        await page.get_by_role("button", name="View details →").click()
        await page.get_by_role("dialog", name="Record evidence").wait_for()
        await page.keyboard.press("Escape")
        await page.get_by_role("dialog", name="Record evidence").wait_for(
            state="hidden"
        )
        await page.get_by_role("button", name="View details →").click()
        await page.get_by_role("button", name="Close details").click()
        await page.get_by_role("textbox", name="Search results").fill(
            "unmatched-company"
        )
        await page.get_by_role("heading", name="No matching records").wait_for()
        await page.get_by_role("textbox", name="Search results").fill("")
        for format in ["CSV", "JSON"]:
            async with page.expect_download() as received:
                await page.get_by_role("button", name=format, exact=True).click()
            download = await received.value
            path = artifacts / f"smoke-results.{format.lower()}"
            await download.save_as(path)
            assert "Acme Labs" in path.read_text()
        await page.screenshot(
            path=str(artifacts / "results-desktop.png"), full_page=True
        )
        await page.locator('nav a[href="/scrape"]').click()
        await page.get_by_label("Website URL", exact=True).fill(
            "https://redirect-fixture.test/"
        )
        await page.get_by_label("Maximum pages", exact=True).fill("1")
        await page.get_by_role(
            "checkbox", name="I confirm crawl authorization", exact=True
        ).check()
        await page.get_by_role("button", name="Run agent", exact=True).click()
        await page.get_by_role(
            "link", name="Review redirect authorization", exact=True
        ).click()
        extra = page.get_by_role(
            "checkbox",
            name="Authorize www.redirect-fixture.test for this execution",
            exact=True,
        )
        await extra.wait_for()
        assert not await extra.is_checked()
        assert not await page.get_by_role(
            "checkbox", name="I confirm crawl authorization", exact=True
        ).is_checked()
        await extra.check()
        await page.get_by_role(
            "checkbox", name="I confirm crawl authorization", exact=True
        ).check()
        await page.get_by_role("button", name="Run agent", exact=True).click()
        await page.get_by_role("link", name="View results", exact=True).wait_for()
        await page.goto("http://127.0.0.1:15173", wait_until="networkidle")
        await page.screenshot(
            path=str(artifacts / "dashboard-desktop.png"), full_page=True
        )
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.screenshot(
            path=str(artifacts / "dashboard-mobile.png"), full_page=True
        )
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        await page.get_by_role("link", name="Workspace settings", exact=True).click()
        await page.get_by_role("heading", name="Execution policy").wait_for()
        await page.locator('nav a[href="/scrape"]').click()
        await page.get_by_label("Website URL", exact=True).fill("http://127.0.0.1")
        await page.get_by_role(
            "checkbox", name="I confirm crawl authorization", exact=True
        ).check()
        await page.get_by_role("button", name="Run agent", exact=True).click()
        await page.get_by_role("alert").wait_for()
        assert "Non-public" in await page.get_by_role("alert").inner_text()
        await page.screenshot(
            path=str(artifacts / "scraping-mobile.png"), full_page=True
        )
        assert not errors, errors
        await browser.close()
        return {
            "status": "passed",
            "checks": [
                "create agent",
                "consent required and reset on target change",
                "cross-host redirect review and scoped retry",
                "submit execution",
                "monitor persisted progress",
                "view results",
                "open evidence",
                "search records",
                "CSV download",
                "JSON download",
                "desktop layout",
                "mobile overflow",
                "mobile settings",
                "reject private target",
                "no JavaScript errors",
            ],
        }


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(
            DATABASE_URL=f"sqlite:///{directory}/qa.db",
            QUEUE_EAGER="true",
            ALLOWED_DOMAINS="example.com",
            API_TOKEN="",
        )
        sys.path.insert(0, str(ROOT / "backend"))
        import uvicorn
        from app.main import app
        from app.database.session import Base, engine
        from app.agents.web_scraper.fetcher import Fetcher, Page

        Base.metadata.create_all(engine)
        html = (ROOT / "backend/tests/fixtures/company.html").read_text()
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=18000, log_level="warning")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        frontend = None

        async def fixture_fetch(self, url, robots_check=True):
            self.policy.check(url)
            if url.startswith("https://redirect-fixture.test/"):
                url = self.policy.redirect_url("https://www.redirect-fixture.test/")
            return Page(url, html, 200)

        with patch.object(Fetcher, "request", fixture_fetch):
            try:
                thread.start()
                ready("http://127.0.0.1:18000/api/health")
                frontend = subprocess.Popen(
                    [
                        "npm",
                        "run",
                        "dev",
                        "--",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "15173",
                        "--strictPort",
                    ],
                    cwd=ROOT / "frontend",
                    env={**os.environ, "API_PROXY_TARGET": "http://127.0.0.1:18000"},
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                ready("http://127.0.0.1:15173")
                result = asyncio.run(exercise(artifacts))
                (artifacts / "browser-report.json").write_text(
                    json.dumps(result, indent=2)
                )
                print(json.dumps(result, indent=2))
            finally:
                if frontend:
                    import signal

                    os.killpg(frontend.pid, signal.SIGTERM)
                    frontend.wait(timeout=5)
                server.should_exit = True
                thread.join(timeout=5)
                engine.dispose()


if __name__ == "__main__":
    main()

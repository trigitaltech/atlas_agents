"""Render HTML while mediating all HTTP(S) requests through the safe fetcher."""

from app.core.config import settings
from app.core.policies import PolicyError, RedirectAuthorizationRequired, normalize
from app.agents.web_scraper.fetcher import Fetcher, Page


async def render(url: str, fetcher: Fetcher) -> Page:
    if not settings().browser_enabled:
        raise PolicyError("JavaScript rendering is disabled by server policy")
    from playwright.async_api import async_playwright

    requests = 0
    navigation_targets = {normalize(url)}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, args=["--disable-quic", "--disable-background-networking"]
        )
        try:
            context = await browser.new_context(
                service_workers="block", accept_downloads=False
            )
            await context.add_init_script("""
                HTMLFormElement.prototype.submit = function() {};
                HTMLFormElement.prototype.requestSubmit = function() {};
                document.addEventListener('submit', e => e.preventDefault(), true);
                window.open = function() { return null; };
            """)

            blocked_navigation = None

            async def intercept(route):
                nonlocal requests, blocked_navigation
                requests += 1
                request = route.request
                navigating = request.is_navigation_request()
                if navigating and normalize(request.url) not in navigation_targets:
                    try:
                        fetcher.policy.redirect_url(request.url)
                        blocked_navigation = PolicyError(
                            "Website attempted an unrequested browser navigation; automatic navigation is blocked"
                        )
                    except PolicyError as exc:
                        blocked_navigation = exc
                    await route.abort()
                    return
                if (
                    request.method != "GET"
                    or requests > 30
                    or request.resource_type in {"image", "media", "font"}
                    or (navigating and normalize(request.url) not in navigation_targets)
                ):
                    await route.abort()
                    return
                try:
                    fetched = await fetcher.request(request.url)
                    if navigating and normalize(fetched.url) != normalize(request.url):
                        navigation_targets.add(normalize(fetched.url))
                        await route.fulfill(
                            status=302, headers={"location": fetched.url}
                        )
                        return
                    if navigating:
                        navigation_targets.discard(normalize(request.url))
                    await route.fulfill(
                        status=fetched.status_code,
                        content_type=fetched.content_type,
                        body=fetched.html,
                    )
                except Exception as exc:
                    if isinstance(exc, PolicyError) and (
                        navigating or isinstance(exc, RedirectAuthorizationRequired)
                    ):
                        blocked_navigation = exc
                    # Resource failures never open a fallback path around the network policy.
                    await route.abort()

            await context.route("**/*", intercept)
            await context.route_web_socket("**/*", lambda ws: ws.close())
            page = await context.new_page()
            try:
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=20000
                )
            except Exception:
                if blocked_navigation is not None:
                    raise blocked_navigation from None
                raise PolicyError(
                    "JavaScript rendering failed or the website is unreachable"
                ) from None
            await page.wait_for_timeout(1000)
            if blocked_navigation is not None:
                raise blocked_navigation
            fetcher.policy.check(page.url)
            html = await page.content()
            if len(html.encode()) > settings().max_response_bytes:
                raise PolicyError("Rendered document exceeds size limit")
            return Page(page.url, html, response.status if response else 200)
        finally:
            await browser.close()

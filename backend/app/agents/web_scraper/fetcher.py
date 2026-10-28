import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit, urljoin
from urllib.robotparser import RobotFileParser
import httpx
from app.core.config import settings
from app.core.policies import NetworkPolicy, PolicyError

USER_AGENT = "AgentPlatformBot/1.0"


@dataclass
class Page:
    url: str
    html: str
    status_code: int
    content_type: str = "text/html"


class Fetcher:
    def __init__(self, policy: NetworkPolicy):
        self.policy = policy
        self.robots: dict[str, RobotFileParser] = {}
        self.last: dict[str, float] = {}
        self.delays: dict[str, float] = {}
        self.client = httpx.AsyncClient(
            timeout=15, follow_redirects=False, trust_env=False
        )

    async def close(self):
        await self.client.aclose()

    async def throttle(self, host: str):
        # Redis coordinates limits across worker processes. Fail closed when configured Redis fails.
        interval = max(settings().rate_interval, self.delays.get(host, 0))
        from redis.asyncio import Redis

        if not settings().queue_eager:
            redis = Redis.from_url(settings().redis_url)
            try:
                while not await redis.set(
                    f"crawl:rate:{host}",
                    "1",
                    nx=True,
                    px=int(interval * 1000),
                ):
                    await asyncio.sleep(interval)
            finally:
                await redis.aclose()
        else:
            await asyncio.sleep(
                max(
                    0,
                    interval - (time.monotonic() - self.last.get(host, 0)),
                )
            )
            self.last[host] = time.monotonic()

    async def request(self, url: str, robots_check: bool = True) -> Page:
        try:
            return await self._request(url, robots_check)
        except httpx.RequestError:
            raise PolicyError(
                "Website is unreachable or TLS verification failed"
            ) from None

    async def _request(self, url: str, robots_check: bool = True) -> Page:
        for _ in range(6):
            host = self.policy.check(url)
            if robots_check:
                await self.check_robots(url)
            await self.throttle(host)
            # Resolve after every wait, immediately before connecting to the pinned IP.
            host, ip = await self.policy.resolve(url)
            p = urlsplit(url)
            # Connect to the validated IP; preserve HTTP Host and TLS SNI/certificate verification.
            netloc = f"[{ip}]" if ":" in ip else ip
            pinned = urlunsplit((p.scheme, netloc, p.path or "/", p.query, ""))
            async with self.client.stream(
                "GET",
                pinned,
                headers={
                    "Host": f"[{host}]" if ":" in host else host,
                    "User-Agent": USER_AGENT,
                },
                extensions={"sni_hostname": host},
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise PolicyError("Redirect has no location")
                    url = self.policy.redirect_url(urljoin(url, location))
                    continue
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > settings().max_response_bytes:
                        raise PolicyError("Response exceeds size limit")
                return Page(
                    url,
                    data.decode(response.encoding or "utf-8", errors="replace"),
                    response.status_code,
                    response.headers.get("content-type", ""),
                )
        raise PolicyError("Too many redirects")

    async def check_robots(self, url: str):
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self.robots:
            page = await self.request(origin + "/robots.txt", robots_check=False)
            if page.status_code == 404:
                lines = []
            elif page.status_code == 200:
                lines = page.html.splitlines()
            else:
                raise PolicyError("robots.txt could not authorize access")
            parser = RobotFileParser()
            parser.parse(lines)
            self.robots[origin] = parser
        parser = self.robots[origin]
        if not parser.can_fetch(USER_AGENT, url):
            raise PolicyError("robots.txt disallows this URL")
        delay = parser.crawl_delay(USER_AGENT) or 0
        rate = parser.request_rate(USER_AGENT)
        if rate and rate.requests:
            delay = max(delay, rate.seconds / rate.requests)
        self.delays[p.hostname] = max(self.delays.get(p.hostname, 0), delay)

"""Per-job consent/scopes and SSRF regressions: no live DNS, websites or models."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.agents.web_scraper.schemas import ScrapeRequest
from app.agents.web_scraper.fetcher import Fetcher, Page
from app.agents.web_scraper.crawler import discover
from app.agents.web_scraper.access import check_access
from app.core.config import settings
from app.core.policies import (
    NetworkPolicy,
    PolicyError,
    AuthorizationError,
    RedirectAuthorizationRequired,
    normalize,
    public_address,
)


def request(url="https://fresh-public.test/", **kwargs):
    return ScrapeRequest(
        url=url,
        instruction="Extract title",
        fields=["title"],
        authorization_confirmed=True,
        **kwargs,
    )


def body(**kwargs):
    return {
        "url": "https://fresh-public.test/",
        "instruction": "Extract title",
        "fields": ["title"],
        "authorization_confirmed": True,
        "max_pages": 1,
        **kwargs,
    }


def resolve_to(monkeypatch, *addresses):
    resolver = AsyncMock(return_value=[(2, 1, 6, "", (ip, 443)) for ip in addresses])
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
    return resolver


@pytest.mark.parametrize("value", [None, False])
def test_confirmation_required_even_for_static_targets(client, monkeypatch, value):
    enqueue = monkeypatch.setattr(
        "app.services.jobs.execute_job.apply_async",
        lambda **kwargs: pytest.fail("Unconfirmed job must not enqueue"),
    )
    payload = body(url="https://example.com/")
    if value is None:
        payload.pop("authorization_confirmed")
    else:
        payload["authorization_confirmed"] = value
    assert client.post("/api/scraping/jobs", json=payload).status_code == 403
    assert client.get("/api/scraping/jobs").json() == []


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None])
def test_confirmation_is_a_strict_boolean(client, value):
    assert (
        client.post(
            "/api/scraping/jobs", json=body(authorization_confirmed=value)
        ).status_code
        == 422
    )


def test_new_public_target_is_scoped_per_job_without_global_mutation(
    client, monkeypatch
):
    monkeypatch.setattr(
        "app.services.jobs.execute_job.apply_async", lambda **kwargs: None
    )
    static = settings().domains.copy()
    for host in ["fresh-public.test", "second-public.test", "example.com"]:
        response = client.post("/api/scraping/jobs", json=body(url="https://" + host))
        assert response.status_code == 202
        assert response.json()["context"]["authorized_hostnames"] == [host]
        assert response.json()["input_data"]["authorization_confirmed"] is True
    assert settings().domains == static
    first = NetworkPolicy.for_execution(request())
    with pytest.raises(PolicyError):
        first.check("https://second-public.test/")
    # A static entry is not implicitly in a different execution's scope.
    with pytest.raises(PolicyError):
        first.check("https://example.com/")


def test_extra_hostnames_need_explicit_approval_and_are_exact():
    policy = NetworkPolicy.for_execution(
        request(additional_authorized_domains=["www.fresh-public.test"])
    )
    assert policy.check("https://www.fresh-public.test/") == "www.fresh-public.test"
    with pytest.raises(PolicyError):
        policy.check("https://other.fresh-public.test/")
    with pytest.raises(AuthorizationError):
        NetworkPolicy.for_execution(
            ScrapeRequest(
                url="https://fresh-public.test",
                instruction="Extract",
                fields=["title"],
                additional_authorized_domains=["www.fresh-public.test"],
            )
        )


def test_legacy_static_policy_and_filter_remain_supported():
    assert NetworkPolicy(["example.com"]).check("https://example.com/") == "example.com"
    with pytest.raises(PolicyError):
        NetworkPolicy(["fresh-public.test"])
    assert NetworkPolicy.for_execution(
        request("https://example.com", allowed_domains=["example.com"])
    ).domains == {"example.com"}
    assert NetworkPolicy.for_execution(
        request(allowed_domains=["fresh-public.test"])
    ).domains == {"fresh-public.test"}
    with pytest.raises(AuthorizationError):
        NetworkPolicy.for_execution(request(allowed_domains=["example.com"]))
    with pytest.raises(AuthorizationError):
        NetworkPolicy.for_execution(
            request(allowed_domains=["fresh-public.test", "unapproved.test"])
        )


@pytest.mark.parametrize(
    "url,expected",
    [
        ("HTTPS://Fresh-Public.TEST:443/a#fragment", "https://fresh-public.test/a"),
        ("http://fresh-public.test:80", "http://fresh-public.test/"),
        ("https://fresh-public.test./", "https://fresh-public.test/"),
        ("https://bücher.test/a", "https://xn--bcher-kva.test/a"),
        ("https://93.184.216.34/", "https://93.184.216.34/"),
        ("https://[2606:4700:4700::1111]/", "https://[2606:4700:4700::1111]/"),
    ],
)
def test_url_canonicalization(url, expected):
    assert request(url).url == expected


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://fresh-public.test",
        "https://user:password@fresh-public.test/",
        "https://fresh-public.test:80",
        "http://fresh-public.test:443",
        "http://fresh-public.test:8080",
        " https://fresh-public.test",
        "https://fresh-public.test/\npath",
        "https://fresh-public.test/has space",
        "https://fresh-public.test\\@127.0.0.1/",
        "https://fresh-public.test%2f.evil.test/",
        "http://localhost",
        "http://localhost.",
        "http://foo.localhost",
        "http://host.docker.internal",
        "http://metadata.google.internal",
        "http://169.254.169.254",
        "http://100.100.100.200",
        "http://168.63.129.16",
        "http://127.0.0.1",
        "http://0.0.0.0",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "http://172.16.0.1",
        "http://224.0.0.1",
        "http://240.0.0.1",
        "http://2130706433",
        "http://0x7f000001",
        "http://0177.0.0.1",
        "http://127.1",
        "http://[::1]",
        "http://[::]",
        "http://[fe80::1%25en0]",
        "http://[::ffff:127.0.0.1]",
        "http://[64:ff9b::7f00:1]",
        "https://*.fresh-public.test",
        "https://fresh-public.test..",
    ],
)
def test_unsafe_url_edge_cases(url):
    with pytest.raises(ValueError):
        request(url)


@pytest.mark.parametrize(
    "host",
    [
        "*",
        "*.fresh-public.test",
        "https://extra.test",
        "extra.test/path",
        "localhost",
        "127.0.0.1",
        "metadata.google.internal",
    ],
)
def test_extra_hostnames_cannot_bypass_url_validation(client, host):
    assert (
        client.post(
            "/api/scraping/jobs", json=body(additional_authorized_domains=[host])
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.31.0.1",
        "192.168.5.5",
        "169.254.169.254",
        "168.63.129.16",
        "100.100.100.200",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "240.0.0.1",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "2002:7f00:1::",
        "64:ff9b::7f00:1",
    ],
)
async def test_public_looking_host_cannot_resolve_to_internal_addresses(
    monkeypatch, ip
):
    resolve_to(monkeypatch, ip)
    with pytest.raises(PolicyError, match="non-public|metadata"):
        await NetworkPolicy.for_execution(request()).resolve(
            "https://fresh-public.test/"
        )


async def test_public_resolution_and_mixed_answers(monkeypatch):
    policy = NetworkPolicy.for_execution(request())
    resolve_to(monkeypatch, "93.184.216.34")
    assert await policy.resolve("https://fresh-public.test/") == (
        "fresh-public.test",
        "93.184.216.34",
    )
    resolve_to(monkeypatch, "93.184.216.34", "127.0.0.1")
    with pytest.raises(PolicyError):
        await policy.resolve("https://fresh-public.test/")


async def mocked_fetcher(handler):
    fetcher = Fetcher(NetworkPolicy.for_execution(request()))
    await fetcher.client.aclose()
    fetcher.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher.throttle = AsyncMock()
    return fetcher


async def test_cross_host_redirect_stops_before_destination_request(monkeypatch):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(
            302, headers={"location": "https://www.fresh-public.test/target"}
        )

    resolve_to(monkeypatch, "93.184.216.34")
    fetcher = await mocked_fetcher(handler)
    try:
        with pytest.raises(RedirectAuthorizationRequired) as caught:
            await fetcher.request("https://fresh-public.test/", False)
        assert caught.value.hostname == "www.fresh-public.test"
        assert len(calls) == 1
    finally:
        await fetcher.close()


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/",
        "http://metadata.google.internal/",
        "file:///etc/passwd",
    ],
)
async def test_internal_redirect_never_becomes_an_authorization_prompt(
    monkeypatch, target
):
    resolve_to(monkeypatch, "93.184.216.34")
    fetcher = await mocked_fetcher(
        lambda req: httpx.Response(302, headers={"location": target})
    )
    try:
        with pytest.raises(PolicyError) as caught:
            await fetcher.request("https://fresh-public.test/", False)
        assert not isinstance(caught.value, RedirectAuthorizationRequired)
    finally:
        await fetcher.close()


async def test_dns_rechecked_after_throttle_to_prevent_rebinding(monkeypatch):
    resolver = resolve_to(monkeypatch, "93.184.216.34")
    requests = []
    fetcher = await mocked_fetcher(
        lambda req: requests.append(req) or httpx.Response(200, text="safe")
    )

    async def wait(_host):
        resolver.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]

    fetcher.throttle = wait
    try:
        with pytest.raises(PolicyError):
            await fetcher.request("https://fresh-public.test/", False)
        assert not requests
    finally:
        await fetcher.close()


async def test_each_redirect_revalidates_dns(monkeypatch):
    resolver = resolve_to(monkeypatch, "93.184.216.34")
    resolver.side_effect = [
        [(2, 1, 6, "", ("93.184.216.34", 443))],
        [(2, 1, 6, "", ("127.0.0.1", 443))],
    ]
    calls = []
    fetcher = await mocked_fetcher(
        lambda req: (
            calls.append(req) or httpx.Response(302, headers={"location": "/next"})
        )
    )
    try:
        with pytest.raises(PolicyError):
            await fetcher.request("https://fresh-public.test/", False)
        assert len(calls) == 1 and resolver.await_count == 2
    finally:
        await fetcher.close()


async def test_approved_redirect_and_robots_are_checked(monkeypatch):
    seen = []

    def handler(req):
        host = req.headers["host"]
        seen.append((host, req.url.path))
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if host == "fresh-public.test":
            return httpx.Response(
                302, headers={"location": "https://www.fresh-public.test/"}
            )
        return httpx.Response(
            200, text="<html>Permitted</html>", headers={"content-type": "text/html"}
        )

    resolve_to(monkeypatch, "93.184.216.34")
    fetcher = await mocked_fetcher(handler)
    fetcher.policy = NetworkPolicy.for_execution(
        request(additional_authorized_domains=["www.fresh-public.test"])
    )
    try:
        page = await fetcher.request("https://fresh-public.test/")
        assert page.url == "https://www.fresh-public.test/"
        assert seen == [
            ("fresh-public.test", "/robots.txt"),
            ("fresh-public.test", "/"),
            ("www.fresh-public.test", "/robots.txt"),
            ("www.fresh-public.test", "/"),
        ]
    finally:
        await fetcher.close()


async def test_robots_disallow_prevents_page_fetch(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /")

    resolve_to(monkeypatch, "93.184.216.34")
    fetcher = await mocked_fetcher(handler)
    try:
        with pytest.raises(PolicyError, match="robots.txt disallows"):
            await fetcher.request("https://fresh-public.test/")
        assert calls == ["/robots.txt"]
    finally:
        await fetcher.close()


def test_external_and_malformed_links_are_ignored():
    html = '<a href="/inside">ok</a><a href="https://example.com/">static but external</a><a href="https://www.fresh-public.test/">subdomain</a><a href="http://[bad">malformed</a><a href="http://127.0.0.1/">internal</a>'
    assert discover(
        html, "https://fresh-public.test/", NetworkPolicy.for_execution(request())
    ) == ["https://fresh-public.test/inside"]


def test_redirect_job_records_hostname_for_explicit_retry(client, monkeypatch):
    calls = []

    async def redirected(self, url, robots_check=True):
        calls.append(url)
        if self.policy.check(url) == "fresh-public.test":
            destination = self.policy.redirect_url("https://www.fresh-public.test/")
            return await redirected(self, destination)
        return Page(url, "<html><title>Fixture</title><body>Fixture</body></html>", 200)

    monkeypatch.setattr(Fetcher, "request", redirected)
    first = client.post("/api/scraping/jobs", json=body()).json()
    assert first["status"] == "failed"
    assert (
        first["context"]["authorization_required_hostname"] == "www.fresh-public.test"
    )
    assert first["context"]["error_code"] == "redirect_authorization_required"
    assert calls == ["https://fresh-public.test/"]
    second = client.post(
        "/api/scraping/jobs",
        json=body(
            additional_authorized_domains=["www.fresh-public.test"],
            authorization_source_job_id=first["id"],
        ),
    ).json()
    assert second["id"] != first["id"] and second["status"] == "completed"
    assert first["context"]["authorized_hostnames"] == ["fresh-public.test"]
    assert second["context"]["authorized_hostnames"] == [
        "fresh-public.test",
        "www.fresh-public.test",
    ]


@pytest.mark.parametrize(
    "html,status,reason",
    [
        ("<h1>Denied</h1>", 403, "restricted"),
        ("<h1>Verify you are human</h1>", 200, "CAPTCHA"),
        ('<h1>Login required</h1><input type="password">', 200, "login"),
        ("<p>Not found</p>", 404, "HTTP 404"),
    ],
)
def test_access_barriers_stop_with_clear_reason(html, status, reason):
    with pytest.raises(PolicyError, match=reason):
        check_access(html, status)


def test_captcha_article_does_not_mean_bypass_required():
    check_access("<article>We explain how CAPTCHA works.</article>", 200)


def test_arbitrary_extra_hosts_need_observed_redirect_reference(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.jobs.execute_job.apply_async",
        lambda **kwargs: pytest.fail("Unobserved scope expansion must not enqueue"),
    )
    for host in ["www.fresh-public.test", "example.com"]:
        result = client.post(
            "/api/scraping/jobs", json=body(additional_authorized_domains=[host])
        )
        assert result.status_code == 403
    assert client.get("/api/scraping/jobs").json() == []


def test_redirect_approval_bound_to_original_url_and_observed_host(client, monkeypatch):
    async def redirect(self, url, robots_check=True):
        self.policy.redirect_url("https://www.fresh-public.test/")

    monkeypatch.setattr(Fetcher, "request", redirect)
    source = client.post("/api/scraping/jobs", json=body()).json()
    assert source["status"] == "failed"
    wrong_target = client.post(
        "/api/scraping/jobs",
        json=body(
            url="https://different-public.test/",
            additional_authorized_domains=["www.fresh-public.test"],
            authorization_source_job_id=source["id"],
        ),
    )
    assert wrong_target.status_code == 403
    unrelated = client.post(
        "/api/scraping/jobs",
        json=body(
            additional_authorized_domains=["unrelated-public.test"],
            authorization_source_job_id=source["id"],
        ),
    )
    assert unrelated.status_code == 403


@pytest.mark.parametrize("target", ["https://fresh-public.test/", "file:///private"])
def test_legacy_unconfirmed_jobs_fail_closed_with_clear_history(
    client, monkeypatch, target
):
    from app.database.session import SessionLocal
    from app.models.entities import Agent, Job
    from app.agents.web_scraper.schemas import AgentConfiguration
    from app.workers.tasks import execute_job

    monkeypatch.setattr(
        Fetcher, "request", AsyncMock(side_effect=AssertionError("No fetch permitted"))
    )
    with SessionLocal() as db:
        agent = Agent(name="Legacy", configuration=AgentConfiguration().model_dump())
        db.add(agent)
        db.flush()
        job = Job(
            agent_id=agent.id,
            input_data={"url": target, "instruction": "Extract", "fields": ["title"]},
        )
        db.add(job)
        db.commit()
        id = job.id
    execute_job(id)
    saved = client.get(f"/api/scraping/jobs/{id}").json()
    assert saved["status"] == "failed"
    assert "Confirm" in saved["error_message"] or "confirmed" in saved["error_message"]

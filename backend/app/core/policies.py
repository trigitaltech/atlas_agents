"""Exact execution scopes and public-only, freshly resolved HTTP destinations."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

import idna

from app.core.config import settings

if TYPE_CHECKING:
    from app.agents.web_scraper.schemas import ScrapeRequest


class PolicyError(ValueError):
    pass


class AuthorizationError(PolicyError):
    pass


class RedirectAuthorizationRequired(PolicyError):
    def __init__(self, hostname: str):
        self.hostname = hostname
        super().__init__(
            f"Redirect requires separate authorization for hostname {hostname}. Review and confirm it before starting a new execution."
        )


def public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    blocked = (
        address.is_private,
        address.is_loopback,
        address.is_link_local,
        address.is_multicast,
        address.is_reserved,
        address.is_unspecified,
    )
    transition = isinstance(address, ipaddress.IPv6Address) and (
        address.sixtofour is not None
        or address.teredo is not None
        or address.ipv4_mapped is not None
        or address in ipaddress.ip_network("64:ff9b::/96")
        or address in ipaddress.ip_network("64:ff9b:1::/48")
    )
    # Azure platform/metadata virtual IP is globally classified but not a public website.
    return (
        address.is_global
        and not any(blocked)
        and not transition
        and str(address) != "168.63.129.16"
    )


def canonical_hostname(value: str) -> str:
    if (
        not value
        or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in value)
        or any(c in value for c in "/\\@%?#*")
    ):
        raise PolicyError(
            "Invalid hostname; use an exact hostname without URL components or wildcards"
        )
    value = value.lower()
    if value.endswith(".."):
        raise PolicyError("Invalid hostname")
    value = value.removesuffix(".")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        address = None
    if address is not None:
        if not public_address(str(address)):
            raise PolicyError("Non-public or metadata destination blocked")
        return str(address)
    try:
        host = idna.encode(value, uts46=True, std3_rules=True).decode("ascii").lower()
    except (idna.IDNAError, UnicodeError):
        raise PolicyError("Invalid hostname") from None
    if (
        "." not in host
        or host.endswith((".localhost", ".local", ".internal", ".lan", ".home"))
        or host in {"localhost", "metadata", "instance-data"}
    ):
        raise PolicyError("Local or internal destination blocked")
    labels = host.split(".")
    if len(host) > 253 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    ):
        raise PolicyError("Invalid hostname")
    if labels[-1].isdigit() or re.fullmatch(r"0x[0-9a-f]+", host):
        raise PolicyError("Ambiguous numeric network destination blocked")
    return host


def normalize(url: str) -> str:
    if (
        not isinstance(url, str)
        or len(url) > 2048
        or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in url)
        or "\\" in url
    ):
        raise PolicyError(
            "Invalid URL; whitespace, control characters and backslashes are not allowed"
        )
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise PolicyError("Use an HTTP(S) URL without embedded credentials")
        if parsed.port not in {None, 443 if parsed.scheme == "https" else 80}:
            raise PolicyError("Only the standard port for the URL scheme is allowed")
        host = canonical_hostname(parsed.hostname)
    except ValueError as exc:
        if isinstance(exc, PolicyError):
            raise
        raise PolicyError("Invalid URL or port") from None
    netloc = f"[{host}]" if ":" in host else host
    return urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))


class NetworkPolicy:
    def __init__(self, domains: list[str], *, job_scope: set[str] | None = None):
        self.job_scoped = job_scope is not None
        if job_scope is not None:
            self.domains = {canonical_hostname(host) for host in job_scope}
        else:
            static = {canonical_hostname(host) for host in settings().domains}
            self.domains = (
                {canonical_hostname(host) for host in domains} if domains else static
            )
            if not self.domains <= static:
                raise PolicyError("Requested domains must be in the server allowlist")
        if not self.domains:
            raise PolicyError("No hostname is authorized")

    @classmethod
    def for_execution(cls, request: ScrapeRequest) -> NetworkPolicy:
        if request.authorization_confirmed is not True:
            raise AuthorizationError(
                "Confirm that you are authorized to crawl the target and any additional hostnames for this execution"
            )
        target = urlsplit(normalize(request.url)).hostname
        scope = {target, *request.additional_authorized_domains}
        if request.allowed_domains:
            # Backward-compatible static filter never adds hosts to this job's consent scope.
            requested = {canonical_hostname(host) for host in request.allowed_domains}
            static = {canonical_hostname(host) for host in settings().domains}
            if not requested <= static | scope:
                raise AuthorizationError(
                    "Each additional hostname needs explicit per-execution authorization"
                )
            scope &= requested
            if target not in scope:
                raise AuthorizationError(
                    "Target is outside the requested allowed_domains filter"
                )
        return cls([], job_scope=scope)

    def check(self, url: str) -> str:
        host = urlsplit(normalize(url)).hostname
        if host not in self.domains:
            raise PolicyError("Domain is not explicitly authorized for this execution")
        return host

    def redirect_url(self, url: str) -> str:
        normalized = normalize(url)
        host = urlsplit(normalized).hostname
        if host not in self.domains and self.job_scoped:
            raise RedirectAuthorizationRequired(host)
        self.check(normalized)
        return normalized

    async def resolve(self, url: str) -> tuple[str, str]:
        normalized = normalize(url)
        host = self.check(normalized)
        port = 443 if urlsplit(normalized).scheme == "https" else 80
        try:
            answers = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        except OSError:
            raise PolicyError(
                "Target DNS lookup failed; the website is unreachable"
            ) from None
        addresses = {a[4][0] for a in answers}
        if not addresses or any(not public_address(ip) for ip in addresses):
            raise PolicyError("DNS resolved to a non-public or metadata destination")
        return host, sorted(addresses)[0]

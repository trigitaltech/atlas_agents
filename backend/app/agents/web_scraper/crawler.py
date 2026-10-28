from urllib.parse import urljoin
from bs4 import BeautifulSoup
from app.core.policies import NetworkPolicy, PolicyError, normalize


def discover(html: str, url: str, policy: NetworkPolicy) -> list[str]:
    links = []
    for tag in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        try:
            candidate = normalize(urljoin(url, tag["href"]))
            policy.check(candidate)
        except (PolicyError, ValueError):
            continue
        if candidate not in links:
            links.append(candidate)
        if len(links) >= 200:
            break
    return links

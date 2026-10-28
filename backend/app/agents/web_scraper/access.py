"""Conservative access-barrier detection; never attempts to bypass a restriction."""

import re
from bs4 import BeautifulSoup
from app.core.policies import PolicyError


def check_access(html: str, status: int) -> None:
    if status in {401, 403, 407, 429, 451}:
        raise PolicyError(
            f"Website access restricted (HTTP {status}); authentication, blocking or rate limits are not bypassed"
        )
    if status != 200:
        raise PolicyError(f"Website returned HTTP {status}; no content was extracted")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True).lower()
    headings = " ".join(
        t.get_text(" ", strip=True) for t in soup.find_all(["title", "h1"])
    ).lower()
    challenge = re.search(
        r"verify (?:that )?you are (?:a )?human|complete (?:the|this) (?:captcha|security check)|checking your browser|captcha required|access denied",
        headings + " " + text[:2000],
    )
    widget = soup.select_one(
        'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], .cf-turnstile, #challenge-form'
    )
    if challenge or (widget and len(text) < 400):
        raise PolicyError(
            "Website requires a CAPTCHA or browser security challenge; access restrictions are not bypassed"
        )
    password = soup.select_one('input[type="password"]')
    login = re.search(
        r"(?:sign|log) in to (?:continue|access)|authentication required|login required",
        text[:2000],
    )
    if login or (
        password and (len(text) < 500 or re.search(r"log ?in|sign ?in", headings))
    ):
        raise PolicyError(
            "Website requires login; authenticated content is not crawled"
        )

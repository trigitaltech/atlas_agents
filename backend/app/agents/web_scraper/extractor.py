import re
import json
from bs4 import BeautifulSoup
from app.agents.web_scraper.schemas import Extraction, ExtractedValue
from app.agents.web_scraper.validator import supported_value


def parse_cloud_extraction(content: str, fields: list[str], text: str) -> Extraction:
    """Parse one JSON object; null unsupported fields and require exact source evidence."""
    content = content.strip()
    # A single whole JSON fence is harmless; never search prose for a JSON substring.
    lines = content.splitlines()
    if len(lines) >= 3 and lines[0] in {"```json", "```"} and lines[-1] == "```":
        content = "\n".join(lines[1:-1])

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("Non-JSON number")

    parsed = json.loads(
        content, object_pairs_hook=unique_object, parse_constant=reject_constant
    )
    if (
        not isinstance(parsed, dict)
        or set(parsed) != {"fields"}
        or not isinstance(parsed["fields"], dict)
    ):
        raise ValueError("Invalid extraction envelope")
    output = {}
    for field in fields:
        raw = parsed["fields"].get(field)
        item = ExtractedValue()
        if (
            isinstance(raw, dict)
            and not set(raw) - {"value", "evidence"}
            and all(value is None or isinstance(value, str) for value in raw.values())
        ):
            item = ExtractedValue.model_validate(raw)
        output[field] = supported_value(item, text)
    return Extraction(fields=output)


def parse(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "iframe", "form", "svg"]):
        tag.decompose()
    return title, soup.get_text(" ", strip=True)[:12000]


def deterministic(text: str, title: str, fields: list[str]) -> Extraction:
    values = {}
    for field in fields:
        value = None
        if field in {"title", "company_name"} and title and title in text:
            value = title
        elif field in {"email", "business_email"}:
            match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
            value = match.group(0) if match else None
        values[field] = ExtractedValue(value=value, evidence=value)
    return Extraction(fields=values)

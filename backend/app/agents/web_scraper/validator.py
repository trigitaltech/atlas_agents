import json
from app.agents.web_scraper.schemas import Extraction, ExtractedValue


def supported_value(item: ExtractedValue | None, text: str) -> ExtractedValue:
    """Use the same evidence rule for prompt-only cloud and schema-based local output."""
    if (
        item
        and item.value
        and item.evidence
        and item.value in item.evidence
        and item.evidence in text
    ):
        return item
    return ExtractedValue()


def validate(extraction: Extraction, fields: list[str], text: str, url: str) -> dict:
    data, evidence = {}, {}
    for field in fields:
        item = supported_value(extraction.fields.get(field), text)
        if field == "source_url":
            data[field] = url
            evidence[field] = url
        elif item.value is not None:
            data[field] = item.value
            evidence[field] = item.evidence
        else:
            data[field] = None
    return {
        "source_url": url,
        "extracted_data": data,
        "evidence": evidence,
        "validation_status": "validated",
    }


def fingerprint(record: dict) -> str:
    return json.dumps(
        {k: v for k, v in record["extracted_data"].items() if k != "source_url"},
        sort_keys=True,
    )

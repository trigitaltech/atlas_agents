"""Verify the actual API → Redis/Celery → PostgreSQL flow against example.com."""

import json
import os
import time
import urllib.request

BASE = os.environ.get("ATLAS_BASE_URL", "http://127.0.0.1:8080")
TOKEN = os.environ.get("API_TOKEN", "")


def request(path, body=None):
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


if os.environ.get("ATLAS_CRAWL_AUTHORIZED") != "true":
    raise SystemExit(
        "Explicit authorization required: set ATLAS_CRAWL_AUTHORIZED=true only if permitted to crawl this script's target"
    )

health = request("/api/health")
assert health["status"] == "ok", health
job = request(
    "/api/scraping/jobs",
    {
        "agent_name": "Public-site smoke test",
        "authorization_confirmed": True,
        "url": "https://example.com/",
        "instruction": "Extract the page title with its source URL",
        "fields": ["title", "source_url"],
        "max_pages": 1,
        "max_depth": 0,
        "timeout": 30,
        "token_budget": 1000,
    },
)
for _ in range(80):
    job = request(f"/api/scraping/jobs/{job['id']}")
    if job["status"] not in {"queued", "running"}:
        break
    time.sleep(0.5)
assert job["status"] == "completed", {
    "status": job["status"],
    "error": job.get("error_message"),
}
records = request(f"/api/scraping/jobs/{job['id']}/results")
assert records and records[0]["extracted_data"]["title"] == "Example Domain", records
assert records[0]["evidence"]["title"] == "Example Domain", records
print(
    json.dumps(
        {
            "status": "passed",
            "job_id": job["id"],
            "health": health,
            "records": len(records),
            "title": records[0]["extracted_data"]["title"],
        },
        indent=2,
    )
)

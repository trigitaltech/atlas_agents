from unittest.mock import AsyncMock
from app.agents.web_scraper.fetcher import Fetcher, Page
from app.database.session import SessionLocal
from app.models.entities import Job, Record
from app.core.config import settings


def test_system(client):
    assert client.get("/api/health").status_code == 200
    assert len(client.get("/api/tools").json()) == 9
    assert "openai_api_key" not in client.get("/api/settings").text
    assert client.get("/api/models").status_code == 200


def test_agent_crud(client):
    created = client.post("/api/agents", json={"name": "Company agent"})
    assert created.status_code == 201
    id = created.json()["id"]
    assert client.get(f"/api/agents/{id}").json()["name"] == "Company agent"
    assert (
        client.put(
            f"/api/agents/{id}", json={"name": "Updated", "enabled": False}
        ).json()["enabled"]
        is False
    )
    assert len(client.get("/api/agents").json()) == 1
    assert client.delete(f"/api/agents/{id}").status_code == 204
    assert client.get(f"/api/agents/{id}").status_code == 404


def test_full_job_persistence_export(client, html, monkeypatch):
    monkeypatch.setattr(
        Fetcher,
        "request",
        AsyncMock(return_value=Page("https://example.com/", html, 200)),
    )
    response = client.post(
        "/api/scraping/jobs",
        json={
            "authorization_confirmed": True,
            "url": "https://example.com",
            "instruction": "Extract company",
            "fields": ["company_name", "business_email", "location"],
            "max_pages": 1,
        },
    )
    assert response.status_code == 202, response.text
    id = response.json()["id"]
    job = client.get(f"/api/scraping/jobs/{id}").json()
    assert job["status"] == "completed", job
    records = client.get(f"/api/scraping/jobs/{id}/results").json()
    assert records[0]["extracted_data"]["company_name"] == "Acme Labs"
    assert records[0]["extracted_data"]["location"] is None
    assert job["executions"]
    assert "Acme Labs" in client.get(f"/api/scraping/jobs/{id}/export?format=csv").text
    assert (
        client.get(f"/api/scraping/jobs/{id}/export?format=json").json()[0][
            "business_email"
        ]
        == "hello@acme.test"
    )
    assert client.delete(f"/api/agents/{job['agent_id']}").status_code == 409
    assert client.get("/api/stats").json()["completed"] == 1
    # Repeated delivery cannot duplicate results.
    from app.workers.tasks import execute_job

    execute_job(id)
    assert len(client.get(f"/api/scraping/jobs/{id}/results").json()) == 1


def test_cancel_queued(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.jobs.execute_job.apply_async", lambda **kwargs: None
    )
    job = client.post(
        "/api/scraping/jobs",
        json={
            "authorization_confirmed": True,
            "url": "https://example.com",
            "instruction": "Extract",
            "fields": ["title"],
        },
    ).json()
    id = job["id"]
    assert (
        client.post(f"/api/scraping/jobs/{id}/cancel").json()["status"] == "cancelled"
    )
    from app.workers.tasks import execute_job

    execute_job(id)
    assert client.get(f"/api/scraping/jobs/{id}").json()["status"] == "cancelled"


def test_bad_requests(client):
    assert (
        client.post(
            "/api/scraping/jobs",
            json={
                "authorization_confirmed": True,
                "url": "http://127.0.0.1",
                "instruction": "Extract",
                "fields": ["title"],
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/agents", json={"name": "Test", "configuration": {"tools": ["shell"]}}
        ).status_code
        == 422
    )
    assert client.get("/api/scraping/jobs/missing").status_code == 404


def test_disabled_agent(client):
    agent = client.post("/api/agents", json={"name": "Off", "enabled": False}).json()
    assert (
        client.post(
            "/api/scraping/jobs",
            json={
                "authorization_confirmed": True,
                "agent_id": agent["id"],
                "url": "https://example.com",
                "instruction": "Extract",
                "fields": ["title"],
            },
        ).status_code
        == 409
    )


def test_auth(client, monkeypatch):
    monkeypatch.setattr(settings(), "api_token", "secret-test-token")
    assert client.get("/api/agents").status_code == 401
    assert (
        client.get(
            "/api/agents", headers={"Authorization": "Bearer secret-test-token"}
        ).status_code
        == 200
    )


def test_queue_failure(client, monkeypatch):
    def unavailable(**kwargs):
        raise ConnectionError()

    monkeypatch.setattr("app.services.jobs.execute_job.apply_async", unavailable)
    assert (
        client.post(
            "/api/scraping/jobs",
            json={
                "authorization_confirmed": True,
                "url": "https://example.com",
                "instruction": "Extract",
                "fields": ["title"],
            },
        ).status_code
        == 503
    )
    assert client.get("/api/scraping/jobs").json()[0]["status"] == "failed"


def test_configuration_snapshot(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.jobs.execute_job.apply_async", lambda **kwargs: None
    )
    agent = client.post("/api/agents", json={"name": "Snapshot"}).json()
    created = client.post(
        "/api/scraping/jobs",
        json={
            "authorization_confirmed": True,
            "agent_id": agent["id"],
            "url": "https://example.com",
            "instruction": "Extract",
            "fields": ["title"],
        },
    ).json()
    client.put(
        f"/api/agents/{agent['id']}",
        json={
            "name": "Changed",
            "configuration": {"provider": "ollama", "model": "different"},
        },
    )
    assert created["context"]["configuration"]["provider"] == "deterministic"


def test_stale_job_recovery(client):
    from datetime import timedelta
    from app.database.session import SessionLocal
    from app.models.entities import Agent, Job, now

    with SessionLocal() as db:
        agent = Agent(name="Recovery", configuration={})
        db.add(agent)
        db.flush()
        job = Job(
            agent_id=agent.id,
            status="running",
            input_data={"timeout": 5},
            started_at=now() - timedelta(seconds=100),
        )
        db.add(job)
        db.commit()
        id = job.id
    result = client.get(f"/api/scraping/jobs/{id}").json()
    assert result["status"] == "failed"
    assert "Worker interrupted" in result["error_message"]


def test_api_timestamps_and_schema(client):
    agent = client.post("/api/agents", json={"name": "Timezone"}).json()
    assert agent["created_at"].endswith("Z")
    schema = client.get("/openapi.json").json()
    assert "JobResponse" in schema["components"]["schemas"]
    assert "RecordResponse" in schema["components"]["schemas"]

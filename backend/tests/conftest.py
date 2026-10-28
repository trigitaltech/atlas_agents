import os
import tempfile
from pathlib import Path
import pytest

TEST_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or "sqlite:///" + str(
    Path(TEST_DIR.name) / "test.db"
)
os.environ["QUEUE_EAGER"] = "true"
os.environ["ALLOWED_DOMAINS"] = "example.com,acme.test"
os.environ["RATE_INTERVAL"] = "0.1"
os.environ["OLLAMA_URL"] = "http://localhost:11434"
os.environ["OLLAMA_MODE"] = "local"
os.environ["OLLAMA_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["API_TOKEN"] = ""
from app.database.session import Base, engine
from app.models import entities


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def html():
    return (Path(__file__).parent / "fixtures/company.html").read_text()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    """All automated provider/site traffic and DNS must be explicitly mocked."""
    import socket
    import httpx

    original_dns = socket.getaddrinfo
    database_host = (
        engine.url.host if engine.url.get_backend_name() == "postgresql" else None
    )
    database_port = engine.url.port or 5432

    def deny_dns(host, port=0, *args, **kwargs):
        # Optional PostgreSQL integration infrastructure is not website/provider traffic.
        if database_host and host == database_host and str(port) == str(database_port):
            return original_dns(host, port, *args, **kwargs)
        raise AssertionError(
            "Live website DNS is disabled in tests; provide a mocked resolver"
        )

    async def deny_async(*args, **kwargs):
        raise AssertionError(
            "Live HTTP is disabled in tests; use MockTransport or mock the provider"
        )

    def deny_sync(*args, **kwargs):
        raise AssertionError("Live HTTP is disabled in tests")

    monkeypatch.setattr(socket, "getaddrinfo", deny_dns)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_async)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny_sync)

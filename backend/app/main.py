import asyncio
import secrets
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text, select, func
from app.core.config import settings
from app.core.logging import configure_logging
from app.database.session import SessionLocal, get_db
from app.api import agents, scraping, jobs, exports
from app.core.tool_registry import registry
from app.models.entities import Job, Agent

configure_logging()


async def authorize(authorization: str | None = Header(default=None)):
    token = settings().api_token
    if token and not secrets.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(401, "Valid bearer token required")


@asynccontextmanager
async def lifespan(app):
    yield


app = FastAPI(
    title="Atlas Agent Platform",
    version="1.0.0",
    lifespan=lifespan,
    description="Bounded, evidence-backed web intelligence. Authorize targets on the server before submitting jobs.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().cors_origins.split(","),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
for router in (agents.router, scraping.router, jobs.router, exports.router):
    app.include_router(router, dependencies=[Depends(authorize)])


@app.middleware("http")
async def request_id(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.status_code, "message": exc.detail}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": 422,
                "message": "Request validation failed",
                "details": [
                    {"field": ".".join(map(str, e["loc"])), "message": e["msg"]}
                    for e in exc.errors()
                ],
            }
        },
    )


@app.get("/api/health", tags=["System"])
async def health():
    def database_ready():
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))

    services = {"database": "ok", "redis": "ok"}
    try:
        await asyncio.to_thread(database_ready)
    except Exception:
        services["database"] = "unavailable"
    if settings().queue_eager:
        services["redis"] = "eager mode"
    else:
        from redis.asyncio import Redis

        redis = Redis.from_url(
            settings().redis_url, socket_connect_timeout=2, socket_timeout=2
        )
        try:
            await redis.ping()
        except Exception:
            services["redis"] = "unavailable"
        finally:
            await redis.aclose()
    ok = "unavailable" not in services.values()
    return JSONResponse(
        {"status": "ok" if ok else "degraded", "services": services},
        status_code=200 if ok else 503,
    )


@app.get("/api/tools", tags=["System"], dependencies=[Depends(authorize)])
def tools():
    return [
        {
            "name": t.name,
            "description": t.description,
            "permission": t.permission,
            "timeout": t.timeout,
            "input_schema": t.input_schema.model_json_schema(),
            "output_schema": t.output_schema.model_json_schema(),
        }
        for t in registry.values()
    ]


@app.get("/api/models", tags=["System"], dependencies=[Depends(authorize)])
def models():
    return {
        "providers": [
            {"id": "deterministic", "models": ["rules-v1"], "available": True},
            {
                "id": "openai",
                "models": ["gpt-4.1-mini"],
                "available": bool(settings().openai_api_key),
            },
            {"id": "ollama", "models": [], "available": True},
        ],
        "note": "Model IDs are configurable; choose a model available on the configured Ollama provider. Cloud models need no local installation.",
    }


@app.get("/api/settings", tags=["System"], dependencies=[Depends(authorize)])
def public_settings():
    cfg = settings()
    return {
        "allowed_domains": sorted(cfg.domains),
        "max_pages": cfg.max_pages,
        "max_timeout": cfg.max_timeout,
        "max_tokens": cfg.max_tokens,
        "rate_interval": cfg.rate_interval,
        "browser_enabled": cfg.browser_enabled,
        "configuration_source": "Backend environment; restart API and worker after edits",
    }


@app.get("/api/stats", tags=["System"], dependencies=[Depends(authorize)])
def stats(db=Depends(get_db)):
    counts = dict(
        db.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    )
    return {
        "agents": db.scalar(select(func.count()).select_from(Agent)),
        "active": counts.get("queued", 0) + counts.get("running", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
    }

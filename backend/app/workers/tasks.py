import asyncio
import logging
from pydantic import ValidationError
from celery import Celery
from celery.signals import setup_logging
from app.core.logging import configure_logging
from sqlalchemy import update
from app.core.config import settings
from app.database.session import SessionLocal
from app.models.entities import Job, Agent, now, Execution
from app.core.memory import JobMemory
from app.core.policies import RedirectAuthorizationRequired
from app.core.orchestrator import build_agent
from app.agents.web_scraper.agent import JobCancelled
from app.agents.web_scraper.schemas import ScrapeRequest, AgentConfiguration


@setup_logging.connect
def worker_logging(**kwargs):
    configure_logging()


celery = Celery(
    "agent_platform", broker=settings().redis_url, backend=settings().redis_url
)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings().max_timeout + 30,
    task_always_eager=settings().queue_eager,
)
log = logging.getLogger(__name__)


@celery.task(name="platform.execute_job")
def execute_job(job_id):
    # Atomic claim makes duplicate deliveries harmless. Interrupted jobs require explicit resubmission.
    with SessionLocal() as db:
        claim = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "queued")
            .values(status="running", started_at=now())
        )
        db.commit()
        if claim.rowcount != 1:
            return
        job = db.get(Job, job_id)
        agent = db.get(Agent, job.agent_id)
        input_data = job.input_data
        configuration_data = job.context.get("configuration", agent.configuration)
        agent_type = agent.agent_type
    memory = JobMemory(job_id)
    try:
        request = ScrapeRequest.model_validate(input_data)
        config = AgentConfiguration.model_validate(configuration_data)
        result = asyncio.run(
            build_agent(
                agent_type, request, config, memory.checkpoint, memory.cancelled
            ).run()
        )
        status, error = "completed", None
    except ValidationError:
        status, error, result = (
            "failed",
            "Stored execution settings are invalid; start a new confirmed execution",
            {},
        )
    except (JobCancelled, asyncio.CancelledError):
        status, error, result = "cancelled", None, {}
    except RedirectAuthorizationRequired as exc:
        status, error, result = (
            "failed",
            str(exc),
            {
                "error_code": "redirect_authorization_required",
                "authorization_required_hostname": exc.hostname,
                "stop_reason": "authorization_required",
            },
        )
    except TimeoutError:
        status, error, result = (
            "failed",
            "Execution time limit reached",
            {"stop_reason": "time_limit"},
        )
    except Exception as exc:
        status, error, result = "failed", public_error(exc), {}
        log.warning(
            "job_failed", extra={"job_id": job_id, "error_type": type(exc).__name__}
        )
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        context = dict(job.context or {})
        context.update(result)
        db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "running")
            .values(
                status=status, error_message=error, completed_at=now(), context=context
            )
        )
        if status == "failed":
            db.add(
                Execution(
                    job_id=job_id,
                    step_name="execution",
                    status="failed",
                    error_message=error,
                )
            )
        db.commit()


def public_error(exc):
    from app.core.policies import PolicyError
    from app.core.llm_gateway import LLMProviderError

    if isinstance(exc, LLMProviderError):
        return str(exc)
    if isinstance(exc, (PolicyError, ValueError, PermissionError)):
        return str(exc)[:300]
    return "Execution failed; check worker logs and service configuration"

from fastapi import HTTPException
from sqlalchemy import update
from app.models.entities import Agent, Job, now
from app.core.config import settings
from app.core.policies import NetworkPolicy, AuthorizationError, normalize
from app.agents.web_scraper.schemas import AgentConfiguration
from app.workers.tasks import execute_job

REQUIRED_TOOLS = {
    "http_fetch",
    "html_parser",
    "link_discovery",
    "validation",
    "database_storage",
}


def submit(db, body):
    cfg = settings()
    if (
        body.max_pages > cfg.max_pages
        or body.timeout > cfg.max_timeout
        or body.token_budget > cfg.max_tokens
    ):
        raise HTTPException(422, "Request exceeds server execution limits")
    if body.additional_authorized_domains:
        source = (
            db.get(Job, body.authorization_source_job_id)
            if body.authorization_source_job_id
            else None
        )
        if (
            source is None
            or source.status != "failed"
            or source.context.get("error_code") != "redirect_authorization_required"
            or normalize(source.input_data["url"]) != body.url
        ):
            raise HTTPException(
                403,
                "Additional hostname approval must reference the stopped redirect execution and its original target URL",
            )
        observed = source.context.get("authorization_required_hostname")
        previously_approved = set(
            source.input_data.get("additional_authorized_domains", [])
        )
        if not set(body.additional_authorized_domains) <= previously_approved | {
            observed
        }:
            raise HTTPException(
                403,
                "Only hostnames recorded in the stopped redirect execution may be approved",
            )
    try:
        policy = NetworkPolicy.for_execution(body)
        policy.check(body.url)
    except AuthorizationError as exc:
        raise HTTPException(403, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if body.agent_id:
        agent = db.get(Agent, body.agent_id)
        if not agent:
            raise HTTPException(404, "Agent not found")
        if not agent.enabled:
            raise HTTPException(409, "Agent is disabled")
    else:
        agent = Agent(
            name=body.agent_name, configuration=AgentConfiguration().model_dump()
        )
        db.add(agent)
        db.flush()
    config = AgentConfiguration.model_validate(agent.configuration)
    required = (
        REQUIRED_TOOLS
        | ({"ai_extraction"} if config.provider != "deterministic" else set())
        | ({"browser_navigation"} if body.render_js else set())
    )
    if not required <= set(config.tools):
        raise HTTPException(422, "Agent is missing required execution tools")
    if body.render_js and not cfg.browser_enabled:
        raise HTTPException(422, "JavaScript rendering is disabled on this server")
    job = Job(
        agent_id=agent.id,
        input_data=body.model_dump(),
        context={
            "configuration": config.model_dump(),
            "agent_type": agent.agent_type,
            "authorized_hostnames": sorted(policy.domains),
            "authorization_confirmed": True,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        execute_job.apply_async(args=[job.id], task_id=job.id)
    except Exception:
        db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "queued")
            .values(
                status="failed",
                error_message="Job queue is unavailable",
                completed_at=now(),
            )
        )
        db.commit()
        raise HTTPException(
            503, "Job queue unavailable; job retained in execution history"
        ) from None
    db.refresh(job)
    return job

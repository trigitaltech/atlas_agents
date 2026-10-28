from typing import Literal
from fastapi import APIRouter, Depends, Response, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database.session import get_db
from app.models.entities import Job, Record, Agent
from app.api.dependencies import require
from app.core.tool_registry import registry

router = APIRouter(tags=["Exports"])


@router.get("/api/scraping/jobs/{job_id}/export")
async def download(
    job_id: str, format: Literal["csv", "json"] = "json", db: Session = Depends(get_db)
):
    job = require(db, Job, job_id)
    agent = require(db, Agent, job.agent_id)
    tool = format + "_export"
    if tool not in agent.configuration.get("tools", []):
        raise HTTPException(403, "Export tool is disabled for this agent")
    records = [
        r.extracted_data
        for r in db.scalars(
            select(Record).where(Record.job_id == job_id).order_by(Record.created_at)
        )
    ]
    data = await registry[tool].execute([records], set(agent.configuration["tools"]))
    return Response(
        data,
        media_type="text/csv" if format == "csv" else "application/json",
        headers={"Content-Disposition": f'attachment; filename="{job_id}.{format}"'},
    )

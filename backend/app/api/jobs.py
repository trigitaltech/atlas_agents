from app.api.schemas import JobResponse, JobDetail, RecordResponse
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from app.database.session import get_db
from app.models.entities import Job, Execution, Record, now
from app.api.dependencies import require, serialize
from app.services.recovery import reconcile

router = APIRouter(prefix="/api/scraping/jobs", tags=["Jobs"])


@router.get("", response_model=list[JobResponse])
def list_jobs(
    agent_id: str | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    reconcile(db)
    query = select(Job)
    if agent_id:
        query = query.where(Job.agent_id == agent_id)
    return [
        serialize(job)
        for job in db.scalars(
            query.order_by(Job.created_at.desc()).offset(offset).limit(limit)
        )
    ]


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str, db: Session = Depends(get_db)):
    reconcile(db)
    job = serialize(require(db, Job, job_id))
    job["executions"] = [
        serialize(row)
        for row in db.scalars(
            select(Execution)
            .where(Execution.job_id == job_id)
            .order_by(Execution.created_at)
        )
    ]
    return job


@router.get("/{job_id}/results", response_model=list[RecordResponse])
def get_results(job_id: str, db: Session = Depends(get_db)):
    require(db, Job, job_id)
    return [
        serialize(row)
        for row in db.scalars(
            select(Record).where(Record.job_id == job_id).order_by(Record.created_at)
        )
    ]


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel(job_id: str, db: Session = Depends(get_db)):
    require(db, Job, job_id)
    db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status.in_(["queued", "running"]))
        .values(status="cancelled", completed_at=now())
    )
    db.commit()
    db.expire_all()
    return serialize(db.get(Job, job_id))

"""Reconcile abandoned executions without silently rerunning billable work."""

from datetime import timedelta
from sqlalchemy import select, update
from app.models.entities import Job, now


def reconcile(db):
    current = now()
    candidates = db.scalars(
        select(Job).where(
            Job.status == "running", Job.started_at < current - timedelta(seconds=35)
        )
    )
    for job in candidates:
        started = job.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=current.tzinfo)
        if (current - started).total_seconds() > job.input_data.get(
            "timeout", 600
        ) + 30:
            db.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == "running")
                .values(
                    status="failed",
                    completed_at=current,
                    error_message="Worker interrupted or execution deadline exceeded; resubmit explicitly",
                )
            )
    db.commit()

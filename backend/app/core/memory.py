import logging
from sqlalchemy import update
from app.database.session import SessionLocal
from app.models.entities import Job, Execution, ScrapedPage, Record


class JobMemory:
    def __init__(self, job_id):
        self.job_id = job_id

    def cancelled(self):
        with SessionLocal() as db:
            return db.get(Job, self.job_id).status == "cancelled"

    def checkpoint(self, step, payload):
        with SessionLocal() as db:
            job = db.get(Job, self.job_id)
            if job.status == "cancelled":
                return
            context = dict(job.context or {})
            context.update(
                {
                    k: v
                    for k, v in payload.items()
                    if k not in {"record", "content_hash"}
                }
            )
            context["step"] = step
            # A conditional write avoids overwriting cancellation requested in another process.
            changed = db.execute(
                update(Job)
                .where(Job.id == self.job_id, Job.status == "running")
                .values(context=context)
            )
            if changed.rowcount != 1:
                db.rollback()
                return
            db.add(
                Execution(
                    job_id=self.job_id,
                    step_name=step,
                    status="completed",
                    duration_ms=payload.get("duration_ms", 0),
                )
            )
            if step == "stored":
                db.add(
                    ScrapedPage(
                        job_id=self.job_id,
                        **{
                            k: payload[k]
                            for k in ["url", "title", "status_code", "content_hash"]
                        },
                    )
                )
                if "record" in payload:
                    db.add(Record(job_id=self.job_id, **payload["record"]))
            db.commit()
            logging.getLogger(__name__).info(
                "agent_checkpoint",
                extra={
                    "job_id": self.job_id,
                    "step": step,
                    "duration_ms": payload.get("duration_ms", 0),
                },
            )

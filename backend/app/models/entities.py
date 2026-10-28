import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Text,
    JSON,
    ForeignKey,
    DateTime,
    Boolean,
    Integer,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    agent_type: Mapped[str] = mapped_column(String(40), default="web_scraper")
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )
    jobs: Mapped[list["Job"]] = relationship(back_populates="agent")
    schedules: Mapped[list["Schedule"]] = relationship(cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "agent_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled')",
            name="job_status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    input_data: Mapped[dict] = mapped_column(JSON)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    agent: Mapped[Agent] = relationship(back_populates="jobs")
    pages: Mapped[list["ScrapedPage"]] = relationship(cascade="all, delete-orphan")
    records: Mapped[list["Record"]] = relationship(cascade="all, delete-orphan")
    executions: Mapped[list["Execution"]] = relationship(cascade="all, delete-orphan")


class ScrapedPage(Base):
    __tablename__ = "scraped_pages"
    __table_args__ = (UniqueConstraint("job_id", "url"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Record(Base):
    __tablename__ = "extracted_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True
    )
    source_url: Mapped[str] = mapped_column(Text)
    extracted_data: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Execution(Base):
    __tablename__ = "agent_executions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True
    )
    step_name: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Schedule(Base):
    __tablename__ = "agent_schedules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    schedule_expression: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )

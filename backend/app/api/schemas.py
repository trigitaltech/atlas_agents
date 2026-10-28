"""Public response contracts; service credentials are never response fields."""

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator
from app.agents.web_scraper.schemas import AgentConfiguration


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="after")
    @classmethod
    def utc_datetime(cls, value):
        # SQLite loses timezone metadata; all persisted timestamps originate in UTC.
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class AgentResponse(APIModel):
    id: str
    name: str
    description: str
    agent_type: str
    configuration: AgentConfiguration
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ExecutionResponse(APIModel):
    id: str
    job_id: str
    step_name: str
    status: str
    duration_ms: int
    error_message: str | None
    created_at: datetime


class JobResponse(APIModel):
    id: str
    agent_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    input_data: dict
    context: dict
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


class JobDetail(JobResponse):
    executions: list[ExecutionResponse]


class RecordResponse(APIModel):
    id: str
    job_id: str
    source_url: str
    extracted_data: dict[str, str | None]
    evidence: dict[str, str]
    validation_status: str
    created_at: datetime

import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict, StrictBool
from app.core.policies import normalize, canonical_hostname


class AgentConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    provider: Literal["deterministic", "openai", "ollama"] = "deterministic"
    model: str = "gpt-4.1-mini"
    temperature: float = Field(default=0, ge=0, le=1)
    tools: list[str] = Field(
        default_factory=lambda: [
            "http_fetch",
            "html_parser",
            "link_discovery",
            "ai_extraction",
            "validation",
            "database_storage",
            "csv_export",
            "json_export",
        ]
    )


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    agent_type: Literal["web_scraper"] = "web_scraper"
    configuration: AgentConfiguration = Field(default_factory=AgentConfiguration)
    enabled: bool = True


class ScrapeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str | None = None
    agent_name: str = Field(
        default="Web intelligence agent", min_length=1, max_length=120
    )
    url: str = Field(max_length=2048)
    instruction: str = Field(min_length=1, max_length=4000)
    fields: list[str] = Field(min_length=1, max_length=30)
    max_depth: int = Field(default=1, ge=0, le=5)
    max_pages: int = Field(default=5, ge=1, le=50)
    timeout: int = Field(default=120, ge=5, le=600)
    token_budget: int = Field(default=10000, ge=100, le=100000)
    authorization_confirmed: StrictBool = False
    authorization_source_job_id: str | None = Field(
        default=None, min_length=36, max_length=36
    )
    additional_authorized_domains: list[str] = Field(
        default_factory=list, max_length=10
    )
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)
    output_format: Literal["json", "csv"] = "json"
    render_js: bool = False

    @field_validator("url")
    @classmethod
    def url_format(cls, value: str) -> str:
        return normalize(value)

    @field_validator("allowed_domains", "additional_authorized_domains")
    @classmethod
    def exact_hostnames(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(canonical_hostname(value) for value in values))

    @field_validator("fields")
    @classmethod
    def field_names(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", v) for v in values):
            raise ValueError("Fields must use lowercase snake_case")
        return list(dict.fromkeys(values))


class ExtractedValue(BaseModel):
    value: str | None = None
    evidence: str | None = None


class Extraction(BaseModel):
    fields: dict[str, ExtractedValue]


def extraction_schema(fields: list[str]) -> dict:
    """A closed schema with required, nullable values for each requested field."""
    value = {
        "type": "object",
        "properties": {
            "value": {"type": ["string", "null"]},
            "evidence": {"type": ["string", "null"]},
        },
        "required": ["value", "evidence"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "properties": {key: value for key in fields},
                "required": fields,
                "additionalProperties": False,
            }
        },
        "required": ["fields"],
        "additionalProperties": False,
    }

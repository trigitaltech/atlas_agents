from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, field_validator
from urllib.parse import urlsplit
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = "sqlite:///./platform.db"
    redis_url: str = "redis://localhost:6379/0"
    allowed_domains: str = "example.com"
    api_token: str = ""
    openai_api_key: str = ""
    ollama_url: str = "http://localhost:11434"
    ollama_mode: Literal["local", "cloud"] = "local"
    ollama_api_key: SecretStr = Field(default=SecretStr(""), exclude=True, repr=False)
    cors_origins: str = "http://localhost:5173"
    rate_interval: float = Field(default=1.0, ge=0.1)
    max_response_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    max_pages: int = Field(default=50, ge=1, le=50)
    max_timeout: int = Field(default=600, ge=5, le=600)
    max_tokens: int = Field(default=20000, ge=100, le=100000)
    input_cost_per_million: float = Field(default=0, ge=0)
    output_cost_per_million: float = Field(default=0, ge=0)
    browser_enabled: bool = False
    queue_eager: bool = False

    @field_validator("ollama_url")
    @classmethod
    def ollama_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "OLLAMA_URL must be an HTTP(S) base URL without credentials, query, or fragment"
            )
        try:
            parsed.port
        except ValueError:
            raise ValueError("OLLAMA_URL has an invalid port") from None
        return value.rstrip("/")

    @property
    def domains(self) -> set[str]:
        return {d.strip().lower() for d in self.allowed_domains.split(",") if d.strip()}


@lru_cache
def settings() -> Settings:
    return Settings()

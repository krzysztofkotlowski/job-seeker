"""Central configuration from environment variables."""

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment. Validates at startup."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Security
    cors_origins: str = ""
    rate_limit: str = "100/minute"

    # Limits for full-table operations (avoid loading millions of rows)
    resume_match_job_limit: int = 2000
    skills_match_job_limit: int = 2000


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_cors_origins() -> List[str]:
    """
    Parse CORS_ORIGINS env var. Comma-separated list.
    Default: localhost dev origins when unset.
    """
    raw = get_settings().cors_origins.strip()
    if not raw:
        return [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:80",
            "http://127.0.0.1:5173",
        ]
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def get_rate_limit() -> str:
    """Rate limit string for slowapi, e.g. '100/minute'."""
    return get_settings().rate_limit.strip() or "100/minute"

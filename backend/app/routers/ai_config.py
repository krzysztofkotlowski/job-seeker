"""AI config router: list models, get/update config."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.services.ai_config_service import (
    ensure_ollama_model,
    get_ai_config,
    list_ollama_models,
    list_openai_models,
    update_ai_config,
    validate_openai_key,
)
from app.services.inference_log_service import get_metrics

router = APIRouter()


class EnsureModelRequest(BaseModel):
    """Request body for POST /ai/ensure-model."""

    model: str = Field(..., min_length=1, max_length=255)


class ValidateKeyRequest(BaseModel):
    """Request body for POST /ai/config/validate-key."""

    openai_api_key: str = Field(..., min_length=1, max_length=500)


class AIConfigUpdate(BaseModel):
    """Request body for PUT /ai/config."""

    provider: str | None = Field(None, pattern="^(ollama|openai)$")
    openai_api_key: str | None = Field(None, max_length=500)
    openai_llm_model: str | None = Field(None, min_length=1, max_length=100)
    embed_source: str | None = Field(None, pattern="^(ollama|openai)$")
    llm_model: str | None = Field(None, min_length=1, max_length=255)
    embed_model: str | None = Field(None, min_length=1, max_length=255)
    embed_profile: str | None = Field(None, min_length=1, max_length=50)
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    max_output_tokens: int | None = Field(None, ge=512, le=4096)


def _sanitize_config_for_response(cfg: dict) -> dict:
    """Remove openai_api_key from config before returning to client."""
    out = {k: v for k, v in cfg.items() if k != "openai_api_key"}
    return out


@router.get("/models")
def list_models(
    provider: str | None = None,
    db: Session = Depends(get_db),
):
    """List available models. Use ?provider=ollama|openai to override config."""
    cfg = get_ai_config(db)
    p = (provider or cfg.get("provider") or "ollama").strip().lower()
    if p == "openai":
        return list_openai_models()
    return list_ollama_models()


@router.post("/ensure-model")
def ensure_model(
    body: EnsureModelRequest,
    user: Annotated[dict | None, Depends(require_auth)] = None,
):
    """Ensure a self-hosted model is available; pull if missing. Returns { status, error? }."""
    result = ensure_ollama_model(body.model)
    return result


@router.post("/config/validate-key")
def validate_key(
    body: ValidateKeyRequest,
    user: Annotated[dict | None, Depends(require_auth)] = None,
):
    """Validate OpenAI API key. Returns { valid: true } or { valid: false, error: "..." }."""
    valid = validate_openai_key(body.openai_api_key)
    if valid:
        return {"valid": True}
    return {"valid": False, "error": "Invalid or unreachable API key"}


@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    """Return current AI config (from DB or env defaults). Never returns api_key."""
    cfg = get_ai_config(db)
    return _sanitize_config_for_response(cfg)


@router.put("/config")
def put_config(
    body: AIConfigUpdate,
    db: Session = Depends(get_db),
    user: Annotated[dict | None, Depends(require_auth)] = None,
):
    """Update AI config. Requires auth when Keycloak is enabled."""
    updated = update_ai_config(
        db,
        provider=body.provider,
        openai_api_key=body.openai_api_key,
        openai_llm_model=body.openai_llm_model,
        embed_source=body.embed_source,
        llm_model=body.llm_model,
        embed_model=body.embed_model,
        embed_profile=body.embed_profile,
        temperature=body.temperature,
        max_output_tokens=body.max_output_tokens,
    )
    return _sanitize_config_for_response(updated)


@router.get("/metrics")
def get_ai_metrics(db: Session = Depends(get_db)):
    """Return inference metrics for the last 7 days."""
    return get_metrics(db, days=7)

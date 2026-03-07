"""AI config router: list models, get/update config."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.services.ai_config_service import (
    get_ai_config,
    list_ollama_models,
    update_ai_config,
)
from app.services.inference_log_service import get_metrics

router = APIRouter()


class AIConfigUpdate(BaseModel):
    """Request body for PUT /ai/config."""

    llm_model: str | None = Field(None, min_length=1, max_length=255)
    embed_model: str | None = Field(None, min_length=1, max_length=255)
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    max_output_tokens: int | None = Field(None, ge=256, le=4096)


@router.get("/models")
def list_models():
    """List available Ollama models (LLM and embeddings)."""
    return list_ollama_models()


@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    """Return current AI config (from DB or env defaults)."""
    return get_ai_config(db)


@router.put("/config")
def put_config(
    body: AIConfigUpdate,
    db: Session = Depends(get_db),
    user: Annotated[dict | None, Depends(require_auth)] = None,
):
    """Update AI config. Requires auth when Keycloak is enabled."""
    return update_ai_config(
        db,
        llm_model=body.llm_model,
        embed_model=body.embed_model,
        temperature=body.temperature,
        max_output_tokens=body.max_output_tokens,
    )


@router.get("/metrics")
def get_ai_metrics(db: Session = Depends(get_db)):
    """Return inference metrics for the last 7 days."""
    return get_metrics(db, days=7)

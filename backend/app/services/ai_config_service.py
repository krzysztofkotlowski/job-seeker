"""AI config service: load/save config from DB, list Ollama models."""

import logging
import os

import httpx
from sqlalchemy.orm import Session

from app.models.tables import AIConfigRow

log = logging.getLogger(__name__)

OLLAMA_URL = (os.environ.get("LLM_URL", "") or "").rstrip("/")
DEFAULT_LLM_MODEL = os.environ.get("LLM_MODEL", "phi3:mini") or "phi3:mini"
DEFAULT_EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text") or "nomic-embed-text"
DEFAULT_MAX_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "1024") or "1024")


def get_ai_config(db: Session) -> dict:
    """Return current AI config from DB or env defaults."""
    row = db.query(AIConfigRow).filter(AIConfigRow.id == 1).first()
    if row:
        return {
            "llm_model": row.llm_model or DEFAULT_LLM_MODEL,
            "embed_model": row.embed_model or DEFAULT_EMBED_MODEL,
            "temperature": float(row.temperature) if row.temperature is not None else 0.3,
            "max_output_tokens": row.max_output_tokens or DEFAULT_MAX_TOKENS,
        }
    return {
        "llm_model": DEFAULT_LLM_MODEL,
        "embed_model": DEFAULT_EMBED_MODEL,
        "temperature": 0.3,
        "max_output_tokens": DEFAULT_MAX_TOKENS,
    }


def update_ai_config(
    db: Session,
    *,
    llm_model: str | None = None,
    embed_model: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> dict:
    """Update AI config in DB. Returns updated config."""
    row = db.query(AIConfigRow).filter(AIConfigRow.id == 1).first()
    if not row:
        row = AIConfigRow(
            id=1,
            llm_model=DEFAULT_LLM_MODEL,
            embed_model=DEFAULT_EMBED_MODEL,
            temperature=0.3,
            max_output_tokens=DEFAULT_MAX_TOKENS,
        )
        db.add(row)
        db.flush()

    if llm_model is not None:
        row.llm_model = llm_model.strip() or DEFAULT_LLM_MODEL
    if embed_model is not None:
        row.embed_model = embed_model.strip() or DEFAULT_EMBED_MODEL
    if temperature is not None:
        row.temperature = max(0.0, min(1.0, float(temperature)))
    if max_output_tokens is not None:
        row.max_output_tokens = max(256, min(4096, int(max_output_tokens)))

    db.commit()
    db.refresh(row)
    return get_ai_config(db)


def list_ollama_models() -> dict:
    """Fetch available models from Ollama /api/tags. Returns { models: [...] }."""
    if not OLLAMA_URL:
        return {"models": []}
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code != 200:
                return {"models": []}
            data = resp.json()
            models = data.get("models") or []
            return {"models": models}
    except Exception as e:
        log.debug("Failed to list Ollama models: %s", e)
        return {"models": []}

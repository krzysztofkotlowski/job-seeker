"""AI config service: load/save config from DB, list Ollama/OpenAI models."""

import logging
import os

import httpx
from sqlalchemy.orm import Session

from app.models.tables import AIConfigRow

log = logging.getLogger(__name__)

# Re-exports for test patching; implementations live in other modules
from app.services.embedding_service import get_ollama_embedding_dims
from app.services.self_hosted_runtime_service import (
    best_effort_activate_self_hosted_models as _best_effort_activate_self_hosted_models,
    is_self_hosted_model_ready,
    list_self_hosted_models,
)

OLLAMA_URL = (os.environ.get("LLM_URL", "") or "").rstrip("/")
SELF_HOSTED_URL = (os.environ.get("LLM_URL", "") or "").rstrip("/")
DEFAULT_LLM_MODEL = os.environ.get("LLM_MODEL", "phi3:mini") or "phi3:mini"
DEFAULT_EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text") or "nomic-embed-text"
DEFAULT_MAX_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "2048") or "2048")
OPENAI_EMBED_DIMS = 1536
OLLAMA_EMBED_DIMS = int(os.environ.get("EMBED_DIMS", "768") or "768")

OPENAI_LLM_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
]
OPENAI_EMBED_MODEL = "text-embedding-3-small"

# Known self-hosted embedding model dimensions
_EMBED_DIMS_BY_MODEL: dict[str, int] = {
    "nomic-embed-text": 768,
    "all-minilm": 384,
    "all-minilm-l6-v2": 384,
    "bge-base-en": 768,
    "bge-base-en:v1.5": 768,
}


def resolve_ollama_embed_dims(model: str, configured_dims: int = 0) -> int:
    """Resolve embedding dimensions for a self-hosted model. Uses configured_dims if valid, else model lookup."""
    if configured_dims and 256 <= configured_dims <= 4096:
        return configured_dims
    m = (model or "").strip().lower()
    for key, dims in _EMBED_DIMS_BY_MODEL.items():
        if key in m:
            return dims
    return OLLAMA_EMBED_DIMS


def get_ai_config(db: Session) -> dict:
    """Return current AI config from DB or env defaults. Never returns api_key."""
    row = db.query(AIConfigRow).filter(AIConfigRow.id == 1).first()
    if row:
        provider = getattr(row, "provider", None) or "ollama"
        embed_source = getattr(row, "embed_source", None) or "ollama"
        embed_dims = getattr(row, "embed_dims", None)
        if embed_dims is None:
            embed_dims = OPENAI_EMBED_DIMS if embed_source == "openai" else OLLAMA_EMBED_DIMS
        return {
            "provider": provider,
            "openai_llm_model": getattr(row, "openai_llm_model", None) or "gpt-4o-mini",
            "embed_source": embed_source,
            "api_key_set": bool(getattr(row, "openai_api_key", None) and str(row.openai_api_key).strip()),
            "llm_model": row.llm_model or DEFAULT_LLM_MODEL,
            "embed_model": row.embed_model or DEFAULT_EMBED_MODEL,
            "embed_profile": getattr(row, "embed_profile", None),
            "temperature": float(row.temperature) if row.temperature is not None else 0.3,
            "max_output_tokens": row.max_output_tokens or DEFAULT_MAX_TOKENS,
            "embed_dims": embed_dims,
            "openai_api_key": row.openai_api_key if hasattr(row, "openai_api_key") else None,
        }
    return {
        "provider": "ollama",
        "openai_llm_model": "gpt-4o-mini",
        "embed_source": "ollama",
        "api_key_set": False,
        "llm_model": DEFAULT_LLM_MODEL,
        "embed_model": DEFAULT_EMBED_MODEL,
        "embed_profile": None,
        "temperature": 0.3,
        "max_output_tokens": DEFAULT_MAX_TOKENS,
        "embed_dims": OLLAMA_EMBED_DIMS,
        "openai_api_key": None,
    }


def update_ai_config(
    db: Session,
    *,
    provider: str | None = None,
    openai_api_key: str | None = None,
    openai_llm_model: str | None = None,
    embed_source: str | None = None,
    llm_model: str | None = None,
    embed_model: str | None = None,
    embed_profile: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    embed_dims: int | None = None,
) -> dict:
    """Update AI config in DB. Returns updated config (without api_key)."""
    row = db.query(AIConfigRow).filter(AIConfigRow.id == 1).first()
    old_llm = row.llm_model if row else None
    old_embed = row.embed_model if row else None
    if not row:
        row = AIConfigRow(
            id=1,
            provider="ollama",
            llm_model=DEFAULT_LLM_MODEL,
            embed_model=DEFAULT_EMBED_MODEL,
            temperature=0.3,
            max_output_tokens=DEFAULT_MAX_TOKENS,
        )
        db.add(row)
        db.flush()

    if provider is not None:
        p = provider.strip().lower()
        if p in ("ollama", "openai"):
            row.provider = p
    if openai_api_key is not None:
        if isinstance(openai_api_key, str) and openai_api_key.strip():
            row.openai_api_key = openai_api_key.strip()
        else:
            row.openai_api_key = None
    if openai_llm_model is not None:
        row.openai_llm_model = openai_llm_model.strip() or "gpt-4o-mini"
    if embed_source is not None:
        es = embed_source.strip().lower()
        if es in ("ollama", "openai"):
            row.embed_source = es
    if llm_model is not None:
        row.llm_model = llm_model.strip() or DEFAULT_LLM_MODEL
    if embed_model is not None:
        row.embed_model = embed_model.strip() or DEFAULT_EMBED_MODEL
    if embed_profile is not None:
        row.embed_profile = embed_profile.strip() or None
    if temperature is not None:
        row.temperature = max(0.0, min(1.0, float(temperature)))
    if max_output_tokens is not None:
        row.max_output_tokens = max(512, min(4096, int(max_output_tokens)))
    if embed_dims is not None:
        row.embed_dims = max(256, min(4096, int(embed_dims)))

    # Resolve embed_dims from Ollama model when embed_source is ollama and embed_model provided
    if (
        row.embed_source == "ollama"
        and row.embed_model
        and (embed_model is not None or embed_source is not None)
    ):
        resolved = get_ollama_embedding_dims(row.embed_model)
        if isinstance(resolved, int) and 256 <= resolved <= 4096:
            row.embed_dims = resolved

    db.commit()
    db.refresh(row)
    updated = get_ai_config(db)

    # Best-effort activate self-hosted models when saving ollama config
    if row.provider == "ollama":
        # Skip activation when models unchanged and already ready
        if not (
            row.llm_model == old_llm
            and row.embed_model == old_embed
            and is_self_hosted_model_ready(row.llm_model)
            and is_self_hosted_model_ready(row.embed_model)
        ):
            _best_effort_activate_self_hosted_models(
                chat_model=row.llm_model,
                embed_model=row.embed_model,
            )

    return updated


def validate_openai_key(api_key: str) -> bool:
    """Validate OpenAI API key with a minimal request. Returns True if valid."""
    if not api_key or not str(api_key).strip():
        return False
    key = api_key.strip()
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            return resp.status_code == 200
    except Exception as e:
        log.debug("OpenAI key validation failed: %s", e)
        return False


def list_ollama_models() -> dict:
    """Fetch available models from self-hosted catalog when available, else Ollama /api/tags."""
    try:
        result = list_self_hosted_models()
        if result and "runtime" in result:
            return result
        if result and result.get("models"):
            return result
    except Exception as e:
        log.debug("list_self_hosted_models failed, falling back to Ollama: %s", e)
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


def list_openai_models() -> dict:
    """Return static list of OpenAI models for UI."""
    return {
        "models": [
            {"name": m, "model": m}
            for m in OPENAI_LLM_MODELS
        ]
    }

"""AI config service: load/save config from DB, list Ollama/OpenAI models."""

import logging
import os

import httpx
from sqlalchemy.orm import Session

from app.models.tables import AIConfigRow
from app.services.embedding_service import get_ollama_embedding_dims

log = logging.getLogger(__name__)

OLLAMA_URL = (os.environ.get("LLM_URL", "") or "").rstrip("/")
DEFAULT_LLM_MODEL = os.environ.get("LLM_MODEL", "phi3:mini") or "phi3:mini"
DEFAULT_EMBED_MODEL = os.environ.get("EMBED_MODEL", "all-minilm") or "all-minilm"
DEFAULT_MAX_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "2048") or "2048")
OPENAI_EMBED_DIMS = 1536
OLLAMA_EMBED_DIMS = int(os.environ.get("EMBED_DIMS", "384") or "384")

OPENAI_LLM_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
]
OPENAI_EMBED_MODEL = "text-embedding-3-small"


def _clamp_embed_dims(embed_dims: int) -> int:
    """Clamp embed dims to sane range accepted by current schema/UI."""
    return max(256, min(4096, int(embed_dims)))


def resolve_embed_dims(embed_source: str | None, embed_dims: int | None) -> int:
    """
    Resolve active embedding dimensions for index/query operations.
    OpenAI embeddings are fixed in-app to text-embedding-3-small (1536 dims).
    """
    source = (embed_source or "ollama").strip().lower()
    if source == "openai":
        return OPENAI_EMBED_DIMS
    if embed_dims is None:
        return OLLAMA_EMBED_DIMS
    return _clamp_embed_dims(embed_dims)


def resolve_ollama_embed_dims(embed_model: str | None, fallback_dims: int | None = None) -> int:
    """Resolve Ollama embedding dims from the selected model, falling back safely when probing fails."""
    detected = get_ollama_embedding_dims(embed_model)
    if isinstance(detected, int) and detected > 0:
        return detected
    if isinstance(fallback_dims, int) and fallback_dims > 0:
        return _clamp_embed_dims(fallback_dims)
    return OLLAMA_EMBED_DIMS


def get_ai_config(db: Session) -> dict:
    """Return current AI config from DB or env defaults. Never returns api_key."""
    row = db.query(AIConfigRow).filter(AIConfigRow.id == 1).first()
    if row:
        provider = getattr(row, "provider", None) or "ollama"
        embed_source = getattr(row, "embed_source", None) or "ollama"
        embed_dims = resolve_embed_dims(embed_source, getattr(row, "embed_dims", None))
        return {
            "provider": provider,
            "openai_llm_model": getattr(row, "openai_llm_model", None) or "gpt-4o-mini",
            "embed_source": embed_source,
            "api_key_set": bool(getattr(row, "openai_api_key", None) and str(row.openai_api_key).strip()),
            "llm_model": row.llm_model or DEFAULT_LLM_MODEL,
            "embed_model": row.embed_model or DEFAULT_EMBED_MODEL,
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
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    embed_dims: int | None = None,
) -> dict:
    """Update AI config in DB. Returns updated config (without api_key)."""
    row = db.query(AIConfigRow).filter(AIConfigRow.id == 1).first()
    if not row:
        row = AIConfigRow(
            id=1,
            provider="ollama",
            embed_source="ollama",
            llm_model=DEFAULT_LLM_MODEL,
            embed_model=DEFAULT_EMBED_MODEL,
            temperature=0.3,
            max_output_tokens=DEFAULT_MAX_TOKENS,
            embed_dims=OLLAMA_EMBED_DIMS,
        )
        db.add(row)
        db.flush()

    previous_embed_source = (getattr(row, "embed_source", None) or "ollama").strip().lower()
    effective_embed_source = previous_embed_source

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
            effective_embed_source = es
    if llm_model is not None:
        row.llm_model = llm_model.strip() or DEFAULT_LLM_MODEL
    if embed_model is not None:
        row.embed_model = embed_model.strip() or DEFAULT_EMBED_MODEL
    if temperature is not None:
        row.temperature = max(0.0, min(1.0, float(temperature)))
    if max_output_tokens is not None:
        row.max_output_tokens = max(512, min(4096, int(max_output_tokens)))
    if effective_embed_source == "openai":
        # Keep dimensions aligned with active OpenAI embedding model in this app.
        row.embed_dims = OPENAI_EMBED_DIMS
    elif effective_embed_source == "ollama":
        previous_was_ollama = previous_embed_source == "ollama"
        fallback_dims = (
            embed_dims
            if embed_dims is not None
            else getattr(row, "embed_dims", None) if previous_was_ollama else OLLAMA_EMBED_DIMS
        )
        desired_dims = resolve_ollama_embed_dims(
            row.embed_model,
            fallback_dims,
        )
        row.embed_dims = desired_dims
    elif embed_dims is not None:
        row.embed_dims = _clamp_embed_dims(embed_dims)
    elif row.embed_dims is None:
        row.embed_dims = OLLAMA_EMBED_DIMS

    db.commit()
    db.refresh(row)
    return get_ai_config(db)


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


def ensure_ollama_model(model: str) -> dict:
    """Ensure Ollama model is available; pull if missing. Returns { status: 'ok' } or { status: 'error', error: '...' }."""
    if not model or not str(model).strip():
        return {"status": "error", "error": "Model name is required"}
    name = str(model).strip()
    if not OLLAMA_URL:
        return {"status": "error", "error": "Ollama URL not configured"}
    try:
        with httpx.Client(timeout=300) as client:
            resp = client.post(
                f"{OLLAMA_URL}/api/pull",
                json={"model": name, "stream": False},
            )
            if resp.status_code != 200:
                return {"status": "error", "error": resp.text or f"HTTP {resp.status_code}"}
            data = resp.json()
            status = data.get("status", "")
            if status == "success":
                return {"status": "ok"}
            return {"status": "error", "error": status or "Pull failed"}
    except httpx.TimeoutException:
        return {"status": "error", "error": "Ollama request timed out"}
    except Exception as e:
        log.debug("Ollama ensure-model failed: %s", e)
        return {"status": "error", "error": str(e)}


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


def list_openai_models() -> dict:
    """Return static list of OpenAI models for UI."""
    return {
        "models": [
            {"name": m, "model": m}
            for m in OPENAI_LLM_MODELS
        ]
    }

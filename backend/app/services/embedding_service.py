"""Embedding service: generate vectors via a self-hosted runtime or OpenAI for RAG."""

import hashlib
import logging
import os
import time
import httpx

EMBED_CACHE_MAX = int(os.environ.get("EMBED_CACHE_MAX", "200") or "200")

from app.services.embedding_profiles import (
    prepare_embedding_input,
    resolve_selected_embed_profile,
)
from app.services.self_hosted_runtime_service import (
    get_self_hosted_embedding_dims,
    is_self_hosted_model_available,
    is_self_hosted_model_ready,
)

log = logging.getLogger(__name__)

EMBED_URL = os.environ.get("LLM_URL", "").rstrip("/")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
EMBED_TIMEOUT = int(os.environ.get("EMBED_TIMEOUT", "120"))
SELF_HOSTED_DOCUMENT_RETRIES = int(
    os.environ.get("SELF_HOSTED_DOCUMENT_EMBED_RETRIES", "2")
)

# nomic-embed-text and bge-base-en:v1.5 both use 768 dims here; text-embedding-3-small is 1536.
EMBED_DIMS = int(os.environ.get("EMBED_DIMS", "768"))
OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_EMBED_DIMS = 1536


def _clean_text(value: str | None) -> str:
    return str(value or "").strip()


def embed_text_openai(text: str, model: str | None = None, api_key: str | None = None) -> list[float] | None:
    """Embed text via OpenAI API. Returns None if unavailable or error."""
    if not api_key or not str(api_key).strip() or not text or not str(text).strip():
        return None
    effective_model = (model or "").strip() or OPENAI_EMBED_MODEL
    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    payload = {"model": effective_model, "input": str(text).strip()[:8000]}
    try:
        with httpx.Client(timeout=EMBED_TIMEOUT) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data") or []
            if items:
                return items[0].get("embedding")
    except httpx.TimeoutException:
        log.warning("OpenAI embedding timed out")
    except httpx.HTTPStatusError as e:
        log.warning("OpenAI embedding API error: %s", e)
    except Exception as e:
        log.warning("OpenAI embedding failed: %s", e)
    return None


def embed_batch_openai(texts: list[str], model: str | None = None, api_key: str | None = None) -> list[list[float]]:
    """Embed multiple texts via OpenAI API."""
    if not api_key or not str(api_key).strip() or not texts:
        return []
    cleaned = [str(t).strip()[:8000] for t in texts if t and str(t).strip()]
    if not cleaned:
        return []
    effective_model = (model or "").strip() or OPENAI_EMBED_MODEL
    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    payload = {"model": effective_model, "input": cleaned}
    try:
        with httpx.Client(timeout=EMBED_TIMEOUT) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            items = sorted((data.get("data") or []), key=lambda x: x.get("index", 0))
            return [item.get("embedding", []) for item in items[: len(cleaned)]]
    except httpx.TimeoutException:
        log.warning("OpenAI batch embedding timed out")
    except httpx.HTTPStatusError as e:
        log.warning("OpenAI batch embedding API error: %s", e)
    except Exception as e:
        log.warning("OpenAI batch embedding failed: %s", e)
    return []


def is_available() -> bool:
    """Return True if the configured self-hosted embedding model is ready."""
    return is_ollama_model_ready(EMBED_MODEL)


def is_ollama_model_available(model: str | None) -> bool:
    """Return True if the requested self-hosted embedding model is installed."""
    return is_self_hosted_model_available((model or "").strip() or EMBED_MODEL)


def is_ollama_model_ready(model: str | None) -> bool:
    """Return True if the requested self-hosted embedding model is ready to serve."""
    return is_self_hosted_model_ready((model or "").strip() or EMBED_MODEL)


def get_ollama_embedding_dims(model: str | None) -> int | None:
    """Resolve embedding dims from runtime metadata first, then fall back to a tiny probe."""
    requested = (model or "").strip() or EMBED_MODEL
    dims = get_self_hosted_embedding_dims(requested)
    if isinstance(dims, int) and dims > 0:
        return dims
    vec = embed_text(
        "dimension probe",
        model=requested,
        ai_config={
            "embed_source": "ollama",
            "embed_profile": resolve_selected_embed_profile("ollama", requested),
        },
        usage="document",
    )
    if not vec:
        return None
    try:
        return len(vec)
    except Exception:
        return None


_embed_cache: dict[str, list[float]] = {}
_embed_cache_keys: list[str] = []


def _embed_cache_key(
    prepared_input: str,
    model: str,
    source: str,
    profile: str,
    usage: str,
) -> str:
    h = hashlib.sha256(
        (prepared_input[:8000] + "|" + model + "|" + source + "|" + profile + "|" + usage).encode()
    ).hexdigest()
    return h


def _embed_cache_get(key: str) -> list[float] | None:
    if key in _embed_cache:
        return _embed_cache[key]
    return None


def _embed_cache_set(key: str, vec: list[float]) -> None:
    global _embed_cache_keys
    if key in _embed_cache:
        return
    while len(_embed_cache) >= EMBED_CACHE_MAX and _embed_cache_keys:
        old = _embed_cache_keys.pop(0)
        _embed_cache.pop(old, None)
    _embed_cache[key] = vec
    _embed_cache_keys.append(key)


def _should_cache_embedding(usage: str) -> bool:
    return usage == "query"


def embed_text(
    text: str,
    model: str | None = None,
    ai_config: dict | None = None,
    *,
    usage: str = "document",
) -> list[float] | None:
    """
    Embed a single text string. Returns None if service unavailable or error.
    When ai_config has embed_source=openai, uses OpenAI API.
    Logs latency for observability. Caches query embeddings for repeated analyses.
    """
    effective_model = (model or "").strip() or ((ai_config or {}).get("embed_model") or EMBED_MODEL)
    embed_source = str((ai_config or {}).get("embed_source") or "ollama").strip().lower() or "ollama"
    embed_profile = resolve_selected_embed_profile(
        embed_source,
        effective_model,
        (ai_config or {}).get("embed_profile"),
    )
    prepared = prepare_embedding_input(
        text,
        embed_source=embed_source,
        embed_model=effective_model,
        embed_profile=embed_profile,
        usage=usage,
    )
    if not prepared:
        return None

    cache_key = None
    if _should_cache_embedding(usage):
        cache_key = _embed_cache_key(
            prepared,
            effective_model,
            embed_source,
            embed_profile,
            usage,
        )
        cached = _embed_cache_get(cache_key)
        if cached is not None:
            log.debug("embed_text cache hit model=%s usage=%s", effective_model, usage)
            return cached

    start = time.perf_counter()
    if ai_config and embed_source == "openai" and ai_config.get("openai_api_key"):
        result = embed_text_openai(
            prepared,
            model=(model or "").strip() or OPENAI_EMBED_MODEL,
            api_key=ai_config["openai_api_key"],
        )
        if result and cache_key is not None:
            log.info("embed_text latency_ms=%d model=openai usage=%s", int((time.perf_counter() - start) * 1000), usage)
            _embed_cache_set(cache_key, result)
        return result
    if not EMBED_URL:
        return None
    effective_model = (model or "").strip() or EMBED_MODEL
    url = f"{EMBED_URL}/api/embed"
    payload = {"model": effective_model, "input": prepared[:8000]}
    try:
        with httpx.Client(timeout=EMBED_TIMEOUT) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embs = data.get("embeddings")
            if embs and len(embs) > 0:
                vec = embs[0]
                latency_ms = int((time.perf_counter() - start) * 1000)
                log.info("embed_text latency_ms=%d model=%s usage=%s", latency_ms, effective_model, usage)
                if cache_key is not None:
                    _embed_cache_set(cache_key, vec)
                return vec
    except httpx.TimeoutException:
        log.warning("Embedding request timed out")
    except httpx.HTTPStatusError as e:
        log.warning("Self-hosted embedding API error: %s", e)
    except Exception as e:
        log.warning("Self-hosted embedding failed: %s", e)
    return None


def embed_batch(
    texts: list[str],
    model: str | None = None,
    ai_config: dict | None = None,
    *,
    usage: str = "document",
) -> list[list[float]]:
    """
    Embed multiple texts. Returns list of vectors.
    When ai_config has embed_source=openai, uses OpenAI API.
    """
    if ai_config and ai_config.get("embed_source") == "openai" and ai_config.get("openai_api_key"):
        return embed_batch_openai(
            texts,
            model=(model or "").strip() or OPENAI_EMBED_MODEL,
            api_key=ai_config["openai_api_key"],
        )
    if not EMBED_URL or not texts:
        return []
    effective_model = (model or "").strip() or EMBED_MODEL
    cleaned = [
        prepared[:8000]
        for text in texts
        if (
            prepared := prepare_embedding_input(
                text,
                embed_source=(ai_config or {}).get("embed_source"),
                embed_model=effective_model,
                embed_profile=(ai_config or {}).get("embed_profile"),
                usage=usage,
            )
        )
    ]
    if not cleaned:
        return []
    url = f"{EMBED_URL}/api/embed"
    payload = {"model": effective_model, "input": cleaned}
    try:
        with httpx.Client(timeout=EMBED_TIMEOUT) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embs = data.get("embeddings") or []
            return embs[: len(cleaned)]
    except httpx.TimeoutException:
        log.warning("Batch embedding timed out")
    except httpx.HTTPStatusError as e:
        log.warning("Self-hosted batch embedding API error: %s", e)
    except Exception as e:
        log.warning("Self-hosted batch embedding failed: %s", e)
    return []


def embed_documents_individually(
    texts: list[str],
    model: str | None = None,
    ai_config: dict | None = None,
    *,
    usage: str = "document",
) -> list[list[float] | None]:
    """Embed one document per self-hosted request to avoid oversized batched inputs."""
    if not texts:
        return []

    attempts = max(1, SELF_HOSTED_DOCUMENT_RETRIES + 1)
    results: list[list[float] | None] = []
    for text in texts:
        vector: list[float] | None = None
        for _ in range(attempts):
            vector = embed_text(
                text,
                model=model,
                ai_config=ai_config,
                usage=usage,
            )
            if vector:
                break
        results.append(vector)
    return results

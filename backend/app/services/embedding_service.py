"""Embedding service: generate vectors via Ollama or OpenAI for RAG."""

import logging
import os

import httpx

log = logging.getLogger(__name__)

EMBED_URL = os.environ.get("LLM_URL", "").rstrip("/")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
EMBED_TIMEOUT = int(os.environ.get("EMBED_TIMEOUT", "120"))

# nomic-embed-text: 768 dims; text-embedding-3-small: 1536 dims
EMBED_DIMS = int(os.environ.get("EMBED_DIMS", "768"))
OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_EMBED_DIMS = 1536


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
    """Return True if embedding service is configured and reachable."""
    if not EMBED_URL:
        return False
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{EMBED_URL}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models") or []
                return any(m.get("name", "").startswith(EMBED_MODEL) for m in models)
    except Exception as e:
        log.debug("Embedding service check failed: %s", e)
    return False


def embed_text(
    text: str,
    model: str | None = None,
    ai_config: dict | None = None,
) -> list[float] | None:
    """
    Embed a single text string. Returns None if service unavailable or error.
    When ai_config has embed_source=openai, uses OpenAI API.
    """
    if ai_config and ai_config.get("embed_source") == "openai" and ai_config.get("openai_api_key"):
        return embed_text_openai(
            text,
            model=(model or "").strip() or OPENAI_EMBED_MODEL,
            api_key=ai_config["openai_api_key"],
        )
    if not EMBED_URL or not text or not str(text).strip():
        return None
    effective_model = (model or "").strip() or EMBED_MODEL
    url = f"{EMBED_URL}/api/embed"
    payload = {"model": effective_model, "input": str(text).strip()[:8000]}
    try:
        with httpx.Client(timeout=EMBED_TIMEOUT) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embs = data.get("embeddings")
            if embs and len(embs) > 0:
                return embs[0]
    except httpx.TimeoutException:
        log.warning("Embedding request timed out")
    except httpx.HTTPStatusError as e:
        log.warning("Embedding API error: %s", e)
    except Exception as e:
        log.warning("Embedding failed: %s", e)
    return None


def embed_batch(
    texts: list[str],
    model: str | None = None,
    ai_config: dict | None = None,
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
    cleaned = [str(t).strip()[:8000] for t in texts if t and str(t).strip()]
    if not cleaned:
        return []
    effective_model = (model or "").strip() or EMBED_MODEL
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
        log.warning("Batch embedding API error: %s", e)
    except Exception as e:
        log.warning("Batch embedding failed: %s", e)
    return []

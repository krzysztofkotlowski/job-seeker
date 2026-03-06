"""Embedding service: generate vectors via Ollama /api/embed for RAG."""

import logging
import os

import httpx

log = logging.getLogger(__name__)

EMBED_URL = os.environ.get("LLM_URL", "").rstrip("/")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
EMBED_TIMEOUT = int(os.environ.get("EMBED_TIMEOUT", "120"))

# nomic-embed-text: 768 dims; all-minilm: 384 dims
EMBED_DIMS = int(os.environ.get("EMBED_DIMS", "768"))


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


def embed_text(text: str) -> list[float] | None:
    """
    Embed a single text string. Returns None if service unavailable or error.
    """
    if not EMBED_URL or not text or not str(text).strip():
        return None
    url = f"{EMBED_URL}/api/embed"
    payload = {"model": EMBED_MODEL, "input": str(text).strip()[:8000]}
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


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed multiple texts in one request. Returns list of vectors (or None for failed items).
    Ollama accepts array input for batch embedding.
    """
    if not EMBED_URL or not texts:
        return []
    cleaned = [str(t).strip()[:8000] for t in texts if t and str(t).strip()]
    if not cleaned:
        return []
    url = f"{EMBED_URL}/api/embed"
    payload = {"model": EMBED_MODEL, "input": cleaned}
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

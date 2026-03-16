"""Cross-encoder re-ranking for RAG. Optional: requires sentence-transformers."""

import logging

log = logging.getLogger(__name__)

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANK_TOP_K = 10
RERANK_CANDIDATES = 30

_model = None


def _get_reranker():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import CrossEncoder

        _model = CrossEncoder(RERANKER_MODEL)
        log.info("Loaded cross-encoder reranker: %s", RERANKER_MODEL)
        return _model
    except ImportError as e:
        log.debug("sentence-transformers not installed, reranking disabled: %s", e)
        return None
    except Exception as e:
        log.warning("Failed to load reranker: %s", e)
        return None


def _job_to_text_for_rerank(hit: dict) -> str:
    """Build text representation of a job hit for reranking."""
    parts = [
        hit.get("title") or "",
        hit.get("company") or "",
        hit.get("category") or "",
    ]
    skills = hit.get("skills_combined") or ""
    if isinstance(skills, list):
        skills = " ".join(str(s) for s in skills)
    if skills:
        parts.append(str(skills))
    desc = hit.get("description") or ""
    if desc:
        parts.append(str(desc)[:500])
    return " ".join(p for p in parts if p).strip() or "unknown"


def rerank_hits(
    query_text: str,
    hits: list[dict],
    top_k: int = RERANK_TOP_K,
    job_text_fn=None,
) -> list[dict]:
    """
    Re-rank hits using a cross-encoder. Returns top_k hits sorted by relevance.
    If reranker is unavailable, returns original hits[:top_k].
    """
    if not hits or not (query_text or "").strip():
        return hits[:top_k]
    encoder = _get_reranker()
    if encoder is None:
        return hits[:top_k]
    text_fn = job_text_fn or _job_to_text_for_rerank
    pairs = [(query_text.strip(), text_fn(h)) for h in hits]
    try:
        scores = encoder.predict(pairs)
    except Exception as e:
        log.warning("Reranker predict failed: %s", e)
        return hits[:top_k]
    if len(scores) != len(hits):
        return hits[:top_k]
    scored = list(zip(scores, hits))
    scored.sort(key=lambda x: float(x[0]), reverse=True)
    out = []
    for _, h in scored[:top_k]:
        out.append(dict(h))
    return out

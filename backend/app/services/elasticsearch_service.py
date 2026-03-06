"""Elasticsearch service: vector index for job semantic search."""

import logging
import os
import threading
from typing import TYPE_CHECKING, Callable

from elasticsearch import Elasticsearch

_sync_lock = threading.Lock()
_sync_in_progress = False


def set_sync_in_progress(value: bool) -> None:
    global _sync_in_progress
    with _sync_lock:
        _sync_in_progress = value


def is_sync_in_progress() -> bool:
    with _sync_lock:
        return _sync_in_progress

from app.services.embedding_service import EMBED_DIMS, embed_batch, embed_text

if TYPE_CHECKING:
    from app.models.tables import JobRow

log = logging.getLogger(__name__)

ES_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200").rstrip("/")
ES_TIMEOUT = int(os.environ.get("ES_TIMEOUT", "30"))
JOBS_INDEX = "jobseeker_jobs"


def _get_client() -> Elasticsearch | None:
    if not ES_URL:
        return None
    try:
        return Elasticsearch(
            ES_URL,
            request_timeout=ES_TIMEOUT,
        )
    except Exception as e:
        log.debug("Elasticsearch client init failed: %s", e)
        return None


def is_available() -> bool:
    """Return True if Elasticsearch is reachable."""
    client = _get_client()
    if not client:
        return False
    try:
        return client.ping()
    except Exception as e:
        log.warning("Elasticsearch ping failed (url=%s): %s", ES_URL, e)
        return False


def _job_to_text(job: "JobRow") -> str:
    """Build searchable text from job for embedding."""
    parts = [
        job.title or "",
        job.company or "",
        job.category or "",
        " ".join(job.skills_required or []),
        " ".join(job.skills_nice_to_have or []),
    ]
    desc = (job.description or "")[:2000]
    if desc:
        parts.append(desc)
    return " ".join(p for p in parts if p).strip() or "unknown"


def ensure_index(client: Elasticsearch) -> bool:
    """Create index with dense_vector mapping if not exists."""
    try:
        if client.indices.exists(index=JOBS_INDEX):
            return True
        client.indices.create(
            index=JOBS_INDEX,
            mappings={
                "properties": {
                        "job_id": {"type": "keyword"},
                        "title": {"type": "text"},
                        "company": {"type": "keyword"},
                        "title_keyword": {"type": "keyword"},
                        "company_keyword": {"type": "keyword"},
                        "category": {"type": "keyword"},
                        "url": {"type": "keyword"},
                        "skills_combined": {"type": "text"},
                        "description": {"type": "text"},
                        "embedding": {
                            "type": "dense_vector",
                            "dims": EMBED_DIMS,
                            "index": True,
                            "similarity": "cosine",
                        },
                    }
            },
        )
        log.info("Created Elasticsearch index %s", JOBS_INDEX)
        return True
    except Exception as e:
        log.warning("Failed to create index %s: %s", JOBS_INDEX, e)
        return False


def index_job(job: "JobRow", embedding: list[float] | None = None) -> bool:
    """Index a single job. Generates embedding if not provided."""
    client = _get_client()
    if not client:
        return False
    if not ensure_index(client):
        return False
    text = _job_to_text(job)
    if embedding is None:
        embedding = embed_text(text)
    if not embedding or len(embedding) != EMBED_DIMS:
        return False
    try:
        doc = {
            "job_id": str(job.id),
            "title": job.title or "",
            "company": job.company or "",
            "title_keyword": job.title or "",
            "company_keyword": job.company or "",
            "category": job.category or "",
            "url": job.url or "",
            "skills_combined": " ".join((job.skills_required or []) + (job.skills_nice_to_have or [])),
            "description": (job.description or "")[:5000],
            "embedding": embedding,
        }
        client.index(index=JOBS_INDEX, id=str(job.id), document=doc)
        return True
    except Exception as e:
        log.warning("Failed to index job %s: %s", job.id, e)
        return False


BULK_BATCH_SIZE = 15


def bulk_index_jobs(jobs: list["JobRow"]) -> int:
    """Batch embed and index jobs. Returns count of successfully indexed."""
    set_sync_in_progress(True)
    try:
        return bulk_index_jobs_with_progress(jobs, on_progress=None)
    finally:
        set_sync_in_progress(False)


def bulk_index_jobs_with_progress(
    jobs: list["JobRow"],
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """Batch embed and index jobs, optionally calling on_progress(indexed, total) after each batch."""
    if not jobs:
        return 0
    client = _get_client()
    if not client:
        return 0
    if not ensure_index(client):
        return 0
    total = len(jobs)
    indexed = 0
    for i in range(0, total, BULK_BATCH_SIZE):
        batch = jobs[i : i + BULK_BATCH_SIZE]
        texts = [_job_to_text(j) for j in batch]
        embeddings = embed_batch(texts)
        if len(embeddings) != len(batch):
            log.warning("Embedding count mismatch: got %d, expected %d", len(embeddings), len(batch))
            embeddings = embeddings[: len(batch)]
        for job, emb in zip(batch, embeddings):
            if not emb or len(emb) != EMBED_DIMS:
                continue
            try:
                doc = {
                    "job_id": str(job.id),
                    "title": job.title or "",
                    "company": job.company or "",
                    "title_keyword": job.title or "",
                    "company_keyword": job.company or "",
                    "category": job.category or "",
                    "url": job.url or "",
                    "skills_combined": " ".join((job.skills_required or []) + (job.skills_nice_to_have or [])),
                    "description": (job.description or "")[:5000],
                    "embedding": emb,
                }
                client.index(index=JOBS_INDEX, id=str(job.id), document=doc)
                indexed += 1
            except Exception as e:
                log.warning("Failed to index job %s: %s", job.id, e)
        if on_progress:
            on_progress(indexed, total)
    return indexed


def bulk_index_jobs_stream(jobs: list["JobRow"]):
    """
    Generator that indexes jobs in batches and yields progress events.
    Yields {"indexed": N, "total": M} during run, then {"done": True, "indexed": N, "total": M}.
    """
    set_sync_in_progress(True)
    try:
        if not jobs:
            yield {"done": True, "indexed": 0, "total": 0}
            return
        client = _get_client()
        if not client:
            yield {"done": True, "indexed": 0, "total": 0}
            return
        if not ensure_index(client):
            yield {"done": True, "indexed": 0, "total": 0}
            return
        total = len(jobs)
        indexed = 0
        for i in range(0, total, BULK_BATCH_SIZE):
            batch = jobs[i : i + BULK_BATCH_SIZE]
            texts = [_job_to_text(j) for j in batch]
            embeddings = embed_batch(texts)
            if len(embeddings) != len(batch):
                log.warning("Embedding count mismatch: got %d, expected %d", len(embeddings), len(batch))
                embeddings = embeddings[: len(batch)]
            for job, emb in zip(batch, embeddings):
                if not emb or len(emb) != EMBED_DIMS:
                    continue
                try:
                    doc = {
                        "job_id": str(job.id),
                        "title": job.title or "",
                        "company": job.company or "",
                        "title_keyword": job.title or "",
                        "company_keyword": job.company or "",
                        "category": job.category or "",
                        "url": job.url or "",
                        "skills_combined": " ".join((job.skills_required or []) + (job.skills_nice_to_have or [])),
                        "description": (job.description or "")[:5000],
                        "embedding": emb,
                    }
                    client.index(index=JOBS_INDEX, id=str(job.id), document=doc)
                    indexed += 1
                except Exception as e:
                    log.warning("Failed to index job %s: %s", job.id, e)
            yield {"indexed": indexed, "total": total}
        yield {"done": True, "indexed": indexed, "total": total}
    finally:
        set_sync_in_progress(False)


def search_keyword(
    query_text: str,
    top_k: int = 10,
) -> list[dict]:
    """
    Keyword search (multi_match) only. No kNN, no RRF. Works with free ES license.
    Returns list of dicts with job_id, title, company, url, category, score.
    """
    client = _get_client()
    if not client or not (query_text or "").strip():
        return []
    try:
        resp = client.search(
            index=JOBS_INDEX,
            query={
                "multi_match": {
                    "query": query_text.strip(),
                    "fields": ["title^2", "company", "skills_combined^1.5", "description"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            _source=["job_id", "title", "company", "url", "category"],
            size=top_k,
        )
        hits = resp.get("hits", {}).get("hits", [])
        out = []
        for h in hits:
            src = h.get("_source", {})
            score = h.get("_score", 0)
            out.append({
                "job_id": src.get("job_id"),
                "title": src.get("title", ""),
                "company": src.get("company", ""),
                "url": src.get("url", ""),
                "category": src.get("category", ""),
                "score": float(score),
            })
        return out
    except Exception as e:
        log.warning("Keyword search failed: %s", e)
        return []


def _merge_rrf(
    hits_a: list[dict],
    hits_b: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Merge two hit lists using Reciprocal Rank Fusion. Dedupes by job_id.
    RRF score = 1/(k+rank_a) + 1/(k+rank_b). Missing rank uses k+len+1.
    """
    def _job_id(h: dict) -> str | None:
        j = h.get("job_id")
        return str(j) if j is not None else None

    rank_a: dict[str, int] = {}
    rank_b: dict[str, int] = {}
    doc_a: dict[str, dict] = {}
    doc_b: dict[str, dict] = {}

    for i, h in enumerate(hits_a):
        jid = _job_id(h)
        if jid and jid not in rank_a:
            rank_a[jid] = i + 1
            doc_a[jid] = h

    for i, h in enumerate(hits_b):
        jid = _job_id(h)
        if jid and jid not in rank_b:
            rank_b[jid] = i + 1
            doc_b[jid] = h

    all_ids = set(rank_a) | set(rank_b)
    max_rank = max(len(hits_a), len(hits_b), 1) + 1

    scored: list[tuple[float, dict]] = []
    for jid in all_ids:
        r_a = rank_a.get(jid, max_rank)
        r_b = rank_b.get(jid, max_rank)
        rrf_score = 1.0 / (k + r_a) + 1.0 / (k + r_b)
        doc = doc_a.get(jid) or doc_b.get(jid)
        if doc:
            doc = dict(doc)
            doc["score"] = rrf_score
            scored.append((rrf_score, doc))

    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored]


def search_similar(
    query_embedding: list[float],
    top_k: int = 10,
) -> list[dict]:
    """
    kNN search for similar jobs. Returns list of dicts with job_id, title, company, url, score.
    """
    client = _get_client()
    if not client or not query_embedding:
        return []
    try:
        resp = client.search(
            index=JOBS_INDEX,
            knn={
                "field": "embedding",
                "query_vector": query_embedding,
                "k": top_k,
                "num_candidates": top_k * 2,
            },
            _source=["job_id", "title", "company", "url", "category"],
            size=top_k,
        )
        hits = resp.get("hits", {}).get("hits", [])
        out = []
        for h in hits:
            src = h.get("_source", {})
            score = h.get("_score", 0)
            out.append({
                "job_id": src.get("job_id"),
                "title": src.get("title", ""),
                "company": src.get("company", ""),
                "url": src.get("url", ""),
                "category": src.get("category", ""),
                "score": float(score),
            })
        return out
    except Exception as e:
        log.warning("kNN search failed: %s", e)
        return []


def search_hybrid(
    query_text: str,
    query_embedding: list[float],
    top_k: int = 10,
) -> list[dict]:
    """
    Hybrid search: combines keyword (multi_match) and kNN vector search.
    Uses Python-side RRF merge to avoid Elasticsearch paid license requirement.
    Returns list of dicts with job_id, title, company, url, category, score.
    """
    if not query_embedding:
        return []
    query_text = (query_text or "").strip()
    if not query_text:
        return search_similar(query_embedding, top_k)

    # Run both searches (no ES RRF - works with free license)
    keyword_hits = search_keyword(query_text, top_k=top_k * 2)
    knn_hits = search_similar(query_embedding, top_k=top_k * 2)

    if not keyword_hits and not knn_hits:
        return []
    if not keyword_hits:
        return knn_hits[:top_k]
    if not knn_hits:
        return keyword_hits[:top_k]

    merged = _merge_rrf(keyword_hits, knn_hits, k=60)
    return merged[:top_k]

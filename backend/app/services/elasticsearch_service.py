"""Elasticsearch service: vector index for job semantic search."""

import logging
import os
from typing import TYPE_CHECKING, Callable

from elasticsearch import Elasticsearch
try:
    from elasticsearch import helpers as es_helpers
except Exception:  # pragma: no cover - optional in some test environments
    es_helpers = None

from app.services.embedding_service import EMBED_DIMS, embed_batch, embed_text

if TYPE_CHECKING:
    from app.models.tables import JobRow

log = logging.getLogger(__name__)

ES_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200").rstrip("/")
ES_TIMEOUT = int(os.environ.get("ES_TIMEOUT", "30"))
JOBS_INDEX = "jobseeker_jobs"
JOBS_INDEX_ALIAS = f"{JOBS_INDEX}_active"
MANAGED_INDEX_PREFIX = f"{JOBS_INDEX}_run"
BULK_BATCH_SIZE = int(os.environ.get("EMBED_BULK_BATCH_SIZE", "8"))
ES_BULK_CHUNK_SIZE = int(os.environ.get("ES_BULK_CHUNK_SIZE", "500"))
ES_INDEX_REPLICAS = int(os.environ.get("ES_INDEX_REPLICAS", "0"))


def _index_for_dims(embed_dims: int | None) -> str:
    """Index name for given embedding dimensions. 768 uses default; others use suffix."""
    dims = embed_dims or EMBED_DIMS
    return JOBS_INDEX if dims == 768 else f"{JOBS_INDEX}_{dims}"


def managed_index_name(run_id: str) -> str:
    """Managed physical index name for a given sync run."""
    return f"{MANAGED_INDEX_PREFIX}_{str(run_id).replace('-', '')}"


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


def ensure_index(
    client: Elasticsearch,
    embed_dims: int | None = None,
    index_name: str | None = None,
) -> bool:
    """Create index with dense_vector mapping if not exists."""
    dims = embed_dims or EMBED_DIMS
    target_index = index_name or _index_for_dims(dims)
    try:
        if client.indices.exists(index=target_index):
            return True
        client.indices.create(
            index=target_index,
            settings={
                "index": {
                    # Single-node default for faster writes and fewer yellow-health surprises.
                    "number_of_replicas": ES_INDEX_REPLICAS,
                }
            },
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
                        "dims": dims,
                        "index": True,
                        "similarity": "cosine",
                    },
                }
            },
        )
        log.info("Created Elasticsearch index %s (dims=%d)", target_index, dims)
        return True
    except Exception as e:
        log.warning("Failed to create index %s: %s", target_index, e)
        return False


def clear_index(embed_dims: int | None = None, index_name: str | None = None) -> bool:
    """Delete the jobs index. Next ensure_index will recreate it. Returns True on success."""
    client = _get_client()
    if not client:
        return False
    target_index = index_name or _index_for_dims(embed_dims)
    try:
        if client.indices.exists(index=target_index):
            client.indices.delete(index=target_index)
            log.info("Deleted Elasticsearch index %s", target_index)
        return True
    except Exception as e:
        log.warning("Failed to clear index %s: %s", target_index, e)
        return False


def get_missing_job_ids(job_ids: list[str], index_name: str) -> list[str]:
    """Return job ids missing from the given index/alias."""
    client = _get_client()
    if not client:
        return []
    try:
        if not client.indices.exists(index=index_name):
            return list(job_ids)
    except Exception as e:
        log.warning("Failed to check index existence for %s: %s", index_name, e)
        return []

    indexed_ids: set[str] = set()
    batch_size = 500
    for i in range(0, len(job_ids), batch_size):
        batch = job_ids[i : i + batch_size]
        try:
            resp = client.mget(index=index_name, ids=batch)
            for doc in resp.get("docs", []):
                if doc.get("found"):
                    indexed_ids.add(doc["_id"])
        except Exception as e:
            log.warning("mget failed for batch on %s: %s", index_name, e)
            return []
    return [job_id for job_id in job_ids if job_id not in indexed_ids]


def get_jobs_not_indexed(
    jobs: list["JobRow"],
    embed_dims: int | None = None,
    index_name: str | None = None,
) -> list["JobRow"]:
    """Return jobs that are not yet in the Elasticsearch index."""
    target_index = index_name or _index_for_dims(embed_dims)
    missing_ids = set(get_missing_job_ids([str(j.id) for j in jobs], target_index))
    return [j for j in jobs if str(j.id) in missing_ids]


def list_job_index_dims() -> list[int]:
    """
    Return embedding dimensions for existing job indices (e.g. jobseeker_jobs, jobseeker_jobs_1536).
    Useful for safe fallback searches after model/provider switches.
    """
    client = _get_client()
    if not client:
        return []
    try:
        idx_info = client.indices.get(index=f"{JOBS_INDEX}*")
    except Exception:
        return []

    dims: set[int] = set()
    for name in idx_info.keys():
        if name == JOBS_INDEX:
            dims.add(768)
            continue
        prefix = f"{JOBS_INDEX}_"
        if name.startswith(prefix):
            suffix = name[len(prefix):]
            try:
                dims.add(int(suffix))
            except ValueError:
                continue
    return sorted(dims)


def list_job_indices() -> list[str]:
    """Return all job-related indices and aliases known to Elasticsearch."""
    client = _get_client()
    if not client:
        return []
    try:
        idx_info = client.indices.get(index=f"{JOBS_INDEX}*")
    except Exception:
        return []
    return sorted(idx_info.keys())


def list_legacy_job_indices() -> list[str]:
    """Return job indices that are not managed run indices or the active alias."""
    legacy: list[str] = []
    for name in list_job_indices():
        if name == JOBS_INDEX_ALIAS:
            continue
        if name.startswith(f"{MANAGED_INDEX_PREFIX}_"):
            continue
        legacy.append(name)
    return legacy


def count_documents(index_name: str) -> int:
    """Return document count for an index or alias, or 0 when unavailable."""
    client = _get_client()
    if not client:
        return 0
    try:
        return int(client.count(index=index_name).get("count", 0))
    except Exception as e:
        log.warning("Failed to count documents in %s: %s", index_name, e)
        return 0


def get_alias_targets(alias_name: str) -> list[str]:
    """Return indices currently behind the alias."""
    client = _get_client()
    if not client:
        return []
    try:
        alias_info = client.indices.get_alias(name=alias_name)
    except Exception:
        return []
    return sorted(alias_info.keys())


def activate_alias(alias_name: str, target_index: str) -> bool:
    """Atomically repoint alias to the given managed index."""
    client = _get_client()
    if not client:
        return False
    try:
        actions = [{"remove": {"index": idx, "alias": alias_name}} for idx in get_alias_targets(alias_name)]
        actions.append({"add": {"index": target_index, "alias": alias_name}})
        client.indices.update_aliases(actions=actions)
        return True
    except Exception as e:
        log.warning("Failed to activate alias %s -> %s: %s", alias_name, target_index, e)
        return False


def _job_to_doc(job: "JobRow", embedding: list[float]) -> dict:
    """Convert DB row + embedding vector into Elasticsearch document."""
    return {
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


def _index_docs(client: Elasticsearch, index_name: str, docs: list[dict]) -> int:
    """Index docs using Elasticsearch bulk API, falling back to single-doc indexing."""
    if not docs:
        return 0

    if es_helpers is not None and isinstance(client, Elasticsearch):
        actions = [
            {
                "_op_type": "index",
                "_index": index_name,
                "_id": doc["job_id"],
                "_source": doc,
            }
            for doc in docs
        ]
        try:
            bulk_result = es_helpers.bulk(
                client,
                actions,
                stats_only=True,
                raise_on_error=False,
                raise_on_exception=False,
                chunk_size=ES_BULK_CHUNK_SIZE,
                request_timeout=ES_TIMEOUT,
                refresh=False,
            )
            success = int(bulk_result[0]) if isinstance(bulk_result, tuple) else int(bulk_result)
            bulk_errors = bulk_result[1] if isinstance(bulk_result, tuple) and len(bulk_result) > 1 else 0
            error_count = bulk_errors if isinstance(bulk_errors, int) else len(bulk_errors or [])
            if error_count:
                log.warning(
                    "Bulk index partial failures: success=%d, errors=%d (index=%s)",
                    success,
                    error_count,
                    index_name,
                )
            return success
        except Exception as e:
            log.warning("Bulk index failed (index=%s), falling back to per-doc indexing: %s", index_name, e)

    indexed = 0
    for doc in docs:
        try:
            client.index(index=index_name, id=doc["job_id"], document=doc)
            indexed += 1
        except Exception as e:
            log.warning("Failed to index job %s: %s", doc.get("job_id"), e)
    return indexed


def _refresh_index(client: Elasticsearch, index_name: str) -> None:
    """Refresh index after bulk sync to make docs searchable immediately."""
    try:
        client.indices.refresh(index=index_name)
    except Exception as e:
        log.debug("Index refresh skipped/failed for %s: %s", index_name, e)


def index_job(
    job: "JobRow",
    embedding: list[float] | None = None,
    embed_model: str | None = None,
    ai_config: dict | None = None,
) -> bool:
    """Index a single job. Generates embedding if not provided."""
    client = _get_client()
    if not client:
        return False
    embed_dims = (ai_config or {}).get("embed_dims") or EMBED_DIMS
    if not ensure_index(client, embed_dims=embed_dims):
        return False
    text = _job_to_text(job)
    if embedding is None:
        embedding = embed_text(text, model=embed_model, ai_config=ai_config, usage="document")
    if not embedding or len(embedding) != embed_dims:
        return False
    index_name = _index_for_dims(embed_dims)
    try:
        doc = _job_to_doc(job, embedding)
        client.index(index=index_name, id=str(job.id), document=doc)
        return True
    except Exception as e:
        log.warning("Failed to index job %s: %s", job.id, e)
        return False


def bulk_index_jobs(jobs: list["JobRow"], embed_model: str | None = None, ai_config: dict | None = None) -> int:
    """Batch embed and index jobs. Returns count of successfully indexed."""
    return bulk_index_jobs_with_progress(jobs, on_progress=None, embed_model=embed_model, ai_config=ai_config)


def bulk_index_jobs_with_progress(
    jobs: list["JobRow"],
    on_progress: Callable[[int, int], None] | None = None,
    embed_model: str | None = None,
    ai_config: dict | None = None,
) -> int:
    """Batch embed and index jobs, optionally calling on_progress(indexed, total) after each batch."""
    if not jobs:
        return 0
    client = _get_client()
    if not client:
        return 0
    config_dims = (ai_config or {}).get("embed_dims") or EMBED_DIMS
    total = len(jobs)
    indexed = 0
    effective_dims: int | None = None
    for i in range(0, total, BULK_BATCH_SIZE):
        batch = jobs[i : i + BULK_BATCH_SIZE]
        texts = [_job_to_text(j) for j in batch]
        embeddings = embed_batch(texts, model=embed_model, ai_config=ai_config, usage="document")
        if len(embeddings) != len(batch):
            log.warning("Embedding count mismatch: got %d, expected %d", len(embeddings), len(batch))
            embeddings = embeddings[: len(batch)]
        if effective_dims is None and embeddings:
            first_emb = next((e for e in embeddings if e and len(e) > 0), None)
            if first_emb:
                effective_dims = len(first_emb)
                if effective_dims != config_dims:
                    log.warning(
                        "Embed dims mismatch: config=%d, actual=%d. Using actual for index.",
                        config_dims,
                        effective_dims,
                    )
                if not ensure_index(client, embed_dims=effective_dims):
                    return indexed
        if effective_dims is None:
            continue
        index_name = _index_for_dims(effective_dims)
        batch_docs: list[dict] = []
        for job, emb in zip(batch, embeddings):
            if not emb or len(emb) != effective_dims:
                continue
            batch_docs.append(_job_to_doc(job, emb))
        indexed += _index_docs(client, index_name, batch_docs)
        if on_progress:
            on_progress(indexed, total)
    if effective_dims is not None:
        _refresh_index(client, _index_for_dims(effective_dims))
    return indexed


def bulk_index_jobs_stream(jobs: list["JobRow"], embed_model: str | None = None, ai_config: dict | None = None):
    """
    Generator that indexes jobs in batches and yields progress events.
    Yields {"indexed": N, "total": M} during run, then {"done": True, "indexed": N, "total": M}.
    """
    if not jobs:
        yield {"done": True, "indexed": 0, "total": 0}
        return
    total = len(jobs)
    indexed = 0
    for progress in iter_index_job_batches(
        jobs,
        index_name=None,
        embed_model=embed_model,
        ai_config=ai_config,
    ):
        indexed = int(progress["indexed"])
        yield {"indexed": indexed, "total": total}
    yield {"done": True, "indexed": indexed, "total": total}


def iter_index_job_batches(
    jobs: list["JobRow"],
    index_name: str | None,
    embed_model: str | None = None,
    ai_config: dict | None = None,
):
    """
    Yield batch progress while indexing jobs into an explicit index.
    Progress dict keys: processed, indexed, failed, total, index_name.
    """
    if not jobs:
        return
    client = _get_client()
    if not client:
        return

    config_dims = (ai_config or {}).get("embed_dims") or EMBED_DIMS
    target_index = index_name or _index_for_dims(config_dims)
    if not ensure_index(client, embed_dims=config_dims, index_name=target_index):
        return

    total = len(jobs)
    processed = 0
    indexed = 0
    failed = 0
    dims_verified = False

    for i in range(0, total, BULK_BATCH_SIZE):
        batch = jobs[i : i + BULK_BATCH_SIZE]
        texts = [_job_to_text(j) for j in batch]
        embeddings = embed_batch(texts, model=embed_model, ai_config=ai_config, usage="document")
        aligned_embeddings = list(embeddings[: len(batch)])
        if len(aligned_embeddings) < len(batch):
            aligned_embeddings.extend([None] * (len(batch) - len(aligned_embeddings)))

        if not dims_verified:
            first_emb = next((e for e in aligned_embeddings if e and len(e) > 0), None)
            if first_emb and len(first_emb) != config_dims:
                raise ValueError(
                    f"Embedding model returned dims={len(first_emb)} but run expected dims={config_dims}"
                )
            dims_verified = True

        batch_docs: list[dict] = []
        invalid_docs = 0
        for job, emb in zip(batch, aligned_embeddings):
            if not emb or len(emb) != config_dims:
                invalid_docs += 1
                continue
            batch_docs.append(_job_to_doc(job, emb))

        success = _index_docs(client, target_index, batch_docs)
        processed += len(batch)
        indexed += success
        failed += invalid_docs + max(0, len(batch_docs) - success)

        yield {
            "processed": processed,
            "indexed": indexed,
            "failed": failed,
            "total": total,
            "index_name": target_index,
        }

    _refresh_index(client, target_index)


def search_keyword(
    query_text: str,
    top_k: int = 10,
    embed_dims: int | None = None,
    index_name: str | None = None,
) -> list[dict]:
    """
    Keyword search (multi_match) only. No kNN, no RRF. Works with free ES license.
    Returns list of dicts with job_id, title, company, url, category, score.
    """
    client = _get_client()
    if not client or not (query_text or "").strip():
        return []
    target_index = index_name or _index_for_dims(embed_dims)
    try:
        resp = client.search(
            index=target_index,
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
        if not hits:
            log.debug("Keyword search returned no hits (index=%s, query_len=%d)", target_index, len(query_text.strip()))
        out = []
        for idx, h in enumerate(hits, start=1):
            src = h.get("_source", {})
            score = h.get("_score", 0)
            out.append({
                "job_id": src.get("job_id"),
                "title": src.get("title", ""),
                "company": src.get("company", ""),
                "url": src.get("url", ""),
                "category": src.get("category", ""),
                "score": float(score),
                "keyword_score": float(score),
                "keyword_rank": idx,
                "sources": {"keyword": True, "semantic": False},
            })
        return out
    except Exception as e:
        log.warning("Keyword search failed (index=%s): %s", target_index, e, exc_info=True)
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
            doc["keyword_score"] = doc_a.get(jid, {}).get("keyword_score")
            doc["semantic_score"] = doc_b.get(jid, {}).get("semantic_score")
            doc["keyword_rank"] = rank_a.get(jid)
            doc["semantic_rank"] = rank_b.get(jid)
            doc["sources"] = {
                "keyword": jid in rank_a,
                "semantic": jid in rank_b,
            }
            scored.append((rrf_score, doc))

    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored]


def search_similar(
    query_embedding: list[float],
    top_k: int = 10,
    embed_dims: int | None = None,
    index_name: str | None = None,
) -> list[dict]:
    """
    kNN search for similar jobs. Returns list of dicts with job_id, title, company, url, score.
    """
    client = _get_client()
    if not client or not query_embedding:
        return []
    target_index = index_name or _index_for_dims(embed_dims)
    try:
        resp = client.search(
            index=target_index,
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
        if not hits:
            log.debug("kNN search returned no hits (index=%s, embedding_dims=%d)", target_index, len(query_embedding))
        out = []
        for idx, h in enumerate(hits, start=1):
            src = h.get("_source", {})
            score = h.get("_score", 0)
            out.append({
                "job_id": src.get("job_id"),
                "title": src.get("title", ""),
                "company": src.get("company", ""),
                "url": src.get("url", ""),
                "category": src.get("category", ""),
                "score": float(score),
                "semantic_score": float(score),
                "semantic_rank": idx,
                "sources": {"keyword": False, "semantic": True},
            })
        return out
    except Exception as e:
        log.warning("kNN search failed (index=%s): %s", target_index, e, exc_info=True)
        return []


def search_hybrid(
    query_text: str,
    query_embedding: list[float],
    top_k: int = 10,
    embed_dims: int | None = None,
    index_name: str | None = None,
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
        return search_similar(query_embedding, top_k, embed_dims=embed_dims, index_name=index_name)

    # Run both searches (no ES RRF - works with free license)
    target_index = index_name or _index_for_dims(embed_dims)
    keyword_hits = search_keyword(query_text, top_k=top_k * 2, embed_dims=embed_dims, index_name=target_index)
    knn_hits = search_similar(query_embedding, top_k=top_k * 2, embed_dims=embed_dims, index_name=target_index)

    log.info(
        "Hybrid search: keyword_hits=%d, knn_hits=%d (index=%s, embed_dims=%s)",
        len(keyword_hits),
        len(knn_hits),
        target_index,
        embed_dims,
    )

    if not keyword_hits and not knn_hits:
        return []
    if not keyword_hits:
        return knn_hits[:top_k]
    if not knn_hits:
        return keyword_hits[:top_k]

    merged = _merge_rrf(keyword_hits, knn_hits, k=60)
    result = merged[:top_k]
    log.info("Hybrid search: merged=%d, returning top_k=%d", len(merged), len(result))
    return result

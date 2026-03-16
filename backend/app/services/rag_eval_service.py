"""RAG evaluation: recall@k and metrics for retrieval quality."""

import logging
import time
from typing import Callable

log = logging.getLogger(__name__)


def recall_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int | None = None) -> float:
    """
    Compute recall@k: fraction of gold items found in top-k retrieved.
    If k is None, uses all retrieved.
    """
    if not gold_ids:
        return 1.0
    top = retrieved_ids[:k] if k is not None else retrieved_ids
    top_set = set(str(x) for x in top)
    hits = len(gold_ids & top_set)
    return hits / len(gold_ids)


def evaluate_retrieval(
    query_text: str,
    gold_job_ids: set[str],
    retrieve_fn: Callable[[str, int], list[dict]],
    k_values: list[int] | None = None,
) -> dict:
    """
    Evaluate retrieval with recall@k for given k values.
    retrieve_fn(query_text, top_k) -> list of dicts with job_id.
    """
    k_values = k_values or [5, 10, 20]
    max_k = max(k_values)
    start = time.perf_counter()
    hits = retrieve_fn(query_text, max_k)
    latency_ms = int((time.perf_counter() - start) * 1000)
    retrieved_ids = [str(h.get("job_id", "")) for h in hits if h.get("job_id")]
    results = {f"recall@{k}": recall_at_k(retrieved_ids, gold_job_ids, k) for k in k_values}
    results["latency_ms"] = latency_ms
    results["retrieved_count"] = len(retrieved_ids)
    log.info(
        "RAG eval: recall@10=%.2f latency=%dms retrieved=%d",
        results.get("recall@10", 0),
        latency_ms,
        len(retrieved_ids),
    )
    return results

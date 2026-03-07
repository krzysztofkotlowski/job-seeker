"""Inference logging and metrics for LLM calls."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.tables import InferenceLogRow

log = logging.getLogger(__name__)


def log_inference(
    db: Session,
    *,
    model: str,
    operation: str,
    latency_ms: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    user_id: int | None = None,
) -> None:
    """Append an inference log entry."""
    try:
        row = InferenceLogRow(
            model=model,
            operation=operation,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            user_id=user_id,
        )
        db.add(row)
        db.commit()
    except Exception as e:
        log.debug("Failed to log inference: %s", e)
        db.rollback()


def get_metrics(db: Session, days: int = 7) -> dict:
    """Aggregate inference metrics for the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        by_model = (
            db.query(
                InferenceLogRow.model,
                func.count(InferenceLogRow.id).label("count"),
                func.avg(InferenceLogRow.latency_ms).label("avg_latency"),
                func.coalesce(func.sum(InferenceLogRow.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(InferenceLogRow.output_tokens), 0).label("output_tokens"),
            )
            .filter(InferenceLogRow.created_at >= since)
            .group_by(InferenceLogRow.model)
            .all()
        )
    except Exception as e:
        log.debug("Failed to get inference metrics: %s", e)
        return {
            "avg_latency_ms": None,
            "total_requests": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "by_model": [],
            "last_7_days": True,
        }

    total_requests = sum(int(r.count) for r in by_model)
    total_input = sum(int(r.input_tokens or 0) for r in by_model)
    total_output = sum(int(r.output_tokens or 0) for r in by_model)

    weighted_latency = sum((r.avg_latency or 0) * r.count for r in by_model)
    avg_latency = weighted_latency / total_requests if total_requests > 0 else None

    return {
        "avg_latency_ms": round(float(avg_latency), 1) if avg_latency is not None else None,
        "total_requests": total_requests,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "by_model": [{"model": r.model, "count": int(r.count)} for r in by_model],
        "last_7_days": True,
    }

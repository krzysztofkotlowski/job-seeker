"""Persistent embedding sync run management and active index resolution."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database import SessionLocal
from app.models.tables import EmbeddingSyncRunRow, JobRow
from app.services.ai_config_service import (
    get_ai_config,
    resolve_ollama_embed_dims,
    update_ai_config,
)
from app.services.embedding_service import OPENAI_EMBED_MODEL, OPENAI_EMBED_DIMS
from app.services.elasticsearch_service import (
    JOBS_INDEX_ALIAS,
    activate_alias,
    count_documents,
    get_jobs_not_indexed,
    is_available as es_available,
    list_legacy_job_indices,
    managed_index_name,
)
from app.services.jobs_service import duplicate_grouped_job_ids_subquery

log = logging.getLogger(__name__)

RUN_ACTIVE_STATUSES = ("queued", "running")
RUN_TERMINAL_STATUSES = ("completed", "failed", "interrupted")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EmbeddingSyncError(RuntimeError):
    """Base embedding sync orchestration error."""


class SyncAlreadyRunningError(EmbeddingSyncError):
    """Raised when another embedding sync run is already active."""


class IncrementalReindexRequiredError(EmbeddingSyncError):
    """Raised when incremental indexing is not compatible with the active run."""


def _effective_embed_settings(ai_cfg: dict[str, Any]) -> tuple[str, str, int]:
    source = str(ai_cfg.get("embed_source") or "ollama").strip().lower()
    if source == "openai":
        return source, OPENAI_EMBED_MODEL, OPENAI_EMBED_DIMS
    model = str(ai_cfg.get("embed_model") or "").strip() or "all-minilm"
    dims = resolve_ollama_embed_dims(model, int(ai_cfg.get("embed_dims") or 0) or 384)
    return source, model, dims


def serialize_run(row: EmbeddingSyncRunRow | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row.id),
        "status": row.status,
        "mode": row.mode,
        "unique_only": bool(row.unique_only),
        "embed_source": row.embed_source,
        "embed_model": row.embed_model,
        "embed_dims": int(row.embed_dims or 0),
        "db_total_snapshot": int(row.db_total_snapshot or 0),
        "selection_total": int(row.selection_total or 0),
        "target_total": int(row.target_total or 0),
        "processed": int(row.processed or 0),
        "indexed": int(row.indexed or 0),
        "failed": int(row.failed or 0),
        "index_alias": row.index_alias,
        "physical_index_name": row.physical_index_name,
        "celery_task_id": row.celery_task_id,
        "error_message": row.error_message,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
    }


def _selected_jobs(db: Session, unique_only: bool) -> list[JobRow]:
    if not unique_only:
        return db.query(JobRow).all()
    rep_ids_sq = duplicate_grouped_job_ids_subquery(db.query(JobRow))
    return db.query(JobRow).filter(JobRow.id.in_(select(rep_ids_sq.c.id))).all()


def _config_matches_run(ai_cfg: dict[str, Any], run: EmbeddingSyncRunRow | None) -> bool:
    if not run:
        return False
    source, model, dims = _effective_embed_settings(ai_cfg)
    return (
        run.embed_source == source
        and run.embed_model == model
        and int(run.embed_dims or 0) == int(dims)
    )


def get_running_run(db: Session) -> EmbeddingSyncRunRow | None:
    return (
        db.query(EmbeddingSyncRunRow)
        .filter(EmbeddingSyncRunRow.status.in_(RUN_ACTIVE_STATUSES))
        .order_by(EmbeddingSyncRunRow.updated_at.desc())
        .first()
    )


def get_latest_run(db: Session) -> EmbeddingSyncRunRow | None:
    return (
        db.query(EmbeddingSyncRunRow)
        .order_by(EmbeddingSyncRunRow.updated_at.desc())
        .first()
    )


def get_active_run(db: Session) -> EmbeddingSyncRunRow | None:
    return (
        db.query(EmbeddingSyncRunRow)
        .filter(
            EmbeddingSyncRunRow.status == "completed",
            EmbeddingSyncRunRow.activated_at.isnot(None),
        )
        .order_by(EmbeddingSyncRunRow.activated_at.desc())
        .first()
    )


def mark_interrupted_runs(db: Session) -> int:
    rows = (
        db.query(EmbeddingSyncRunRow)
        .filter(EmbeddingSyncRunRow.status.in_(RUN_ACTIVE_STATUSES))
        .all()
    )
    for row in rows:
        row.status = "interrupted"
        row.finished_at = _now()
        row.updated_at = _now()
        row.error_message = row.error_message or "Embedding sync interrupted by server restart"
    if rows:
        db.commit()
    return len(rows)


def recover_interrupted_runs() -> int:
    db = SessionLocal()
    try:
        return mark_interrupted_runs(db)
    finally:
        db.close()


def _deactivate_other_runs(db: Session, run_id: uuid.UUID) -> None:
    (
        db.query(EmbeddingSyncRunRow)
        .filter(
            EmbeddingSyncRunRow.id != run_id,
            EmbeddingSyncRunRow.activated_at.isnot(None),
        )
        .update(
            {
                EmbeddingSyncRunRow.activated_at: None,
                EmbeddingSyncRunRow.updated_at: _now(),
            },
            synchronize_session=False,
        )
    )


def activate_run(db: Session, row: EmbeddingSyncRunRow) -> None:
    _deactivate_other_runs(db, row.id)
    row.activated_at = _now()
    row.updated_at = _now()


def get_status(db: Session) -> dict[str, Any]:
    available = es_available()
    latest_or_running = get_running_run(db) or get_latest_run(db)
    active_run = get_active_run(db)
    ai_cfg = get_ai_config(db)
    current_db_total = int(db.query(JobRow).count())
    current_config_matches_active = _config_matches_run(ai_cfg, active_run)
    active_index_name = None
    active_indexed_documents = 0
    if active_run:
        active_index_name = active_run.index_alias or active_run.physical_index_name
        if active_index_name and available:
            active_indexed_documents = count_documents(active_index_name)

    return {
        "available": available,
        "current_db_total": current_db_total,
        "run": serialize_run(latest_or_running),
        "active_run": serialize_run(active_run),
        "active_index_name": active_index_name,
        "active_indexed_documents": active_indexed_documents,
        "current_config_matches_active": current_config_matches_active,
        "reindex_required": active_run is None or not current_config_matches_active,
        "legacy_indices": list_legacy_job_indices() if available else [],
    }


def queue_sync_run(
    db: Session,
    *,
    mode: str,
    unique_only: bool,
) -> EmbeddingSyncRunRow:
    normalized_mode = (mode or "incremental").strip().lower()
    if normalized_mode not in ("full", "incremental"):
        raise ValueError("mode must be 'full' or 'incremental'")

    if get_running_run(db):
        raise SyncAlreadyRunningError("Embedding sync is already running")

    ai_cfg = get_ai_config(db)
    embed_source, embed_model, embed_dims = _effective_embed_settings(ai_cfg)
    configured_dims = int(ai_cfg.get("embed_dims") or 0)
    if embed_source == "ollama" and configured_dims != embed_dims:
        log.info(
            "Normalizing Ollama embed dims before queueing sync: model=%s stored=%s resolved=%s",
            embed_model,
            configured_dims,
            embed_dims,
        )
        ai_cfg = update_ai_config(
            db,
            embed_source="ollama",
            embed_model=embed_model,
            embed_dims=embed_dims,
        )
        embed_source, embed_model, embed_dims = _effective_embed_settings(ai_cfg)

    selected_jobs = _selected_jobs(db, unique_only)
    db_total_snapshot = int(db.query(JobRow).count())
    selection_total = len(selected_jobs)

    active_run = get_active_run(db)
    physical_index_name: str | None = None
    target_total = selection_total

    run_id = uuid.uuid4()
    if normalized_mode == "full":
        physical_index_name = managed_index_name(str(run_id))
    else:
        if not active_run:
            raise IncrementalReindexRequiredError("No active embedding index. Run a full rebuild first.")
        if active_run.unique_only != unique_only or not _config_matches_run(ai_cfg, active_run):
            raise IncrementalReindexRequiredError(
                "Incremental indexing requires the same duplicate setting and embedding configuration as the active index."
            )
        physical_index_name = active_run.physical_index_name
        if not physical_index_name:
            raise IncrementalReindexRequiredError(
                "Active embedding index metadata is incomplete. Run a full rebuild first."
            )
        jobs_to_index = get_jobs_not_indexed(selected_jobs, index_name=physical_index_name)
        target_total = len(jobs_to_index)

    row = EmbeddingSyncRunRow(
        id=run_id,
        status="queued",
        mode=normalized_mode,
        unique_only=unique_only,
        embed_source=embed_source,
        embed_model=embed_model,
        embed_dims=embed_dims,
        db_total_snapshot=db_total_snapshot,
        selection_total=selection_total,
        target_total=target_total,
        processed=0,
        indexed=0,
        failed=0,
        index_alias=JOBS_INDEX_ALIAS,
        physical_index_name=physical_index_name,
        updated_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def attach_celery_task_id(db: Session, run_id: str, celery_task_id: str | None) -> EmbeddingSyncRunRow | None:
    row = db.query(EmbeddingSyncRunRow).filter(EmbeddingSyncRunRow.id == run_id).first()
    if not row:
        return None
    row.celery_task_id = celery_task_id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def _update_run_progress(
    db: Session,
    row: EmbeddingSyncRunRow,
    *,
    status: str | None = None,
    processed: int | None = None,
    indexed: int | None = None,
    failed: int | None = None,
    error_message: str | None = None,
    finished: bool = False,
) -> None:
    if status is not None:
        row.status = status
    if processed is not None:
        row.processed = processed
    if indexed is not None:
        row.indexed = indexed
    if failed is not None:
        row.failed = failed
    if error_message is not None:
        row.error_message = error_message
    row.updated_at = _now()
    if finished:
        row.finished_at = _now()
    db.commit()


def run_sync_task(run_id: str) -> None:
    from app.services.elasticsearch_service import (
        _get_client,
        clear_index,
        ensure_index,
        get_jobs_not_indexed,
        iter_index_job_batches,
    )

    db = SessionLocal()
    try:
        row = db.query(EmbeddingSyncRunRow).filter(EmbeddingSyncRunRow.id == run_id).first()
        if not row:
            return

        _update_run_progress(db, row, status="running")
        if row.started_at is None:
            row.started_at = _now()
            row.updated_at = _now()
            db.commit()

        selected_jobs = _selected_jobs(db, bool(row.unique_only))
        if row.mode == "incremental":
            if not row.physical_index_name:
                raise RuntimeError("Incremental sync requires an active managed Elasticsearch index")
            jobs_to_index = get_jobs_not_indexed(selected_jobs, index_name=row.physical_index_name)
        else:
            client = _get_client()
            if not client or not ensure_index(client, embed_dims=row.embed_dims, index_name=row.physical_index_name):
                raise RuntimeError("Failed to create managed Elasticsearch index")
            jobs_to_index = selected_jobs

        row.target_total = len(jobs_to_index)
        row.selection_total = len(selected_jobs)
        row.db_total_snapshot = int(db.query(JobRow).count())
        row.updated_at = _now()
        db.commit()
        db.refresh(row)

        for progress in iter_index_job_batches(
            jobs_to_index,
            index_name=row.physical_index_name,
            embed_model=row.embed_model if row.embed_source != "openai" else None,
            ai_config={
                "embed_source": row.embed_source,
                "embed_dims": row.embed_dims,
            },
        ):
            _update_run_progress(
                db,
                row,
                processed=int(progress["processed"]),
                indexed=int(progress["indexed"]),
                failed=int(progress["failed"]),
            )
            db.refresh(row)

        if row.mode == "full":
            if not activate_alias(row.index_alias, row.physical_index_name):
                raise RuntimeError("Failed to activate Elasticsearch alias")

        activate_run(db, row)
        _update_run_progress(db, row, status="completed", finished=True, error_message=None)
    except Exception as e:
        log.exception("Embedding sync run %s failed", run_id)
        fail_db = db
        try:
            row = fail_db.query(EmbeddingSyncRunRow).filter(EmbeddingSyncRunRow.id == run_id).first()
            if row:
                _update_run_progress(fail_db, row, status="failed", finished=True, error_message=str(e))
                if row.mode == "full" and row.physical_index_name:
                    clear_index(index_name=row.physical_index_name)
        except Exception:
            log.exception("Failed to persist embedding sync failure for %s", run_id)
        raise
    finally:
        db.close()


def resolve_active_recommendation_source(db: Session) -> dict[str, Any]:
    ai_cfg = get_ai_config(db)
    active_run = get_active_run(db)
    if not active_run:
        return {
            "status": "reindex_required",
            "message": "No active embedding index. Run a full re-index first.",
            "active_run": None,
            "active_run_meta": None,
            "active_index_name": None,
            "config_matches_active": False,
        }

    current_config_matches_active = _config_matches_run(ai_cfg, active_run)
    active_index_name = active_run.index_alias or active_run.physical_index_name
    return {
        "status": "ok",
        "message": None,
        "active_run": active_run,
        "active_run_meta": serialize_run(active_run),
        "active_index_name": active_index_name,
        "config_matches_active": current_config_matches_active,
    }

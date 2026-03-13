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
    get_ollama_embedding_dims,
    resolve_ollama_embed_dims,
    update_ai_config,
)
from app.services.embedding_profiles import (
    EMBED_PROFILE_NOMIC_LEGACY,
    EMBED_PROFILE_NOMIC_SEARCH,
    resolve_run_embed_profile,
    resolve_selected_embed_profile,
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


def _effective_embed_settings(ai_cfg: dict[str, Any]) -> tuple[str, str, int, str]:
    source = str(ai_cfg.get("embed_source") or "ollama").strip().lower()
    if source == "openai":
        return (
            source,
            OPENAI_EMBED_MODEL,
            OPENAI_EMBED_DIMS,
            resolve_selected_embed_profile(source, OPENAI_EMBED_MODEL, ai_cfg.get("embed_profile")),
        )
    model = str(ai_cfg.get("embed_model") or "").strip() or "nomic-embed-text"
    configured = int(ai_cfg.get("embed_dims") or 0) or 768
    runtime_dims = get_ollama_embedding_dims(model)
    dims = int(runtime_dims) if isinstance(runtime_dims, int) and 256 <= runtime_dims <= 4096 else resolve_ollama_embed_dims(model, configured)
    return source, model, dims, resolve_selected_embed_profile(source, model, ai_cfg.get("embed_profile"))


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
        "embed_profile": resolve_run_embed_profile(
            row.embed_source,
            row.embed_model,
            getattr(row, "embed_profile", None),
        ),
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
    source, model, dims, profile = _effective_embed_settings(ai_cfg)
    return (
        run.embed_source == source
        and run.embed_model == model
        and int(run.embed_dims or 0) == int(dims)
        and resolve_run_embed_profile(
            run.embed_source,
            run.embed_model,
            getattr(run, "embed_profile", None),
        ) == profile
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


def _run_is_queryable(
    row: EmbeddingSyncRunRow | None,
    *,
    active_indexed_documents: int,
) -> bool:
    if not row:
        return False
    if row.status != "completed" or row.activated_at is None:
        return False
    if int(row.failed or 0) != 0:
        return False
    if not str(row.physical_index_name or "").strip():
        return False
    if row.mode == "full":
        target_total = int(row.target_total or 0)
        indexed = int(row.indexed or 0)
        if target_total <= 0 or indexed <= 0 or indexed != target_total:
            return False
    return int(active_indexed_documents or 0) > 0


def _recommendation_status_payload(
    *,
    status: str,
    message: str | None,
    active_run: EmbeddingSyncRunRow | None,
    ai_cfg: dict[str, Any],
    active_query_model_ready: bool,
) -> dict[str, Any]:
    _, selected_embed_model, selected_embed_dims, selected_embed_profile = _effective_embed_settings(ai_cfg)
    return {
        "status": status,
        "message": message,
        "active_embed_model": active_run.embed_model if active_run else None,
        "active_embed_dims": int(active_run.embed_dims or 0) if active_run else 0,
        "active_embed_profile": (
            resolve_run_embed_profile(
                active_run.embed_source,
                active_run.embed_model,
                getattr(active_run, "embed_profile", None),
            )
            if active_run
            else None
        ),
        "selected_embed_model": selected_embed_model,
        "selected_embed_dims": int(selected_embed_dims or 0),
        "selected_embed_profile": selected_embed_profile,
        "active_query_model_ready": bool(active_query_model_ready),
    }


def get_recommendation_readiness(
    db: Session,
    *,
    ai_cfg: dict[str, Any] | None = None,
    active_run: EmbeddingSyncRunRow | None = None,
    active_index_name: str | None = None,
    active_indexed_documents: int | None = None,
) -> dict[str, Any]:
    current_ai_cfg = ai_cfg or get_ai_config(db)
    current_active_run = active_run if active_run is not None else get_active_run(db)
    current_active_index_name = active_index_name
    current_active_docs = active_indexed_documents

    if current_active_run and current_active_index_name is None:
        current_active_index_name = current_active_run.index_alias or current_active_run.physical_index_name
    if current_active_docs is None:
        current_active_docs = (
            count_documents(current_active_index_name)
            if current_active_index_name and es_available()
            else 0
        )

    if not current_active_run:
        return _recommendation_status_payload(
            status="reindex_required",
            message="No active embedding index. Run a full re-index first.",
            active_run=None,
            ai_cfg=current_ai_cfg,
            active_query_model_ready=False,
        )

    if not _run_is_queryable(
        current_active_run,
        active_indexed_documents=int(current_active_docs or 0),
    ):
        return _recommendation_status_payload(
            status="reindex_required",
            message="The active embedding index is incomplete or empty. Run a full re-index.",
            active_run=current_active_run,
            ai_cfg=current_ai_cfg,
            active_query_model_ready=False,
        )

    selected_source, selected_embed_model, selected_embed_dims, selected_embed_profile = _effective_embed_settings(current_ai_cfg)
    active_embed_profile = resolve_run_embed_profile(
        current_active_run.embed_source,
        current_active_run.embed_model,
        getattr(current_active_run, "embed_profile", None),
    )

    if (
        current_active_run.embed_source != selected_source
        or current_active_run.embed_model != selected_embed_model
        or int(current_active_run.embed_dims or 0) != int(selected_embed_dims or 0)
        or active_embed_profile != selected_embed_profile
    ):
        if current_active_run.embed_model == selected_embed_model and (
            active_embed_profile == EMBED_PROFILE_NOMIC_LEGACY
            and selected_embed_profile == EMBED_PROFILE_NOMIC_SEARCH
        ):
            message = (
                "The active embedding index still uses the legacy raw-text nomic profile, "
                "but the current configuration uses prefix-correct nomic search embeddings. "
                "Run a full rebuild to activate the new index."
            )
        else:
            message = (
                f"The active embedding index was built with '{current_active_run.embed_model}' "
                f"({active_embed_profile}), but the current embedding configuration uses "
                f"'{selected_embed_model}' ({selected_embed_profile}). "
                "Run a full rebuild to activate the new index."
            )
        return _recommendation_status_payload(
            status="reindex_required",
            message=message,
            active_run=current_active_run,
            ai_cfg=current_ai_cfg,
            active_query_model_ready=False,
        )

    if current_active_run.embed_source == "openai":
        api_key = str(current_ai_cfg.get("openai_api_key") or "").strip()
        if not api_key:
            return _recommendation_status_payload(
                status="active_embedding_unavailable",
                message=(
                    "The active recommendation index was built with OpenAI embeddings, "
                    "but no OpenAI API key is configured for query embeddings."
                ),
                active_run=current_active_run,
                ai_cfg=current_ai_cfg,
                active_query_model_ready=False,
            )
        return _recommendation_status_payload(
            status="ok",
            message=None,
            active_run=current_active_run,
            ai_cfg=current_ai_cfg,
            active_query_model_ready=True,
        )

    from app.services.embedding_service import is_ollama_model_ready

    if not is_ollama_model_ready(current_active_run.embed_model):
        selected_suffix = ""
        if selected_embed_model and selected_embed_model != current_active_run.embed_model:
            selected_suffix = f" thin-llama is currently serving '{selected_embed_model}'."
        return _recommendation_status_payload(
            status="active_embedding_unavailable",
            message=(
                f"The active embedding index still uses '{current_active_run.embed_model}', "
                f"which is not queryable in thin-llama.{selected_suffix} "
                "Recommendations are unavailable until a successful full rebuild activates the new index."
            ),
            active_run=current_active_run,
            ai_cfg=current_ai_cfg,
            active_query_model_ready=False,
        )

    return _recommendation_status_payload(
        status="ok",
        message=None,
        active_run=current_active_run,
        ai_cfg=current_ai_cfg,
        active_query_model_ready=True,
    )


def get_status(db: Session) -> dict[str, Any]:
    available = es_available()
    latest_or_running = get_running_run(db) or get_latest_run(db)
    active_run = get_active_run(db)
    ai_cfg = get_ai_config(db)
    current_db_total = int(db.query(JobRow).count())
    active_index_name = None
    active_indexed_documents = 0
    if active_run:
        active_index_name = active_run.index_alias or active_run.physical_index_name
        if active_index_name and available:
            active_indexed_documents = count_documents(active_index_name)
    active_run_usable = _run_is_queryable(
        active_run,
        active_indexed_documents=active_indexed_documents,
    )
    current_config_matches_active = active_run_usable and _config_matches_run(ai_cfg, active_run)
    recommendations = get_recommendation_readiness(
        db,
        ai_cfg=ai_cfg,
        active_run=active_run,
        active_index_name=active_index_name,
        active_indexed_documents=active_indexed_documents,
    )

    return {
        "available": available,
        "current_db_total": current_db_total,
        "run": serialize_run(latest_or_running),
        "active_run": serialize_run(active_run),
        "active_index_name": active_index_name,
        "active_indexed_documents": active_indexed_documents,
        "current_config_matches_active": current_config_matches_active,
        "reindex_required": not active_run_usable or not current_config_matches_active,
        "legacy_indices": list_legacy_job_indices() if available else [],
        "recommendations": recommendations,
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
    embed_source, embed_model, embed_dims, embed_profile = _effective_embed_settings(ai_cfg)
    configured_dims = int(ai_cfg.get("embed_dims") or 0)
    if embed_source == "ollama" and configured_dims != embed_dims:
        log.info(
            "Normalizing self-hosted embed dims before queueing sync: model=%s stored=%s resolved=%s",
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
        embed_source, embed_model, embed_dims, embed_profile = _effective_embed_settings(ai_cfg)

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
        active_index_name = active_run.index_alias or active_run.physical_index_name if active_run else None
        active_indexed_documents = count_documents(active_index_name) if active_index_name and es_available() else 0
        if not _run_is_queryable(active_run, active_indexed_documents=active_indexed_documents):
            raise IncrementalReindexRequiredError("No usable active embedding index. Run a full rebuild first.")
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
        embed_profile=embed_profile,
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
                "embed_profile": resolve_run_embed_profile(
                    row.embed_source,
                    row.embed_model,
                    getattr(row, "embed_profile", None),
                ),
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

        db.refresh(row)
        if int(row.failed or 0) != 0:
            raise RuntimeError(
                f"Embedding sync incomplete: indexed={int(row.indexed or 0)} failed={int(row.failed or 0)} target_total={int(row.target_total or 0)}"
            )
        if row.mode == "full":
            if int(row.target_total or 0) <= 0 or int(row.indexed or 0) <= 0 or int(row.indexed or 0) != int(row.target_total or 0):
                raise RuntimeError(
                    f"Full embedding rebuild incomplete: indexed={int(row.indexed or 0)} failed={int(row.failed or 0)} target_total={int(row.target_total or 0)}"
                )
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
    active_index_name = active_run.index_alias or active_run.physical_index_name if active_run else None
    active_indexed_documents = count_documents(active_index_name) if active_index_name and es_available() else 0
    current_config_matches_active = _config_matches_run(ai_cfg, active_run)
    recommendations = get_recommendation_readiness(
        db,
        ai_cfg=ai_cfg,
        active_run=active_run,
        active_index_name=active_index_name,
        active_indexed_documents=active_indexed_documents,
    )
    return {
        "status": recommendations["status"],
        "message": recommendations["message"],
        "active_run": active_run,
        "active_run_meta": serialize_run(active_run),
        "active_index_name": active_index_name,
        "config_matches_active": current_config_matches_active,
        "recommendations": recommendations,
    }

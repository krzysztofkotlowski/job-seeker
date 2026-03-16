"""Background enrichment of jobs with missing descriptions."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.tables import EnrichmentRunRow, JobRow
from app.parsers.detector import detect_and_parse, is_supported_url
from app.services.skill_detector import run_detection_batch

log = logging.getLogger(__name__)

RUN_ACTIVE_STATUSES = ("queued", "running")
RUN_TERMINAL_STATUSES = ("completed", "failed", "interrupted")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_run(row: EnrichmentRunRow | None) -> dict[str, Any] | None:
    if not row:
        return None
    error_log = (row.error_log or [])[-20:]
    return {
        "id": str(row.id),
        "status": row.status,
        "total": int(row.total or 0),
        "enriched": int(row.enriched or 0),
        "errors_count": int(row.errors_count or 0),
        "error_log": error_log,
        "errors": error_log,
        "celery_task_id": row.celery_task_id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_running_run(db: Session) -> EnrichmentRunRow | None:
    return (
        db.query(EnrichmentRunRow)
        .filter(EnrichmentRunRow.status.in_(RUN_ACTIVE_STATUSES))
        .order_by(EnrichmentRunRow.updated_at.desc())
        .first()
    )


def get_run(db: Session, run_id: str) -> EnrichmentRunRow | None:
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        return None
    return db.query(EnrichmentRunRow).filter(EnrichmentRunRow.id == uid).first()


def attach_celery_task_id(db: Session, run_id: str, celery_task_id: str | None) -> EnrichmentRunRow | None:
    row = get_run(db, run_id)
    if not row:
        return None
    row.celery_task_id = celery_task_id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def get_latest_run(db: Session) -> EnrichmentRunRow | None:
    return (
        db.query(EnrichmentRunRow)
        .order_by(EnrichmentRunRow.updated_at.desc())
        .first()
    )


class EnrichmentAlreadyRunningError(RuntimeError):
    """Raised when another enrichment run is already active."""


def queue_enrichment_run(
    db: Session,
    limit: int = 2000,
    delay_sec: float = 0.5,
) -> EnrichmentRunRow:
    """Create and return a new enrichment run. Caller must start the Celery task."""
    if get_running_run(db):
        raise EnrichmentAlreadyRunningError("An enrichment run is already in progress.")

    empty_desc = (JobRow.description.is_(None)) | (func.trim(func.coalesce(JobRow.description, "")) == "")
    rows = (
        db.query(JobRow)
        .filter(empty_desc)
        .limit(limit)
        .all()
    )
    job_ids = [str(r.id) for r in rows if is_supported_url(r.url)]

    row = EnrichmentRunRow(
        status="queued",
        total=len(job_ids),
        enriched=0,
        errors_count=0,
        error_log=[],
        pending_job_ids=job_ids,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def run_enrichment_task(run_id: str, delay_sec: float = 0.5) -> None:
    """Execute enrichment in the worker. Updates EnrichmentRunRow progress."""
    db = SessionLocal()
    try:
        row = get_run(db, run_id)
        if not row:
            log.warning("Enrichment run %s not found", run_id)
            return
        if row.status not in RUN_ACTIVE_STATUSES:
            log.info("Enrichment run %s already finished (status=%s)", run_id, row.status)
            return

        job_ids = list(row.pending_job_ids or [])
        if not job_ids:
            row.status = "completed"
            row.finished_at = _now()
            row.updated_at = _now()
            db.commit()
            return

        row.status = "running"
        row.started_at = row.started_at or _now()
        row.total = len(job_ids)
        db.commit()

        enriched = 0
        enriched_ids: list = []
        errors: list[str] = []
        error_log = list(row.error_log or [])
        processed = 0

        for job_id in job_ids:
            if row.status == "interrupted":
                break

            job_row = db.query(JobRow).filter(JobRow.id == job_id).first()
            if not job_row:
                errors.append(f"{job_id}: not found")
                continue
            needs = (not job_row.description or not job_row.description.strip()) or (
                not job_row.skills_nice_to_have or len(job_row.skills_nice_to_have) == 0
            )
            if not needs:
                continue
            if not is_supported_url(job_row.url):
                errors.append(f"{job_id}: unsupported URL")
                continue

            try:
                parsed = detect_and_parse(job_row.url)
                if parsed.description and (not job_row.description or not job_row.description.strip()):
                    job_row.description = parsed.description
                if parsed.skills_required:
                    job_row.skills_required = parsed.skills_required
                if parsed.skills_nice_to_have:
                    job_row.skills_nice_to_have = parsed.skills_nice_to_have
                enriched += 1
                enriched_ids.append(job_row.id)
            except Exception as e:
                err_msg = f"{job_id}: {e}"
                errors.append(err_msg)
                error_log.append(err_msg)

            processed += 1
            if delay_sec > 0:
                time.sleep(delay_sec)

            # Update progress every 10 jobs
            if processed % 10 == 0:
                row.enriched = enriched
                row.errors_count = len(errors)
                row.error_log = error_log[-50:]
                row.updated_at = _now()
                db.commit()

        db.refresh(row)
        row.enriched = enriched
        row.errors_count = len(errors)
        row.error_log = error_log[-50:]
        row.status = "completed"
        row.finished_at = _now()
        row.updated_at = _now()
        db.commit()

        if enriched_ids:
            run_detection_batch(db, job_ids=enriched_ids)

        log.info("Enrichment run %s completed: enriched=%d errors=%d", run_id, enriched, len(errors))
    except Exception as e:
        log.exception("Enrichment run %s failed: %s", run_id, e)
        try:
            db.rollback()
            row = get_run(db, run_id)
            if row and row.status in RUN_ACTIVE_STATUSES:
                row.status = "failed"
                row.finished_at = _now()
                row.updated_at = _now()
                row.error_log = (row.error_log or []) + [str(e)]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def recover_interrupted_runs() -> int:
    """Mark any runs stuck in queued/running as interrupted. Returns count."""
    db = SessionLocal()
    try:
        stuck = (
            db.query(EnrichmentRunRow)
            .filter(EnrichmentRunRow.status.in_(RUN_ACTIVE_STATUSES))
            .all()
        )
        for row in stuck:
            row.status = "interrupted"
            row.finished_at = _now()
            row.updated_at = _now()
            if row.error_log is None:
                row.error_log = []
            row.error_log = list(row.error_log) + ["Run interrupted by server restart"]
        if stuck:
            db.commit()
            log.info("Marked %d interrupted enrichment run(s)", len(stuck))
        return len(stuck)
    except Exception as e:
        log.warning("Failed to recover enrichment runs: %s", e)
        return 0
    finally:
        db.close()

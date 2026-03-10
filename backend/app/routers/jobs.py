import asyncio
import logging
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.celery_app import run_embedding_sync
from app.database import get_db
from app.errors import api_error
from app.services import jobs_service
from app.models.tables import JobRow
from app.parsers.base import format_category
from app.models.job import (
    DuplicateCheck,
    Job,
    JobCreate,
    JobStatus,
    JobUpdate,
    ParseRequest,
)
from app.parsers.detector import detect_and_parse, is_supported_url
from app.services.currency import normalize_salary

router = APIRouter()
log = logging.getLogger(__name__)
@router.post("/parse")
def parse_url(req: ParseRequest):
    if not is_supported_url(req.url):
        raise api_error(
            "UNSUPPORTED_URL",
            "Unsupported URL. Supported: justjoin.it, nofluffjobs.com",
            status_code=400,
        )
    try:
        parsed = detect_and_parse(req.url)
        return parsed.model_dump()
    except Exception as e:
        raise api_error(
            "PARSE_FAILED",
            "Failed to parse job listing from this URL.",
            status_code=502,
        )


@router.post("", status_code=201)
def create_job(job_data: JobCreate, db: Session = Depends(get_db)):
    existing = db.query(JobRow).filter(JobRow.url == job_data.url).first()
    if existing:
        raise api_error(
            "JOB_ALREADY_EXISTS",
            "Job with this URL already exists.",
            status_code=409,
            existing_id=str(existing.id),
        )

    row = _pydantic_to_row(job_data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.get("")
def list_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    seniority: Optional[str] = Query(None),
    skill: Optional[str] = Query(None, description="Single skill (deprecated, use skills)"),
    skills: Optional[str] = Query(None, description="Comma-separated skills; job must have ALL"),
    search: Optional[str] = Query(None),
    is_reposted: Optional[bool] = Query(None),
    work_type: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    group_duplicates: bool = Query(False),
    saved: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    params = jobs_service.ListJobsParams(
        page=page,
        per_page=per_page,
        status=status,
        source=source,
        category=category,
        seniority=seniority,
        skill=skill,
        skills=skills,
        search=search,
        is_reposted=is_reposted,
        work_type=work_type,
        location=location,
        sort_by=sort_by,
        group_duplicates=group_duplicates,
        saved=saved,
    )
    return jobs_service.list_jobs(db, params)


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    return jobs_service.list_categories(db)


@router.get("/work-types")
def list_work_types(db: Session = Depends(get_db)):
    return jobs_service.list_work_types(db)


@router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    return jobs_service.list_locations(db)


@router.get("/seniorities")
def list_seniorities(db: Session = Depends(get_db)):
    return jobs_service.list_seniorities(db)


@router.get("/top-skills")
def list_top_skills(top: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    """Return top N skill names for autocomplete."""
    return jobs_service.list_top_skills(db, top)


@router.get("/analytics")
def analytics(
    seniority: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    skill: Optional[str] = Query(None, description="Single skill (deprecated, use skills)"),
    skills: Optional[str] = Query(None, description="Comma-separated skills; job must have ALL"),
    search: Optional[str] = Query(None),
    is_reposted: Optional[bool] = Query(None),
    work_type: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    saved: Optional[bool] = Query(None),
    group_duplicates: bool = Query(False),
    db: Session = Depends(get_db),
):
    params = jobs_service.AnalyticsParams(
        seniority=seniority,
        source=source,
        category=category,
        skill=skill,
        skills=skills,
        search=search,
        is_reposted=is_reposted,
        work_type=work_type,
        location=location,
        saved=saved,
        group_duplicates=group_duplicates,
    )
    return jobs_service.get_analytics(db, params)


@router.post("/sync-embeddings")
def sync_embeddings(
    db: Session = Depends(get_db),
    mode: str = Query("full", description="full=create new managed index, incremental=add missing docs"),
    unique_only: bool = Query(False, description="Index one newest job per (company,title)"),
):
    """
    Queue a persistent embedding sync run.
    Full mode builds a new managed physical index and cuts the alias over on success.
    Incremental mode only indexes missing jobs into the currently active managed index.
    """
    try:
        from app.services.elasticsearch_service import is_available
        from app.services.embedding_sync_service import (
            IncrementalReindexRequiredError,
            SyncAlreadyRunningError,
            attach_celery_task_id,
            queue_sync_run,
            serialize_run,
        )
    except ImportError:
        raise api_error(
            "RAG_UNAVAILABLE",
            "Elasticsearch not configured. Install elasticsearch package.",
            status_code=503,
        )
    if not is_available():
        raise api_error(
            "ELASTICSEARCH_UNAVAILABLE",
            "Elasticsearch is not reachable. Ensure it is running.",
            status_code=503,
        )
    try:
        row = queue_sync_run(db, mode=mode, unique_only=unique_only)
    except SyncAlreadyRunningError as e:
        raise api_error("SYNC_IN_PROGRESS", str(e), status_code=409)
    except IncrementalReindexRequiredError as e:
        raise api_error("FULL_REINDEX_REQUIRED", str(e), status_code=409)
    except ValueError as e:
        raise api_error("INVALID_MODE", str(e), status_code=400)

    task = run_embedding_sync.delay(str(row.id))
    row = attach_celery_task_id(db, str(row.id), getattr(task, "id", None)) or row
    return serialize_run(row)


@router.get("/embedding-status")
def embedding_status(db: Session = Depends(get_db)):
    """
    Return DB-backed embedding sync status and the currently active recommendation index.
    """
    try:
        from app.services.embedding_sync_service import get_status
    except ImportError:
        return {
            "available": False,
            "current_db_total": 0,
            "run": None,
            "active_run": None,
            "active_index_name": None,
            "active_indexed_documents": 0,
            "current_config_matches_active": False,
            "reindex_required": True,
            "legacy_indices": [],
        }
    return get_status(db)


@router.delete("/embedding-index")
def clear_embedding_index(db: Session = Depends(get_db)):
    """Clear the active managed embedding index and deactivate recommendation source metadata."""
    try:
        from app.services.elasticsearch_service import clear_index, is_available
        from app.services.embedding_sync_service import get_active_run, get_running_run
        from app.models.tables import EmbeddingSyncRunRow
    except ImportError:
        raise api_error(
            "RAG_UNAVAILABLE",
            "Elasticsearch not configured. Install elasticsearch package.",
            status_code=503,
        )
    if not is_available():
        raise api_error(
            "ELASTICSEARCH_UNAVAILABLE",
            "Elasticsearch is not reachable. Ensure it is running.",
            status_code=503,
        )
    if get_running_run(db):
        raise api_error(
            "SYNC_IN_PROGRESS",
            "Embedding sync is already running. Please wait for it to complete.",
            status_code=409,
        )
    active_run = get_active_run(db)
    if not active_run or not active_run.physical_index_name:
        return {"cleared": False, "message": "No active managed embedding index to clear."}
    ok = clear_index(index_name=active_run.physical_index_name)
    if not ok:
        raise api_error("CLEAR_FAILED", "Failed to clear embedding index", status_code=500)
    (
        db.query(EmbeddingSyncRunRow)
        .filter(EmbeddingSyncRunRow.activated_at.isnot(None))
        .update({EmbeddingSyncRunRow.activated_at: None}, synchronize_session=False)
    )
    db.commit()
    return {"cleared": True, "index_name": active_run.physical_index_name}


@router.post("/sync-embeddings/stream")
def sync_embeddings_stream(
    db: Session = Depends(get_db),
    mode: str = Query("full", description="full=create new managed index, incremental=add missing only"),
    unique_only: bool = Query(False, description="Index one newest job per (company,title)"),
):
    """
    Deprecated compatibility wrapper around the DB-backed embedding sync API.
    Starts a run when none is active, then streams run status until completion.
    """
    import json

    from fastapi.responses import StreamingResponse

    try:
        from app.services.embedding_sync_service import get_running_run, get_status
    except ImportError:
        raise api_error(
            "RAG_UNAVAILABLE",
            "Elasticsearch not configured. Install elasticsearch package.",
            status_code=503,
        )
    if not get_running_run(db):
        sync_embeddings(db=db, mode=mode, unique_only=unique_only)

    async def stream_gen_async():
        while True:
            status = get_status(db)
            run = status.get("run") or {}
            done = (run.get("status") or "") in {"completed", "failed", "interrupted"}
            payload = {
                "run": run,
                "done": done,
                "status": status,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if done:
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        stream_gen_async(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/recalculate-salaries")
def recalculate_salaries(db: Session = Depends(get_db)):
    rows = db.query(JobRow).filter(
        JobRow.salary_min.isnot(None) | JobRow.salary_max.isnot(None)
    ).all()
    updated = 0
    for row in rows:
        normalize_salary(row)
        updated += 1
    db.commit()
    return {"updated": updated}


@router.get("/find-by-url")
def find_by_url(url: str, db: Session = Depends(get_db)):
    """Look up a job by its original listing URL. Returns {id} or 404."""
    row = db.query(JobRow).filter(JobRow.url == url).first()
    if not row:
        # Try partial match (URL without trailing slash or query params)
        clean = url.rstrip("/")
        row = db.query(JobRow).filter(JobRow.url.ilike(f"%{clean}%")).first()
    if row:
        return {"id": str(row.id)}
    raise HTTPException(404, "No job found with this URL")


@router.get("/check-duplicate")
def check_duplicate(url: str, db: Session = Depends(get_db)):
    existing = db.query(JobRow).filter(JobRow.url == url).first()
    if existing:
        d = existing.to_dict()
        return DuplicateCheck(is_duplicate=True, existing_job=Job(**d))
    return DuplicateCheck(is_duplicate=False)


@router.post("/fix-categories")
def fix_categories(db: Session = Depends(get_db)):
    """One-off: normalise all stored category values to human-readable names."""
    log = logging.getLogger(__name__)
    rows = db.query(JobRow).filter(JobRow.category.isnot(None), JobRow.category != "").all()
    fixed = 0
    for row in rows:
        new_cat = format_category(row.category)
        if new_cat and new_cat != row.category:
            row.category = new_cat
            fixed += 1
    db.commit()
    log.info("Fixed %d category values", fixed)
    return {"fixed": fixed}


@router.post("/enrich")
def enrich_jobs_batch(
    ids: Optional[str] = Query(None, description="Comma-separated job UUIDs to enrich"),
    db: Session = Depends(get_db),
):
    """Enrich jobs missing description or skills_nice_to_have by re-parsing their URLs."""
    if not ids:
        raise api_error("MISSING_IDS", "Provide ids query param (comma-separated UUIDs)", status_code=400)
    job_ids = [i.strip() for i in ids.split(",") if i.strip()]
    if not job_ids:
        raise api_error("MISSING_IDS", "Provide at least one job ID", status_code=400)

    from app.parsers.detector import detect_and_parse, is_supported_url
    from app.services.skill_detector import run_detection_batch

    enriched = 0
    enriched_ids: list = []
    errors: list[str] = []
    for job_id in job_ids:
        row = db.query(JobRow).filter(JobRow.id == job_id).first()
        if not row:
            errors.append(f"{job_id}: not found")
            continue
        needs = (not row.description or not row.description.strip()) or (
            not row.skills_nice_to_have or len(row.skills_nice_to_have) == 0
        )
        if not needs:
            continue
        if not is_supported_url(row.url):
            errors.append(f"{job_id}: unsupported URL source")
            continue
        try:
            parsed = detect_and_parse(row.url)
            if parsed.description and (not row.description or not row.description.strip()):
                row.description = parsed.description
            if parsed.skills_required:
                row.skills_required = parsed.skills_required
            if parsed.skills_nice_to_have:
                row.skills_nice_to_have = parsed.skills_nice_to_have
            enriched += 1
            enriched_ids.append(row.id)
        except Exception as e:
            errors.append(f"{job_id}: {e}")

    db.commit()
    if enriched > 0:
        run_detection_batch(db, job_ids=enriched_ids)
    return {"enriched": enriched, "errors": errors[:20]}


@router.post("/{job_id}/enrich")
def enrich_job(job_id: str, db: Session = Depends(get_db)):
    """Enrich a single job by re-parsing its URL for description and skills."""
    row = db.query(JobRow).filter(JobRow.id == job_id).first()
    if not row:
        raise HTTPException(404, "Job not found")

    from app.parsers.detector import detect_and_parse, is_supported_url
    from app.services.skill_detector import run_detection_batch

    if not is_supported_url(row.url):
        raise api_error(
            "UNSUPPORTED_URL",
            f"Job source {row.source} is not supported for enrichment.",
            status_code=400,
        )

    try:
        parsed = detect_and_parse(row.url)
    except Exception as e:
        raise api_error(
            "PARSE_FAILED",
            f"Failed to parse job listing: {e}",
            status_code=502,
        )

    if parsed.description and (not row.description or not row.description.strip()):
        row.description = parsed.description
    if parsed.skills_required:
        row.skills_required = parsed.skills_required
    if parsed.skills_nice_to_have:
        row.skills_nice_to_have = parsed.skills_nice_to_have

    db.commit()
    db.refresh(row)
    run_detection_batch(db, job_ids=[row.id])
    return row.to_dict()


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    row = db.query(JobRow).filter(JobRow.id == job_id).first()
    if not row:
        raise HTTPException(404, "Job not found")
    data = row.to_dict()

    # Find other listings for the same role (same title + company) on different sources.
    alt_rows = (
        db.query(JobRow.id, JobRow.source, JobRow.url)
        .filter(
            func.lower(JobRow.title) == func.lower(row.title),
            func.lower(JobRow.company) == func.lower(row.company),
            JobRow.id != row.id,
            JobRow.source != row.source,
        )
        .all()
    )
    data["alternate_listings"] = [
        {"id": str(jid), "source": source, "url": url} for jid, source, url in alt_rows
    ]
    return data


@router.patch("/{job_id}")
def update_job(job_id: str, update: JobUpdate, db: Session = Depends(get_db)):
    row = db.query(JobRow).filter(JobRow.id == job_id).first()
    if not row:
        raise HTTPException(404, "Job not found")

    if update.status is not None:
        row.status = update.status.value
        if update.status == JobStatus.APPLIED and not update.applied_date:
            row.applied_date = date.today().isoformat()
    if update.applied_date is not None:
        row.applied_date = update.applied_date
    if update.notes is not None:
        row.notes = update.notes
    if update.is_reposted is not None:
        row.is_reposted = update.is_reposted
    if update.saved is not None:
        row.saved = update.saved

    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    row = db.query(JobRow).filter(JobRow.id == job_id).first()
    if not row:
        raise HTTPException(404, "Job not found")
    db.delete(row)
    db.commit()


def _pydantic_to_row(job_data: JobCreate) -> JobRow:
    sal = job_data.salary
    row = JobRow(
        id=uuid.uuid4(),
        url=job_data.url,
        source=job_data.source,
        title=job_data.title,
        company=job_data.company,
        location=job_data.location,
        salary_min=sal.min if sal else None,
        salary_max=sal.max if sal else None,
        salary_currency=sal.currency if sal else None,
        salary_type=sal.type if sal else None,
        skills_required=job_data.skills_required,
        skills_nice_to_have=job_data.skills_nice_to_have,
        seniority=job_data.seniority,
        work_type=job_data.work_type,
        employment_types=job_data.employment_types,
        description=job_data.description,
        category=job_data.category,
        date_published=job_data.date_published,
        date_expires=job_data.date_expires,
        date_added=date.today().isoformat(),
        status="new",
        notes="",
    )
    explicit_period = sal.period if sal and hasattr(sal, "period") else None
    normalize_salary(row, explicit_period=explicit_period)
    return row

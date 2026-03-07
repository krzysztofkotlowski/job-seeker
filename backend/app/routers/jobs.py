import asyncio
import logging
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import api_error
from app.services.ai_config_service import get_ai_config
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
def sync_embeddings(db: Session = Depends(get_db)):
    """
    Index all jobs into Elasticsearch for RAG/semantic search.
    Call after imports to enable resume AI summaries with vector retrieval.
    """
    try:
        from app.services.elasticsearch_service import bulk_index_jobs, is_available
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
    ai_cfg = get_ai_config(db)
    rows = db.query(JobRow).all()
    indexed = bulk_index_jobs(rows, embed_model=ai_cfg["embed_model"])
    return {"indexed": indexed, "total": len(rows)}


@router.get("/embedding-status")
def embedding_status(db: Session = Depends(get_db)):
    """
    Return embedding index status when Elasticsearch is available.
    """
    try:
        from app.services.elasticsearch_service import (
            JOBS_INDEX,
            _get_client,
            is_available,
            is_sync_in_progress,
            ensure_index,
        )
    except ImportError:
        return {"available": False, "indexed": 0, "total": 0, "syncing": False}
    if not is_available():
        return {"available": False, "indexed": 0, "total": 0, "syncing": False}
    try:
        client = _get_client()
        if not client or not ensure_index(client):
            return {"available": True, "indexed": 0, "total": 0, "syncing": is_sync_in_progress()}
        total = db.query(JobRow).count()
        count_resp = client.count(index=JOBS_INDEX)
        indexed = count_resp.get("count", 0)
        return {"available": True, "indexed": indexed, "total": total, "syncing": is_sync_in_progress()}
    except Exception:
        return {"available": True, "indexed": 0, "total": 0, "syncing": is_sync_in_progress()}


@router.delete("/embedding-index")
def clear_embedding_index():
    """Clear the Elasticsearch jobs index. Use before full re-index."""
    try:
        from app.services.elasticsearch_service import clear_index, is_available, is_sync_in_progress
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
    if is_sync_in_progress():
        raise api_error(
            "SYNC_IN_PROGRESS",
            "Embedding sync is already running. Please wait for it to complete.",
            status_code=409,
        )
    ok = clear_index()
    if not ok:
        raise api_error("CLEAR_FAILED", "Failed to clear embedding index", status_code=500)
    return {"cleared": True}


@router.post("/sync-embeddings/stream")
def sync_embeddings_stream(
    db: Session = Depends(get_db),
    mode: str = Query("incremental", description="full=clear+reindex all, incremental=add missing only"),
):
    """
    Index all jobs into Elasticsearch with SSE progress updates.
    Streams events: data: {"indexed": N, "total": M}\n\n and final data: {"done": true, "indexed": N, "total": M}\n\n
    """
    import json

    from fastapi.responses import StreamingResponse

    try:
        from app.services.elasticsearch_service import (
            bulk_index_jobs_stream,
            clear_index,
            get_jobs_not_indexed,
            is_available,
            is_sync_in_progress,
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
    if is_sync_in_progress():
        raise api_error(
            "SYNC_IN_PROGRESS",
            "Embedding sync is already running. Please wait for it to complete.",
            status_code=409,
        )
    ai_cfg = get_ai_config(db)
    rows = db.query(JobRow).all()

    if mode == "full":
        if not clear_index():
            raise api_error("CLEAR_FAILED", "Failed to clear embedding index", status_code=500)
        jobs_to_index = rows
    else:
        jobs_to_index = get_jobs_not_indexed(rows)
        if not jobs_to_index:
            async def empty_stream():
                yield f"data: {json.dumps({'done': True, 'indexed': 0, 'total': 0})}\n\n"
                await asyncio.sleep(0)
            return StreamingResponse(
                empty_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    async def stream_gen_async():
        for event in bulk_index_jobs_stream(jobs_to_index, embed_model=ai_cfg["embed_model"]):
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(0)  # Force flush to client

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

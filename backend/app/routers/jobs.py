import asyncio
import logging
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import func, or_, cast, Numeric, and_, tuple_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import api_error
from app.models.tables import JobRow, DetectedSkillRow
from app.parsers.base import format_category

SENIORITY_BLACKLIST = {"C-level"}
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


def _attach_detected_skills(items: list[dict], db: Session) -> None:
    """Batch-load detected skills for a page of jobs.

    For grouped results the representative row might not have detected skills
    but a sibling row (same company + title) might, so we look up skills from
    ALL rows sharing the same (company, lower(title)) group.
    """
    if not items:
        return

    from sqlalchemy import tuple_

    groups = list({(i["company"], i["title"].lower()) for i in items})

    title_l = func.lower(JobRow.title)
    rows = (
        db.query(JobRow.company, title_l, DetectedSkillRow.skill_name)
        .join(DetectedSkillRow, DetectedSkillRow.job_id == JobRow.id)
        .filter(
            DetectedSkillRow.skill_name != "",
            tuple_(JobRow.company, title_l).in_(groups),
        )
        .all()
    )

    by_group: dict[tuple[str, str], set[str]] = {}
    for company, tl, skill in rows:
        by_group.setdefault((company, tl), set()).add(skill)

    for item in items:
        key = (item["company"], item["title"].lower())
        item["detected_skills"] = sorted(by_group.get(key, set()))


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
    q = db.query(JobRow)

    if status:
        q = q.filter(JobRow.status == status)
    if saved is not None:
        q = q.filter(JobRow.saved == saved)
    if source:
        q = q.filter(JobRow.source.ilike(f"%{source}%"))
    if category:
        q = q.filter(JobRow.category == category)
    if seniority:
        parts = [s.strip() for s in seniority.split(",") if s.strip()]
        if len(parts) == 1:
            q = q.filter(JobRow.seniority.ilike(f"%{parts[0]}%"))
        else:
            q = q.filter(JobRow.seniority.in_(parts))
    if work_type:
        q = q.filter(JobRow.work_type.ilike(f"%{work_type}%"))
    if location:
        q = q.filter(JobRow.location.any(location))
    skill_list = [s.strip() for s in (skills or skill or "").split(",") if s.strip()]
    for s in skill_list:
        q = q.filter(
            or_(
                JobRow.skills_required.any(s),
                JobRow.skills_nice_to_have.any(s),
            )
        )
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                JobRow.title.ilike(pattern),
                JobRow.company.ilike(pattern),
                JobRow.description.ilike(pattern),
            )
        )
    if is_reposted is not None:
        q = q.filter(JobRow.is_reposted == is_reposted)

    if sort_by == "salary_desc":
        order = [JobRow.salary_max_pln.desc().nullslast(), JobRow.created_at.desc()]
    elif sort_by == "salary_asc":
        order = [JobRow.salary_min_pln.asc().nullslast(), JobRow.created_at.desc()]
    else:
        order = [JobRow.date_added.desc(), JobRow.created_at.desc()]

    title_l = func.lower(JobRow.title)

    # Pre-compute duplicate counts for all (company, title) groups
    dup_count_sq = (
        db.query(
            JobRow.company.label("dc_company"),
            func.lower(JobRow.title).label("dc_title"),
            func.count().label("dup_count"),
        )
        .group_by(JobRow.company, func.lower(JobRow.title))
        .subquery()
    )

    if group_duplicates:
        # DISTINCT ON (company, lower(title)) to get one representative per group
        rep_ids_sq = (
            q.with_entities(JobRow.id)
            .distinct(JobRow.company, title_l)
            .order_by(JobRow.company, title_l, JobRow.created_at.desc())
            .subquery()
        )

        total = db.query(func.count()).select_from(rep_ids_sq).scalar() or 0
        pages = max(1, (total + per_page - 1) // per_page)

        rows_q = (
            db.query(JobRow, dup_count_sq.c.dup_count)
            .outerjoin(
                dup_count_sq,
                and_(
                    JobRow.company == dup_count_sq.c.dc_company,
                    title_l == dup_count_sq.c.dc_title,
                ),
            )
            .filter(JobRow.id.in_(db.query(rep_ids_sq)))
            .order_by(*order)
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        items = []
        for row, dc in rows_q:
            d = row.to_dict()
            d["duplicate_count"] = dc or 1
            items.append(d)

        _attach_detected_skills(items, db)
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    # Normal (non-grouped) flow
    total = q.count()
    pages = max(1, (total + per_page - 1) // per_page)

    ids_subq = q.with_entities(JobRow.id).subquery()
    rows_q = (
        db.query(JobRow, dup_count_sq.c.dup_count)
        .outerjoin(
            dup_count_sq,
            and_(
                JobRow.company == dup_count_sq.c.dc_company,
                title_l == dup_count_sq.c.dc_title,
            ),
        )
        .filter(JobRow.id.in_(select(ids_subq.c.id)))
        .order_by(*order)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = []
    for row, dc in rows_q:
        d = row.to_dict()
        d["duplicate_count"] = dc or 1
        items.append(d)

    _attach_detected_skills(items, db)
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    rows = (
        db.query(JobRow.category)
        .filter(JobRow.category.isnot(None), JobRow.category != "")
        .distinct()
        .order_by(JobRow.category)
        .all()
    )
    return [r[0] for r in rows]


@router.get("/work-types")
def list_work_types(db: Session = Depends(get_db)):
    rows = (
        db.query(JobRow.work_type)
        .filter(JobRow.work_type.isnot(None), JobRow.work_type != "")
        .distinct()
        .order_by(JobRow.work_type)
        .all()
    )
    return [r[0] for r in rows]


@router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    rows = (
        db.query(func.unnest(JobRow.location).label("loc"))
        .group_by("loc")
        .order_by(func.count().desc())
        .limit(50)
        .all()
    )
    return [r[0] for r in rows]


@router.get("/seniorities")
def list_seniorities(db: Session = Depends(get_db)):
    rows = (
        db.query(JobRow.seniority)
        .filter(
            JobRow.seniority.isnot(None),
            JobRow.seniority != "",
            JobRow.seniority.notin_(SENIORITY_BLACKLIST),
        )
        .distinct()
        .order_by(JobRow.seniority)
        .all()
    )
    return [r[0] for r in rows]


@router.get("/top-skills")
def list_top_skills(top: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    """Return top N skill names for autocomplete."""
    from sqlalchemy import literal_column
    skill = func.unnest(JobRow.skills_required).label("skill")
    rows = (
        db.query(skill, func.count().label("cnt"))
        .select_from(JobRow)
        .group_by(literal_column("skill"))
        .order_by(func.count().desc())
        .limit(top)
        .all()
    )
    return [r[0] for r in rows]


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
    def _base():
        q = db.query(JobRow)
        if source:
            q = q.filter(JobRow.source.ilike(f"%{source}%"))
        if category:
            q = q.filter(JobRow.category == category)
        if seniority:
            parts = [s.strip() for s in seniority.split(",") if s.strip()]
            if len(parts) == 1:
                q = q.filter(JobRow.seniority.ilike(f"%{parts[0]}%"))
            else:
                q = q.filter(JobRow.seniority.in_(parts))
        if work_type:
            q = q.filter(JobRow.work_type.ilike(f"%{work_type}%"))
        if location:
            q = q.filter(JobRow.location.any(location))
        skill_list = [s.strip() for s in (skills or skill or "").split(",") if s.strip()]
        for s in skill_list:
            q = q.filter(
                or_(
                    JobRow.skills_required.any(s),
                    JobRow.skills_nice_to_have.any(s),
                )
            )
        if search:
            pattern = f"%{search}%"
            q = q.filter(
                or_(
                    JobRow.title.ilike(pattern),
                    JobRow.company.ilike(pattern),
                    JobRow.description.ilike(pattern),
                )
            )
        if is_reposted is not None:
            q = q.filter(JobRow.is_reposted == is_reposted)
        if saved is not None:
            q = q.filter(JobRow.saved == saved)
        return q

    base_q = _base()
    title_l = func.lower(JobRow.title)
    group_key = tuple_(JobRow.company, title_l)

    if group_duplicates:
        # One row per (company, title) with a representative status; then count by status.
        # Subquery avoids COUNT(DISTINCT (a,b)) which can be unreliable across DBs.
        status_subq = (
            base_q.with_entities(
                JobRow.company,
                title_l,
                func.max(JobRow.status).label("status"),
            )
            .group_by(JobRow.company, title_l)
            .subquery()
        )
        total = db.query(func.count()).select_from(status_subq).scalar() or 0
        status_rows = (
            db.query(status_subq.c.status, func.count())
            .group_by(status_subq.c.status)
            .all()
        )
        by_status = {r[0]: r[1] for r in status_rows}

        saved_subq = (
            base_q.filter(JobRow.saved.is_(True))
            .with_entities(JobRow.company, title_l)
            .distinct()
            .subquery()
        )
        saved_count = db.query(func.count()).select_from(saved_subq).scalar() or 0

        source_rows = (
            base_q.with_entities(JobRow.source, func.count(func.distinct(group_key)))
            .group_by(JobRow.source).all()
        )
        by_source = {r[0]: r[1] for r in source_rows}

        cat_rows = (
            base_q.with_entities(JobRow.category, func.count(func.distinct(group_key)))
            .filter(JobRow.category.isnot(None), JobRow.category != "")
            .group_by(JobRow.category)
            .order_by(func.count(func.distinct(group_key)).desc()).limit(20).all()
        )
        by_category = [{"category": r[0], "count": r[1]} for r in cat_rows]

        sen_rows = (
            base_q.with_entities(JobRow.seniority, func.count(func.distinct(group_key)))
            .filter(
                JobRow.seniority.isnot(None),
                JobRow.seniority != "",
                JobRow.seniority.notin_(SENIORITY_BLACKLIST),
            )
            .group_by(JobRow.seniority)
            .order_by(func.count(func.distinct(group_key)).desc()).all()
        )
        by_seniority = [{"seniority": r[0], "count": r[1]} for r in sen_rows]

        wt_rows = (
            base_q.with_entities(JobRow.work_type, func.count(func.distinct(group_key)))
            .filter(JobRow.work_type.isnot(None), JobRow.work_type != "")
            .group_by(JobRow.work_type)
            .order_by(func.count(func.distinct(group_key)).desc()).all()
        )
        by_work_type = [{"work_type": r[0], "count": r[1]} for r in wt_rows]

        reposted_count = (
            base_q.filter(JobRow.is_reposted.is_(True))
            .with_entities(func.count(func.distinct(group_key))).scalar() or 0
        )

        company_rows = (
            base_q.with_entities(JobRow.company, func.count(func.distinct(group_key)))
            .group_by(JobRow.company)
            .order_by(func.count(func.distinct(group_key)).desc()).limit(15).all()
        )
        top_companies = [{"company": r[0], "count": r[1]} for r in company_rows]

        # Salary: one avg per (company, title) then average across groups
        sal_subq = (
            base_q.filter(JobRow.salary_min_pln.isnot(None))
            .with_entities(
                group_key,
                func.avg(JobRow.salary_min_pln).label("am"),
                func.avg(JobRow.salary_max_pln).label("ax"),
                func.max(JobRow.category).label("cat"),
            )
            .group_by(JobRow.company, title_l)
            .subquery()
        )
        avg_min = db.query(func.avg(sal_subq.c.am)).scalar()
        avg_max = db.query(func.avg(sal_subq.c.ax)).scalar()
        sal_by_cat_q = (
            db.query(
                sal_subq.c.cat,
                func.round(cast(func.avg(sal_subq.c.am), Numeric), 0),
                func.round(cast(func.avg(sal_subq.c.ax), Numeric), 0),
            )
            .filter(sal_subq.c.cat.isnot(None), sal_subq.c.cat != "")
            .group_by(sal_subq.c.cat)
            .order_by(func.avg(sal_subq.c.ax).desc())
            .limit(15).all()
        )

        # Timeline: one date per (company, title) = min(date_added), then count by date
        timeline_subq = (
            base_q.filter(JobRow.date_added.isnot(None))
            .with_entities(group_key, func.min(JobRow.date_added).label("d"))
            .group_by(JobRow.company, title_l)
            .subquery()
        )
        timeline_rows = (
            db.query(timeline_subq.c.d, func.count())
            .group_by(timeline_subq.c.d)
            .order_by(timeline_subq.c.d).all()
        )
        added_over_time = [{"date": r[0], "count": r[1]} for r in timeline_rows]

        # Top locations: one row per (company, title) then unnest locations.
        # Use DISTINCT ON instead of min(id) since PostgreSQL has no min(uuid).
        id_subq = (
            base_q.with_entities(JobRow.id)
            .distinct(JobRow.company, title_l)
            .order_by(JobRow.company, title_l, JobRow.created_at.desc())
            .subquery()
        )
        loc_rows = (
            db.query(func.unnest(JobRow.location).label("loc"), func.count())
            .select_from(JobRow)
            .join(id_subq, JobRow.id == id_subq.c.id)
            .group_by("loc")
            .order_by(func.count().desc()).limit(15).all()
        )
        top_locations = [{"location": r[0], "count": r[1]} for r in loc_rows]
    else:
        total = base_q.count()

        status_rows = (
            base_q.with_entities(JobRow.status, func.count())
            .group_by(JobRow.status)
            .all()
        )
        by_status = {r[0]: r[1] for r in status_rows}

        saved_count = base_q.filter(JobRow.saved.is_(True)).count()

        source_rows = (
            base_q.with_entities(JobRow.source, func.count())
            .group_by(JobRow.source).all()
        )
        by_source = {r[0]: r[1] for r in source_rows}

        cat_rows = (
            base_q.with_entities(JobRow.category, func.count())
            .filter(JobRow.category.isnot(None), JobRow.category != "")
            .group_by(JobRow.category)
            .order_by(func.count().desc()).limit(20).all()
        )
        by_category = [{"category": r[0], "count": r[1]} for r in cat_rows]

        sen_rows = (
            base_q.with_entities(JobRow.seniority, func.count())
            .filter(
                JobRow.seniority.isnot(None),
                JobRow.seniority != "",
                JobRow.seniority.notin_(SENIORITY_BLACKLIST),
            )
            .group_by(JobRow.seniority)
            .order_by(func.count().desc()).all()
        )
        by_seniority = [{"seniority": r[0], "count": r[1]} for r in sen_rows]

        wt_rows = (
            base_q.with_entities(JobRow.work_type, func.count())
            .filter(JobRow.work_type.isnot(None), JobRow.work_type != "")
            .group_by(JobRow.work_type)
            .order_by(func.count().desc()).all()
        )
        by_work_type = [{"work_type": r[0], "count": r[1]} for r in wt_rows]

        avg_min = (
            base_q.with_entities(func.avg(JobRow.salary_min_pln))
            .filter(JobRow.salary_min_pln.isnot(None)).scalar()
        )
        avg_max = (
            base_q.with_entities(func.avg(JobRow.salary_max_pln))
            .filter(JobRow.salary_max_pln.isnot(None)).scalar()
        )

        sal_by_cat_q = (
            base_q.with_entities(
                JobRow.category,
                func.round(cast(func.avg(JobRow.salary_min_pln), Numeric), 0),
                func.round(cast(func.avg(JobRow.salary_max_pln), Numeric), 0),
            )
            .filter(
                JobRow.salary_min_pln.isnot(None),
                JobRow.category.isnot(None),
                JobRow.category != "",
            )
            .group_by(JobRow.category)
            .order_by(func.avg(JobRow.salary_max_pln).desc())
            .limit(15).all()
        )

        timeline_rows = (
            base_q.with_entities(JobRow.date_added, func.count())
            .filter(JobRow.date_added.isnot(None))
            .group_by(JobRow.date_added)
            .order_by(JobRow.date_added).all()
        )
        added_over_time = [{"date": r[0], "count": r[1]} for r in timeline_rows]

        company_rows = (
            _base().with_entities(JobRow.company, func.count())
            .group_by(JobRow.company)
            .order_by(func.count().desc()).limit(15).all()
        )
        top_companies = [{"company": r[0], "count": r[1]} for r in company_rows]

        loc_rows = (
            db.query(func.unnest(JobRow.location).label("loc"), func.count())
            .select_from(JobRow)
        )
        if seniority:
            loc_rows = loc_rows.filter(JobRow.seniority.ilike(f"%{seniority}%"))
        loc_rows = loc_rows.group_by("loc").order_by(func.count().desc()).limit(15).all()
        top_locations = [{"location": r[0], "count": r[1]} for r in loc_rows]

        reposted_count = base_q.filter(JobRow.is_reposted.is_(True)).count()

    return {
        "total_jobs": total,
        "by_status": by_status,
        "saved_count": saved_count,
        "by_source": by_source,
        "by_category": by_category,
        "by_seniority": by_seniority,
        "by_work_type": by_work_type,
        "salary_stats": {
            "avg_min_pln": round(avg_min, 0) if avg_min else None,
            "avg_max_pln": round(avg_max, 0) if avg_max else None,
            "by_category": [
                {"category": r[0], "avg_min": r[1], "avg_max": r[2]}
                for r in sal_by_cat_q
            ],
        },
        "added_over_time": added_over_time,
        "top_companies": top_companies,
        "top_locations": top_locations,
        "reposted_count": reposted_count,
    }


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
    rows = db.query(JobRow).all()
    indexed = bulk_index_jobs(rows)
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
        for event in bulk_index_jobs_stream(jobs_to_index):
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

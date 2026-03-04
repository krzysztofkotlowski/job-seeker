import logging
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import func, or_, cast, Numeric
from sqlalchemy.orm import Session

from app.database import get_db
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
        raise HTTPException(400, "Unsupported URL. Supported: justjoin.it, nofluffjobs.com")
    try:
        parsed = detect_and_parse(req.url)
        return parsed.model_dump()
    except Exception as e:
        raise HTTPException(502, f"Failed to parse URL: {e}")


@router.post("", status_code=201)
def create_job(job_data: JobCreate, db: Session = Depends(get_db)):
    existing = db.query(JobRow).filter(JobRow.url == job_data.url).first()
    if existing:
        raise HTTPException(
            409,
            detail={
                "message": "Job with this URL already exists",
                "existing_id": str(existing.id),
            },
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
    skill: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    is_reposted: Optional[bool] = Query(None),
    work_type: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(JobRow)

    if status:
        q = q.filter(JobRow.status == status)
    if source:
        q = q.filter(JobRow.source.ilike(f"%{source}%"))
    if category:
        q = q.filter(JobRow.category == category)
    if seniority:
        q = q.filter(JobRow.seniority.ilike(f"%{seniority}%"))
    if work_type:
        q = q.filter(JobRow.work_type.ilike(f"%{work_type}%"))
    if location:
        q = q.filter(JobRow.location.any(location))
    if skill:
        q = q.filter(
            or_(
                JobRow.skills_required.any(skill),
                JobRow.skills_nice_to_have.any(skill),
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

    total = q.count()
    pages = max(1, (total + per_page - 1) // per_page)

    if sort_by == "salary_desc":
        order = [JobRow.salary_max_pln.desc().nullslast(), JobRow.created_at.desc()]
    elif sort_by == "salary_asc":
        order = [JobRow.salary_min_pln.asc().nullslast(), JobRow.created_at.desc()]
    else:
        order = [JobRow.date_added.desc(), JobRow.created_at.desc()]

    rows = (
        q.order_by(*order)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "items": [r.to_dict() for r in rows],
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
        .filter(JobRow.seniority.isnot(None), JobRow.seniority != "")
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
    db: Session = Depends(get_db),
):
    def _base():
        q = db.query(JobRow)
        if seniority:
            q = q.filter(JobRow.seniority.ilike(f"%{seniority}%"))
        return q

    total = _base().count()

    status_rows = (
        _base().with_entities(JobRow.status, func.count())
        .group_by(JobRow.status).all()
    )
    by_status = {r[0]: r[1] for r in status_rows}

    source_rows = (
        _base().with_entities(JobRow.source, func.count())
        .group_by(JobRow.source).all()
    )
    by_source = {r[0]: r[1] for r in source_rows}

    cat_rows = (
        _base().with_entities(JobRow.category, func.count())
        .filter(JobRow.category.isnot(None), JobRow.category != "")
        .group_by(JobRow.category)
        .order_by(func.count().desc()).limit(20).all()
    )
    by_category = [{"category": r[0], "count": r[1]} for r in cat_rows]

    sen_rows = (
        _base().with_entities(JobRow.seniority, func.count())
        .filter(JobRow.seniority.isnot(None), JobRow.seniority != "")
        .group_by(JobRow.seniority)
        .order_by(func.count().desc()).all()
    )
    by_seniority = [{"seniority": r[0], "count": r[1]} for r in sen_rows]

    wt_rows = (
        _base().with_entities(JobRow.work_type, func.count())
        .filter(JobRow.work_type.isnot(None), JobRow.work_type != "")
        .group_by(JobRow.work_type)
        .order_by(func.count().desc()).all()
    )
    by_work_type = [{"work_type": r[0], "count": r[1]} for r in wt_rows]

    avg_min = (
        _base().with_entities(func.avg(JobRow.salary_min_pln))
        .filter(JobRow.salary_min_pln.isnot(None)).scalar()
    )
    avg_max = (
        _base().with_entities(func.avg(JobRow.salary_max_pln))
        .filter(JobRow.salary_max_pln.isnot(None)).scalar()
    )

    sal_by_cat_q = (
        _base().with_entities(
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
        _base().with_entities(JobRow.date_added, func.count())
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

    reposted_count = _base().filter(
        JobRow.is_reposted.is_(True)
    ).count()

    return {
        "total_jobs": total,
        "by_status": by_status,
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


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    row = db.query(JobRow).filter(JobRow.id == job_id).first()
    if not row:
        raise HTTPException(404, "Job not found")
    return row.to_dict()


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

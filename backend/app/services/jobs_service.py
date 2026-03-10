"""Jobs service: list, analytics, and query building logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, or_, cast, Numeric, and_, tuple_, select
from sqlalchemy.orm import Session

from app.models.tables import JobRow, DetectedSkillRow

SENIORITY_BLACKLIST = {"C-level"}


@dataclass
class ListJobsParams:
    """Parameters for listing jobs with filters and pagination."""

    page: int = 1
    per_page: int = 50
    status: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    seniority: Optional[str] = None
    skill: Optional[str] = None
    skills: Optional[str] = None
    search: Optional[str] = None
    is_reposted: Optional[bool] = None
    work_type: Optional[str] = None
    location: Optional[str] = None
    sort_by: Optional[str] = None
    group_duplicates: bool = False
    saved: Optional[bool] = None


@dataclass
class AnalyticsParams:
    """Parameters for analytics aggregation."""

    seniority: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    skill: Optional[str] = None
    skills: Optional[str] = None
    search: Optional[str] = None
    is_reposted: Optional[bool] = None
    work_type: Optional[str] = None
    location: Optional[str] = None
    saved: Optional[bool] = None
    group_duplicates: bool = False


def _apply_filters(q, params: ListJobsParams | AnalyticsParams):
    """Apply common filters to a JobRow query."""
    if hasattr(params, "status") and params.status:
        q = q.filter(JobRow.status == params.status)
    if params.saved is not None:
        q = q.filter(JobRow.saved == params.saved)
    if params.source:
        q = q.filter(JobRow.source.ilike(f"%{params.source}%"))
    if params.category:
        q = q.filter(JobRow.category == params.category)
    if params.seniority:
        parts = [s.strip() for s in params.seniority.split(",") if s.strip()]
        if len(parts) == 1:
            q = q.filter(JobRow.seniority.ilike(f"%{parts[0]}%"))
        else:
            q = q.filter(JobRow.seniority.in_(parts))
    if params.work_type:
        q = q.filter(JobRow.work_type.ilike(f"%{params.work_type}%"))
    if params.location:
        q = q.filter(JobRow.location.any(params.location))
    skill_list = [s.strip() for s in (params.skills or params.skill or "").split(",") if s.strip()]
    for s in skill_list:
        q = q.filter(
            or_(
                JobRow.skills_required.any(s),
                JobRow.skills_nice_to_have.any(s),
            )
        )
    if params.search:
        pattern = f"%{params.search}%"
        q = q.filter(
            or_(
                JobRow.title.ilike(pattern),
                JobRow.company.ilike(pattern),
                JobRow.description.ilike(pattern),
            )
        )
    if params.is_reposted is not None:
        q = q.filter(JobRow.is_reposted == params.is_reposted)
    return q


def _attach_detected_skills(items: list[dict], db: Session) -> None:
    """Batch-load detected skills for a page of jobs."""
    if not items:
        return

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


def duplicate_grouped_job_ids_subquery(query):
    """
    Return a subquery of representative JobRow ids using the same grouping
    logic as "Hide duplicates": newest row per (company, lower(title)).
    """
    title_l = func.lower(JobRow.title)
    return (
        query.with_entities(JobRow.id)
        .distinct(JobRow.company, title_l)
        .order_by(JobRow.company, title_l, JobRow.created_at.desc())
        .subquery()
    )


def list_jobs(db: Session, params: ListJobsParams) -> dict:
    """List jobs with filters, pagination, and optional duplicate grouping."""
    q = db.query(JobRow)
    q = _apply_filters(q, params)

    if params.sort_by == "salary_desc":
        order = [JobRow.salary_max_pln.desc().nullslast(), JobRow.created_at.desc()]
    elif params.sort_by == "salary_asc":
        order = [JobRow.salary_min_pln.asc().nullslast(), JobRow.created_at.desc()]
    else:
        order = [JobRow.date_added.desc(), JobRow.created_at.desc()]

    title_l = func.lower(JobRow.title)

    dup_count_sq = (
        db.query(
            JobRow.company.label("dc_company"),
            func.lower(JobRow.title).label("dc_title"),
            func.count().label("dup_count"),
        )
        .group_by(JobRow.company, func.lower(JobRow.title))
        .subquery()
    )

    if params.group_duplicates:
        rep_ids_sq = duplicate_grouped_job_ids_subquery(q)

        total = db.query(func.count()).select_from(rep_ids_sq).scalar() or 0
        pages = max(1, (total + params.per_page - 1) // params.per_page)

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
            .offset((params.page - 1) * params.per_page)
            .limit(params.per_page)
            .all()
        )
    else:
        total = q.count()
        pages = max(1, (total + params.per_page - 1) // params.per_page)

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
            .offset((params.page - 1) * params.per_page)
            .limit(params.per_page)
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
        "page": params.page,
        "per_page": params.per_page,
        "pages": pages,
    }


def get_analytics(db: Session, params: AnalyticsParams) -> dict:
    """Compute analytics aggregates (by_status, salary_stats, etc.)."""

    def _base():
        q = db.query(JobRow)
        return _apply_filters(q, params)

    base_q = _base()
    title_l = func.lower(JobRow.title)
    group_key = tuple_(JobRow.company, title_l)

    if params.group_duplicates:
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

        id_subq = (
            duplicate_grouped_job_ids_subquery(base_q)
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
        if params.seniority:
            loc_rows = loc_rows.filter(JobRow.seniority.ilike(f"%{params.seniority}%"))
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


def list_categories(db: Session) -> list[str]:
    """Return distinct job categories."""
    rows = (
        db.query(JobRow.category)
        .filter(JobRow.category.isnot(None), JobRow.category != "")
        .distinct()
        .order_by(JobRow.category)
        .all()
    )
    return [r[0] for r in rows]


def list_work_types(db: Session) -> list[str]:
    """Return distinct work types."""
    rows = (
        db.query(JobRow.work_type)
        .filter(JobRow.work_type.isnot(None), JobRow.work_type != "")
        .distinct()
        .order_by(JobRow.work_type)
        .all()
    )
    return [r[0] for r in rows]


def list_locations(db: Session) -> list[str]:
    """Return top 50 locations by job count."""
    rows = (
        db.query(func.unnest(JobRow.location).label("loc"))
        .group_by("loc")
        .order_by(func.count().desc())
        .limit(50)
        .all()
    )
    return [r[0] for r in rows]


def list_seniorities(db: Session) -> list[str]:
    """Return distinct seniorities excluding blacklist."""
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


def list_top_skills(db: Session, top: int = 50) -> list[str]:
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

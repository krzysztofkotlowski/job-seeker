from typing import Optional

from fastapi import APIRouter, Query, Depends
from sqlalchemy import func, literal_column
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tables import JobRow, DetectedSkillRow

router = APIRouter()


@router.get("/summary")
def skills_summary(
    top: int = Query(30, ge=1, le=500),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    base = db.query(JobRow)
    if category:
        base = base.filter(JobRow.category == category)

    total_jobs = base.count()

    req_skill = func.unnest(JobRow.skills_required).label("skill")
    req_q = db.query(req_skill, func.count().label("cnt")).select_from(JobRow)
    if category:
        req_q = req_q.filter(JobRow.category == category)
    req_all = req_q.group_by(literal_column("skill")).order_by(func.count().desc()).all()

    nice_skill = func.unnest(JobRow.skills_nice_to_have).label("skill")
    nice_q = db.query(nice_skill, func.count().label("cnt")).select_from(JobRow)
    if category:
        nice_q = nice_q.filter(JobRow.category == category)
    nice_all = nice_q.group_by(literal_column("skill")).order_by(func.count().desc()).all()

    required_map = {r[0]: r[1] for r in req_all}
    nice_map = {r[0]: r[1] for r in nice_all}
    all_skills: dict[str, int] = {}
    for s, c in required_map.items():
        all_skills[s] = all_skills.get(s, 0) + c
    for s, c in nice_map.items():
        all_skills[s] = all_skills.get(s, 0) + c

    sorted_skills = sorted(all_skills.items(), key=lambda x: x[1], reverse=True)
    total_skills = len(sorted_skills)

    offset = (page - 1) * per_page
    page_skills = sorted_skills[offset:offset + per_page]
    pages = max(1, (total_skills + per_page - 1) // per_page)

    return {
        "total_jobs": total_jobs,
        "total_skills": total_skills,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "top_skills": [
            {"skill": s, "count": c, "required_count": required_map.get(s, 0)}
            for s, c in page_skills
        ],
        "required_skills": [
            {"skill": s, "count": c} for s, c in req_all[:top]
        ],
        "nice_to_have_skills": [
            {"skill": s, "count": c} for s, c in nice_all[:top]
        ],
    }


@router.get("/detected")
def detected_skills(
    job_id: str = Query(..., description="Job UUID"),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(DetectedSkillRow)
        .filter(DetectedSkillRow.job_id == job_id)
        .order_by(DetectedSkillRow.skill_name)
        .all()
    )
    return [
        {"skill_name": r.skill_name, "source_field": r.source_field}
        for r in rows
    ]


@router.get("/match")
def skills_match(
    skills: str = Query(..., description="Comma-separated skill names"),
    db: Session = Depends(get_db),
):
    target_skills = {s.strip().lower() for s in skills.split(",") if s.strip()}
    if not target_skills:
        return []

    rows = db.query(JobRow).all()
    results = []
    for row in rows:
        job_skills = {
            s.lower()
            for s in (row.skills_required or []) + (row.skills_nice_to_have or [])
        }
        matched = target_skills & job_skills
        if matched:
            results.append({
                "job": row.to_dict(),
                "matched_skills": sorted(matched),
                "match_count": len(matched),
                "match_ratio": len(matched) / len(target_skills) if target_skills else 0,
            })

    results.sort(key=lambda x: x["match_count"], reverse=True)
    return results

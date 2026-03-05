"""Resume analysis service: match jobs and build by-category stats."""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.tables import JobRow


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def match_jobs_to_skills(db: Session, resume_skills: set[str]) -> list[dict]:
    """Return jobs with match_ratio and matched_skills, sorted by match_count desc."""
    target = {_normalize(s) for s in resume_skills if s and isinstance(s, str) and s.strip()}
    if not target:
        return []

    rows = db.query(JobRow).all()
    results = []
    for row in rows:
        raw_skills = (row.skills_required or []) + (row.skills_nice_to_have or [])
        job_skills = {_normalize(s) for s in raw_skills if s is not None and str(s).strip()}
        matched = target & job_skills
        if matched:
            raw_set = {_normalize(s): s for s in raw_skills if s}
            matched_display = sorted([raw_set.get(m, m) for m in matched])
            results.append({
                "job": row.to_dict(),
                "matched_skills": matched_display,
                "match_count": len(matched),
                "match_ratio": len(matched) / len(target) if target else 0,
            })

    results.sort(key=lambda x: x["match_count"], reverse=True)
    return results


def build_by_category(db: Session, extracted_skills: set[str]) -> list[dict]:
    """For each category, compute matching/unmatched skills with occurrence weights and match score 1-100."""
    extracted_lower = {_normalize(s) for s in extracted_skills if s}
    rows = db.query(JobRow).filter(
        JobRow.category.isnot(None),
        JobRow.category != "",
    ).all()

    cat_skill_weight: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cat_skill_required: dict[str, dict[str, bool]] = defaultdict(dict)
    skill_canonical: dict[str, dict[str, str]] = defaultdict(dict)
    cat_job_count: dict[str, int] = defaultdict(int)

    for row in rows:
        cat = (row.category or "").strip()
        if not cat:
            continue
        cat_job_count[cat] += 1
        for s in (row.skills_required or []):
            if not s:
                continue
            k = _normalize(s)
            cat_skill_weight[cat][k] += 1
            cat_skill_required[cat][k] = True
            if k not in skill_canonical[cat]:
                skill_canonical[cat][k] = s
        for s in (row.skills_nice_to_have or []):
            if not s:
                continue
            k = _normalize(s)
            cat_skill_weight[cat][k] += 1
            if k not in cat_skill_required[cat]:
                cat_skill_required[cat][k] = False
            if k not in skill_canonical[cat]:
                skill_canonical[cat][k] = s

    MIN_JOBS = 5
    out = []
    for cat in sorted(cat_job_count.keys()):
        if cat_job_count.get(cat, 0) < MIN_JOBS:
            continue
        weights = cat_skill_weight.get(cat, {})
        cano = skill_canonical.get(cat, {})
        total_weight = sum(weights.values())
        if total_weight == 0:
            out.append({
                "category": cat,
                "job_count": cat_job_count.get(cat, 0),
                "match_score": 0,
                "matching_skills": [],
                "skills_to_add": [],
            })
            continue

        matching = [(cano.get(k, k), w) for k, w in weights.items() if k in extracted_lower]
        to_add = [(cano.get(k, k), w) for k, w in weights.items() if k not in extracted_lower]

        matched_weight = sum(w for _, w in matching)
        match_score = min(100, max(0, round(matched_weight / total_weight * 100)))

        matching.sort(key=lambda x: -x[1])
        to_add.sort(key=lambda x: -x[1])

        out.append({
            "category": cat,
            "job_count": cat_job_count.get(cat, 0),
            "match_score": match_score,
            "matching_skills": [{"skill": s, "weight": w} for s, w in matching],
            "skills_to_add": [{"skill": s, "weight": w} for s, w in to_add],
        })

    return out

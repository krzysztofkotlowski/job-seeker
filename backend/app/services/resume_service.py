"""Resume analysis service: match jobs and build by-category stats."""

import logging
import os
from collections import defaultdict
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.tables import JobRow

log = logging.getLogger(__name__)

RAG_ENABLED = os.environ.get("RAG_ENABLED", "false").lower() in ("1", "true", "yes")

DEFAULT_MATCH_LIMIT = 100


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def match_jobs_to_skills(
    db: Session,
    resume_skills: set[str],
    limit: int | None = DEFAULT_MATCH_LIMIT,
) -> list[dict]:
    """
    Return jobs with match_ratio and matched_skills, sorted by match_count desc.

    limit: max number of matches to return (None = no limit). Default 100 to avoid
    returning excessive results when the job database is large.
    """
    target = {_normalize(s) for s in resume_skills if s and isinstance(s, str) and s.strip()}
    if not target:
        return []

    skill_list = [s.strip() for s in resume_skills if s and isinstance(s, str) and s.strip()]
    if not skill_list:
        return []

    q = db.query(JobRow).filter(
        or_(
            or_(*(JobRow.skills_required.any(s) for s in skill_list)),
            or_(*(JobRow.skills_nice_to_have.any(s) for s in skill_list)),
        )
    )
    rows = q.all()

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
    if limit is not None:
        results = results[:limit]
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


def retrieve_semantic_matches(
    db: Session,
    extracted_skills: set[str],
    top_k: int = 10,
    embed_model: str | None = None,
    ai_config: dict | None = None,
) -> list[dict]:
    """
    RAG: embed resume skills, kNN search in Elasticsearch, return matches with full job dict.
    Returns [] if RAG unavailable (ES or embeddings disabled).
    """
    try:
        from app.services.embedding_service import embed_text
        from app.services.elasticsearch_service import is_available, search_similar
    except ImportError:
        return []

    if not is_available():
        return []
    query_text = " ".join(sorted(extracted_skills)) if extracted_skills else ""
    if not query_text.strip():
        return []
    embedding = embed_text(query_text, model=embed_model, ai_config=ai_config)
    if not embedding:
        return []
    embed_dims = (ai_config or {}).get("embed_dims")
    hits = search_similar(query_embedding=embedding, top_k=top_k, embed_dims=embed_dims)
    if not hits:
        return []
    results = []
    for h in hits:
        job_id = h.get("job_id")
        if not job_id:
            continue
        try:
            uid = UUID(job_id) if isinstance(job_id, str) else job_id
        except (ValueError, TypeError):
            continue
        row = db.query(JobRow).filter(JobRow.id == uid).first()
        if row:
            results.append({
                "job": row.to_dict(),
                "matched_skills": [],
                "match_count": 0,
                "match_ratio": float(h.get("score", 0)),
                "semantic": True,
            })
    return results


def retrieve_hybrid_recommendations(
    db: Session,
    extracted_skills: set[str],
    top_k: int = 10,
    embed_model: str | None = None,
    ai_config: dict | None = None,
) -> list[dict]:
    """
    RAG: hybrid search (vector + keyword) in Elasticsearch, return job recommendations with URLs from DB.
    Returns [] if RAG unavailable (ES or embeddings disabled).
    """
    try:
        from app.services.embedding_service import embed_text
        from app.services.elasticsearch_service import is_available, search_hybrid
    except ImportError:
        return []

    if not is_available():
        return []
    query_text = " ".join(sorted(extracted_skills)) if extracted_skills else ""
    if not query_text.strip():
        return []
    embedding = embed_text(query_text, model=embed_model, ai_config=ai_config)
    if not embedding:
        return []
    embed_dims = (ai_config or {}).get("embed_dims")
    hits = search_hybrid(
        query_text=query_text,
        query_embedding=embedding,
        top_k=top_k,
        embed_dims=embed_dims,
    )
    if not hits:
        return []
    results = []
    for h in hits:
        job_id = h.get("job_id")
        if not job_id:
            continue
        try:
            uid = UUID(job_id) if isinstance(job_id, str) else job_id
        except (ValueError, TypeError):
            continue
        row = db.query(JobRow).filter(JobRow.id == uid).first()
        if row:
            job_dict = row.to_dict()
            results.append({
                "job": job_dict,
                "score": float(h.get("score", 0)),
            })
    return results


def merge_keyword_and_semantic_matches(
    keyword_matches: list[dict],
    semantic_matches: list[dict],
    max_total: int = 8,
) -> list[dict]:
    """
    Merge keyword and semantic matches, deduplicating by (title, company).
    Keyword matches come first (higher relevance).
    """
    seen: set[tuple[str, str]] = set()
    merged = []
    for m in keyword_matches:
        job = m.get("job") or {}
        key = (job.get("title", "") or "", job.get("company", "") or "")
        if key not in seen and key != ("", ""):
            seen.add(key)
            merged.append(m)
    for m in semantic_matches:
        job = m.get("job") or {}
        key = (job.get("title", "") or "", job.get("company", "") or "")
        if key not in seen and key != ("", ""):
            seen.add(key)
            merged.append(m)
        if len(merged) >= max_total:
            break
    return merged[:max_total]

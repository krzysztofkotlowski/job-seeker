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


def _keyword_fallback_hits(
    *,
    query_text: str,
    top_k: int,
    index_name: str | None,
) -> list[dict]:
    """Run Elasticsearch keyword search against the active managed index only."""
    try:
        from app.services.elasticsearch_service import search_keyword
    except ImportError:
        return []
    if not index_name:
        return []
    hits = search_keyword(query_text=query_text, top_k=top_k, index_name=index_name)
    if hits:
        log.info(
            "Resume recommendations: keyword fallback hits=%d (index=%s)",
            len(hits),
            index_name,
        )
    return hits


def _hydrate_hits_to_jobs(db: Session, hits: list[dict]) -> list[dict]:
    """Resolve Elasticsearch hits back to DB jobs, falling back to source fields when missing."""
    results: list[dict] = []
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
        else:
            job_dict = {
                "id": job_id,
                "title": h.get("title", ""),
                "company": h.get("company", ""),
                "url": h.get("url", ""),
                "category": h.get("category", ""),
            }
        results.append({"job": job_dict, "score": float(h.get("score", 0))})
    return results


def _active_embedding_context(db: Session, ai_config: dict | None = None) -> dict:
    """Resolve the active managed recommendation source and whether it is queryable."""
    try:
        from app.services.embedding_service import is_ollama_model_available
        from app.services.embedding_sync_service import resolve_active_recommendation_source
    except ImportError:
        return {
            "status": "reindex_required",
            "message": "Embedding sync services are unavailable.",
            "active_run": None,
            "active_run_meta": None,
            "active_index_name": None,
            "config_matches_active": False,
        }

    resolved = resolve_active_recommendation_source(db)
    if resolved.get("status") != "ok":
        return resolved

    active_run = resolved["active_run"]
    current_cfg = ai_config or {}
    if active_run.embed_source == "openai":
        api_key = (current_cfg.get("openai_api_key") or "").strip()
        if not api_key:
            resolved.update(
                {
                    "status": "active_embedding_unavailable",
                    "message": (
                        "The active recommendation index was built with OpenAI embeddings, "
                        "but no OpenAI API key is configured for query embeddings."
                    ),
                }
            )
            return resolved
        resolved["embed_ai_config"] = {
            "embed_source": "openai",
            "openai_api_key": api_key,
            "embed_dims": int(active_run.embed_dims or 0),
        }
        resolved["embed_model"] = active_run.embed_model
        return resolved

    if not is_ollama_model_available(active_run.embed_model):
        resolved.update(
            {
                "status": "active_embedding_unavailable",
                "message": (
                    f"The active embedding model '{active_run.embed_model}' is not available in Ollama."
                ),
            }
        )
        return resolved

    resolved["embed_ai_config"] = {
        "embed_source": "ollama",
        "embed_dims": int(active_run.embed_dims or 0),
    }
    resolved["embed_model"] = active_run.embed_model
    return resolved


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
    resolved = _active_embedding_context(db, ai_config=ai_config)
    if resolved.get("status") != "ok":
        log.info(
            "Resume semantic matches skipped: status=%s message=%s",
            resolved.get("status"),
            resolved.get("message"),
        )
        return []
    active_run = resolved["active_run"]
    active_index_name = resolved.get("active_index_name")
    embedding = embed_text(
        query_text,
        model=resolved.get("embed_model") or embed_model,
        ai_config=resolved.get("embed_ai_config"),
    )
    if not embedding:
        return []
    if len(embedding) != int(active_run.embed_dims or 0):
        log.warning(
            "Resume semantic matches: active run dims mismatch (run_id=%s, expected=%s, query=%s, index=%s)",
            active_run.id,
            active_run.embed_dims,
            len(embedding),
            active_index_name,
        )
        return []
    hits = search_similar(
        query_embedding=embedding,
        top_k=top_k,
        embed_dims=int(active_run.embed_dims or 0),
        index_name=active_index_name,
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
            results.append({
                "job": row.to_dict(),
                "matched_skills": [],
                "match_count": 0,
                "match_ratio": float(h.get("score", 0)),
                "semantic": True,
            })
    return results


def retrieve_hybrid_recommendations_response(
    db: Session,
    extracted_skills: set[str],
    top_k: int = 10,
    embed_model: str | None = None,
    ai_config: dict | None = None,
) -> dict:
    """
    RAG: query the active managed recommendation index, not config-derived legacy indices.
    Returns a structured response with status, message, and recommendation list.
    """
    try:
        from app.services.embedding_service import embed_text
        from app.services.elasticsearch_service import is_available, search_hybrid
    except ImportError:
        log.warning("Resume recommendations: RAG modules not available")
        return {
            "status": "reindex_required",
            "message": "Recommendation services are unavailable.",
            "recommendations": [],
            "active_run": None,
            "config_matches_active": False,
        }

    if not is_available():
        log.info("Resume recommendations: Elasticsearch unavailable")
        return {
            "status": "unavailable",
            "message": "Elasticsearch is unavailable.",
            "recommendations": [],
            "active_run": None,
            "config_matches_active": False,
        }
    query_text = " ".join(sorted(extracted_skills)) if extracted_skills else ""
    if not query_text.strip():
        return {
            "status": "ok",
            "message": None,
            "recommendations": [],
            "active_run": None,
            "config_matches_active": False,
        }

    resolved = _active_embedding_context(db, ai_config=ai_config)
    active_run = resolved.get("active_run")
    active_run_meta = resolved.get("active_run_meta")
    active_index_name = resolved.get("active_index_name")
    status = str(resolved.get("status") or "ok")
    log.info(
        "Resume recommendations: status=%s active_run_id=%s index=%s unique_only=%s model=%s dims=%s config_matches_active=%s query_len=%d",
        status,
        active_run_meta.get("id") if active_run_meta else None,
        active_index_name,
        active_run_meta.get("unique_only") if active_run_meta else None,
        active_run_meta.get("embed_model") if active_run_meta else None,
        active_run_meta.get("embed_dims") if active_run_meta else None,
        resolved.get("config_matches_active"),
        len(query_text),
    )

    if status != "ok":
        fallback_hits = _keyword_fallback_hits(
            query_text=query_text,
            top_k=top_k,
            index_name=active_index_name,
        )
        if fallback_hits:
            return {
                "status": "fallback",
                "message": resolved.get("message"),
                "recommendations": _hydrate_hits_to_jobs(db, fallback_hits),
                "active_run": active_run_meta,
                "config_matches_active": bool(resolved.get("config_matches_active")),
            }
        return {
            "status": status,
            "message": resolved.get("message"),
            "recommendations": [],
            "active_run": active_run_meta,
            "config_matches_active": bool(resolved.get("config_matches_active")),
        }

    embedding = embed_text(
        query_text,
        model=resolved.get("embed_model") or embed_model,
        ai_config=resolved.get("embed_ai_config"),
    )
    if not embedding:
        log.warning("Resume recommendations: query embedding failed for active index %s", active_index_name)
        fallback_hits = _keyword_fallback_hits(
            query_text=query_text,
            top_k=top_k,
            index_name=active_index_name,
        )
        if fallback_hits:
            return {
                "status": "fallback",
                "message": "Embedding query failed; using keyword fallback on the active index.",
                "recommendations": _hydrate_hits_to_jobs(db, fallback_hits),
                "active_run": active_run_meta,
                "config_matches_active": bool(resolved.get("config_matches_active")),
            }
        return {
            "status": "active_embedding_unavailable",
            "message": "Embedding query failed for the active recommendation index.",
            "recommendations": [],
            "active_run": active_run_meta,
            "config_matches_active": bool(resolved.get("config_matches_active")),
        }

    expected_dims = int(active_run.embed_dims or 0)
    if len(embedding) != expected_dims:
        log.warning(
            "Resume recommendations: active run dims mismatch (run_id=%s, expected=%d, query=%d, index=%s, config_matches_active=%s)",
            active_run.id,
            expected_dims,
            len(embedding),
            active_index_name,
            resolved.get("config_matches_active"),
        )
        fallback_hits = _keyword_fallback_hits(
            query_text=query_text,
            top_k=top_k,
            index_name=active_index_name,
        )
        if fallback_hits:
            return {
                "status": "fallback",
                "message": "Active embedding dimensions do not match the query model; using keyword fallback on the active index.",
                "recommendations": _hydrate_hits_to_jobs(db, fallback_hits),
                "active_run": active_run_meta,
                "config_matches_active": bool(resolved.get("config_matches_active")),
            }
        return {
            "status": "reindex_required",
            "message": "The active recommendation index uses a different embedding shape. Run a full rebuild.",
            "recommendations": [],
            "active_run": active_run_meta,
            "config_matches_active": bool(resolved.get("config_matches_active")),
        }

    hits = search_hybrid(
        query_text=query_text,
        query_embedding=embedding,
        top_k=top_k,
        embed_dims=expected_dims,
        index_name=active_index_name,
    )
    if not hits:
        fallback_hits = _keyword_fallback_hits(
            query_text=query_text,
            top_k=top_k,
            index_name=active_index_name,
        )
        if fallback_hits:
            log.warning(
                "Resume recommendations: hybrid empty on active index %s; using keyword fallback",
                active_index_name,
            )
            return {
                "status": "fallback",
                "message": "Hybrid search returned no vector hits; using keyword fallback on the active index.",
                "recommendations": _hydrate_hits_to_jobs(db, fallback_hits),
                "active_run": active_run_meta,
                "config_matches_active": bool(resolved.get("config_matches_active")),
            }
        if not fallback_hits:
            log.info(
                "Resume recommendations: no hits after hybrid+fallback (index=%s, embed_dims=%s, skills=%d)",
                active_index_name,
                expected_dims,
                len(extracted_skills),
            )
            return {
                "status": "ok",
                "message": None,
                "recommendations": [],
                "active_run": active_run_meta,
                "config_matches_active": bool(resolved.get("config_matches_active")),
            }

    results = _hydrate_hits_to_jobs(db, hits)
    log.info("Resume recommendations: hits=%d, kept=%d", len(hits), len(results))
    return {
        "status": "ok",
        "message": None,
        "recommendations": results,
        "active_run": active_run_meta,
        "config_matches_active": bool(resolved.get("config_matches_active")),
    }


def retrieve_hybrid_recommendations(
    db: Session,
    extracted_skills: set[str],
    top_k: int = 10,
    embed_model: str | None = None,
    ai_config: dict | None = None,
) -> list[dict]:
    """Backward-compatible wrapper returning only recommendation hits."""
    return retrieve_hybrid_recommendations_response(
        db,
        extracted_skills,
        top_k=top_k,
        embed_model=embed_model,
        ai_config=ai_config,
    ).get("recommendations", [])


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

"""Resume analysis: upload PDF, extract keywords (system skills only), match by job/category."""

import json
import logging
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, File, HTTPException, UploadFile, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user_optional, require_auth
from app.database import get_db
from app.models.resume import ResumeRecommendationsRequest, ResumeSummarizeRequest
from app.services.ai_config_service import get_ai_config
from app.services.inference_log_service import log_inference
from app.services.user_service import get_or_create_user
from app.models.tables import ResumeRow, UserRow
from app.services.llm_service import (
    OpenAIStreamError,
    summarize_resume_match,
    summarize_resume_match_stream,
)
from app.services.resume_keywords import extract_keywords_from_text, extract_text_from_pdf
from app.services.resume_llm_extraction import extract_skills_from_text_llm
from app.services.resume_service import (
    build_by_category,
    match_jobs_to_skills,
    merge_keyword_and_semantic_matches,
    retrieve_hybrid_recommendations_response,
    retrieve_semantic_matches,
    RAG_ENABLED,
)
from app.services.skill_detector import _get_known_skills

log = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


@router.get("/history")
def resume_history(
    user: Annotated[dict | None, Depends(require_auth)] = None,
    db: Session = Depends(get_db),
):
    """List authenticated user's past resume analyses (extracted skills, uploaded_at)."""
    if not user:
        return []
    db_user = db.query(UserRow).filter(UserRow.keycloak_id == user["sub"]).first()
    if not db_user:
        return []
    rows = db.query(ResumeRow).filter(ResumeRow.user_id == db_user.id).order_by(ResumeRow.uploaded_at.desc()).all()
    return [
        {
            "id": str(r.id),
            "filename": r.filename,
            "extracted_skills": r.extracted_skills or [],
            "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
        }
        for r in rows
    ]


@router.post("/analyze")
async def analyze_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Annotated[dict | None, Depends(get_current_user_optional)] = None,
):
    """
    Upload a resume PDF. Extracts keywords/skills from the text and returns job matches.
    """
    try:
        if not file.filename:
            raise HTTPException(400, "No file name")
        content = await file.read()
        if not content:
            raise HTTPException(400, "File is empty")
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)")

        filename_lower = (file.filename or "").lower()
        if not filename_lower.endswith(".pdf"):
            raise HTTPException(400, "Only PDF files are supported.")

        try:
            text = extract_text_from_pdf(content)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            log.exception("PDF extraction failed")
            raise HTTPException(400, f"PDF could not be read: {e!s}")

        try:
            known_skills = _get_known_skills(db)
            keywords = extract_keywords_from_text(text, known_skills=known_skills)
        except Exception as e:
            log.exception("Keyword extraction failed")
            raise HTTPException(400, f"Could not extract keywords: {e!s}") from e

        # LLM extraction (optional, merges with rule-based)
        try:
            ai_cfg = get_ai_config(db)
            llm_skills = await extract_skills_from_text_llm(text, ai_config=ai_cfg)
            if llm_skills:
                keywords = keywords | llm_skills
        except Exception as e:
            log.debug("LLM skill extraction skipped: %s", e)

        keywords_lower = {_normalize(k) for k in keywords if k}
        known_lower_to_canonical = {_normalize(s): s for s in known_skills if s}
        known_matches = {known_lower_to_canonical[k] for k in keywords_lower if k in known_lower_to_canonical}

        # Use known matches when available; else fall back to raw tokens for RAG/display
        if known_matches:
            extracted_skills = known_matches
        else:
            # Fallback: use raw tokens (cap at 50) when no known skills match
            raw_tokens = sorted(keywords - {""})[:50]
            extracted_skills = {t for t in raw_tokens if t and len(t) >= 2}

        if not extracted_skills:
            return {
                "extracted_skills": [],
                "match_count": 0,
                "matches": [],
                "by_category": [],
                "message": "No skills from the PDF matched our system (skills from scraped offers).",
            }

        # For keyword match and by_category we need known skills; use extracted when known_matches exist
        skills_for_match = known_matches if known_matches else extracted_skills

        keyword_matches = match_jobs_to_skills(db, skills_for_match)
        by_category = build_by_category(db, skills_for_match)

        # RAG: merge semantic matches when enabled (use full extracted_skills for richer query)
        if RAG_ENABLED:
            ai_cfg = get_ai_config(db)
            embed_model = ai_cfg["embed_model"] if ai_cfg.get("embed_source") != "openai" else None
            semantic_matches = retrieve_semantic_matches(
                db,
                extracted_skills,  # full set for semantic search
                top_k=10,
                embed_model=embed_model,
                ai_config=ai_cfg,
            )
            matches = merge_keyword_and_semantic_matches(
                keyword_matches, semantic_matches, max_total=8
            )
        else:
            matches = keyword_matches

        # Persist when user is authenticated
        if user:
            db_user = get_or_create_user(
                db,
                keycloak_id=user["sub"],
                email=user.get("email"),
                username=user.get("preferred_username"),
            )
            resume = ResumeRow(
                id=uuid.uuid4(),
                user_id=db_user.id,
                filename=file.filename or "resume.pdf",
                extracted_skills=sorted(extracted_skills),
            )
            db.add(resume)
            db.commit()

        message = None
        if not known_matches and extracted_skills:
            message = (
                "Skills extracted from PDF (no direct match in our job database). "
                "Using for recommendations and additional matching."
            )

        return {
            "extracted_skills": sorted(extracted_skills),
            "match_count": len(matches),
            "matches": matches,
            "by_category": by_category,
            "message": message,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Resume analyze failed")
        raise HTTPException(500, f"Resume analysis failed: {e!s}")


@router.post("/recommendations")
def resume_recommendations(
    body: ResumeRecommendationsRequest = Body(...),
    db: Session = Depends(get_db),
):
    """
    Fetch hybrid search (keyword + semantic) job recommendations for extracted skills.
    Used by the frontend after resume analyze when RAG is enabled.
    """
    extracted = set((body.extracted_skills or [])[:200])  # cap for safety
    return retrieve_hybrid_recommendations_response(
        db,
        extracted,
        top_k=10,
        ai_config=get_ai_config(db),
    )


@router.post("/summarize")
async def summarize_match(
    body: ResumeSummarizeRequest = Body(...),
    db: Session = Depends(get_db),
    user: Annotated[dict | None, Depends(get_current_user_optional)] = None,
):
    """
    Generate AI summary for resume-job match data. Call this on user request after analyze.
    Returns 503 if LLM is disabled or unavailable.
    Uses AI config from DB; model_override in body overrides for this request.
    """
    extracted_skills = body.extracted_skills or []
    matches = body.matches or []
    by_category = body.by_category or []
    ai_cfg = get_ai_config(db)
    model = (body.model_override or "").strip()
    if not model:
        model = ai_cfg["openai_llm_model"] if ai_cfg.get("provider") == "openai" else ai_cfg["llm_model"]

    start = time.perf_counter()
    try:
        summary, eval_count = await summarize_resume_match(
            extracted_skills,
            matches,
            by_category,
            ai_config=ai_cfg,
            model=model or None,
            max_tokens=ai_cfg["max_output_tokens"],
            temperature=ai_cfg["temperature"],
        )
    except OpenAIStreamError as e:
        raise HTTPException(503, str(e))
    latency_ms = int((time.perf_counter() - start) * 1000)

    if summary is None:
        msg = (
            "AI summary unavailable. "
            + ("Check your OpenAI API key and model." if ai_cfg.get("provider") == "openai" else "Ensure Ollama is running with a model (e.g. ollama pull phi3:mini).")
        )
        raise HTTPException(503, msg)

    user_id = None
    if user:
        db_user = get_or_create_user(
            db,
            keycloak_id=user["sub"],
            email=user.get("email"),
            username=user.get("preferred_username"),
        )
        user_id = db_user.id

    log_inference(
        db,
        model=model or ai_cfg["llm_model"],
        operation="summarize",
        latency_ms=latency_ms,
        output_tokens=eval_count,
        user_id=user_id,
    )

    return {"summary": summary}


@router.post("/summarize/stream")
async def summarize_match_stream(
    body: ResumeSummarizeRequest = Body(...),
    db: Session = Depends(get_db),
):
    """
    Stream AI summary as Server-Sent Events. Each event is a JSON object with a "chunk" field.
    Uses AI config from DB; model_override in body overrides for this request.
    """
    extracted_skills = body.extracted_skills or []
    matches = body.matches or []
    by_category = body.by_category or []
    ai_cfg = get_ai_config(db)
    model = (body.model_override or "").strip()
    if not model:
        model = ai_cfg["openai_llm_model"] if ai_cfg.get("provider") == "openai" else ai_cfg["llm_model"]

    async def generate():
        async for event in summarize_resume_match_stream(
            extracted_skills,
            matches,
            by_category,
            ai_config=ai_cfg,
            model=model or None,
            max_tokens=ai_cfg["max_output_tokens"],
            temperature=ai_cfg["temperature"],
        ):
            payload = json.dumps(event)
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

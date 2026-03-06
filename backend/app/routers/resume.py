"""Resume analysis: upload PDF, extract keywords (system skills only), match by job/category."""

import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, File, HTTPException, UploadFile, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user_optional, require_auth
from app.database import get_db
from app.models.tables import ResumeRow, UserRow
from app.services.llm_service import summarize_resume_match, summarize_resume_match_stream
from app.services.resume_keywords import extract_keywords_from_pdf
from app.services.resume_service import (
    build_by_category,
    match_jobs_to_skills,
    merge_keyword_and_semantic_matches,
    retrieve_semantic_matches,
    RAG_ENABLED,
)
from app.services.skill_detector import _get_known_skills
from app.services.user_service import get_or_create_user

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
            known_skills = _get_known_skills(db)
            keywords = extract_keywords_from_pdf(content, known_skills=known_skills)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            log.exception("PDF extraction failed")
            raise HTTPException(400, f"PDF could not be read: {e!s}")

        # Keep only skills that exist in our system (from scraped offers)
        keywords_lower = {_normalize(k) for k in keywords if k}
        known_lower_to_canonical = {_normalize(s): s for s in known_skills if s}
        extracted_skills = {known_lower_to_canonical[k] for k in keywords_lower if k in known_lower_to_canonical}

        if not extracted_skills:
            return {
                "extracted_skills": [],
                "match_count": 0,
                "matches": [],
                "by_category": [],
                "message": "No skills from the PDF matched our system (skills from scraped offers).",
            }

        keyword_matches = match_jobs_to_skills(db, extracted_skills)
        by_category = build_by_category(db, extracted_skills)

        # RAG: merge semantic matches when enabled
        if RAG_ENABLED:
            semantic_matches = retrieve_semantic_matches(db, extracted_skills, top_k=10)
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

        return {
            "extracted_skills": sorted(extracted_skills),
            "match_count": len(matches),
            "matches": matches,
            "by_category": by_category,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Resume analyze failed")
        raise HTTPException(500, f"Resume analysis failed: {e!s}")


@router.post("/summarize")
async def summarize_match(
    body: dict = Body(
        ...,
        examples=[{
            "extracted_skills": ["Python", "FastAPI"],
            "matches": [{"job": {"title": "Backend Dev", "company": "Acme"}, "matched_skills": ["Python"], "match_count": 1}],
            "by_category": [{"category": "Backend", "match_score": 80, "matching_skills": [], "skills_to_add": []}],
        }],
    ),
):
    """
    Generate AI summary for resume-job match data. Call this on user request after analyze.
    Returns 503 if LLM is disabled or unavailable.
    """
    extracted_skills = body.get("extracted_skills") or []
    matches = body.get("matches") or []
    by_category = body.get("by_category") or []
    summary = await summarize_resume_match(extracted_skills, matches, by_category)
    if summary is None:
        raise HTTPException(
            503,
            "AI summary unavailable. Ensure Ollama is running with a model (e.g. ollama pull tinyllama).",
        )
    return {"summary": summary}


@router.post("/summarize/stream")
async def summarize_match_stream(
    body: dict = Body(
        ...,
        examples=[{
            "extracted_skills": ["Python", "FastAPI"],
            "matches": [{"job": {"title": "Backend Dev", "company": "Acme", "url": "https://example.com/job/1"}, "matched_skills": ["Python"], "match_count": 1}],
            "by_category": [{"category": "Backend", "match_score": 80, "matching_skills": [], "skills_to_add": []}],
        }],
    ),
):
    """
    Stream AI summary as Server-Sent Events. Each event is a JSON object with a "chunk" field.
    """
    extracted_skills = body.get("extracted_skills") or []
    matches = body.get("matches") or []
    by_category = body.get("by_category") or []

    async def generate():
        async for chunk in summarize_resume_match_stream(extracted_skills, matches, by_category):
            payload = json.dumps({"chunk": chunk})
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

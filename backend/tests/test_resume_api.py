"""Tests for resume analysis API."""

from io import BytesIO
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.tables import ResumeRow, UserRow


def test_resume_analyze_no_skills_in_pdf(client: TestClient):
    """When PDF has no matching skills, return empty result."""
    with (
        patch("app.routers.resume.extract_text_from_pdf", return_value="fake pdf content"),
        patch("app.routers.resume.extract_keywords_from_text", return_value=set()),
        patch("app.routers.resume.extract_skills_from_text_llm", new_callable=AsyncMock, return_value=set()),
    ):
        pdf_content = b"%PDF-1.4 fake pdf content"
        files = {"file": ("resume.pdf", BytesIO(pdf_content), "application/pdf")}
        r = client.post("/api/v1/resume/analyze", files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["extracted_skills"] == []
    assert data["match_count"] == 0
    assert data["matches"] == []
    assert data["by_category"] == []
    assert "message" in data


def test_resume_analyze_with_skills(client: TestClient):
    """When PDF has matching skills, return matches and by_category."""
    with (
        patch("app.routers.resume.extract_text_from_pdf", return_value="Python Django experience"),
        patch("app.routers.resume.extract_keywords_from_text", return_value={"Python", "Django"}),
        patch("app.routers.resume.extract_skills_from_text_llm", new_callable=AsyncMock, return_value=set()),
        patch("app.routers.resume._get_known_skills", return_value={"Python", "Django", "React"}),
    ):
        pdf_content = b"%PDF-1.4 fake pdf"
        files = {"file": ("resume.pdf", BytesIO(pdf_content), "application/pdf")}
        r = client.post("/api/v1/resume/analyze", files=files)
    assert r.status_code == 200
    data = r.json()
    assert "Python" in data["extracted_skills"]
    assert "Django" in data["extracted_skills"]
    assert "extracted_skills" in data
    assert "matches" in data
    assert "by_category" in data


def test_resume_analyze_returns_without_summary(client: TestClient):
    """Analyze returns matches without summary (summary is on-demand)."""
    with (
        patch("app.routers.resume.extract_text_from_pdf", return_value="Python"),
        patch("app.routers.resume.extract_keywords_from_text", return_value={"Python"}),
        patch("app.routers.resume.extract_skills_from_text_llm", new_callable=AsyncMock, return_value=set()),
        patch("app.routers.resume._get_known_skills", return_value={"Python"}),
    ):
        files = {"file": ("resume.pdf", BytesIO(b"%PDF-1.4 x"), "application/pdf")}
        r = client.post("/api/v1/resume/analyze", files=files)
    assert r.status_code == 200
    data = r.json()
    assert "summary" not in data
    assert "Python" in data["extracted_skills"]


def test_resume_summarize_returns_summary(client: TestClient):
    """Summarize endpoint returns AI summary when LLM responds."""
    async def fake_summary(*_args, **_kwargs):
        return ("Your resume matches well with Backend positions.", 42)

    with patch("app.routers.resume.summarize_resume_match", side_effect=fake_summary):
        r = client.post(
            "/api/v1/resume/summarize",
            json={
                "extracted_skills": ["Python"],
                "matches": [{"job": {"title": "Backend", "company": "Acme"}, "matched_skills": ["Python"], "match_count": 1}],
                "by_category": [{"category": "Backend", "match_score": 80, "matching_skills": [], "skills_to_add": []}],
            },
        )
    assert r.status_code == 200
    assert r.json()["summary"] == "Your resume matches well with Backend positions."


def test_resume_summarize_503_when_llm_unavailable(client: TestClient):
    """Summarize returns 503 when LLM returns None."""
    with patch("app.routers.resume.summarize_resume_match", new_callable=AsyncMock, return_value=(None, None)):
        r = client.post(
            "/api/v1/resume/summarize",
            json={"extracted_skills": ["Python"], "matches": [], "by_category": []},
        )
    assert r.status_code == 503


def test_resume_summarize_stream_returns_sse(client: TestClient):
    """Summarize stream returns SSE with chunks."""
    async def fake_stream(*_args, **_kwargs):
        yield "Hello "
        yield "world."

    with patch("app.routers.resume.summarize_resume_match_stream", side_effect=fake_stream):
        r = client.post(
            "/api/v1/resume/summarize/stream",
            json={
                "extracted_skills": ["Python"],
                "matches": [{"job": {"title": "Backend", "company": "Acme", "url": "https://example.com/1"}, "matched_skills": ["Python"], "match_count": 1}],
                "by_category": [{"category": "Backend", "match_score": 80, "matching_skills": [], "skills_to_add": []}],
            },
        )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/event-stream")
    body = r.text
    assert "Hello " in body
    assert "world." in body


def test_resume_recommendations_returns_hybrid_response(client: TestClient):
    """Recommendations endpoint returns hybrid search response."""
    mock_response = {
        "status": "ok",
        "message": None,
        "recommendations": [
            {"job": {"id": "1", "title": "Backend Dev", "company": "Acme"}, "score": 0.9, "explanation": {}}
        ],
        "active_run": {"id": "run-1", "embed_model": "nomic-embed-text"},
        "config_matches_active": True,
    }
    with patch(
        "app.routers.resume.retrieve_hybrid_recommendations_response",
        return_value=mock_response,
    ):
        r = client.post(
            "/api/v1/resume/recommendations",
            json={"extracted_skills": ["Python", "Django"]},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["job"]["title"] == "Backend Dev"


def test_resume_analyze_rejects_non_pdf(client: TestClient):
    """Reject non-PDF files."""
    files = {"file": ("resume.txt", BytesIO(b"plain text"), "text/plain")}
    r = client.post("/api/v1/resume/analyze", files=files)
    assert r.status_code == 400


def test_resume_history_empty_without_auth(client: TestClient):
    """Resume history returns empty when auth is disabled (no user)."""
    r = client.get("/api/v1/resume/history")
    assert r.status_code == 200
    assert r.json() == []


def test_resume_analyze_works_without_login(client: TestClient):
    """Resume analyze works without any auth token (optional login for persistence only)."""
    with (
        patch("app.routers.resume.extract_text_from_pdf", return_value="Python"),
        patch("app.routers.resume.extract_keywords_from_text", return_value={"Python"}),
        patch("app.routers.resume.extract_skills_from_text_llm", new_callable=AsyncMock, return_value=set()),
        patch("app.routers.resume._get_known_skills", return_value={"Python"}),
    ):
        files = {"file": ("resume.pdf", BytesIO(b"%PDF-1.4 x"), "application/pdf")}
        r = client.post("/api/v1/resume/analyze", files=files)
    assert r.status_code == 200
    assert "Python" in r.json()["extracted_skills"]


def test_resume_analyze_persists_when_authenticated(client: TestClient, db: Session):
    """When user is authenticated, resume analysis is saved to DB."""
    from app.auth import get_current_user_optional
    from app.main import app

    def fake_user():
        return {"sub": "kc-123", "email": "test@example.com", "preferred_username": "test"}

    app.dependency_overrides[get_current_user_optional] = fake_user
    try:
        with (
            patch("app.routers.resume.extract_text_from_pdf", return_value="Python"),
            patch("app.routers.resume.extract_keywords_from_text", return_value={"Python"}),
            patch("app.routers.resume.extract_skills_from_text_llm", new_callable=AsyncMock, return_value=set()),
            patch("app.routers.resume._get_known_skills", return_value={"Python"}),
        ):
            files = {"file": ("my_resume.pdf", BytesIO(b"%PDF-1.4 x"), "application/pdf")}
            r = client.post("/api/v1/resume/analyze", files=files)
        assert r.status_code == 200
        user = db.query(UserRow).filter(UserRow.keycloak_id == "kc-123").first()
        assert user is not None
        resumes = db.query(ResumeRow).filter(ResumeRow.user_id == user.id).all()
        assert len(resumes) == 1
        assert resumes[0].filename == "my_resume.pdf"
        assert "Python" in resumes[0].extracted_skills
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)

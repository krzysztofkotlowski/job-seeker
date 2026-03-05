"""Tests for LLM summarization service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_service import summarize_resume_match


def test_summarize_resume_match_returns_none_when_disabled():
    """When LLM_URL is unset, return None."""
    with patch("app.services.llm_service.LLM_URL", ""):
        result = asyncio.run(summarize_resume_match(["Python"], [], []))
    assert result is None


def test_summarize_resume_match_returns_none_when_empty_input():
    """When all inputs are empty, return None."""
    with patch("app.services.llm_service.LLM_URL", "http://ollama:11434"):
        result = asyncio.run(summarize_resume_match([], [], []))
    assert result is None


def test_summarize_resume_match_returns_summary_when_llm_responds():
    """When LLM returns a response, return the summary text."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "Your skills align well with Backend roles."}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.llm_service.LLM_URL", "http://ollama:11434"),
        patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client),
    ):
        result = asyncio.run(
            summarize_resume_match(
                ["Python", "FastAPI"],
                [{"job": {"title": "Backend Dev", "company": "Acme"}, "matched_skills": ["Python"], "match_count": 1}],
                [{"category": "Backend", "match_score": 80, "matching_skills": [], "skills_to_add": []}],
            )
        )

    assert result == "Your skills align well with Backend roles."

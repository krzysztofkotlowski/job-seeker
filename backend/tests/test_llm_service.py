"""Tests for LLM summarization service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_service import DEFAULT_LLM_MODEL, LLMConfig, get_llm_config, summarize_resume_match


def test_summarize_resume_match_returns_none_when_disabled():
    """When LLM is disabled (no URL), return (None, None)."""
    empty_cfg = LLMConfig(url="", model=DEFAULT_LLM_MODEL, timeout=30, summarize_timeout=90, max_output_tokens=512)
    with patch("app.services.llm_service.get_llm_config", return_value=empty_cfg):
        summary, _ = asyncio.run(summarize_resume_match(["Python"], [], []))
    assert summary is None


def test_summarize_resume_match_returns_none_when_empty_input():
    """When all inputs are empty, return (None, None)."""
    summary, _ = asyncio.run(summarize_resume_match([], [], []))
    assert summary is None


def test_summarize_resume_match_returns_summary_when_llm_responds():
    """When LLM returns a response, return the summary text and eval_count."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {"content": "Your skills align well with Backend roles."},
        "eval_count": 42,
    }
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    cfg = LLMConfig(url="http://ollama:11434", model=DEFAULT_LLM_MODEL, timeout=30, summarize_timeout=90, max_output_tokens=512)
    with (
        patch("app.services.llm_service.get_llm_config", return_value=cfg),
        patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client),
    ):
        summary, eval_count = asyncio.run(
            summarize_resume_match(
                ["Python", "FastAPI"],
                [{"job": {"title": "Backend Dev", "company": "Acme"}, "matched_skills": ["Python"], "match_count": 1}],
                [{"category": "Backend", "match_score": 80, "matching_skills": [], "skills_to_add": []}],
            )
        )

    assert summary == "Your skills align well with Backend roles."
    assert eval_count == 42

"""Tests for cross-encoder reranker service."""

from unittest.mock import patch

from app.services.reranker_service import _job_to_text_for_rerank, rerank_hits


def test_rerank_hits_empty_input():
    """Return empty when hits is empty."""
    assert rerank_hits("Python", [], top_k=5) == []


def test_rerank_hits_empty_query():
    """Return top_k when query is empty."""
    hits = [{"job_id": "1", "title": "Backend", "company": "Acme"}]
    assert rerank_hits("", hits, top_k=5) == hits[:5]


def test_rerank_hits_skips_when_unavailable():
    """When CrossEncoder unavailable, return original hits[:top_k]."""
    hits = [
        {"job_id": "1", "title": "Backend", "company": "Acme"},
        {"job_id": "2", "title": "Frontend", "company": "Beta"},
    ]
    with patch("app.services.reranker_service._get_reranker", return_value=None):
        result = rerank_hits("Python backend", hits, top_k=1)
    assert len(result) == 1
    assert result[0]["job_id"] == "1"


def test_job_to_text_for_rerank():
    """Build text from hit fields."""
    hit = {
        "title": "Backend Dev",
        "company": "Acme",
        "category": "Backend",
        "skills_combined": "Python Django",
        "description": "We build APIs.",
    }
    text = _job_to_text_for_rerank(hit)
    assert "Backend Dev" in text
    assert "Acme" in text
    assert "Python Django" in text
    assert "We build APIs" in text


def test_job_to_text_for_rerank_minimal():
    """Handle minimal hit with missing fields."""
    hit = {"job_id": "1"}
    text = _job_to_text_for_rerank(hit)
    assert text == "unknown"

"""Tests for resume service RAG functions."""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Allow elasticsearch_service to load when elasticsearch is not installed
if "elasticsearch" not in sys.modules:
    sys.modules["elasticsearch"] = MagicMock()
    sys.modules["elasticsearch"].Elasticsearch = MagicMock()

from app.services.resume_service import (
    match_jobs_to_skills,
    merge_keyword_and_semantic_matches,
    retrieve_semantic_matches,
)


def test_match_jobs_to_skills_returns_matches_with_limit(db):
    """match_jobs_to_skills filters by skills and respects limit."""
    from app.models.tables import JobRow
    from uuid import uuid4

    for i in range(5):
        job = JobRow(
            id=uuid4(),
            url=f"https://example.com/job/{uuid4()}",
            source="test",
            title="Engineer",
            company=f"Company{i}",
            skills_required=["Python", "Django"] if i < 3 else ["Java"],
            skills_nice_to_have=[],
            date_added="2024-01-01",
        )
        db.add(job)
    db.commit()

    result = match_jobs_to_skills(db, {"Python", "Django"}, limit=2)
    assert len(result) == 2
    assert all("job" in m and "matched_skills" in m for m in result)
    assert result[0]["match_count"] >= result[1]["match_count"]


def test_match_jobs_to_skills_empty_skills_returns_empty(db):
    """match_jobs_to_skills returns [] when resume_skills is empty."""
    assert match_jobs_to_skills(db, set()) == []
    assert match_jobs_to_skills(db, {""}) == []


def test_merge_keyword_and_semantic_matches_dedup():
    """Merge deduplicates by (title, company), keyword matches first."""
    keyword = [
        {"job": {"title": "Dev", "company": "Acme", "url": "https://a.com"}, "matched_skills": ["Python"]},
    ]
    semantic = [
        {"job": {"title": "Dev", "company": "Acme", "url": "https://a.com"}, "semantic": True},
        {"job": {"title": "Engineer", "company": "Beta", "url": "https://b.com"}, "semantic": True},
    ]
    result = merge_keyword_and_semantic_matches(keyword, semantic, max_total=5)
    assert len(result) == 2
    assert result[0]["job"]["company"] == "Acme"
    assert result[1]["job"]["company"] == "Beta"


def test_merge_keyword_and_semantic_matches_respects_max_total():
    """Merge respects max_total limit."""
    keyword = [{"job": {"title": "A", "company": "X"}}]
    semantic = [
        {"job": {"title": "B", "company": "Y"}},
        {"job": {"title": "C", "company": "Z"}},
    ]
    result = merge_keyword_and_semantic_matches(keyword, semantic, max_total=2)
    assert len(result) == 2


def test_retrieve_semantic_matches_returns_empty_when_es_unavailable(db):
    """retrieve_semantic_matches returns [] when Elasticsearch is unavailable."""
    import app.services.elasticsearch_service as es_mod

    with patch.object(es_mod, "is_available", return_value=False):
        result = retrieve_semantic_matches(db, {"Python"}, top_k=5)
    assert result == []


def test_retrieve_semantic_matches_returns_matches(db):
    """retrieve_semantic_matches returns matches when ES and embed available."""
    from app.models.tables import JobRow
    from uuid import uuid4

    job_id = uuid4()
    job_url = f"https://example.com/job/{job_id}"
    job = JobRow(
        id=job_id,
        url=job_url,
        source="test",
        title="ML Engineer",
        company="Acme",
        skills_required=["Python"],
        skills_nice_to_have=[],
        date_added="2024-01-01",
    )
    db.add(job)
    db.commit()

    import app.services.elasticsearch_service as es_mod
    import app.services.embedding_service as embed_mod

    with (
        patch("app.services.resume_service.RAG_ENABLED", True),
        patch.object(embed_mod, "embed_text") as mock_embed,
        patch.object(es_mod, "is_available") as mock_avail,
        patch.object(es_mod, "search_similar") as mock_search,
    ):
        mock_avail.return_value = True
        mock_embed.return_value = [0.1] * 768
        mock_search.return_value = [
            {"job_id": str(job_id), "title": "ML Engineer", "company": "Acme", "url": job_url, "category": "AI", "score": 0.9},
        ]

        result = retrieve_semantic_matches(db, {"Python", "ML"}, top_k=5)
    assert len(result) == 1
    assert result[0]["job"]["title"] == "ML Engineer"
    assert result[0].get("semantic") is True

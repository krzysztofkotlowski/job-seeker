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
    retrieve_hybrid_recommendations,
    retrieve_semantic_matches,
)


def _create_active_run(
    db,
    *,
    embed_source: str = "ollama",
    embed_model: str = "all-minilm",
    embed_dims: int = 768,
):
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.models.tables import EmbeddingSyncRunRow

    row = EmbeddingSyncRunRow(
        id=uuid4(),
        status="completed",
        mode="full",
        unique_only=False,
        embed_source=embed_source,
        embed_model=embed_model,
        embed_dims=embed_dims,
        db_total_snapshot=1,
        selection_total=1,
        target_total=1,
        processed=1,
        indexed=1,
        failed=0,
        index_alias="jobseeker_jobs_active",
        physical_index_name="jobseeker_jobs_run_test",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        activated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


def _seed_category_jobs(db, *, category: str, skills: list[str], count: int = 5):
    from uuid import uuid4

    from app.models.tables import JobRow

    for idx in range(count):
        db.add(
            JobRow(
                id=uuid4(),
                url=f"https://example.com/{category.lower()}/{idx}-{uuid4()}",
                source="test",
                title=f"{category} Engineer {idx}",
                company=f"{category} Co {idx}",
                category=category,
                skills_required=skills,
                skills_nice_to_have=[],
                date_added="2024-01-01",
            )
        )
    db.commit()


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

    _create_active_run(db, embed_dims=768)

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
        patch.object(embed_mod, "is_ollama_model_ready", return_value=True),
        patch.object(es_mod, "is_available") as mock_avail,
        patch.object(es_mod, "search_similar") as mock_search,
        patch("app.services.embedding_sync_service.es_available", return_value=True),
        patch("app.services.embedding_sync_service.count_documents", return_value=1),
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
    mock_search.assert_called_once()
    assert mock_embed.call_args.kwargs["usage"] == "query"
    assert mock_search.call_args.kwargs["index_name"] == "jobseeker_jobs_active"


def test_retrieve_hybrid_recommendations_keyword_fallback_on_dims_mismatch(db):
    """Falls back to keyword search on the active managed index when dims mismatch."""
    from app.models.tables import JobRow
    from uuid import uuid4

    _create_active_run(db, embed_dims=768)

    job_id = uuid4()
    job_url = f"https://example.com/job/{job_id}"
    job = JobRow(
        id=job_id,
        url=job_url,
        source="test",
        title="Python Engineer",
        company="Acme",
        category="Backend",
        skills_required=["Python", "Kafka"],
        skills_nice_to_have=["AWS"],
        date_added="2024-01-01",
    )
    db.add(job)
    db.commit()

    import app.services.elasticsearch_service as es_mod
    import app.services.embedding_service as embed_mod

    with (
        patch.object(embed_mod, "embed_text", return_value=[0.1] * 1536),
        patch.object(embed_mod, "is_ollama_model_ready", return_value=True),
        patch.object(es_mod, "is_available", return_value=True),
        patch.object(es_mod, "search_hybrid", return_value=[]),
        patch.object(
            es_mod,
            "search_keyword",
            return_value=[
                {
                    "job_id": str(job_id),
                    "title": "Python Engineer",
                    "company": "Acme",
                    "url": job_url,
                    "category": "Backend",
                    "score": 0.7,
                }
            ],
        ) as mock_keyword,
    ):
        result = retrieve_hybrid_recommendations(
            db,
            {"Python"},
            top_k=5,
            ai_config={"embed_source": "openai", "embed_dims": 768},
        )

    assert len(result) == 1
    assert result[0]["job"]["title"] == "Python Engineer"
    assert result[0]["job"]["id"] == str(job_id)
    assert result[0]["score"] == pytest.approx(0.7)
    assert result[0]["explanation"]["sources"] == {"keyword": True, "semantic": False}
    assert result[0]["explanation"]["retrieval_reason"] == "keyword_match"
    assert result[0]["explanation"]["missing_skills"][:2] == ["Kafka", "AWS"]
    assert mock_keyword.call_count == 1
    assert mock_keyword.call_args.kwargs["index_name"] == "jobseeker_jobs_active"


def test_retrieve_hybrid_recommendations_keyword_fallback_when_embedding_fails(db):
    """When embedding fails, recommendations still come from Elasticsearch keyword search."""
    from app.models.tables import JobRow
    from uuid import uuid4

    _create_active_run(db, embed_dims=768)

    job_id = uuid4()
    job_url = f"https://example.com/job/{job_id}"
    job = JobRow(
        id=job_id,
        url=job_url,
        source="test",
        title="Platform Engineer",
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
        patch.object(embed_mod, "embed_text", return_value=None),
        patch.object(embed_mod, "is_ollama_model_ready", return_value=True),
        patch.object(es_mod, "is_available", return_value=True),
        patch.object(
            es_mod,
            "search_keyword",
            return_value=[
                {
                    "job_id": str(job_id),
                    "title": "Platform Engineer",
                    "company": "Acme",
                    "url": job_url,
                    "category": "Backend",
                    "score": 0.61,
                }
            ],
        ) as mock_keyword,
    ):
        result = retrieve_hybrid_recommendations(
            db,
            {"Python"},
            top_k=5,
            ai_config={"embed_source": "ollama", "embed_dims": 768},
        )

    assert len(result) == 1
    assert result[0]["job"]["title"] == "Platform Engineer"
    assert result[0]["job"]["id"] == str(job_id)
    assert result[0]["score"] == pytest.approx(0.61)
    assert mock_keyword.call_count == 1
    assert mock_keyword.call_args.kwargs["index_name"] == "jobseeker_jobs_active"


def test_retrieve_hybrid_recommendations_uses_active_run_metadata_when_config_changes(db):
    """Recommendations should query with active-run dims/index, not current config dims."""
    from app.models.tables import JobRow
    from uuid import uuid4

    _create_active_run(db, embed_dims=768)

    job_id = uuid4()
    job_url = f"https://example.com/job/{job_id}"
    job = JobRow(
        id=job_id,
        url=job_url,
        source="test",
        title="Data Platform Engineer",
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
        patch.object(embed_mod, "embed_text", return_value=[0.1] * 768),
        patch.object(embed_mod, "is_ollama_model_ready", return_value=True),
        patch.object(es_mod, "is_available", return_value=True),
        patch.object(
            es_mod,
            "search_hybrid",
            return_value=[
                {
                    "job_id": str(job_id),
                    "title": "Data Platform Engineer",
                    "company": "Acme",
                    "url": job_url,
                    "category": "Backend",
                    "score": 0.88,
                }
            ],
        ) as mock_hybrid,
        patch("app.services.embedding_sync_service.es_available", return_value=True),
        patch("app.services.embedding_sync_service.count_documents", return_value=1),
    ):
        result = retrieve_hybrid_recommendations(
            db,
            {"Python"},
            top_k=5,
            ai_config={"embed_source": "ollama", "embed_model": "all-minilm", "embed_dims": 384},
        )

    assert len(result) == 1
    assert result[0]["job"]["title"] == "Data Platform Engineer"
    assert result[0]["score"] == pytest.approx(0.88)
    assert mock_hybrid.call_args.kwargs["embed_dims"] == 768
    assert mock_hybrid.call_args.kwargs["index_name"] == "jobseeker_jobs_active"


def test_retrieve_hybrid_recommendations_includes_explanation_for_hybrid_hits(db):
    """Hybrid recommendations expose explainability details for UI rendering."""
    from app.models.tables import JobRow
    from uuid import uuid4

    _create_active_run(db, embed_dims=768)
    _seed_category_jobs(db, category="Backend", skills=["Python", "Docker"], count=4)

    job_id = uuid4()
    job_url = f"https://example.com/job/{job_id}"
    job = JobRow(
        id=job_id,
        url=job_url,
        source="test",
        title="Senior Backend Engineer",
        company="Acme",
        category="Backend",
        skills_required=["Python", "Kafka"],
        skills_nice_to_have=["Docker", "AWS"],
        date_added="2024-01-01",
    )
    db.add(job)
    db.commit()

    import app.services.elasticsearch_service as es_mod
    import app.services.embedding_service as embed_mod

    with (
        patch.object(embed_mod, "embed_text", return_value=[0.1] * 768),
        patch.object(embed_mod, "is_ollama_model_ready", return_value=True),
        patch.object(es_mod, "is_available", return_value=True),
        patch.object(
            es_mod,
            "search_hybrid",
            return_value=[
                {
                    "job_id": str(job_id),
                    "title": "Senior Backend Engineer",
                    "company": "Acme",
                    "url": job_url,
                    "category": "Backend",
                    "score": 0.88,
                    "keyword_score": 4.2,
                    "semantic_score": 0.92,
                    "keyword_rank": 1,
                    "semantic_rank": 2,
                    "sources": {"keyword": True, "semantic": True},
                }
            ],
        ),
        patch("app.services.embedding_sync_service.es_available", return_value=True),
        patch("app.services.embedding_sync_service.count_documents", return_value=1),
    ):
        result = retrieve_hybrid_recommendations(
            db,
            {"Python", "Docker"},
            top_k=5,
            ai_config={"embed_source": "ollama", "embed_model": "all-minilm", "embed_dims": 768},
        )

    assert len(result) == 1
    explanation = result[0]["explanation"]
    assert explanation["retrieval_reason"] == "hybrid_match"
    assert explanation["sources"] == {"keyword": True, "semantic": True}
    assert explanation["matched_skills"] == ["Python", "Docker"]
    assert explanation["missing_skills"][:2] == ["Kafka", "AWS"]
    assert explanation["category_overlap"]["category"] == "Backend"
    assert explanation["category_overlap"]["match_score"] > 0
    assert explanation["keyword_rank"] == 1
    assert explanation["semantic_rank"] == 2
    assert "Matched 2 resume skills" in explanation["summary"]

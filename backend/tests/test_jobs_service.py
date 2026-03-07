"""Tests for jobs service."""

from uuid import uuid4

from app.models.tables import JobRow
from app.services import jobs_service


def test_list_jobs_paginated_structure(db):
    """list_jobs returns valid paginated structure."""
    params = jobs_service.ListJobsParams(page=1, per_page=10)
    result = jobs_service.list_jobs(db, params)
    assert "items" in result
    assert "total" in result
    assert "page" in result
    assert "per_page" in result
    assert "pages" in result
    assert result["page"] == 1
    assert result["per_page"] == 10
    assert isinstance(result["items"], list)


def test_list_jobs_with_filters(db):
    """list_jobs filters by search and returns matching job."""
    unique_title = f"UniqueTitleXYZ{uuid4().hex[:8]}"
    job = JobRow(
        id=uuid4(),
        url=f"https://example.com/job/{uuid4()}",
        source="test",
        title=unique_title,
        company="Acme",
        skills_required=["Python"],
        skills_nice_to_have=[],
        date_added="2024-01-01",
        status="new",
    )
    db.add(job)
    db.commit()

    params = jobs_service.ListJobsParams(
        page=1, per_page=10, status="new", search=unique_title
    )
    result = jobs_service.list_jobs(db, params)
    assert result["total"] >= 1
    assert any(i["title"] == unique_title for i in result["items"])


def test_get_analytics_structure(db):
    """get_analytics returns valid structure with required keys."""
    params = jobs_service.AnalyticsParams()
    result = jobs_service.get_analytics(db, params)
    assert "total_jobs" in result
    assert "by_status" in result
    assert "saved_count" in result
    assert isinstance(result["by_status"], dict)
    assert isinstance(result["saved_count"], int)


def test_get_analytics_with_jobs(db):
    """get_analytics returns correct counts for added jobs."""
    for i in range(3):
        job = JobRow(
            id=uuid4(),
            url=f"https://example.com/job/{uuid4()}",
            source="justjoin.it",
            title="Engineer",
            company="Acme",
            skills_required=[],
            skills_nice_to_have=[],
            date_added="2024-01-01",
            status="new" if i < 2 else "seen",
        )
        db.add(job)
    db.commit()

    params = jobs_service.AnalyticsParams(source="justjoin.it")
    result = jobs_service.get_analytics(db, params)
    assert result["total_jobs"] >= 3
    assert result["by_status"].get("new", 0) >= 2
    assert result["by_status"].get("seen", 0) >= 1


def test_list_categories(db):
    """list_categories returns distinct categories."""
    for i, cat in enumerate(["Backend", "Frontend", "Backend"]):
        job = JobRow(
            id=uuid4(),
            url=f"https://example.com/{cat}-{uuid4()}",
            source="test",
            title="Dev",
            company="Acme",
            category=cat,
            skills_required=[],
            skills_nice_to_have=[],
            date_added="2024-01-01",
        )
        db.add(job)
    db.commit()

    cats = jobs_service.list_categories(db)
    assert cats == ["Backend", "Frontend"]


def test_list_top_skills(db):
    """list_top_skills returns top skill names."""
    job = JobRow(
        id=uuid4(),
        url=f"https://example.com/{uuid4()}",
        source="test",
        title="Dev",
        company="Acme",
        skills_required=["Python", "Python", "Django"],
        skills_nice_to_have=[],
        date_added="2024-01-01",
    )
    db.add(job)
    db.commit()

    skills = jobs_service.list_top_skills(db, top=5)
    assert "Python" in skills
    assert "Django" in skills

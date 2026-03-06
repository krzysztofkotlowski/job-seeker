from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models.job import JobBase


def test_create_and_get_job(client: TestClient):
    payload = {
        "url": "https://example.com/job/123",
        "source": "justjoin.it",
        "title": "Senior Backend Engineer",
        "company": "Acme Corp",
        "location": ["Remote"],
        "salary": None,
        "skills_required": ["Python"],
        "skills_nice_to_have": [],
        "seniority": "Senior",
        "work_type": "Remote",
        "employment_types": [],
        "description": "Great job",
        "category": "Backend",
        "date_published": None,
        "date_expires": None,
    }
    r = client.post("/api/v1/jobs", json=payload)
    assert r.status_code == 201, r.text
    job = r.json()
    job_id = job["id"]

    # Creating with the same URL should return a structured conflict error.
    r_dup = client.post("/api/v1/jobs", json=payload)
    assert r_dup.status_code == 409
    body = r_dup.json()
    assert body["error"]["code"] == "JOB_ALREADY_EXISTS"
    assert "existing_id" in body["error"]["details"]

    # Fetch job and verify default fields.
    r_get = client.get(f"/api/v1/jobs/{job_id}")
    assert r_get.status_code == 200
    fetched = r_get.json()
    assert fetched["url"] == payload["url"]
    assert fetched["status"] == "new"
    assert fetched["saved"] is False


def test_list_jobs_filters_and_analytics(client: TestClient):
    # Ensure there is at least one job.
    r = client.get("/api/v1/jobs", params={"page": 1, "per_page": 50})
    assert r.status_code == 200
    data = r.json()
    assert "items" in data

    # Analytics should return counts, and respect simple filter.
    r_analytics = client.get("/api/v1/jobs/analytics")
    assert r_analytics.status_code == 200
    analytics = r_analytics.json()
    assert "by_status" in analytics

    r_filtered = client.get("/api/v1/jobs/analytics", params={"source": "justjoin.it"})
    assert r_filtered.status_code == 200
    filtered = r_filtered.json()
    assert "by_status" in filtered

    # Analytics with group_duplicates=true (hide duplicates) must return valid counts
    r_grouped = client.get("/api/v1/jobs/analytics", params={"group_duplicates": True})
    assert r_grouped.status_code == 200, r_grouped.text
    grouped = r_grouped.json()
    assert "by_status" in grouped
    assert "total_jobs" in grouped
    assert isinstance(grouped["by_status"], dict)


def test_enrich_job(client: TestClient):
    """Create job with empty description, enrich via mock."""
    payload = {
        "url": "https://justjoin.it/job-offer/test-enrich",
        "source": "justjoin.it",
        "title": "Backend Dev",
        "company": "Test Corp",
        "location": [],
        "salary": None,
        "skills_required": ["Python"],
        "skills_nice_to_have": [],
        "seniority": "Mid",
        "work_type": "Remote",
        "employment_types": [],
        "description": "",
        "category": "Backend",
        "date_published": None,
        "date_expires": None,
    }
    r = client.post("/api/v1/jobs", json=payload)
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]

    # Enrich without mock: unsupported URL in test env would fail; we mock the parser
    mock_parsed = JobBase(
        url=payload["url"],
        source="justjoin.it",
        title=payload["title"],
        company=payload["company"],
        location=[],
        salary=None,
        skills_required=["Python", "Django"],
        skills_nice_to_have=["Redis", "Docker"],
        seniority="Mid",
        work_type="Remote",
        employment_types=[],
        description="We are looking for a Python developer.",
        category="Backend",
        date_published=None,
        date_expires=None,
    )

    with patch("app.parsers.detector.detect_and_parse", return_value=mock_parsed):
        r_enrich = client.post(f"/api/v1/jobs/{job_id}/enrich")
    assert r_enrich.status_code == 200, r_enrich.text
    enriched = r_enrich.json()
    assert enriched["description"] == "We are looking for a Python developer."
    assert enriched["skills_required"] == ["Python", "Django"]
    assert enriched["skills_nice_to_have"] == ["Redis", "Docker"]


def test_sync_embeddings_503_when_elasticsearch_unavailable(client: TestClient):
    """Sync-embeddings returns 503 when Elasticsearch is not reachable or not configured."""
    try:
        import app.services.elasticsearch_service as es_mod
        with patch.object(es_mod, "is_available", return_value=False):
            r = client.post("/api/v1/jobs/sync-embeddings")
    except ImportError:
        r = client.post("/api/v1/jobs/sync-embeddings")
    assert r.status_code == 503


def test_sync_embeddings_returns_indexed_when_available(client: TestClient, db):
    """Sync-embeddings returns indexed count when ES is available."""
    from app.models.tables import JobRow
    from uuid import uuid4

    job = JobRow(
        id=uuid4(),
        url="https://example.com/job/sync-test",
        source="test",
        title="Dev",
        company="Acme",
        skills_required=["Python"],
        skills_nice_to_have=[],
        date_added="2024-01-01",
    )
    db.add(job)
    db.commit()

    with (
        patch("app.services.elasticsearch_service.is_available", return_value=True),
        patch("app.services.elasticsearch_service.bulk_index_jobs", return_value=1),
    ):
        r = client.post("/api/v1/jobs/sync-embeddings")
    assert r.status_code == 200
    data = r.json()
    assert data["indexed"] == 1
    assert data["total"] >= 1


def test_enrich_batch_missing_ids(client: TestClient):
    r = client.post("/api/v1/jobs/enrich")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "MISSING_IDS"


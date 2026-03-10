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
    """Sync-embeddings queues a persistent full run when ES is available."""
    from app.models.tables import EmbeddingSyncRunRow, JobRow
    from uuid import uuid4

    db.query(EmbeddingSyncRunRow).delete(synchronize_session=False)
    db.commit()

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

    fake_task = type("Task", (), {"id": "celery-1"})()
    with (
        patch("app.services.elasticsearch_service.is_available", return_value=True),
        patch("app.routers.jobs.run_embedding_sync.delay", return_value=fake_task),
    ):
        r = client.post("/api/v1/jobs/sync-embeddings")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "queued"
    assert data["mode"] == "full"
    assert data["selection_total"] >= 1
    assert data["target_total"] >= 1
    assert data["celery_task_id"] == "celery-1"


def test_sync_embeddings_unique_only_dedupes_by_company_title(client: TestClient, db):
    """unique_only snapshots the same grouped selection as jobs list duplicate hiding."""
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from app.models.tables import EmbeddingSyncRunRow, JobRow

    # Isolate from prior tests because this suite shares one DB across cases.
    db.query(EmbeddingSyncRunRow).delete(synchronize_session=False)
    db.query(JobRow).delete(synchronize_session=False)
    db.commit()

    older = datetime.now(timezone.utc) - timedelta(days=1)
    newer = datetime.now(timezone.utc)

    same_a = JobRow(
        id=uuid4(),
        url=f"https://example.com/job/{uuid4()}",
        source="test",
        title="Backend Engineer",
        company="Acme",
        skills_required=["Python"],
        skills_nice_to_have=[],
        is_reposted=False,
        date_added="2024-01-01",
        created_at=older,
    )
    same_b = JobRow(
        id=uuid4(),
        url=f"https://example.com/job/{uuid4()}",
        source="test",
        title="Backend Engineer",
        company="Acme",
        skills_required=["Python"],
        skills_nice_to_have=[],
        is_reposted=False,
        date_added="2024-01-01",
        created_at=newer,
    )
    other = JobRow(
        id=uuid4(),
        url=f"https://example.com/job/{uuid4()}",
        source="test",
        title="Data Engineer",
        company="Beta",
        skills_required=["SQL"],
        skills_nice_to_have=[],
        is_reposted=False,
        date_added="2024-01-01",
        created_at=newer,
    )
    db.add_all([same_a, same_b, other])
    db.commit()

    fake_task = type("Task", (), {"id": "celery-2"})()
    with (
        patch("app.services.elasticsearch_service.is_available", return_value=True),
        patch("app.routers.jobs.run_embedding_sync.delay", return_value=fake_task),
    ):
        r = client.post("/api/v1/jobs/sync-embeddings", params={"unique_only": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "queued"
    assert data["mode"] == "full"
    assert data["unique_only"] is True
    assert data["selection_total"] == 2
    assert data["target_total"] == 2


def test_sync_embeddings_normalizes_stale_ollama_dims_before_queueing(client: TestClient, db):
    """Starting sync should heal stale Ollama embed_dims before queueing the run."""
    from uuid import uuid4

    from app.models.tables import AIConfigRow, EmbeddingSyncRunRow, JobRow

    db.query(EmbeddingSyncRunRow).delete(synchronize_session=False)
    db.query(AIConfigRow).delete(synchronize_session=False)
    db.commit()

    db.add(
        AIConfigRow(
            id=1,
            provider="ollama",
            embed_source="ollama",
            llm_model="qwen2.5:7b",
            embed_model="nomic-embed-text",
            embed_dims=384,
            temperature=0.3,
            max_output_tokens=1024,
        )
    )
    db.add(
        JobRow(
            id=uuid4(),
            url=f"https://example.com/job/{uuid4()}",
            source="test",
            title="Backend Engineer",
            company="Acme",
            skills_required=["Python"],
            skills_nice_to_have=[],
            date_added="2024-01-01",
        )
    )
    db.commit()

    fake_task = type("Task", (), {"id": "celery-3"})()
    with (
        patch("app.services.elasticsearch_service.is_available", return_value=True),
        patch("app.services.ai_config_service.get_ollama_embedding_dims", return_value=768),
        patch("app.routers.jobs.run_embedding_sync.delay", return_value=fake_task),
    ):
        r = client.post("/api/v1/jobs/sync-embeddings", params={"mode": "full"})

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["embed_model"] == "nomic-embed-text"
    assert data["embed_dims"] == 768

    db.refresh(db.query(AIConfigRow).filter(AIConfigRow.id == 1).one())
    assert db.query(AIConfigRow).filter(AIConfigRow.id == 1).one().embed_dims == 768


def test_embedding_status_returns_persistent_run_progress(client: TestClient, db):
    """embedding-status should report DB-backed run progress and active-index metadata."""
    from datetime import datetime, timezone
    from uuid import uuid4
    from app.models.tables import EmbeddingSyncRunRow, JobRow

    db.query(EmbeddingSyncRunRow).delete(synchronize_session=False)
    db.commit()

    job = JobRow(
        id=uuid4(),
        url=f"https://example.com/job/{uuid4()}",
        source="test",
        title="Platform Engineer",
        company="Acme",
        skills_required=["Python"],
        skills_nice_to_have=[],
        date_added="2024-01-01",
    )
    db.add(job)
    run = EmbeddingSyncRunRow(
        id=uuid4(),
        status="running",
        mode="full",
        unique_only=True,
        embed_source="ollama",
        embed_model="all-minilm",
        embed_dims=384,
        db_total_snapshot=1,
        selection_total=11783,
        target_total=11783,
        processed=96,
        indexed=96,
        failed=0,
        index_alias="jobseeker_jobs_active",
        physical_index_name="jobseeker_jobs_run_deadbeef",
        started_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()

    with (
        patch("app.services.embedding_sync_service.es_available", return_value=True),
        patch("app.services.embedding_sync_service.list_legacy_job_indices", return_value=[]),
        patch("app.services.embedding_sync_service.count_documents", return_value=0),
    ):
        r = client.get("/api/v1/jobs/embedding-status")

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["available"] is True
    assert data["current_db_total"] >= 1
    assert data["active_indexed_documents"] == 0
    assert data["run"]["status"] == "running"
    assert data["run"]["processed"] == 96
    assert data["run"]["target_total"] == 11783
    assert data["run"]["unique_only"] is True


def test_enrich_batch_missing_ids(client: TestClient):
    r = client.post("/api/v1/jobs/enrich")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "MISSING_IDS"


def test_list_categories(client: TestClient):
    """List categories returns array (may be empty)."""
    r = client.get("/api/v1/jobs/categories")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_list_work_types(client: TestClient):
    """List work types returns array."""
    r = client.get("/api/v1/jobs/work-types")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_locations(client: TestClient):
    """List locations returns array."""
    r = client.get("/api/v1/jobs/locations")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_seniorities(client: TestClient):
    """List seniorities returns array."""
    r = client.get("/api/v1/jobs/seniorities")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_top_skills(client: TestClient):
    """List top skills returns array, respects top param."""
    r = client.get("/api/v1/jobs/top-skills", params={"top": 10})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 10

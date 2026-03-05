from fastapi.testclient import TestClient


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


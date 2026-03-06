"""Tests for skills API."""

from fastapi.testclient import TestClient


def test_skills_summary(client: TestClient):
    """Skills summary returns structure with top_skills."""
    r = client.get("/api/v1/skills/summary")
    assert r.status_code == 200
    data = r.json()
    assert "top_skills" in data
    assert "total_jobs" in data
    assert "total_skills" in data


def test_skills_summary_with_category(client: TestClient):
    """Skills summary accepts category filter."""
    r = client.get("/api/v1/skills/summary", params={"category": "Backend"})
    assert r.status_code == 200

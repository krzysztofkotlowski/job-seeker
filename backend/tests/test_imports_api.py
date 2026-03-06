"""Tests for import API."""

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_import_status(client: TestClient):
    """Import status returns running flag and tasks."""
    r = client.get("/api/v1/import/status")
    assert r.status_code == 200
    data = r.json()
    assert "running" in data
    assert "tasks" in data
    assert isinstance(data["tasks"], list)


def test_import_start_enqueues_task(client: TestClient):
    """Import start enqueues Celery task."""
    with patch("app.routers.imports.run_import_all") as mock_run:
        mock_run.delay.return_value = None
        r = client.post("/api/v1/import/start")
    assert r.status_code == 200
    mock_run.delay.assert_called_once()

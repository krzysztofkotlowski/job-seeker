"""Tests for health endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_returns_ok(client: TestClient):
    """Health returns status ok."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"


def test_health_returns_llm_available_when_configured(client: TestClient):
    """Health includes llm_available when LLM_URL is set."""
    from app.services.llm_service import DEFAULT_LLM_MODEL, LLMConfig

    cfg = LLMConfig(url="http://ollama:11434", model=DEFAULT_LLM_MODEL, timeout=30, summarize_timeout=90, max_output_tokens=512)
    with (
        patch("app.services.llm_service.get_llm_config", return_value=cfg),
        patch("app.services.llm_service.check_ollama_health", new_callable=AsyncMock, return_value=True),
    ):
        r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("llm_available") is True

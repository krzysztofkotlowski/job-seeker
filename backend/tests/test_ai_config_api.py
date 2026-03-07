"""Tests for AI config API."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def test_ai_list_models_returns_empty_when_ollama_unavailable(client: TestClient):
    """When Ollama is not configured, /ai/models returns empty list."""
    with patch("app.services.ai_config_service.list_ollama_models", return_value={"models": []}):
        r = client.get("/api/v1/ai/models")
    assert r.status_code == 200
    assert r.json()["models"] == []


def test_ai_get_config_returns_defaults(client: TestClient):
    """GET /ai/config returns config from DB or env defaults."""
    r = client.get("/api/v1/ai/config")
    assert r.status_code == 200
    data = r.json()
    assert "llm_model" in data
    assert "embed_model" in data
    assert "temperature" in data
    assert "max_output_tokens" in data


def test_ai_put_config_updates(client: TestClient):
    """PUT /ai/config updates config."""
    r = client.put(
        "/api/v1/ai/config",
        json={"llm_model": "llama3.2:1b", "temperature": 0.5},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["llm_model"] == "llama3.2:1b"
    assert data["temperature"] == 0.5


def test_ai_metrics_returns_structure(client: TestClient):
    """GET /ai/metrics returns metrics structure."""
    r = client.get("/api/v1/ai/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "total_requests" in data
    assert "avg_latency_ms" in data
    assert "by_model" in data
    assert "last_7_days" in data

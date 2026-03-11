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
        patch("app.services.embedding_service.is_ollama_model_ready", return_value=True),
        patch(
            "app.services.self_hosted_runtime_service.get_self_hosted_runtime_status",
            return_value={
                "runtime_name": "thin-llama",
                "runtime_ready": True,
                "selected_chat_model": "qwen2.5:3b",
                "selected_embedding_model": "all-minilm",
                "active_chat_model": "qwen2.5:3b",
                "active_embedding_model": "all-minilm",
                "chat_error": None,
                "embedding_error": None,
            },
        ),
    ):
        r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("llm_available") is True
    assert data.get("embedding_available") is True
    assert data.get("self_hosted", {}).get("runtime_name") == "thin-llama"

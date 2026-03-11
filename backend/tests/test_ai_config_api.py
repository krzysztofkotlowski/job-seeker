"""Tests for AI config API."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services import ai_config_service
from app.services.ai_config_service import (
    OLLAMA_EMBED_DIMS,
    OPENAI_EMBED_DIMS,
    list_openai_models,
    validate_openai_key,
)


def test_ai_list_models_returns_empty_when_ollama_unavailable(client: TestClient):
    """When Ollama is not configured, /ai/models returns empty list."""
    with patch("app.services.ai_config_service.list_ollama_models", return_value={"models": []}):
        r = client.get("/api/v1/ai/models")
    assert r.status_code == 200
    assert r.json()["models"] == []


def test_list_ollama_models_prefers_self_hosted_catalog():
    """thin-llama catalog payload is normalized and preferred over installed tags."""
    payload = {
        "runtime": "thin-llama",
        "active": {"chat": "qwen2.5:3b", "embedding": "all-minilm"},
        "models": [
            {"name": "qwen2.5:3b", "role": "chat", "available": True, "active": True},
            {
                "name": "all-minilm",
                "role": "embedding",
                "available": False,
                "active": False,
                "details": {"status": "missing"},
            },
        ],
    }
    with patch("app.services.ai_config_service.list_self_hosted_models", return_value=payload):
        result = ai_config_service.list_ollama_models()
    assert result["runtime"] == "thin-llama"
    assert result["active"]["chat"] == "qwen2.5:3b"
    assert result["models"][0]["role"] == "chat"
    assert result["models"][1]["details"]["status"] == "missing"


def test_ai_get_config_returns_defaults(client: TestClient):
    """GET /ai/config returns config from DB or env defaults. Never returns api_key."""
    r = client.get("/api/v1/ai/config")
    assert r.status_code == 200
    data = r.json()
    assert "llm_model" in data
    assert "embed_model" in data
    assert "temperature" in data
    assert "max_output_tokens" in data
    assert "provider" in data
    assert "api_key_set" in data
    assert "openai_api_key" not in data


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


def test_ai_put_config_openai_provider(client: TestClient):
    """PUT /ai/config can set provider=openai and openai_llm_model."""
    r = client.put(
        "/api/v1/ai/config",
        json={
            "provider": "openai",
            "openai_api_key": "sk-test-key",
            "openai_llm_model": "gpt-4o-mini",
            "embed_source": "openai",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "openai"
    assert data["openai_llm_model"] == "gpt-4o-mini"
    assert data["embed_source"] == "openai"
    assert data["api_key_set"] is True
    assert "openai_api_key" not in data


def test_ai_put_config_resets_embed_dims_when_embed_source_switches(client: TestClient):
    """Switching embed source updates embed_dims to prevent stale index selection."""
    r_openai = client.put(
        "/api/v1/ai/config",
        json={
            "provider": "openai",
            "openai_api_key": "sk-test-key",
            "embed_source": "openai",
        },
    )
    assert r_openai.status_code == 200
    assert r_openai.json()["embed_dims"] == OPENAI_EMBED_DIMS

    r_ollama = client.put(
        "/api/v1/ai/config",
        json={
            "provider": "ollama",
            "embed_source": "ollama",
            "llm_model": "qwen2.5:7b",
        },
    )
    assert r_ollama.status_code == 200
    assert r_ollama.json()["embed_dims"] == OLLAMA_EMBED_DIMS


def test_ai_put_config_resolves_ollama_embed_dims_from_model(client: TestClient):
    """Saving an Ollama embedding model normalizes embed_dims to the model's actual output size."""
    with patch("app.services.ai_config_service.get_ollama_embedding_dims", return_value=768):
        r = client.put(
            "/api/v1/ai/config",
            json={
                "provider": "ollama",
                "embed_source": "ollama",
                "embed_model": "nomic-embed-text",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data["embed_model"] == "nomic-embed-text"
    assert data["embed_dims"] == 768


def test_ai_put_config_best_effort_activates_self_hosted_models(client: TestClient):
    """Saving self-hosted config aligns active models when the runtime supports it."""
    with patch("app.services.ai_config_service._best_effort_activate_self_hosted_models") as activate:
        r = client.put(
            "/api/v1/ai/config",
            json={
                "provider": "ollama",
                "embed_source": "ollama",
                "llm_model": "qwen2.5:3b",
                "embed_model": "all-minilm",
            },
        )
    assert r.status_code == 200
    activate.assert_called_once_with(
        chat_model="qwen2.5:3b",
        embed_model="all-minilm",
    )


def test_ai_put_config_skips_activation_when_models_unchanged_and_ready(client: TestClient):
    """Saving the same ready self-hosted config should not reactivate models."""
    with patch("app.services.ai_config_service._best_effort_activate_self_hosted_models") as activate, patch(
        "app.services.ai_config_service.is_self_hosted_model_ready",
        return_value=True,
    ):
        first = client.put(
            "/api/v1/ai/config",
            json={
                "provider": "ollama",
                "embed_source": "ollama",
                "llm_model": "qwen2.5:3b",
                "embed_model": "all-minilm",
            },
        )
        assert first.status_code == 200
        activate.reset_mock()

        second = client.put(
            "/api/v1/ai/config",
            json={
                "provider": "ollama",
                "embed_source": "ollama",
                "llm_model": "qwen2.5:3b",
                "embed_model": "all-minilm",
            },
        )
    assert second.status_code == 200
    activate.assert_not_called()


def test_ai_metrics_returns_structure(client: TestClient):
    """GET /ai/metrics returns metrics structure."""
    r = client.get("/api/v1/ai/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "total_requests" in data
    assert "avg_latency_ms" in data
    assert "by_model" in data
    assert "last_7_days" in data


def test_list_openai_models_returns_static_list():
    """list_openai_models returns static list of OpenAI models."""
    result = list_openai_models()
    assert "models" in result
    assert len(result["models"]) > 0
    assert any(m["name"] == "gpt-4o-mini" for m in result["models"])


def test_validate_openai_key_returns_false_when_empty():
    """validate_openai_key returns False for empty key."""
    assert validate_openai_key("") is False
    assert validate_openai_key("   ") is False


def test_ai_models_returns_openai_when_provider_openai(client: TestClient):
    """GET /ai/models returns OpenAI models when provider is openai."""
    r = client.put(
        "/api/v1/ai/config",
        json={"provider": "openai", "openai_api_key": "sk-test"},
    )
    assert r.status_code == 200
    r = client.get("/api/v1/ai/models")
    assert r.status_code == 200
    data = r.json()
    assert "models" in data
    assert any("gpt" in str(m.get("name", "")).lower() for m in data["models"])


def test_ai_put_config_openai_partial_update(client: TestClient):
    """PUT with provider=openai omitting llm_model and embed_model succeeds (partial update)."""
    r = client.put(
        "/api/v1/ai/config",
        json={
            "provider": "openai",
            "openai_api_key": "sk-test-key",
            "openai_llm_model": "gpt-4o-mini",
            "embed_source": "openai",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "openai"
    assert data["openai_llm_model"] == "gpt-4o-mini"
    assert "llm_model" in data
    assert "embed_model" in data


def test_ai_put_config_validation_error_empty_llm_model(client: TestClient):
    """PUT with empty llm_model returns 422 validation error."""
    r = client.put(
        "/api/v1/ai/config",
        json={"llm_model": ""},
    )
    assert r.status_code == 422
    data = r.json()
    assert "detail" in data


def test_ai_validate_key_valid(client: TestClient):
    """POST /ai/config/validate-key returns valid when key works."""
    with patch("app.routers.ai_config.validate_openai_key", return_value=True):
        r = client.post(
            "/api/v1/ai/config/validate-key",
            json={"openai_api_key": "sk-valid-key"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True


def test_ai_validate_key_invalid(client: TestClient):
    """POST /ai/config/validate-key returns valid=false when key fails."""
    with patch("app.routers.ai_config.validate_openai_key", return_value=False):
        r = client.post(
            "/api/v1/ai/config/validate-key",
            json={"openai_api_key": "sk-invalid"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is False
    assert "error" in data

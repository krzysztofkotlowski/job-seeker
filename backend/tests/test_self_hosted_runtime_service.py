"""Tests for generic self-hosted runtime client behavior."""

from unittest.mock import patch

from app.services.self_hosted_runtime_service import (
    RuntimeInfo,
    ThinLlamaRuntimeClient,
    get_runtime_client,
)


class DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_get_runtime_client_prefers_thin_llama_when_runtime_endpoint_is_present():
    with patch(
        "app.services.self_hosted_runtime_service.get_runtime_info",
        return_value=RuntimeInfo(
            name="thin-llama",
            version="v0.1.0",
            git_ref="abc123",
            capabilities=["models.catalog"],
        ),
    ):
        client = get_runtime_client()
    assert isinstance(client, ThinLlamaRuntimeClient)
    assert client.runtime_info is not None
    assert client.runtime_info.version == "v0.1.0"


def test_thin_llama_list_models_normalizes_catalog_payload():
    client = ThinLlamaRuntimeClient(
        "http://thin-llama:8080",
        runtime_info=RuntimeInfo(name="thin-llama", version="v0.1.0", git_ref="abc123", capabilities=["models.catalog"]),
    )
    payload = {
        "active": {"chat": "qwen2.5:3b", "embedding": "all-minilm"},
        "models": [
            {
                "name": "qwen2.5:3b",
                "role": "chat",
                "available": True,
                "active": True,
                "download_status": "available",
                "path": "/models/qwen.gguf",
            }
        ],
    }
    with patch.object(client, "_request", return_value=DummyResponse(200, payload)):
        result = client.list_models()
    assert result["runtime"] == "thin-llama"
    assert result["active"]["chat"] == "qwen2.5:3b"
    assert result["models"][0]["available"] is True
    assert result["models"][0]["details"]["path"] == "/models/qwen.gguf"


def test_thin_llama_ensure_model_accepts_already_present_status():
    client = ThinLlamaRuntimeClient("http://thin-llama:8080")
    with patch.object(
        client,
        "_request",
        return_value=DummyResponse(
            200,
            {"status": "success", "pull_state": "already-present"},
        ),
    ):
        result = client.ensure_model("all-minilm")
    assert result == {"status": "ok"}

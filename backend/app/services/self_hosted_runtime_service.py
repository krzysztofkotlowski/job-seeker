"""Generic self-hosted runtime client layer for thin-llama and Ollama-compatible backends."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

SELF_HOSTED_URL = (os.environ.get("LLM_URL", "") or "").rstrip("/")


@dataclass
class RuntimeInfo:
    """Runtime identity and capabilities."""

    name: str
    version: str | None = None
    git_ref: str | None = None
    capabilities: list[str] | None = None


class SelfHostedRuntimeClient:
    """Base client for self-hosted model runtime APIs."""

    runtime_name = "self-hosted"

    def __init__(self, base_url: str, *, timeout: int = 10, runtime_info: RuntimeInfo | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.runtime_info = runtime_info

    def _request(self, method: str, path: str, *, json: dict | None = None, timeout: int | None = None) -> httpx.Response:
        with httpx.Client(timeout=timeout or self.timeout) as client:
            return client.request(method, f"{self.base_url}{path}", json=json)

    def list_models(self) -> dict:
        raise NotImplementedError

    def ensure_model(self, model: str) -> dict:
        raise NotImplementedError

    def activate_models(self, *, chat_model: str | None = None, embed_model: str | None = None) -> bool:
        return False

    def is_model_available(self, model: str | None) -> bool:
        raise NotImplementedError


class ThinLlamaRuntimeClient(SelfHostedRuntimeClient):
    """thin-llama management API client."""

    runtime_name = "thin-llama"

    def list_models(self) -> dict:
        resp = self._request("GET", "/api/models")
        if resp.status_code != 200:
            return {"models": []}
        payload = resp.json()
        models: list[dict] = []
        for item in payload.get("models") or []:
            name = str(item.get("name") or item.get("model") or "").strip()
            if not name:
                continue
            normalized = {
                "name": name,
                "model": name,
                "available": bool(item.get("available")),
                "active": bool(item.get("active")),
                "role": item.get("role"),
            }
            details = {
                "status": item.get("download_status"),
                "path": item.get("path"),
            }
            if item.get("download_error"):
                details["error"] = item.get("download_error")
            if any(v for v in details.values()):
                normalized["details"] = details
            models.append(normalized)
        return {
            "models": models,
            "active": payload.get("active") or {},
            "runtime": self.runtime_name,
            "runtime_info": {
                "name": self.runtime_name,
                "version": self.runtime_info.version if self.runtime_info else None,
                "git_ref": self.runtime_info.git_ref if self.runtime_info else None,
                "capabilities": self.runtime_info.capabilities if self.runtime_info else [],
            },
        }

    def ensure_model(self, model: str) -> dict:
        try:
            resp = self._request(
                "POST",
                "/api/pull",
                json={"model": model, "stream": False},
                timeout=300,
            )
            if resp.status_code != 200:
                return {"status": "error", "error": resp.text or f"HTTP {resp.status_code}"}
            data = resp.json()
            status = str(data.get("status") or "").strip().lower()
            pull_state = str(data.get("pull_state") or status or "").strip().lower()
            if status == "success" or pull_state in {"success", "downloaded", "already-present"}:
                return {"status": "ok"}
            return {"status": "error", "error": pull_state or status or "Pull failed"}
        except httpx.TimeoutException:
            return {"status": "error", "error": "Self-hosted runtime request timed out"}
        except Exception as e:
            log.debug("thin-llama ensure-model failed: %s", e)
            return {"status": "error", "error": str(e)}

    def activate_models(self, *, chat_model: str | None = None, embed_model: str | None = None) -> bool:
        payload: dict[str, str] = {}
        if chat_model:
            payload["chat"] = chat_model
        if embed_model:
            payload["embedding"] = embed_model
        if not payload:
            return False
        try:
            resp = self._request("POST", "/api/models/active", json=payload)
            return resp.status_code == 200
        except Exception as e:
            log.info("Self-hosted model activation failed: %s", e)
            return False

    def is_model_available(self, model: str | None) -> bool:
        requested = _normalize_model_name(model)
        if not requested:
            return False
        try:
            payload = self.list_models()
            for item in payload.get("models") or []:
                name = _normalize_model_name(item.get("name") or item.get("model"))
                if not name:
                    continue
                if name == requested and bool(item.get("available")):
                    return True
                if _base_model_name(name) == _base_model_name(requested) and bool(item.get("available")):
                    return True
        except Exception as e:
            log.debug("thin-llama availability check failed: %s", e)
        return False


class OllamaCompatRuntimeClient(SelfHostedRuntimeClient):
    """Fallback client for plain Ollama-compatible runtimes without catalog APIs."""

    runtime_name = "ollama-compatible"

    def list_models(self) -> dict:
        try:
            resp = self._request("GET", "/api/tags")
            if resp.status_code != 200:
                return {"models": []}
            payload = resp.json()
            return {
                "models": payload.get("models") or [],
                "runtime": self.runtime_name,
                "runtime_info": {
                    "name": self.runtime_name,
                    "version": None,
                    "git_ref": None,
                    "capabilities": ["ollama.tags", "ollama.pull"],
                },
            }
        except Exception as e:
            log.debug("Failed to list self-hosted models: %s", e)
            return {"models": []}

    def ensure_model(self, model: str) -> dict:
        try:
            resp = self._request(
                "POST",
                "/api/pull",
                json={"model": model, "stream": False},
                timeout=300,
            )
            if resp.status_code != 200:
                return {"status": "error", "error": resp.text or f"HTTP {resp.status_code}"}
            data = resp.json()
            status = str(data.get("status") or "").strip().lower()
            pull_state = str(data.get("pull_state") or status or "").strip().lower()
            if status == "success" or pull_state in {"success", "downloaded", "already-present"}:
                return {"status": "ok"}
            return {"status": "error", "error": pull_state or status or "Pull failed"}
        except httpx.TimeoutException:
            return {"status": "error", "error": "Self-hosted runtime request timed out"}
        except Exception as e:
            log.debug("Self-hosted ensure-model failed: %s", e)
            return {"status": "error", "error": str(e)}

    def is_model_available(self, model: str | None) -> bool:
        requested = _normalize_model_name(model)
        if not requested:
            return False
        try:
            resp = self._request("GET", "/api/tags", timeout=5)
            if resp.status_code != 200:
                return False
            models = resp.json().get("models") or []
            for item in models:
                name = _normalize_model_name(item.get("name") or item.get("model"))
                if not name:
                    continue
                if name == requested or _base_model_name(name) == _base_model_name(requested):
                    return True
        except Exception as e:
            log.debug("Self-hosted availability check failed: %s", e)
        return False


def _normalize_model_name(value: str | None) -> str:
    return str(value or "").strip()


def _base_model_name(value: str) -> str:
    return value.split(":", 1)[0]


def get_runtime_info(timeout: int = 5) -> RuntimeInfo | None:
    """Return explicit runtime identity when the backend exposes it."""
    if not SELF_HOSTED_URL:
        return None
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{SELF_HOSTED_URL}/api/runtime")
            if resp.status_code != 200:
                return None
            payload = resp.json()
            name = str(payload.get("runtime") or payload.get("name") or "").strip()
            if not name:
                return None
            caps = payload.get("capabilities") or []
            capabilities = [str(item).strip() for item in caps if str(item).strip()]
            return RuntimeInfo(
                name=name,
                version=(payload.get("version") or None),
                git_ref=(payload.get("git_ref") or None),
                capabilities=capabilities,
            )
    except Exception as e:
        log.debug("Self-hosted runtime probe failed: %s", e)
        return None


def get_runtime_client(timeout: int = 10) -> SelfHostedRuntimeClient:
    """Return the most capable runtime client for the configured self-hosted URL."""
    info = get_runtime_info(timeout=min(timeout, 5))
    if info and info.name == "thin-llama":
        return ThinLlamaRuntimeClient(SELF_HOSTED_URL, timeout=timeout, runtime_info=info)
    return OllamaCompatRuntimeClient(SELF_HOSTED_URL, timeout=timeout, runtime_info=info)


def list_self_hosted_models(timeout: int = 10) -> dict:
    """List self-hosted models using the richest runtime API available."""
    if not SELF_HOSTED_URL:
        return {"models": []}
    try:
        return get_runtime_client(timeout=timeout).list_models()
    except Exception as e:
        log.debug("Failed to list self-hosted models: %s", e)
        return {"models": []}


def ensure_self_hosted_model(model: str) -> dict:
    """Ensure a self-hosted model is available."""
    if not model or not str(model).strip():
        return {"status": "error", "error": "Model name is required"}
    if not SELF_HOSTED_URL:
        return {"status": "error", "error": "Self-hosted runtime URL not configured"}
    return get_runtime_client(timeout=10).ensure_model(str(model).strip())


def best_effort_activate_self_hosted_models(*, chat_model: str | None = None, embed_model: str | None = None) -> None:
    """Try to activate installed chat/embed models when the runtime supports it."""
    if not SELF_HOSTED_URL:
        return
    client = get_runtime_client(timeout=5)
    payload: dict[str, str] = {}
    if chat_model and client.is_model_available(chat_model):
        payload["chat_model"] = chat_model
    if embed_model and client.is_model_available(embed_model):
        payload["embed_model"] = embed_model
    if not payload:
        return
    client.activate_models(
        chat_model=payload.get("chat_model"),
        embed_model=payload.get("embed_model"),
    )


def is_self_hosted_model_available(model: str | None) -> bool:
    """Return True if the requested self-hosted model is installed and usable."""
    if not SELF_HOSTED_URL:
        return False
    return get_runtime_client(timeout=5).is_model_available(model)

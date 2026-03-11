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

    def is_model_ready(self, model: str | None) -> bool:
        return self.is_model_available(model)

    def get_embedding_dims(self, model: str | None) -> int | None:
        return None

    def get_runtime_status(
        self,
        *,
        selected_chat_model: str | None = None,
        selected_embedding_model: str | None = None,
    ) -> dict:
        return {
            "runtime_name": self.runtime_name,
            "runtime_ready": False,
            "selected_chat_model": _normalize_model_name(selected_chat_model),
            "selected_embedding_model": _normalize_model_name(selected_embedding_model),
            "active_chat_model": None,
            "active_embedding_model": None,
            "chat_error": None,
            "embedding_error": None,
        }


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
            available = bool(item.get("available"))
            active = bool(item.get("active"))
            has_error = bool(
                item.get("download_error")
                or item.get("runtime_error")
                or item.get("runtime_message")
                or item.get("orphan_detected")
            )
            if has_error:
                status = "error"
            elif active and available:
                status = "active"
            elif available:
                status = "installed"
            else:
                status = "not_installed"
            normalized = {
                "name": name,
                "model": name,
                "available": available,
                "active": active,
                "supported": True,
                "role": item.get("role"),
                "status": status,
                "embedding_dims": _coerce_positive_int(item.get("embedding_dims")),
            }
            details = {
                "status": status,
                "path": item.get("path"),
                "runtime_running": bool(item.get("runtime_running")),
                "runtime_ready": bool(item.get("runtime_ready")),
                "restart_suppressed": bool(item.get("restart_suppressed")),
                "runtime_pid": _coerce_positive_int(item.get("runtime_pid")),
                "orphan_detected": bool(item.get("orphan_detected")),
            }
            if item.get("download_error"):
                details["error"] = item.get("download_error")
            elif item.get("runtime_error"):
                details["error"] = item.get("runtime_error")
            elif item.get("runtime_message"):
                details["error"] = item.get("runtime_message")
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

    def is_model_ready(self, model: str | None) -> bool:
        requested = _normalize_model_name(model)
        if not requested:
            return False
        try:
            payload = self.list_models()
            for item in payload.get("models") or []:
                name = _normalize_model_name(item.get("name") or item.get("model"))
                if not _model_matches(requested, name):
                    continue
                if not bool(item.get("available")):
                    continue
                if not bool(item.get("active")):
                    continue
                details = item.get("details") or {}
                if details.get("error"):
                    return False
                return bool(details.get("runtime_ready"))
        except Exception as e:
            log.debug("thin-llama readiness check failed: %s", e)
        return False

    def get_embedding_dims(self, model: str | None) -> int | None:
        requested = _normalize_model_name(model)
        if not requested:
            return None
        try:
            payload = self.list_models()
            for item in payload.get("models") or []:
                name = _normalize_model_name(item.get("name") or item.get("model"))
                if not _model_matches(requested, name):
                    continue
                dims = _coerce_positive_int(item.get("embedding_dims"))
                if dims:
                    return dims
        except Exception as e:
            log.debug("thin-llama embedding dims lookup failed: %s", e)
        return None

    def get_runtime_status(
        self,
        *,
        selected_chat_model: str | None = None,
        selected_embedding_model: str | None = None,
    ) -> dict:
        status = super().get_runtime_status(
            selected_chat_model=selected_chat_model,
            selected_embedding_model=selected_embedding_model,
        )
        try:
            resp = self._request("GET", "/health", timeout=5)
            if resp.status_code != 200:
                return status
            payload = resp.json()
            runtime = payload.get("runtime") or {}
            active = payload.get("active") or {}
            chat = payload.get("chat") or {}
            embedding = payload.get("embedding") or {}
            status.update(
                {
                    "runtime_name": str(runtime.get("name") or self.runtime_name).strip() or self.runtime_name,
                    "runtime_ready": bool(payload.get("runtime_ready")),
                    "active_chat_model": _normalize_model_name(active.get("chat") or chat.get("model_name")) or None,
                    "active_embedding_model": _normalize_model_name(active.get("embedding") or embedding.get("model_name")) or None,
                    "chat_error": _first_nonempty(chat.get("last_error"), chat.get("status_message")),
                    "embedding_error": _first_nonempty(
                        embedding.get("last_error"),
                        embedding.get("status_message"),
                    ),
                }
            )
        except Exception as e:
            log.debug("thin-llama runtime status lookup failed: %s", e)
        return status


class OllamaCompatRuntimeClient(SelfHostedRuntimeClient):
    """Fallback client for plain Ollama-compatible runtimes without catalog APIs."""

    runtime_name = "ollama-compatible"

    def list_models(self) -> dict:
        try:
            resp = self._request("GET", "/api/tags")
            if resp.status_code != 200:
                return {"models": []}
            payload = resp.json()
            models: list[dict] = []
            for item in payload.get("models") or []:
                name = _normalize_model_name(item.get("name") or item.get("model"))
                if not name:
                    continue
                models.append(
                    {
                        "name": name,
                        "model": name,
                        "available": True,
                        "active": False,
                        "supported": True,
                        "role": item.get("role"),
                        "status": "installed",
                        "details": {"status": "installed"},
                    }
                )
            return {
                "models": models,
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


def _model_matches(requested: str, candidate: str) -> bool:
    if not candidate:
        return False
    return candidate == requested or _base_model_name(candidate) == _base_model_name(requested)


def _coerce_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


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
    """Return True if the requested self-hosted model is installed."""
    if not SELF_HOSTED_URL:
        return False
    return get_runtime_client(timeout=5).is_model_available(model)


def is_self_hosted_model_ready(model: str | None) -> bool:
    """Return True if the requested self-hosted model is active and ready to serve."""
    if not SELF_HOSTED_URL:
        return False
    return get_runtime_client(timeout=5).is_model_ready(model)


def get_self_hosted_embedding_dims(model: str | None) -> int | None:
    """Return embedding dimensions advertised by the self-hosted runtime, when available."""
    if not SELF_HOSTED_URL:
        return None
    return get_runtime_client(timeout=5).get_embedding_dims(model)


def get_self_hosted_runtime_status(
    *,
    selected_chat_model: str | None = None,
    selected_embedding_model: str | None = None,
) -> dict:
    """Return non-breaking runtime diagnostics for health/UI surfaces."""
    if not SELF_HOSTED_URL:
        return {
            "runtime_name": "self-hosted",
            "runtime_ready": False,
            "selected_chat_model": _normalize_model_name(selected_chat_model) or None,
            "selected_embedding_model": _normalize_model_name(selected_embedding_model) or None,
            "active_chat_model": None,
            "active_embedding_model": None,
            "chat_error": "Self-hosted runtime URL not configured",
            "embedding_error": None,
        }
    return get_runtime_client(timeout=5).get_runtime_status(
        selected_chat_model=selected_chat_model,
        selected_embedding_model=selected_embedding_model,
    )


def _first_nonempty(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None

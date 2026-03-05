"""Shared error helpers and exception handlers."""

import logging
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def api_error(code: str, message: str, *, status_code: int = 400, **details: Any) -> HTTPException:
    """Create a structured API error."""
    payload: Dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return HTTPException(status_code=status_code, detail=payload)


def setup_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers that normalize error responses."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:  # type: ignore[override]
        # If detail is already a structured error, keep it; otherwise wrap it.
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            body = {"error": detail}
        else:
            body = {
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(detail) if detail else exc.detail or "Request failed",
                }
            }
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # type: ignore[override]
        log.exception("Unhandled error while processing request %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "Something went wrong. Please try again."}},
        )


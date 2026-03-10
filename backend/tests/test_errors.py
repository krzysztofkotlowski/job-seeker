"""Tests for error helpers and exception handlers."""

from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.errors import api_error, setup_exception_handlers


def test_api_error_creates_structured_exception():
    """api_error returns HTTPException with structured detail."""
    exc = api_error("TEST_CODE", "Test message", status_code=400)
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 400
    assert exc.detail["code"] == "TEST_CODE"
    assert exc.detail["message"] == "Test message"
    assert "details" not in exc.detail


def test_api_error_with_details():
    """api_error includes optional details dict."""
    exc = api_error("CONFLICT", "Already exists", status_code=409, existing_id="abc-123")
    assert exc.detail["code"] == "CONFLICT"
    assert exc.detail["details"] == {"existing_id": "abc-123"}


def test_http_exception_handler_structured_detail():
    """Handler preserves structured error when detail has code and message."""
    app = FastAPI()
    setup_exception_handlers(app)

    @app.get("/structured")
    def _():
        raise api_error("CUSTOM", "Custom error", status_code=422)

    client = TestClient(app)
    r = client.get("/structured")
    assert r.status_code == 422
    data = r.json()
    assert data["error"]["code"] == "CUSTOM"
    assert data["error"]["message"] == "Custom error"


def test_http_exception_handler_plain_detail():
    """Handler wraps plain string detail as HTTP_ERROR."""
    app = FastAPI()
    setup_exception_handlers(app)

    @app.get("/plain")
    def _():
        raise HTTPException(status_code=404, detail="Not found")

    client = TestClient(app)
    r = client.get("/plain")
    assert r.status_code == 404
    data = r.json()
    assert data["error"]["code"] == "HTTP_ERROR"
    assert "Not found" in data["error"]["message"]


def test_unhandled_exception_handler():
    """Unhandled exceptions return 500 with INTERNAL_SERVER_ERROR."""
    app = FastAPI()
    setup_exception_handlers(app)

    @app.get("/boom")
    def _():
        raise ValueError("Unexpected")

    with patch("app.errors.log") as mock_log:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/boom")
    assert r.status_code == 500
    data = r.json()
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "Something went wrong" in data["error"]["message"]
    mock_log.exception.assert_called_once()

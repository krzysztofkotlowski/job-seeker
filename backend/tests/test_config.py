"""Tests for config module."""

import pytest


def test_get_cors_origins_default_when_empty():
    """When CORS_ORIGINS is empty, returns default localhost origins."""
    import app.config as config_mod

    orig = config_mod._settings
    config_mod._settings = None
    try:
        with pytest.MonkeyPatch.context() as m:
            m.setenv("CORS_ORIGINS", "")
            result = config_mod.get_cors_origins()
        assert "http://localhost:5173" in result
        assert "http://localhost:3000" in result
    finally:
        config_mod._settings = orig


def test_get_cors_origins_wildcard():
    """When CORS_ORIGINS is *, returns ['*']."""
    import app.config as config_mod

    orig = config_mod._settings
    config_mod._settings = None
    try:
        with pytest.MonkeyPatch.context() as m:
            m.setenv("CORS_ORIGINS", "*")
            result = config_mod.get_cors_origins()
        assert result == ["*"]
    finally:
        config_mod._settings = orig


def test_get_cors_origins_comma_separated():
    """When CORS_ORIGINS is comma-separated, returns list."""
    import app.config as config_mod

    orig = config_mod._settings
    config_mod._settings = None
    try:
        with pytest.MonkeyPatch.context() as m:
            m.setenv("CORS_ORIGINS", "https://a.com, https://b.com")
            result = config_mod.get_cors_origins()
        assert "https://a.com" in result
        assert "https://b.com" in result
    finally:
        config_mod._settings = orig


def test_get_rate_limit():
    """get_rate_limit returns rate limit string."""
    from app.config import get_rate_limit

    result = get_rate_limit()
    assert "minute" in result or "second" in result or "/" in result

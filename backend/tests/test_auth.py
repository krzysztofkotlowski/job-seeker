"""Tests for auth (when disabled)."""

from fastapi.testclient import TestClient

from app.auth import is_auth_enabled


def test_auth_config_disabled(client: TestClient):
    """When KEYCLOAK_URL is unset, auth config returns enabled: false."""
    r = client.get("/api/v1/auth/config")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False


def test_is_auth_enabled_false_when_keycloak_unset():
    """is_auth_enabled returns False when KEYCLOAK_URL is unset (test env)."""
    assert is_auth_enabled() is False

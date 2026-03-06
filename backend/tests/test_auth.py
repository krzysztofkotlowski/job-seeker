"""Tests for auth (when disabled)."""

from fastapi.testclient import TestClient


def test_auth_config_disabled(client: TestClient):
    """When KEYCLOAK_URL is unset, auth config returns enabled: false."""
    r = client.get("/api/v1/auth/config")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False

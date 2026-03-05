"""Keycloak JWT validation and user extraction."""

import logging
import os
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

log = logging.getLogger(__name__)

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "").rstrip("/")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "jobseeker")

security = HTTPBearer(auto_error=False)

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if not KEYCLOAK_URL:
        return None
    if _jwks_client is None:
        url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
        try:
            _jwks_client = PyJWKClient(url, cache_keys=True)
        except Exception as e:
            log.warning("Failed to create JWKS client: %s", e)
            return None
    return _jwks_client


def _decode_token(token: str) -> dict | None:
    """Validate and decode JWT using Keycloak JWKS."""
    client = _get_jwks_client()
    if not client:
        return None
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            return None
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": True},
        )
        return payload
    except jwt.PyJWTError as e:
        log.debug("JWT decode failed: %s", e)
        return None


def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict | None:
    """
    Extract and validate user from Bearer token. Returns None if auth is disabled or no token.
    """
    if not KEYCLOAK_URL:
        return None
    if not credentials or not credentials.credentials:
        return None
    payload = _decode_token(credentials.credentials)
    if not payload:
        return None
    return {
        "sub": payload.get("sub"),
        "email": payload.get("email"),
        "preferred_username": payload.get("preferred_username"),
    }


def get_current_user(
    user: Annotated[dict | None, Depends(get_current_user_optional)],
) -> dict:
    """Require authenticated user. Raises 401 if not authenticated."""
    if not KEYCLOAK_URL:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is not configured",
        )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def is_auth_enabled() -> bool:
    """Whether Keycloak auth is configured."""
    return bool(KEYCLOAK_URL)


def require_auth(
    user: Annotated[dict | None, Depends(get_current_user_optional)],
) -> dict | None:
    """
    Require auth when Keycloak is configured; otherwise allow anonymous.
    Use as Depends(require_auth) on protected endpoints.
    """
    if is_auth_enabled() and not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

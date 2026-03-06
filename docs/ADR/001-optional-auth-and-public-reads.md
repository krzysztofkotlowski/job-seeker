# ADR 001: Optional Auth and Public Read-Only Endpoints

## Status

Accepted

## Context

The Job Seeker app needs to support both:
- Quick local use without any auth setup
- Production deployment with Keycloak for import, backup, and resume history

## Decision

- **Auth is optional**: When `KEYCLOAK_ENABLED` is not set, the app runs without authentication.
- **Jobs and skills endpoints are public (read-only)**: List, get, analytics, categories, seniorities, etc. do not require auth. This allows anonymous browsing of job listings.
- **Write operations require auth when enabled**: Import (start/cancel), Backup (create), Resume history (when auth enabled). These use `require_auth` dependency.
- **Resume analyze/summarize**: Work with or without auth; when auth is enabled and user is logged in, analyses are persisted.

## Consequences

- Jobs and skills data is accessible without login. For a job tracker, this is intentional: users can browse before deciding to sign in.
- In production, consider network-level protection (e.g. VPN, private network) if job data is sensitive.
- Rate limiting (RATE_LIMIT env) helps prevent abuse of public endpoints.

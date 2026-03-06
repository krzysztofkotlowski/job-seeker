# ADR 002: Celery Eager Mode by Default

## Status

Accepted

## Context

Imports can be long-running. Celery provides background task execution, but requires Redis (or another broker) to be running.

## Decision

- **Celery runs in eager mode by default** (`CELERY_ALWAYS_EAGER=true`): Tasks execute synchronously in the same process. No Redis required for development.
- **Optional Redis**: Set `CELERY_ALWAYS_EAGER=false` and provide `CELERY_BROKER_URL` for true background workers in production.

## Consequences

- Developers can run `docker compose up` without Redis; imports work out of the box.
- For production with large imports, add Redis and run Celery workers for non-blocking imports.
- Import progress is still persisted in `ImportTaskRow` for recovery.

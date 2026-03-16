# Elasticsearch Index Rebuild and Migration

## Overview

Job Seeker uses managed Elasticsearch indices for RAG (hybrid keyword + semantic search). The active index is built by the embedding sync run and pointed to by the `jobseeker_jobs_active` alias.

## Index Lifecycle

1. **Sync run** creates a physical index `jobseeker_jobs_run_<run_id>` (no hyphens in ID)
2. Jobs are embedded and bulk-indexed
3. On completion, the alias `jobseeker_jobs_active` is repointed to the new index
4. Old physical indices remain until manually deleted

## Rebuild Procedure

### Full rebuild (recommended after model change)

1. Stop any running sync: `POST /api/v1/jobs/sync-embeddings` returns 409 if already running
2. Clear the active index: `DELETE /api/v1/jobs/embedding-index`
3. Start a full sync: `POST /api/v1/jobs/sync-embeddings?mode=full`
4. Poll status: `GET /api/v1/jobs/embedding-status` until `run.status` is `completed`

### Incremental add (add missing jobs only)

1. Ensure an active index exists
2. `POST /api/v1/jobs/sync-embeddings?mode=incremental`
3. Only jobs not yet in the active index are embedded and added

## Dimension Mismatch

If you switch embedding models (e.g. nomic 768d → text-embedding-3-small 1536d), the active index dimensions will not match. You must run a **full rebuild**. The API returns `reindex_required` when this is detected.

## Legacy Indices

Indices matching `jobseeker_jobs*` that are not managed run indices or the active alias are "legacy". They can be deleted manually via Elasticsearch API when no longer needed.

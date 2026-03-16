"""Add enrichment_runs table for background description enrichment."""

from sqlalchemy import inspect, text


def upgrade(conn):
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "enrichment_runs" not in tables:
        conn.execute(text("""
            CREATE TABLE enrichment_runs (
                id UUID PRIMARY KEY,
                status VARCHAR(20) NOT NULL DEFAULT 'queued',
                total INTEGER NOT NULL DEFAULT 0,
                enriched INTEGER NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0,
                error_log TEXT[] DEFAULT '{}',
                pending_job_ids TEXT[] DEFAULT '{}',
                celery_task_id VARCHAR(255),
                started_at TIMESTAMP WITH TIME ZONE,
                finished_at TIMESTAMP WITH TIME ZONE,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(
            "CREATE INDEX idx_enrichment_runs_status_updated_at ON enrichment_runs (status, updated_at)"
        ))

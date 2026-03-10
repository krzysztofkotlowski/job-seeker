"""Add persistent embedding sync runs table."""

from sqlalchemy import inspect, text


def upgrade(conn):
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "embedding_sync_runs" not in tables:
        conn.execute(text("""
            CREATE TABLE embedding_sync_runs (
                id UUID PRIMARY KEY,
                status VARCHAR(20) NOT NULL DEFAULT 'queued',
                mode VARCHAR(20) NOT NULL DEFAULT 'incremental',
                unique_only BOOLEAN NOT NULL DEFAULT FALSE,
                embed_source VARCHAR(20) NOT NULL DEFAULT 'ollama',
                embed_model VARCHAR(255) NOT NULL,
                embed_dims INTEGER NOT NULL,
                db_total_snapshot INTEGER NOT NULL DEFAULT 0,
                selection_total INTEGER NOT NULL DEFAULT 0,
                target_total INTEGER NOT NULL DEFAULT 0,
                processed INTEGER NOT NULL DEFAULT 0,
                indexed INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                index_alias VARCHAR(255) NOT NULL,
                physical_index_name VARCHAR(255),
                celery_task_id VARCHAR(255),
                error_message TEXT,
                started_at TIMESTAMP WITH TIME ZONE,
                finished_at TIMESTAMP WITH TIME ZONE,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                activated_at TIMESTAMP WITH TIME ZONE
            )
        """))

    indexes = {idx["name"] for idx in inspector.get_indexes("embedding_sync_runs")}
    if "ix_embedding_sync_runs_status" not in indexes:
        conn.execute(text(
            "CREATE INDEX ix_embedding_sync_runs_status ON embedding_sync_runs (status)"
        ))
    if "ix_embedding_sync_runs_activated_at" not in indexes:
        conn.execute(text(
            "CREATE INDEX ix_embedding_sync_runs_activated_at ON embedding_sync_runs (activated_at)"
        ))
    if "idx_embedding_sync_runs_status_updated_at" not in indexes:
        conn.execute(text(
            "CREATE INDEX idx_embedding_sync_runs_status_updated_at ON embedding_sync_runs (status, updated_at)"
        ))

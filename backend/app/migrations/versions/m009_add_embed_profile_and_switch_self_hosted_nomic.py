"""Add embed_profile metadata and switch unchanged self-hosted defaults to nomic-embed-text."""

from sqlalchemy import inspect, text


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(conn, inspector, table_name: str, ddl: str) -> None:
    column_name = ddl.split()[0]
    if not _has_column(inspector, table_name, column_name):
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def upgrade(conn):
    inspector = inspect(conn)
    table_names = set(inspector.get_table_names())

    if "ai_config" in table_names:
        _add_column_if_missing(conn, inspector, "ai_config", "embed_profile VARCHAR(50)")
        columns = {c["name"] for c in inspector.get_columns("ai_config")}
        if {"provider", "embed_source", "embed_model", "embed_dims", "embed_profile"} <= columns:
            assignments = [
                "embed_model = 'nomic-embed-text'",
                "embed_dims = 768",
                "embed_profile = 'nomic-search-v1'",
            ]
            if "updated_at" in columns:
                assignments.append("updated_at = CURRENT_TIMESTAMP")
            conn.execute(
                text(
                    f"""
                    UPDATE ai_config
                    SET {", ".join(assignments)}
                    WHERE COALESCE(provider, 'ollama') = 'ollama'
                      AND COALESCE(embed_source, 'ollama') = 'ollama'
                      AND embed_model = 'bge-base-en:v1.5'
                      AND COALESCE(embed_dims, 768) = 768
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE ai_config
                    SET embed_profile =
                      CASE
                        WHEN COALESCE(embed_source, 'ollama') = 'openai' THEN 'openai-v1'
                        WHEN embed_model = 'nomic-embed-text' THEN 'nomic-search-v1'
                        WHEN embed_model = 'bge-base-en:v1.5' THEN 'bge-v1'
                        ELSE 'raw-v1'
                      END
                    WHERE embed_profile IS NULL OR TRIM(embed_profile) = ''
                    """
                )
            )

    inspector = inspect(conn)
    if "embedding_sync_runs" in set(inspector.get_table_names()):
        _add_column_if_missing(conn, inspector, "embedding_sync_runs", "embed_profile VARCHAR(50)")
        columns = {c["name"] for c in inspector.get_columns("embedding_sync_runs")}
        if {"embed_source", "embed_model", "embed_profile"} <= columns:
            conn.execute(
                text(
                    """
                    UPDATE embedding_sync_runs
                    SET embed_profile =
                      CASE
                        WHEN COALESCE(embed_source, 'ollama') = 'openai' THEN 'openai-v1'
                        WHEN embed_model = 'nomic-embed-text' THEN 'nomic-legacy-v1'
                        WHEN embed_model = 'bge-base-en:v1.5' THEN 'bge-v1'
                        ELSE 'raw-v1'
                      END
                    WHERE embed_profile IS NULL OR TRIM(embed_profile) = ''
                    """
                )
            )

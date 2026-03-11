"""Normalize stale self-hosted defaults after the thin-llama migration."""

from sqlalchemy import inspect, text


def upgrade(conn):
    inspector = inspect(conn)
    if "ai_config" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("ai_config")}
    if "llm_model" not in columns:
        return

    has_provider = "provider" in columns
    if has_provider:
        conn.execute(
            text(
                """
                UPDATE ai_config
                SET llm_model = 'qwen2.5:3b'
                WHERE llm_model = 'phi3:mini' AND provider = 'ollama'
                """
            )
        )
        return

    conn.execute(
        text(
            """
            UPDATE ai_config
            SET llm_model = 'qwen2.5:3b'
            WHERE llm_model = 'phi3:mini'
            """
        )
    )

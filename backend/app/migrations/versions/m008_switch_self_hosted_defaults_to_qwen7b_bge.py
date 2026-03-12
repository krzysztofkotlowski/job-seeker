"""Switch unchanged self-hosted defaults to qwen2.5:7b plus bge-base-en:v1.5."""

from sqlalchemy import inspect, text


def upgrade(conn):
    inspector = inspect(conn)
    if "ai_config" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("ai_config")}
    if "llm_model" not in columns or "embed_model" not in columns:
        return

    has_provider = "provider" in columns
    has_embed_source = "embed_source" in columns
    has_embed_dims = "embed_dims" in columns
    has_updated_at = "updated_at" in columns

    filters = ["llm_model = 'qwen2.5:3b'", "embed_model = 'all-minilm'"]
    if has_provider:
        filters.append("COALESCE(provider, 'ollama') = 'ollama'")
    if has_embed_source:
        filters.append("COALESCE(embed_source, 'ollama') = 'ollama'")
    if has_embed_dims:
        filters.append("COALESCE(embed_dims, 384) = 384")

    assignments = [
        "llm_model = 'qwen2.5:7b'",
        "embed_model = 'bge-base-en:v1.5'",
    ]
    if has_embed_dims:
        assignments.append("embed_dims = 768")
    if has_updated_at:
        assignments.append("updated_at = CURRENT_TIMESTAMP")

    conn.execute(
        text(
            f"""
            UPDATE ai_config
            SET {", ".join(assignments)}
            WHERE {" AND ".join(filters)}
            """
        )
    )

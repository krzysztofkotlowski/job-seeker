"""Add OpenAI provider support to ai_config."""

from sqlalchemy import inspect, text


def upgrade(conn):
    inspector = inspect(conn)
    if "ai_config" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("ai_config")}

    if "provider" not in columns:
        conn.execute(text("""
            ALTER TABLE ai_config
            ADD COLUMN provider VARCHAR(20) NOT NULL DEFAULT 'ollama'
        """))
    if "openai_api_key" not in columns:
        conn.execute(text("""
            ALTER TABLE ai_config
            ADD COLUMN openai_api_key VARCHAR(500)
        """))
    if "openai_llm_model" not in columns:
        conn.execute(text("""
            ALTER TABLE ai_config
            ADD COLUMN openai_llm_model VARCHAR(100) NOT NULL DEFAULT 'gpt-4o-mini'
        """))
    if "embed_source" not in columns:
        conn.execute(text("""
            ALTER TABLE ai_config
            ADD COLUMN embed_source VARCHAR(20) NOT NULL DEFAULT 'ollama'
        """))
    if "embed_dims" not in columns:
        conn.execute(text("""
            ALTER TABLE ai_config
            ADD COLUMN embed_dims INTEGER
        """))

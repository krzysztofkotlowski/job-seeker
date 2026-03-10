"""Add ai_config and inference_logs tables."""

from sqlalchemy import inspect, text


def upgrade(conn):
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "ai_config" not in tables:
        conn.execute(text("""
            CREATE TABLE ai_config (
                id SERIAL PRIMARY KEY,
                llm_model VARCHAR(255) NOT NULL DEFAULT 'phi3:mini',
                embed_model VARCHAR(255) NOT NULL DEFAULT 'all-minilm',
                temperature FLOAT NOT NULL DEFAULT 0.3,
                max_output_tokens INTEGER NOT NULL DEFAULT 1024,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO ai_config (id, llm_model, embed_model, temperature, max_output_tokens)
            VALUES (1, 'phi3:mini', 'all-minilm', 0.3, 1024)
        """))

    if "inference_logs" not in tables:
        conn.execute(text("""
            CREATE TABLE inference_logs (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                model VARCHAR(255) NOT NULL,
                operation VARCHAR(50) NOT NULL,
                latency_ms INTEGER,
                input_tokens INTEGER,
                output_tokens INTEGER,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        conn.execute(text("CREATE INDEX ix_inference_logs_user_id ON inference_logs (user_id)"))
        conn.execute(text("CREATE INDEX ix_inference_logs_created_at ON inference_logs (created_at)"))

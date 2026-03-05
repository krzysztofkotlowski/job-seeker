"""Add users and resumes tables."""

from sqlalchemy import text, inspect


def upgrade(conn):
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "users" not in tables:
        conn.execute(text("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                keycloak_id VARCHAR(255) NOT NULL UNIQUE,
                email VARCHAR(255),
                username VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_users_keycloak_id ON users (keycloak_id)"))

    if "resumes" not in tables:
        conn.execute(text("""
            CREATE TABLE resumes (
                id UUID PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                extracted_skills TEXT[] DEFAULT '{}',
                uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX ix_resumes_user_id ON resumes (user_id)"))

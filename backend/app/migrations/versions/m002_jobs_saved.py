"""Add saved column to jobs if missing."""

from sqlalchemy import text, inspect


def upgrade(conn):
    inspector = inspect(conn)
    if "jobs" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("jobs")}
    if "saved" not in existing:
        conn.execute(text("ALTER TABLE jobs ADD COLUMN saved BOOLEAN DEFAULT false"))

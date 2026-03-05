"""Add salary PLN and period columns to jobs if missing."""

from sqlalchemy import text, inspect


def upgrade(conn):
    inspector = inspect(conn)
    if "jobs" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("jobs")}
    for col, ddl in [
        ("salary_period", "ALTER TABLE jobs ADD COLUMN salary_period VARCHAR(10)"),
        ("salary_min_pln", "ALTER TABLE jobs ADD COLUMN salary_min_pln FLOAT"),
        ("salary_max_pln", "ALTER TABLE jobs ADD COLUMN salary_max_pln FLOAT"),
    ]:
        if col not in existing:
            conn.execute(text(ddl))

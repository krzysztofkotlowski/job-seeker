"""Run pending migrations in order. Tracks applied migrations in schema_version table.

To add a new migration:
  1. Create app/migrations/versions/m00N_description.py (use m-prefix so the name is a valid Python module).
  2. Implement upgrade(conn) that performs the schema change (conn is a SQLAlchemy Connection).
  3. Use inspect(conn) and conditional DDL to make migrations idempotent where needed.
  4. On startup, run_migrations(engine) will run any new files in sorted order and record them.
"""

import logging
from importlib import import_module
from pathlib import Path

from sqlalchemy import text

log = logging.getLogger(__name__)

MIGRATIONS_PACKAGE = "app.migrations.versions"


def run_migrations(engine):
    """Create schema_version table and run any pending migrations."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_version (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()

    applied = set()
    with engine.connect() as conn:
        for row in conn.execute(text("SELECT name FROM schema_version")):
            applied.add(row[0])
        conn.commit()

    versions_dir = Path(__file__).parent / "versions"
    if not versions_dir.exists():
        log.info("No migrations/versions directory")
        return

    migration_files = sorted(f.stem for f in versions_dir.glob("*.py") if not f.name.startswith("_"))
    for name in migration_files:
        if name in applied:
            continue
        log.info("Running migration: %s", name)
        try:
            mod = import_module(f"{MIGRATIONS_PACKAGE}.{name}")
            run_fn = getattr(mod, "upgrade", None)
            if run_fn is None:
                log.warning("Migration %s has no upgrade()", name)
                continue
            with engine.connect() as conn:
                run_fn(conn)
                conn.execute(text("INSERT INTO schema_version (name) VALUES (:name)"), {"name": name})
                conn.commit()
        except Exception as e:
            log.exception("Migration %s failed: %s", name, e)
            raise

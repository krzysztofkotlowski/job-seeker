import os
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

def get_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://jobseeker:jobseeker@localhost:5432/jobseeker",
    )


DATABASE_URL = get_database_url()

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def wait_for_db(max_attempts: int = 30, delay: float = 1.0) -> None:
    """Retry connecting to the DB (for Docker when postgres is starting)."""
    for attempt in range(max_attempts):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception:
            if attempt == max_attempts - 1:
                raise
            time.sleep(delay)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import jobs, skills, imports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="Job Seeker Tracker",
    version="2.0.0",
    description="API for tracking job offers from justjoin.it and nofluffjobs.com, "
    "with skills analytics, salary normalization, and bulk import.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    import app.models.tables  # noqa: F401 – ensure models are registered
    Base.metadata.create_all(bind=engine)

    from sqlalchemy import text, inspect
    with engine.connect() as conn:
        inspector = inspect(engine)
        if "jobs" in inspector.get_table_names():
            existing = {c["name"] for c in inspector.get_columns("jobs")}
            migrations = {
                "salary_period": "ALTER TABLE jobs ADD COLUMN salary_period VARCHAR(10)",
                "salary_min_pln": "ALTER TABLE jobs ADD COLUMN salary_min_pln FLOAT",
                "salary_max_pln": "ALTER TABLE jobs ADD COLUMN salary_max_pln FLOAT",
            }
            for col, ddl in migrations.items():
                if col not in existing:
                    conn.execute(text(ddl))
                    logging.getLogger(__name__).info("Added column jobs.%s", col)
            conn.commit()

    logging.getLogger(__name__).info("Database tables created / verified")

    from app.import_engine import recover_interrupted_imports
    recover_interrupted_imports()


app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
app.include_router(imports.router, prefix="/api/import", tags=["import"])


@app.get("/api/health")
def health():
    return {"status": "ok"}

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.errors import setup_exception_handlers
from app.routers import jobs, skills, imports, backup

log = logging.getLogger(__name__)

app = FastAPI(
    title="Job Seeker Tracker",
    version="2.0.0",
    description="API for tracking job offers from justjoin.it and nofluffjobs.com, "
    "with skills analytics, salary normalization, and bulk import.",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

setup_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    import app.models.tables  # noqa: F401
    Base.metadata.create_all(bind=engine)
    from app.migrations import run_migrations
    run_migrations(engine)
    from app.import_engine import recover_interrupted_imports
    recover_interrupted_imports()
    log.info("Startup complete")


app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(skills.router, prefix="/api/v1/skills", tags=["skills"])
app.include_router(imports.router, prefix="/api/v1/import", tags=["import"])
app.include_router(backup.router, prefix="/api/v1/backup", tags=["backup"])


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}

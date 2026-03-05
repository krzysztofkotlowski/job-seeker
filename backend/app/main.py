import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.errors import setup_exception_handlers
from app.routers import jobs, skills, imports, backup

log = logging.getLogger(__name__)

# Resume router is optional (depends on pypdf + python-multipart for PDF upload)
try:
    from app.routers import resume
    resume_router = resume.router
except Exception as e:
    log.warning("Resume module not loaded (PDF/JSON resume analysis disabled): %s", e)
    resume_router = None

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
    try:
        from app.database import wait_for_db
        wait_for_db()
        import app.models.tables  # noqa: F401
        Base.metadata.create_all(bind=engine)
        from app.migrations import run_migrations
        run_migrations(engine)
        from app.import_engine import recover_interrupted_imports
        recover_interrupted_imports()
        log.info("Startup complete")
    except Exception as e:
        log.exception("Startup failed (DB or migrations): %s", e)
        raise


app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(skills.router, prefix="/api/v1/skills", tags=["skills"])
app.include_router(imports.router, prefix="/api/v1/import", tags=["import"])
app.include_router(backup.router, prefix="/api/v1/backup", tags=["backup"])
if resume_router is not None:
    app.include_router(resume_router, prefix="/api/v1/resume", tags=["resume"])


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/auth/config")
def auth_config():
    """Return Keycloak config for frontend when auth is enabled."""
    from app.auth import is_auth_enabled, KEYCLOAK_URL, KEYCLOAK_REALM
    if not is_auth_enabled():
        return {"enabled": False}
    return {
        "enabled": True,
        "url": KEYCLOAK_URL,
        "realm": KEYCLOAK_REALM,
    }

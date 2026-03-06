import logging
import threading

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


def _maybe_sync_embeddings_on_startup():
    """If Elasticsearch and embedding service are available, sync jobs for RAG in background."""
    try:
        from app.services.elasticsearch_service import (
            JOBS_INDEX,
            bulk_index_jobs,
            is_available,
            ensure_index,
            _get_client,
        )
        from app.services.embedding_service import is_available as embed_is_available
        from app.database import SessionLocal
        from app.models.tables import JobRow

        if not is_available():
            return
        if not embed_is_available():
            log.debug("Startup embedding sync skipped: Ollama/embedding model not ready")
            return
        client = _get_client()
        if not client or not ensure_index(client):
            return
        if client.count(index=JOBS_INDEX).get("count", 0) > 0:
            return
        db = SessionLocal()
        try:
            rows = db.query(JobRow).all()
            if rows:
                indexed = bulk_index_jobs(rows)
                log.info("Startup: synced %d jobs to Elasticsearch for RAG", indexed)
        finally:
            db.close()
    except Exception as e:
        log.debug("Startup embedding sync skipped: %s", e)


def _run_sync_in_background():
    """Run embedding sync in a background thread so startup is not blocked."""
    def _run():
        try:
            _maybe_sync_embeddings_on_startup()
        except Exception as e:
            log.warning("Background embedding sync failed: %s", e)
    t = threading.Thread(target=_run, daemon=True)
    t.start()


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
        _run_sync_in_background()
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
async def health():
    from app.services.llm_service import check_ollama_health, get_llm_config
    status = {"status": "ok"}
    cfg = get_llm_config()
    if cfg.url:
        status["llm_available"] = await check_ollama_health()
    return status


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

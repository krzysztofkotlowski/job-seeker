import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_cors_origins, get_rate_limit
from app.database import engine, Base, wait_for_db
from app.errors import setup_exception_handlers
from app.routers import ai_config, jobs, skills, imports, backup

log = logging.getLogger(__name__)

# Resume router is optional (depends on pypdf + python-multipart for PDF upload)
try:
    from app.routers import resume
    resume_router = resume.router
except Exception as e:
    log.warning("Resume module not loaded (PDF/JSON resume analysis disabled): %s", e)
    resume_router = None

limiter = Limiter(key_func=get_remote_address, default_limits=[get_rate_limit()])

app = FastAPI(
    title="Job Seeker Tracker",
    version="2.0.0",
    description="API for tracking job offers from justjoin.it and nofluffjobs.com, "
    "with skills analytics, salary normalization, and bulk import.",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
setup_exception_handlers(app)

from app.middleware.request_id import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _maybe_sync_embeddings_on_startup():
    """If Elasticsearch and embedding service are available, sync jobs for RAG in background."""
    try:
        from app.services.elasticsearch_service import (
            _index_for_dims,
            bulk_index_jobs,
            is_available,
            ensure_index,
            _get_client,
        )
        from app.services.embedding_service import is_available as embed_is_available
        from app.services.ai_config_service import get_ai_config
        from app.database import SessionLocal
        from app.models.tables import JobRow

        if not is_available():
            return
        if not embed_is_available():
            log.debug("Startup embedding sync skipped: Ollama/embedding model not ready")
            return
        db = SessionLocal()
        try:
            ai_cfg = get_ai_config(db)
            embed_dims = ai_cfg.get("embed_dims")
            client = _get_client()
            if not client or not ensure_index(client, embed_dims=embed_dims):
                return
            index_name = _index_for_dims(embed_dims)
            if client.count(index=index_name).get("count", 0) > 0:
                return
            rows = db.query(JobRow).all()
            if rows:
                embed_model = ai_cfg["embed_model"] if ai_cfg.get("embed_source") != "openai" else None
                indexed = bulk_index_jobs(rows, embed_model=embed_model, ai_config=ai_cfg)
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
app.include_router(ai_config.router, prefix="/api/v1/ai", tags=["ai"])
if resume_router is not None:
    app.include_router(resume_router, prefix="/api/v1/resume", tags=["resume"])


@app.get("/api/v1/health")
async def health():
    from app.services.llm_service import check_ollama_health, get_llm_config
    from app.services.ai_config_service import get_ai_config
    from app.database import SessionLocal

    status: dict = {"status": "ok"}
    try:
        wait_for_db(max_attempts=1, delay=0)
        status["database_available"] = True
    except Exception:
        status["database_available"] = False
    try:
        from app.services.elasticsearch_service import is_available as es_available
        status["elasticsearch_available"] = es_available()
    except ImportError:
        status["elasticsearch_available"] = False
    try:
        db = SessionLocal()
        try:
            ai_cfg = get_ai_config(db)
            if ai_cfg.get("provider") == "openai":
                status["llm_available"] = bool(ai_cfg.get("api_key_set"))
            else:
                cfg = get_llm_config()
                if cfg.url:
                    db_model = ai_cfg.get("llm_model") or cfg.model
                    status["llm_available"] = await check_ollama_health(model=db_model)
                else:
                    status["llm_available"] = False
        finally:
            db.close()
    except Exception:
        status["llm_available"] = False
    return status


@app.get("/api/v1/auth/config")
def auth_config():
    """Return Keycloak config for frontend when auth is enabled."""
    from app.auth import is_auth_enabled, KEYCLOAK_PUBLIC_URL, KEYCLOAK_REALM
    if not is_auth_enabled():
        return {"enabled": False}
    return {
        "enabled": True,
        "url": KEYCLOAK_PUBLIC_URL,
        "realm": KEYCLOAK_REALM,
    }

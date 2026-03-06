import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app import import_engine
from app.auth import require_auth
from app.celery_app import run_import_all, run_import_source

router = APIRouter()
log = logging.getLogger(__name__)

VALID_SOURCES = {"justjoin.it", "nofluffjobs.com"}


@router.get("/status")
def import_status():
    return {
        "running": import_engine.is_running(),
        "tasks": import_engine.get_all_status(),
    }


@router.post("/start")
def import_start(_user: Annotated[dict | None, Depends(require_auth)] = None):
    if import_engine.is_running():
        return {"message": "Import already running", "running": True}
    run_import_all.delay()
    log.info("Import started for all sources via Celery")
    return {"message": "Import started", "running": True}


@router.post("/start/{source}")
def import_start_source(source: str, _user: Annotated[dict | None, Depends(require_auth)] = None):
    if source not in VALID_SOURCES:
        raise HTTPException(400, f"Invalid source. Must be one of: {', '.join(VALID_SOURCES)}")
    if import_engine.is_source_running(source):
        return {"message": f"{source} import already running", "running": True}
    run_import_source.delay(source)
    log.info("Import started for %s via Celery", source)
    return {"message": f"Import started for {source}", "running": import_engine.is_running()}


@router.post("/cancel")
def import_cancel(_user: Annotated[dict | None, Depends(require_auth)] = None):
    import_engine.cancel_all()
    return {"message": "Cancel requested"}

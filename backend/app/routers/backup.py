"""Database backup endpoint. Supports PostgreSQL via pg_dump."""

import logging
import os
import subprocess
import tempfile
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.database import DATABASE_URL

log = logging.getLogger(__name__)
router = APIRouter()


def _parse_pg_url(url: str) -> dict:
    """Parse PostgreSQL URL into host, port, user, password, dbname."""
    parsed = urlparse(url)
    if not parsed.hostname:
        netloc = parsed.netloc or ""
        if "@" in netloc:
            auth, hostport = netloc.rsplit("@", 1)
            user, _, password = auth.partition(":")
            host, _, port = hostport.partition(":")
            port = port or "5432"
        else:
            user = parsed.username or "postgres"
            password = parsed.password
            host = "localhost"
            port = "5432"
    else:
        user = parsed.username or "postgres"
        password = parsed.password
        host = parsed.hostname
        port = str(parsed.port or 5432)
    dbname = (parsed.path or "").lstrip("/") or "postgres"
    return {"host": host, "port": port, "user": user, "password": password, "dbname": dbname}


@router.post("/create")
def create_backup():
    """
    Create a database backup and return it as a downloadable .sql file.
    Only supports PostgreSQL (uses pg_dump). Requires pg_dump on PATH.
    """
    url = DATABASE_URL or ""
    if "postgresql" not in url.split(":")[0]:
        raise HTTPException(
            status_code=501,
            detail="Backup is only supported for PostgreSQL. Set DATABASE_URL to a postgresql:// URL.",
        )
    try:
        conn = _parse_pg_url(url)
    except Exception as e:
        log.exception("Failed to parse DATABASE_URL")
        raise HTTPException(status_code=500, detail="Invalid DATABASE_URL for backup.") from e

    cmd = [
        "pg_dump",
        "-h", conn["host"],
        "-p", conn["port"],
        "-U", conn["user"],
        "-d", conn["dbname"],
        "--no-owner",
        "--no-acl",
    ]
    env = os.environ.copy()
    if conn.get("password"):
        env["PGPASSWORD"] = conn["password"]

    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".sql")
        os.close(fd)
        with open(tmp, "wb") as out:
            result = subprocess.run(
                cmd,
                stdout=out,
                stderr=subprocess.PIPE,
                env=env,
            )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")
            if os.path.exists(tmp):
                os.unlink(tmp)
            log.warning("pg_dump failed: %s", err)
            raise HTTPException(status_code=500, detail=f"Backup failed: {err}")
    except FileNotFoundError:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
        raise HTTPException(
            status_code=503,
            detail="pg_dump not found. Install PostgreSQL client tools and ensure pg_dump is on PATH.",
        )
    except HTTPException:
        raise
    except Exception as e:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
        raise HTTPException(status_code=500, detail="Backup failed.") from e

    filename = f"jobseeker_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.sql"

    def stream():
        try:
            with open(tmp, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    yield chunk
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    return StreamingResponse(
        stream(),
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

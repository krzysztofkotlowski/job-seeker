"""Background import engine with persistent progress stored in PostgreSQL."""

import logging
import time
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func

from app.database import SessionLocal
from app.models.tables import JobRow, ImportTaskRow
from app.parsers.justjoin import JustJoinParser
from app.parsers.nofluffjobs import NoFluffJobsParser
from app.services.currency import normalize_salary
from app.services.skill_detector import run_detection_batch

log = logging.getLogger(__name__)

SOURCES = ("justjoin.it", "nofluffjobs.com")


def recover_interrupted_imports():
    """Reset any tasks stuck in running/collecting after a server restart."""
    db = SessionLocal()
    try:
        stuck = (
            db.query(ImportTaskRow)
            .filter(ImportTaskRow.status.in_(["running", "collecting"]))
            .all()
        )
        for row in stuck:
            log.warning(
                "Recovering interrupted %s import (was %s, %d pending)",
                row.source, row.status, len(row.pending_urls or []),
            )
            row.status = "error"
            err = list(row.error_log or [])
            err.append("Import interrupted by server restart")
            row.error_log = err
            row.updated_at = _now()
        if stuck:
            db.commit()
            log.info("Recovered %d interrupted import(s)", len(stuck))
    except Exception as e:
        log.warning("Failed to recover imports: %s", e)
    finally:
        db.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_task_dict(source: str) -> dict:
    return {
        "source": source,
        "status": "idle",
        "total": 0,
        "processed": 0,
        "imported": 0,
        "skipped": 0,
        "errors": 0,
        "error_log": [],
        "pending_urls": [],
        "started_at": None,
        "updated_at": None,
    }


def _get_or_create_task(db, source: str) -> ImportTaskRow:
    row = db.query(ImportTaskRow).filter(ImportTaskRow.source == source).first()
    if not row:
        row = ImportTaskRow(source=source, status="idle")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _update_task(source: str, **kwargs):
    db = SessionLocal()
    try:
        row = _get_or_create_task(db, source)
        for k, v in kwargs.items():
            setattr(row, k, v)
        row.updated_at = _now()
        db.commit()
    finally:
        db.close()


def _read_task(source: str) -> dict:
    db = SessionLocal()
    try:
        row = _get_or_create_task(db, source)
        return {
            "status": row.status,
            "total": row.total or 0,
            "processed": row.processed or 0,
            "imported": row.imported or 0,
            "skipped": row.skipped or 0,
            "errors": row.errors or 0,
            "error_log": row.error_log or [],
            "pending_urls": row.pending_urls or [],
            "started_at": row.started_at,
            "updated_at": row.updated_at,
        }
    finally:
        db.close()


def get_all_status() -> list[dict]:
    db = SessionLocal()
    try:
        result = []
        for source in SOURCES:
            row = _get_or_create_task(db, source)
            result.append(row.to_status_dict())
        db.commit()
        return result
    finally:
        db.close()


def is_running() -> bool:
    """Return True if any import task is in a running state."""
    db = SessionLocal()
    try:
        return (
            db.query(ImportTaskRow)
            .filter(ImportTaskRow.status.in_(["collecting", "running"]))
            .first()
            is not None
        )
    finally:
        db.close()


def is_source_running(source: str) -> bool:
    """Return True if the given source has a running task."""
    db = SessionLocal()
    try:
        row = (
            db.query(ImportTaskRow)
            .filter(
                ImportTaskRow.source == source,
                ImportTaskRow.status.in_(["collecting", "running"]),
            )
            .first()
        )
        return row is not None
    finally:
        db.close()


def cancel_all():
    db = SessionLocal()
    try:
        for source in SOURCES:
            row = _get_or_create_task(db, source)
            if row.status in ("collecting", "running"):
                row.status = "cancelled"
                row.updated_at = _now()
        db.commit()
    finally:
        db.close()
    log.info("Import cancellation requested")


def _prepare_source(source: str):
    task = _read_task(source)
    can_resume = task["status"] in ("error", "cancelled") and task.get("pending_urls")
    if not can_resume:
        _update_task(
            source,
            status="collecting",
            total=0, processed=0, imported=0, skipped=0, errors=0,
            error_log=[], pending_urls=[],
            started_at=_now(),
        )
        log.info("Starting fresh %s import", source)
    else:
        _update_task(source, errors=0, error_log=[])
        log.info("Resuming %s (%d pending), errors cleared", source, len(task["pending_urls"]))


def _should_stop(source: str) -> bool:
    return _read_task(source).get("status") == "cancelled"


def _get_existing_urls() -> set[str]:
    db = SessionLocal()
    try:
        return {r[0] for r in db.query(JobRow.url).all()}
    finally:
        db.close()


def _find_repost(db, title: str, company: str, url: str):
    """Check if a job with the same title+company already exists (different URL)."""
    return (
        db.query(JobRow)
        .filter(
            func.lower(JobRow.title) == title.lower(),
            func.lower(JobRow.company) == company.lower(),
            JobRow.url != url,
        )
        .order_by(JobRow.created_at.asc())
        .first()
    )


def _make_job_row(parsed, is_reposted=False, original_job_id=None) -> JobRow:
    sal = parsed.salary
    row = JobRow(
        id=uuid.uuid4(),
        url=parsed.url,
        source=parsed.source,
        title=parsed.title,
        company=parsed.company,
        location=parsed.location,
        salary_min=sal.min if sal else None,
        salary_max=sal.max if sal else None,
        salary_currency=sal.currency if sal else None,
        salary_type=sal.type if sal else None,
        skills_required=parsed.skills_required,
        skills_nice_to_have=parsed.skills_nice_to_have,
        seniority=parsed.seniority,
        work_type=parsed.work_type,
        employment_types=parsed.employment_types,
        description=parsed.description,
        category=getattr(parsed, "category", None),
        date_published=parsed.date_published,
        date_expires=parsed.date_expires,
        date_added=date.today().isoformat(),
        status="new",
        notes="",
        is_reposted=is_reposted,
        original_job_id=original_job_id,
    )
    explicit_period = sal.period if sal and hasattr(sal, "period") else None
    normalize_salary(row, explicit_period=explicit_period)
    return row


def _bulk_insert_with_repost_check(rows_data: list, source: str) -> tuple[int, int]:
    """Insert rows, checking for reposts. Returns (imported, skipped_as_dup)."""
    if not rows_data:
        return 0, 0
    db = SessionLocal()
    imported = 0
    try:
        for parsed, url in rows_data:
            existing = db.query(JobRow).filter(JobRow.url == url).first()
            if existing:
                continue
            original = _find_repost(db, parsed.title, parsed.company, url)
            row = _make_job_row(
                parsed,
                is_reposted=original is not None,
                original_job_id=original.id if original else None,
            )
            db.add(row)
            imported += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return imported, 0


def _run_skill_detection():
    """Run skill detection on all jobs that haven't been processed yet."""
    db = SessionLocal()
    try:
        run_detection_batch(db)
    except Exception as e:
        log.warning("Skill detection failed: %s", e)
    finally:
        db.close()


# ── JustJoin.it ─────────────────────────────────────────────────────

def _run_justjoin():
    source = "justjoin.it"
    try:
        task = _read_task(source)
        resuming = task["status"] in ("error", "cancelled") and task.get("pending_urls")

        if not resuming:
            _update_task(source, status="collecting")
            log.info("[JJ] Collecting URLs from listing pages...")
            all_urls: list[str] = []

            for page_idx in range(500):
                if _should_stop(source):
                    log.info("[JJ] Cancelled during collection")
                    return
                offset = page_idx * 100
                try:
                    urls = JustJoinParser.scrape_listing_page(offset)
                    if not urls:
                        log.info("[JJ] No more at offset %d", offset)
                        break
                    new = [u for u in urls if u not in all_urls]
                    all_urls.extend(new)
                    log.info("[JJ] offset=%d +%d (total %d)", offset, len(new), len(all_urls))
                    _update_task(source, total=len(all_urls))
                    time.sleep(0.3)
                except Exception as e:
                    log.warning("[JJ] Scrape error offset=%d: %s", offset, e)
                    break

            _update_task(source, status="running", total=len(all_urls), pending_urls=all_urls)
        else:
            all_urls = list(task["pending_urls"])
            _update_task(source, status="running")
            log.info("[JJ] Resuming with %d pending", len(all_urls))

        existing = _get_existing_urls()
        parser = JustJoinParser()
        task = _read_task(source)
        imported = task.get("imported", 0)
        skipped = task.get("skipped", 0)
        errors = task.get("errors", 0)
        error_log = list(task.get("error_log", []))
        batch: list[tuple] = []

        while all_urls:
            if _should_stop(source):
                _flush_batch(batch, source)
                _update_task(source, pending_urls=all_urls)
                log.info("[JJ] Cancelled, %d remaining", len(all_urls))
                return

            url = all_urls.pop(0)
            try:
                if url in existing:
                    skipped += 1
                else:
                    parsed = parser.parse(url)
                    if parsed.url in existing:
                        skipped += 1
                    else:
                        batch.append((parsed, parsed.url))
                        existing.add(parsed.url)
                        imported += 1
            except Exception as e:
                errors += 1
                error_log.append(f"{url}: {e}")
                log.warning("[JJ] Parse error %s: %s", url, e)

            if len(batch) >= 10:
                _flush_batch(batch, source)
                batch = []

            processed = imported + skipped + errors
            if processed % 10 == 0 or not all_urls:
                _update_task(
                    source,
                    processed=processed, imported=imported,
                    skipped=skipped, errors=errors,
                    error_log=error_log[-50:], pending_urls=all_urls,
                )
            time.sleep(0.3)

        _flush_batch(batch, source)

        _update_task(
            source, status="done",
            processed=imported + skipped + errors,
            imported=imported, skipped=skipped, errors=errors,
            error_log=error_log[-50:], pending_urls=[],
        )
        log.info("[JJ] Done: imported=%d skipped=%d errors=%d", imported, skipped, errors)

        _run_skill_detection()

    except Exception as e:
        log.exception("[JJ] Fatal: %s", e)
        _update_task(source, status="error", error_log=[f"FATAL: {e}"])


def _flush_batch(batch: list[tuple], source: str):
    if not batch:
        return
    db = SessionLocal()
    try:
        for parsed, url in batch:
            existing = db.query(JobRow).filter(JobRow.url == url).first()
            if existing:
                continue
            original = _find_repost(db, parsed.title, parsed.company, url)
            row = _make_job_row(
                parsed,
                is_reposted=original is not None,
                original_job_id=original.id if original else None,
            )
            db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        log.warning("[%s] Batch insert failed, rolling back", source)
        raise
    finally:
        db.close()


# ── NoFluffJobs ─────────────────────────────────────────────────────

def _run_nofluffjobs():
    source = "nofluffjobs.com"
    try:
        task = _read_task(source)
        resuming = task["status"] in ("error", "cancelled") and task.get("pending_urls")

        posting_map: dict = {}

        if not resuming:
            _update_task(source, status="collecting")
            log.info("[NF] Fetching postings from API...")
            try:
                postings = NoFluffJobsParser.fetch_all_postings()
            except Exception as e:
                log.error("[NF] API fetch failed: %s", e)
                _update_task(source, status="error", error_log=[f"API fetch: {e}"])
                return

            log.info("[NF] Got %d postings", len(postings))
            all_urls: list[str] = []
            for p in postings:
                try:
                    parsed = NoFluffJobsParser.parse_api_posting(p)
                    if parsed.url not in posting_map:
                        all_urls.append(parsed.url)
                        posting_map[parsed.url] = parsed
                except Exception as e:
                    log.warning("[NF] Pre-parse error %s: %s", p.get("id", "?"), e)

            _update_task(source, status="running", total=len(all_urls), pending_urls=all_urls)
        else:
            all_urls = list(task["pending_urls"])
            _update_task(source, status="running")
            log.info("[NF] Resuming with %d pending", len(all_urls))

        existing = _get_existing_urls()
        task = _read_task(source)
        imported = task.get("imported", 0)
        skipped = task.get("skipped", 0)
        errors = task.get("errors", 0)
        error_log = list(task.get("error_log", []))

        batch_size = 500
        while all_urls:
            if _should_stop(source):
                _update_task(source, pending_urls=all_urls)
                log.info("[NF] Cancelled, %d remaining", len(all_urls))
                return

            chunk = all_urls[:batch_size]
            all_urls = all_urls[batch_size:]

            db = SessionLocal()
            try:
                for url in chunk:
                    if url in existing:
                        skipped += 1
                        continue

                    parsed = posting_map.get(url)
                    if not parsed:
                        try:
                            parsed = NoFluffJobsParser().parse(url)
                        except Exception as e:
                            errors += 1
                            error_log.append(f"{url}: {e}")
                            log.warning("[NF] Parse error %s: %s", url, e)
                            continue

                    try:
                        original = _find_repost(db, parsed.title, parsed.company, url)
                        row = _make_job_row(
                            parsed,
                            is_reposted=original is not None,
                            original_job_id=original.id if original else None,
                        )
                        db.add(row)
                        existing.add(parsed.url)
                        imported += 1
                    except Exception as e:
                        errors += 1
                        error_log.append(f"{url}: {e}")

                db.commit()
            except Exception:
                db.rollback()
                log.warning("[NF] Batch commit failed")
            finally:
                db.close()

            processed = imported + skipped + errors
            _update_task(
                source,
                processed=processed, imported=imported,
                skipped=skipped, errors=errors,
                error_log=error_log[-50:], pending_urls=all_urls,
            )
            total = task.get("total", 0)
            log.info("[NF] %d/%d (imported=%d)", processed, total, imported)

        _update_task(
            source, status="done",
            processed=imported + skipped + errors,
            imported=imported, skipped=skipped, errors=errors,
            error_log=error_log[-50:], pending_urls=[],
        )
        log.info("[NF] Done: imported=%d skipped=%d errors=%d", imported, skipped, errors)

        _run_skill_detection()

    except Exception as e:
        log.exception("[NF] Fatal: %s", e)
        _update_task(source, status="error", error_log=[f"FATAL: {e}"])

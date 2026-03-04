"""Detect known skills from job title/description text."""

import logging
import re

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.tables import JobRow, DetectedSkillRow

log = logging.getLogger(__name__)


def _get_known_skills(db: Session) -> set[str]:
    """Collect all unique skill names from skills_required + skills_nice_to_have."""
    req = (
        db.query(func.unnest(JobRow.skills_required).label("s"))
        .distinct()
        .all()
    )
    nice = (
        db.query(func.unnest(JobRow.skills_nice_to_have).label("s"))
        .distinct()
        .all()
    )
    return {r[0].strip() for r in req if r[0]} | {r[0].strip() for r in nice if r[0]}


def _find_skills_in_text(text: str, known_skills: set[str]) -> dict[str, str]:
    """Return {skill_name: source_field} found in text. Uses word-boundary matching."""
    if not text:
        return {}
    found: dict[str, str] = {}
    text_lower = text.lower()
    for skill in known_skills:
        pattern = re.escape(skill.lower())
        if re.search(r"(?:^|[\s,;()\[\]/|.]){}(?:[\s,;()\[\]/|.]|$)".format(pattern), text_lower):
            found[skill] = "description"
    return found


def detect_skills_for_job(db: Session, job_row: JobRow, known_skills: set[str]) -> int:
    """Detect skills in a single job's title + description. Returns count of new inserts."""
    existing_skills = set(job_row.skills_required or []) | set(job_row.skills_nice_to_have or [])
    existing_lower = {s.lower() for s in existing_skills}

    combined_text = ""
    title = job_row.title or ""
    description = job_row.description or ""

    title_matches = _find_skills_in_text(title, known_skills)
    desc_matches = _find_skills_in_text(description, known_skills)

    all_matches: dict[str, str] = {}
    for skill, _ in desc_matches.items():
        if skill.lower() not in existing_lower:
            all_matches[skill] = "description"
    for skill, _ in title_matches.items():
        if skill.lower() not in existing_lower:
            all_matches[skill] = "title"

    if not all_matches:
        return 0

    inserted = 0
    for skill_name, source_field in all_matches.items():
        stmt = pg_insert(DetectedSkillRow).values(
            job_id=job_row.id,
            skill_name=skill_name,
            source_field=source_field,
        ).on_conflict_do_nothing(index_elements=["job_id", "skill_name"])
        db.execute(stmt)
        inserted += 1

    return inserted


def run_detection_batch(db: Session, job_ids: list | None = None) -> int:
    """Run skill detection for jobs. If job_ids given, only those; else all without detections."""
    known_skills = _get_known_skills(db)
    if not known_skills:
        log.info("No known skills in DB, skipping detection")
        return 0

    log.info("Skill detection: %d known skills", len(known_skills))

    if job_ids:
        jobs = db.query(JobRow).filter(JobRow.id.in_(job_ids)).all()
    else:
        already_detected = db.query(DetectedSkillRow.job_id).distinct().subquery()
        jobs = db.query(JobRow).filter(~JobRow.id.in_(db.query(already_detected.c.job_id))).all()

    total = 0
    for job in jobs:
        count = detect_skills_for_job(db, job, known_skills)
        total += count

    db.commit()
    log.info("Skill detection complete: %d skills found across %d jobs", total, len(jobs))
    return total

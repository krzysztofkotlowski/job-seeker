import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Column, String, Float, Boolean, Text, Integer, DateTime, ARRAY,
    ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class UserRow(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keycloak_id = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ResumeRow(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    extracted_skills = Column(ARRAY(Text), default=list)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class JobRow(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(Text, unique=True, nullable=False, index=True)
    source = Column(String(50), nullable=False, index=True)
    title = Column(Text, nullable=False)
    company = Column(Text, nullable=False)
    location = Column(ARRAY(Text), default=list)

    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(10), nullable=True)
    salary_type = Column(String(30), nullable=True)
    salary_period = Column(String(10), nullable=True)
    salary_min_pln = Column(Float, nullable=True)
    salary_max_pln = Column(Float, nullable=True)

    skills_required = Column(ARRAY(Text), default=list)
    skills_nice_to_have = Column(ARRAY(Text), default=list)
    seniority = Column(String(30), nullable=True)
    work_type = Column(String(30), nullable=True)
    employment_types = Column(ARRAY(Text), default=list)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True, index=True)

    is_reposted = Column(Boolean, default=False, server_default="false")
    original_job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True)

    date_published = Column(String(20), nullable=True)
    date_expires = Column(String(20), nullable=True)
    date_added = Column(String(20), nullable=False, default=lambda: date.today().isoformat())
    status = Column(String(20), nullable=False, default="new")
    applied_date = Column(String(20), nullable=True)
    notes = Column(Text, default="")
    saved = Column(Boolean, default=False, server_default="false")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    original_job = relationship("JobRow", remote_side=[id], foreign_keys=[original_job_id])

    __table_args__ = (
        Index("idx_jobs_company_title", "company", "title"),
    )

    def to_dict(self) -> dict:
        salary = None
        if self.salary_min is not None or self.salary_max is not None:
            salary = {
                "min": self.salary_min,
                "max": self.salary_max,
                "currency": self.salary_currency,
                "type": self.salary_type,
                "period": self.salary_period,
                "min_pln": self.salary_min_pln,
                "max_pln": self.salary_max_pln,
            }
        return {
            "id": str(self.id),
            "url": self.url,
            "source": self.source,
            "title": self.title,
            "company": self.company,
            "location": self.location or [],
            "salary": salary,
            "skills_required": self.skills_required or [],
            "skills_nice_to_have": self.skills_nice_to_have or [],
            "seniority": self.seniority,
            "work_type": self.work_type,
            "employment_types": self.employment_types or [],
            "description": self.description,
            "category": self.category,
            "is_reposted": self.is_reposted or False,
            "original_job_id": str(self.original_job_id) if self.original_job_id else None,
            "date_published": self.date_published,
            "date_expires": self.date_expires,
            "date_added": self.date_added,
            "status": self.status,
            "applied_date": self.applied_date,
            "notes": self.notes or "",
            "saved": self.saved or False,
        }


class DetectedSkillRow(Base):
    __tablename__ = "detected_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_name = Column(Text, nullable=False)
    source_field = Column(String(20), nullable=True)

    __table_args__ = (
        Index("uq_detected_skill_job", "job_id", "skill_name", unique=True),
    )


class ImportTaskRow(Base):
    __tablename__ = "import_tasks"

    source = Column(String(50), primary_key=True)
    status = Column(String(20), default="idle")
    total = Column(Integer, default=0)
    processed = Column(Integer, default=0)
    imported = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    error_log = Column(ARRAY(Text), default=list)
    pending_urls = Column(ARRAY(Text), default=list)
    started_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    def to_status_dict(self) -> dict:
        return {
            "source": self.source,
            "status": self.status or "idle",
            "total": self.total or 0,
            "processed": self.processed or 0,
            "imported": self.imported or 0,
            "skipped": self.skipped or 0,
            "errors": self.errors or 0,
            "error_log": self.error_log or [],
            "pending": len(self.pending_urls or []),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

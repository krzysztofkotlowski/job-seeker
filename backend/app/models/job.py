from __future__ import annotations

import uuid
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    NEW = "new"
    SEEN = "seen"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"


class Salary(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: Optional[str] = None
    type: Optional[str] = None
    period: Optional[str] = None


class JobBase(BaseModel):
    url: str
    source: str
    title: str
    company: str
    location: list[str] = []
    salary: Optional[Salary] = None
    skills_required: list[str] = []
    skills_nice_to_have: list[str] = []
    seniority: Optional[str] = None
    work_type: Optional[str] = None
    employment_types: list[str] = []
    description: Optional[str] = None
    category: Optional[str] = None
    date_published: Optional[str] = None
    date_expires: Optional[str] = None


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    status: Optional[JobStatus] = None
    applied_date: Optional[str] = None
    notes: Optional[str] = None
    is_reposted: Optional[bool] = None
    saved: Optional[bool] = None


class Job(JobBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date_added: str = Field(default_factory=lambda: date.today().isoformat())
    status: JobStatus = JobStatus.NEW
    applied_date: Optional[str] = None
    notes: str = ""
    is_reposted: bool = False
    original_job_id: Optional[str] = None
    saved: bool = False


class ParseRequest(BaseModel):
    url: str


class DuplicateCheck(BaseModel):
    is_duplicate: bool
    existing_job: Optional[Job] = None

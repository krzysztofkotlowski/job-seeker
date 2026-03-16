"""Pydantic schemas for resume analysis."""

from typing import Any

from pydantic import BaseModel, Field


class ResumeSummarizeRequest(BaseModel):
    """Request body for /resume/summarize and /resume/summarize/stream."""

    extracted_skills: list[str] = Field(default_factory=list, description="Skills extracted from resume")
    matches: list[dict[str, Any]] = Field(default_factory=list, description="Job matches with matched_skills")
    by_category: list[dict[str, Any]] = Field(default_factory=list, description="Category match scores and skills")
    model_override: str | None = Field(None, description="Override LLM model for this request")


class ResumeRecommendationsRequest(BaseModel):
    """Request body for /resume/recommendations."""

    extracted_skills: list[str] = Field(default_factory=list, description="Skills extracted from resume")

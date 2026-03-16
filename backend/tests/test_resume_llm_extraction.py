"""Tests for LLM-based skill extraction."""

import pytest

from app.services.resume_llm_extraction import _parse_skills_json


def test_parse_skills_json_valid():
    """Parse valid JSON with skills array."""
    raw = '{"skills": ["Python", "Django", "React"]}'
    result = _parse_skills_json(raw)
    assert result == {"Python", "Django", "React"}


def test_parse_skills_json_with_extra_text():
    """Parse JSON embedded in extra text."""
    raw = 'Here is the result: {"skills": ["Docker", "Kubernetes"]}'
    result = _parse_skills_json(raw)
    assert result == {"Docker", "Kubernetes"}


def test_parse_skills_json_fallback_array_pattern():
    """Fallback to array pattern when JSON block fails."""
    raw = 'Some text ["Python", "FastAPI"] more text'
    result = _parse_skills_json(raw)
    assert "Python" in result
    assert "FastAPI" in result


def test_parse_skills_json_empty():
    """Return empty set for empty or invalid input."""
    assert _parse_skills_json("") == set()
    assert _parse_skills_json("   ") == set()
    assert _parse_skills_json("not json at all") == set()
    assert _parse_skills_json('{"other": "value"}') == set()

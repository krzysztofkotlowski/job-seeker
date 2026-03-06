"""Tests for job parsers (NoFluffJobs, JustJoin)."""

import pytest

from app.parsers.nofluffjobs import NoFluffJobsParser


class TestNoFluffJobsParseApiPosting:
    def test_extracts_skills_required_from_tiles(self):
        posting = {
            "url": "acme-python-dev",
            "title": "Python Developer",
            "name": "Acme",
            "category": {"name": "Backend"},
            "location": {"places": [{"city": "Warszawa"}]},
            "tiles": {
                "values": [
                    {"type": "requirement", "value": "Python"},
                    {"type": "requirement", "value": "Django"},
                ],
            },
            "seniority": ["mid"],
        }
        result = NoFluffJobsParser.parse_api_posting(posting)
        assert result.skills_required == ["Python", "Django"]
        assert result.skills_nice_to_have == []

    def test_extracts_skills_nice_to_have_when_present(self):
        posting = {
            "url": "acme-python-dev",
            "title": "Python Developer",
            "name": "Acme",
            "category": {"name": "Backend"},
            "location": {"places": []},
            "tiles": {
                "values": [
                    {"type": "requirement", "value": "Python"},
                    {"type": "nice_to_have", "value": "Redis"},
                    {"type": "optional", "value": "Docker"},
                ],
            },
            "seniority": ["mid"],
        }
        result = NoFluffJobsParser.parse_api_posting(posting)
        assert result.skills_required == ["Python"]
        assert set(result.skills_nice_to_have) == {"Redis", "Docker"}

    def test_extracts_description_when_present(self):
        posting = {
            "url": "acme-python-dev",
            "title": "Python Developer",
            "name": "Acme",
            "category": {"name": "Backend"},
            "location": {"places": []},
            "tiles": {"values": []},
            "seniority": ["mid"],
            "description": "We are looking for a Python developer.",
        }
        result = NoFluffJobsParser.parse_api_posting(posting)
        assert result.description == "We are looking for a Python developer."

    def test_extracts_description_from_offer_description_fallback(self):
        posting = {
            "url": "acme-python-dev",
            "title": "Python Developer",
            "name": "Acme",
            "category": {"name": "Backend"},
            "location": {"places": []},
            "tiles": {"values": []},
            "seniority": ["mid"],
            "offerDescription": "Full job description here.",
        }
        result = NoFluffJobsParser.parse_api_posting(posting)
        assert result.description == "Full job description here."

    def test_skips_long_tile_values(self):
        posting = {
            "url": "acme-python-dev",
            "title": "Python Developer",
            "name": "Acme",
            "category": {"name": "Backend"},
            "location": {"places": []},
            "tiles": {
                "values": [
                    {"type": "requirement", "value": "Python"},
                    {"type": "requirement", "value": "x" * 60},
                ],
            },
            "seniority": ["mid"],
        }
        result = NoFluffJobsParser.parse_api_posting(posting)
        assert result.skills_required == ["Python"]

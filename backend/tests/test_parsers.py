"""Tests for job parsers (NoFluffJobs, JustJoin)."""

from app.parsers.detector import is_supported_url
from app.parsers.nofluffjobs import NoFluffJobsParser


def test_is_supported_url_true_justjoin():
    """is_supported_url returns True for justjoin.it URLs."""
    assert is_supported_url("https://justjoin.it/jobs/acme-python-dev") is True


def test_is_supported_url_true_nofluff():
    """is_supported_url returns True for nofluffjobs.com URLs."""
    assert is_supported_url("https://nofluffjobs.com/job/acme-python-dev") is True


def test_is_supported_url_false():
    """is_supported_url returns False for unsupported URLs."""
    assert is_supported_url("https://example.com/job/123") is False


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

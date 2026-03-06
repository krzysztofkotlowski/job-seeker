"""Tests for Elasticsearch service."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("elasticsearch")
from app.services import elasticsearch_service


def test_is_available_false_when_es_down():
    """is_available returns False when client.ping raises."""
    with patch.object(elasticsearch_service, "_get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("connection refused")
        mock_get.return_value = mock_client
        assert elasticsearch_service.is_available() is False


def test_is_available_true_when_es_up():
    """is_available returns True when client.ping succeeds."""
    with patch.object(elasticsearch_service, "_get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_get.return_value = mock_client
        assert elasticsearch_service.is_available() is True


def test_search_similar_returns_empty_when_no_client():
    """search_similar returns [] when _get_client returns None."""
    with patch.object(elasticsearch_service, "_get_client", return_value=None):
        assert elasticsearch_service.search_similar([0.1] * 768) == []


def test_search_similar_returns_empty_when_no_embedding():
    """search_similar returns [] when query_embedding is empty."""
    assert elasticsearch_service.search_similar([]) == []


def test_search_similar_returns_hits():
    """search_similar returns parsed hits from kNN response."""
    mock_resp = {
        "hits": {
            "hits": [
                {
                    "_source": {"job_id": "abc", "title": "Dev", "company": "Acme", "url": "https://x.com", "category": "Backend"},
                    "_score": 0.95,
                }
            ]
        }
    }
    with patch.object(elasticsearch_service, "_get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_resp
        mock_get.return_value = mock_client

        result = elasticsearch_service.search_similar([0.1] * 768, top_k=5)
    assert len(result) == 1
    assert result[0]["job_id"] == "abc"
    assert result[0]["title"] == "Dev"
    assert result[0]["score"] == 0.95


def test_bulk_index_jobs_returns_count(db):
    """bulk_index_jobs returns indexed count when mocks succeed."""
    from app.models.tables import JobRow
    from uuid import uuid4

    job = JobRow(
        id=uuid4(),
        url="https://example.com/job/1",
        source="test",
        title="Dev",
        company="Acme",
        skills_required=["Python"],
        skills_nice_to_have=[],
        date_added="2024-01-01",
    )
    db.add(job)
    db.commit()

    with (
        patch.object(elasticsearch_service, "_get_client") as mock_get,
        patch.object(elasticsearch_service, "embed_batch") as mock_embed,
    ):
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_embed.return_value = [[0.1] * 768]
        mock_get.return_value = mock_client

        rows = db.query(JobRow).all()
        result = elasticsearch_service.bulk_index_jobs(rows)
    assert result == 1


def test_ensure_index_creates_when_missing():
    """ensure_index creates index when it does not exist."""
    with patch.object(elasticsearch_service, "_get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = False
        mock_get.return_value = mock_client

        result = elasticsearch_service.ensure_index(mock_client)
    assert result is True
    mock_client.indices.create.assert_called_once()

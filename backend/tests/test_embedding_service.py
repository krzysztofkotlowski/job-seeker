"""Tests for embedding service."""

from unittest.mock import MagicMock, patch

import pytest

from app.services import embedding_service


def test_embed_text_returns_none_when_disabled():
    """When LLM_URL is empty, embed_text returns None."""
    with patch.dict("os.environ", {"LLM_URL": ""}, clear=False):
        embedding_service.EMBED_URL = ""
        result = embedding_service.embed_text("hello")
    assert result is None


def test_embed_text_returns_none_when_empty_input():
    """When input is empty or whitespace, embed_text returns None."""
    with patch.object(embedding_service, "EMBED_URL", "http://ollama:11434"):
        assert embedding_service.embed_text("") is None
        assert embedding_service.embed_text("   ") is None


def test_embed_text_returns_vector_when_ollama_responds():
    """When Ollama returns embeddings, embed_text returns 768-dim vector."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.1] * 768]}

    with (
        patch.object(embedding_service, "EMBED_URL", "http://ollama:11434"),
        patch.object(embedding_service, "httpx") as mock_httpx,
    ):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value = mock_client

        result = embedding_service.embed_text("hello world")
    assert result is not None
    assert len(result) == 768
    assert result[0] == 0.1


def test_embed_batch_returns_list():
    """embed_batch returns list of vectors."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.1] * 768, [0.2] * 768]}

    with (
        patch.object(embedding_service, "EMBED_URL", "http://ollama:11434"),
        patch.object(embedding_service, "httpx") as mock_httpx,
    ):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value = mock_client

        result = embedding_service.embed_batch(["a", "b"])
    assert len(result) == 2
    assert len(result[0]) == 768


def test_embed_batch_returns_empty_when_no_url():
    """embed_batch returns [] when EMBED_URL is empty."""
    with patch.object(embedding_service, "EMBED_URL", ""):
        assert embedding_service.embed_batch(["a"]) == []


def test_is_available_false_when_no_url():
    """is_available returns False when URL is empty."""
    with patch.object(embedding_service, "EMBED_URL", ""):
        assert embedding_service.is_available() is False


def test_is_available_true_when_model_loaded():
    """is_available returns True when model is in /api/tags."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "nomic-embed-text:latest"}]}

    with (
        patch.object(embedding_service, "EMBED_URL", "http://ollama:11434"),
        patch.object(embedding_service, "httpx") as mock_httpx,
    ):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_httpx.Client.return_value = mock_client

        assert embedding_service.is_available() is True

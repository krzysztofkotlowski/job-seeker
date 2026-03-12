"""Tests for embedding service."""

from unittest.mock import MagicMock, patch

from app.services import embedding_service
from app.services.embedding_profiles import (
    BGE_QUERY_PREFIX,
    NOMIC_DOCUMENT_PREFIX,
    NOMIC_QUERY_PREFIX,
)


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


def test_embed_text_prefixes_bge_query_inputs():
    """BGE query embeddings should use the model-card search prefix."""
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

        embedding_service.embed_text(
            "distributed systems",
            model="bge-base-en:v1.5",
            ai_config={"embed_source": "ollama"},
            usage="query",
        )

    posted = mock_client.post.call_args.kwargs["json"]
    assert posted["input"].startswith(BGE_QUERY_PREFIX)
    assert posted["input"].endswith("distributed systems")


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


def test_embed_batch_prefixes_nomic_document_inputs():
    """Prefix-correct nomic indexing should use the document prefix."""
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

        embedding_service.embed_batch(
            ["python backend", "distributed systems"],
            model="nomic-embed-text",
            ai_config={"embed_source": "ollama", "embed_profile": "nomic-search-v1"},
            usage="document",
        )

    posted = mock_client.post.call_args.kwargs["json"]
    assert posted["input"] == [
        f"{NOMIC_DOCUMENT_PREFIX}python backend",
        f"{NOMIC_DOCUMENT_PREFIX}distributed systems",
    ]


def test_embed_text_prefixes_nomic_query_inputs():
    """Prefix-correct nomic queries should use the query prefix."""
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

        embedding_service.embed_text(
            "python backend",
            model="nomic-embed-text",
            ai_config={"embed_source": "ollama", "embed_profile": "nomic-search-v1"},
            usage="query",
        )

    posted = mock_client.post.call_args.kwargs["json"]
    assert posted["input"] == f"{NOMIC_QUERY_PREFIX}python backend"


def test_embed_batch_returns_empty_when_no_url():
    """embed_batch returns [] when EMBED_URL is empty."""
    with patch.object(embedding_service, "EMBED_URL", ""):
        assert embedding_service.embed_batch(["a"]) == []


def test_is_available_false_when_no_url():
    """is_available returns False when URL is empty."""
    with patch.object(embedding_service, "EMBED_URL", ""):
        assert embedding_service.is_available() is False


def test_is_available_true_when_model_loaded():
    """is_available returns True when the self-hosted embedding runtime is ready."""
    with patch.object(embedding_service, "is_ollama_model_ready", return_value=True):
        assert embedding_service.is_available() is True


def test_embed_text_openai_returns_vector_when_api_responds():
    """When ai_config has embed_source=openai, uses OpenAI API."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": [{"embedding": [0.5] * 1536}]}

    with patch.object(embedding_service, "httpx") as mock_httpx:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value = mock_client

        ai_config = {
            "embed_source": "openai",
            "openai_api_key": "sk-test",
        }
        result = embedding_service.embed_text("hello", ai_config=ai_config)
    assert result is not None
    assert len(result) == 1536
    assert result[0] == 0.5


def test_embed_batch_openai_returns_list():
    """embed_batch with ai_config openai uses OpenAI API."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.1] * 1536},
            {"index": 1, "embedding": [0.2] * 1536},
        ]
    }

    with patch.object(embedding_service, "httpx") as mock_httpx:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value = mock_client

        ai_config = {"embed_source": "openai", "openai_api_key": "sk-test"}
        result = embedding_service.embed_batch(["a", "b"], ai_config=ai_config)
    assert len(result) == 2
    assert len(result[0]) == 1536


def test_get_ollama_embedding_dims_prefers_runtime_catalog_metadata():
    with patch.object(embedding_service, "get_self_hosted_embedding_dims", return_value=384), patch.object(
        embedding_service, "embed_text"
    ) as embed_text:
        assert embedding_service.get_ollama_embedding_dims("all-minilm") == 384
    embed_text.assert_not_called()


def test_get_ollama_embedding_dims_falls_back_to_probe_when_catalog_metadata_missing():
    with patch.object(embedding_service, "get_self_hosted_embedding_dims", return_value=None), patch.object(
        embedding_service, "embed_text", return_value=[0.1] * 768
    ) as embed_text:
        assert embedding_service.get_ollama_embedding_dims("custom-embed") == 768
    embed_text.assert_called_once()


def test_embed_documents_individually_retries_failed_items():
    with patch.object(
        embedding_service,
        "embed_text",
        side_effect=[None, [0.1] * 768, [0.2] * 768],
    ) as embed_text:
        result = embedding_service.embed_documents_individually(
            ["first", "second"],
            model="nomic-embed-text",
            ai_config={"embed_source": "ollama", "embed_profile": "nomic-search-v1"},
        )

    assert result == [[0.1] * 768, [0.2] * 768]
    assert embed_text.call_count == 3

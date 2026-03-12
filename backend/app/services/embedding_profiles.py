"""Embedding profile resolution and input preparation for self-hosted search models."""

from __future__ import annotations

EMBED_PROFILE_RAW = "raw-v1"
EMBED_PROFILE_BGE = "bge-v1"
EMBED_PROFILE_NOMIC_LEGACY = "nomic-legacy-v1"
EMBED_PROFILE_NOMIC_SEARCH = "nomic-search-v1"
EMBED_PROFILE_OPENAI = "openai-v1"

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
NOMIC_DOCUMENT_PREFIX = "search_document: "
NOMIC_QUERY_PREFIX = "search_query: "


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _normalized_model(model: str | None) -> str:
    return _clean(model).lower()


def is_bge_model(model: str | None) -> bool:
    return "bge" in _normalized_model(model)


def is_nomic_model(model: str | None) -> bool:
    return "nomic-embed-text" in _normalized_model(model)


def resolve_selected_embed_profile(
    embed_source: str | None,
    embed_model: str | None,
    embed_profile: str | None = None,
) -> str:
    source = _clean(embed_source).lower() or "ollama"
    explicit = _clean(embed_profile)
    if source == "openai":
        return EMBED_PROFILE_OPENAI
    if explicit:
        return explicit
    if is_nomic_model(embed_model):
        return EMBED_PROFILE_NOMIC_SEARCH
    if is_bge_model(embed_model):
        return EMBED_PROFILE_BGE
    return EMBED_PROFILE_RAW


def resolve_run_embed_profile(
    embed_source: str | None,
    embed_model: str | None,
    embed_profile: str | None = None,
) -> str:
    source = _clean(embed_source).lower() or "ollama"
    explicit = _clean(embed_profile)
    if source == "openai":
        return EMBED_PROFILE_OPENAI
    if explicit:
        return explicit
    if is_nomic_model(embed_model):
        return EMBED_PROFILE_NOMIC_LEGACY
    if is_bge_model(embed_model):
        return EMBED_PROFILE_BGE
    return EMBED_PROFILE_RAW


def prepare_embedding_input(
    text: str | None,
    *,
    embed_source: str | None,
    embed_model: str | None,
    embed_profile: str | None,
    usage: str,
) -> str:
    cleaned = _clean(text)
    if not cleaned:
        return ""

    source = _clean(embed_source).lower() or "ollama"
    if source == "openai":
        return cleaned

    profile = resolve_selected_embed_profile(source, embed_model, embed_profile)
    if profile == EMBED_PROFILE_BGE and usage == "query":
        return f"{BGE_QUERY_PREFIX}{cleaned}"
    if profile == EMBED_PROFILE_NOMIC_SEARCH:
        prefix = NOMIC_QUERY_PREFIX if usage == "query" else NOMIC_DOCUMENT_PREFIX
        return f"{prefix}{cleaned}"
    return cleaned

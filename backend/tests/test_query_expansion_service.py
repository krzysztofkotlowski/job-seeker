"""Tests for query expansion service."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.query_expansion_service import _parse_queries_json, expand_query_llm


def test_parse_queries_json_valid():
    """Parse valid JSON with queries array."""
    raw = '{"queries": ["Python backend developer", "Django engineer"]}'
    result = _parse_queries_json(raw)
    assert result == ["Python backend developer", "Django engineer"]


def test_parse_queries_json_empty():
    """Return empty list for empty or invalid input."""
    assert _parse_queries_json("") == []
    assert _parse_queries_json("   ") == []
    assert _parse_queries_json("not json") == []


def test_expand_query_returns_original_on_failure():
    """When LLM fails or returns invalid JSON, return [original]."""
    with patch(
        "app.services.llm_service._chat",
        new_callable=AsyncMock,
        side_effect=Exception("LLM unavailable"),
    ):
        result = asyncio.run(expand_query_llm({"Python", "Django"}))
    assert result == ["Django Python"]

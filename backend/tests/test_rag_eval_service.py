"""Tests for RAG evaluation service."""

import pytest

from app.services.rag_eval_service import recall_at_k


def test_recall_at_k():
    """Compute recall@k correctly."""
    retrieved = ["a", "b", "c", "d", "e"]
    gold = {"a", "c", "e", "f"}
    assert recall_at_k(retrieved, gold, k=3) == 2 / 4  # a, c in top 3
    assert recall_at_k(retrieved, gold, k=5) == 3 / 4  # a, c, e in top 5
    assert recall_at_k(retrieved, gold, k=None) == 3 / 4


def test_recall_at_k_empty_gold():
    """Return 1.0 when gold is empty."""
    assert recall_at_k(["a", "b"], set(), k=5) == 1.0

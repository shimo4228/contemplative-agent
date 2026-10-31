"""Tests for scripts/_bm25.py — the one BM25 the novelty instruments share.

Moved from ``tests/test_retrieval_recall_measure.py`` when that instrument was
retired (P1-04.7); the properties pinned here are what made the arm worth
measuring beside trigram Jaccard.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _bm25 as bm25  # noqa: E402  # pyright: ignore[reportMissingImports]


def _top(scores: dict[str, float]) -> str:
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def test_normalization_ignores_punctuation_and_case():
    assert bm25.bm25_tokens("Map-Structural, constraints!") == ["map", "structural", "constraints"]


def test_the_doc_sharing_rare_terms_ranks_first():
    """A match on a term few documents carry outweighs a match on a common one."""
    docs = [
        "the agent should pause and reflect before answering",
        "the agent should map structural constraints before proposing",
        "the agent should pause and reflect before answering carefully",
    ]
    index = bm25.build_bm25_index(("a", "b", "c"), docs)
    scores = bm25.bm25_scores_from_index(index, "map structural constraints")
    assert _top(scores) == "b"
    assert scores["b"] > scores["a"]


def test_idf_downweights_a_term_every_document_carries():
    """A term with df == N contributes almost nothing and never a NEGATIVE
    amount (the reason the non-negative IDF form is used)."""
    docs = ["agent alpha", "agent beta", "agent gamma"]
    index = bm25.build_bm25_index(("a", "b", "c"), docs)
    everywhere = bm25.bm25_scores_from_index(index, "agent")
    rare = bm25.bm25_scores_from_index(index, "beta")
    assert min(everywhere.values()) >= 0.0
    assert rare["b"] > max(everywhere.values()) * 3
    # No spread from the ubiquitous term: a caller must not rank on it.
    assert len(set(everywhere.values())) == 1


def test_a_query_sharing_nothing_scores_every_document_zero():
    index = bm25.build_bm25_index(("a", "b"), ["alpha", "beta"])
    assert bm25.bm25_scores_from_index(index, "一二三") == {"a": 0.0, "b": 0.0}


def test_an_all_empty_corpus_does_not_divide_by_zero():
    index = bm25.build_bm25_index(("a", "b"), ["", ""])
    assert index.average_length == 1.0
    assert bm25.bm25_scores_from_index(index, "alpha") == {"a": 0.0, "b": 0.0}

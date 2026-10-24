"""Tests for embedding utility functions (cosine).

The Ollama HTTP path (embed_texts) is exercised indirectly by the modules
that call it (distill, rules_distill, views, novelty) with requests mocked;
these tests focus on the pure-numpy utilities. The find_similar / centroid /
argmax_centroid helpers were removed as dead code (no production callers).
"""

from __future__ import annotations

import re

import numpy as np
import pytest
import responses as responses_lib

from contemplative_agent.core.embeddings import cosine, embed_texts
from tests.chaos import (
    add_embed_429,
    add_embed_ragged,
    add_embed_short,
    add_embed_timeout,
)


class TestCosine:
    def test_identical_vectors(self):
        v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal(self):
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0], dtype=np.float32)
        assert cosine(v1, v2) == pytest.approx(0.0)

    def test_opposite(self):
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        v2 = np.array([-1.0, 0.0], dtype=np.float32)
        assert cosine(v1, v2) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        v = np.array([1.0, 1.0], dtype=np.float32)
        zero = np.zeros(2, dtype=np.float32)
        assert cosine(v, zero) == 0.0
        assert cosine(zero, v) == 0.0

    def test_shape_mismatch_returns_zero_not_crash(self):
        # Batch G regression (ultracode sweep 2026-06-23): a dimension mismatch
        # (e.g. an embedding-model swap without re-backfill) must degrade to
        # 0.0 (dissimilar) instead of raising ValueError and crashing every
        # distill / insight / view command.
        v3 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v4 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        assert cosine(v3, v4) == 0.0
        assert cosine(v4, v3) == 0.0


class TestCalibrationDriftNote:
    """ADR-0071/0072 calibration pin: a same-dimension embedding-model swap
    passes every shape check while invalidating all calibrated thresholds —
    the pin makes the swap loudly visible."""

    def test_pinned_model_returns_none(self, monkeypatch):
        from contemplative_agent.core.embeddings import calibration_drift_note

        monkeypatch.delenv("OLLAMA_EMBEDDING_MODEL", raising=False)
        assert calibration_drift_note() is None

    def test_swapped_model_returns_warning(self, monkeypatch):
        from contemplative_agent.core.embeddings import calibration_drift_note

        monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "some-other-768d-model")
        note = calibration_drift_note()
        assert note is not None
        assert "some-other-768d-model" in note
        assert "nomic-embed-text" in note
        assert "0.554" in note  # anchors travel with the warning


class TestEmbedTextsHTTPFaults:
    """ADR-0077 F2: direct HTTP-layer faults on /api/embed (previously only
    the indirect embed_texts-returns-None path was covered). All faults must
    degrade to None — callers treat None as "skip similarity work"."""

    @responses_lib.activate
    def test_429_returns_none(self):
        add_embed_429(responses_lib.mock)
        assert embed_texts(["some text"]) is None

    @responses_lib.activate
    def test_read_timeout_returns_none(self):
        add_embed_timeout(responses_lib.mock)
        assert embed_texts(["some text"]) is None

    @responses_lib.activate
    def test_ragged_rows_return_none(self):
        # Rows of unequal dimension: np.asarray(dtype=float32) must fail
        # inside embed_texts, not propagate a ValueError to the caller.
        add_embed_ragged(responses_lib.mock)
        assert embed_texts(["a", "b"]) is None

    @responses_lib.activate
    def test_short_row_count_parses_but_mismatches(self):
        # M < N rows parse fine — the length mismatch is the CALLER's guard
        # (distill checks shape[0] != len; see test_distill_chaos.py).
        add_embed_short(responses_lib.mock, n_returned=1)
        result = embed_texts(["a", "b", "c"])
        assert result is not None
        assert result.shape[0] == 1


class TestNoRedirectFollow:
    """P1-10.6: the embed POST must not follow a 3xx (same rule as client.py)."""

    def test_post_passes_allow_redirects_false(self, monkeypatch):
        from unittest.mock import MagicMock

        import contemplative_agent.core.embeddings as emb

        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"embeddings": [[1.0, 0.0]]}
        post = MagicMock(return_value=resp)
        monkeypatch.setattr(emb.requests, "post", post)
        emb.embed_texts(["hello"])
        assert post.call_args.kwargs["allow_redirects"] is False

    def test_3xx_is_not_followed(self):
        with responses_lib.RequestsMock(assert_all_requests_are_fired=True) as rsps:
            rsps.add(
                responses_lib.POST,
                re.compile(r"http://[^/]+/api/embed"),
                status=302,
                headers={"Location": "http://evil.example/api/embed"},
            )
            # A followed redirect would hit an unregistered host and raise
            # ConnectionError from the mock; either way the result is None.
            assert embed_texts(["hello"]) is None
            assert len(rsps.calls) == 1

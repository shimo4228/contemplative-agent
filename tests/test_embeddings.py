"""Tests for embedding utility functions (cosine).

The Ollama HTTP path (embed_texts) is exercised indirectly by the modules
that call it (distill, rules_distill, views, novelty) with requests mocked;
these tests focus on the pure-numpy utilities. The find_similar / centroid /
argmax_centroid helpers were removed as dead code (no production callers).
"""

from __future__ import annotations

import numpy as np
import pytest

from contemplative_agent.core.embeddings import cosine


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

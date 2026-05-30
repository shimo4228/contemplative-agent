"""Tests for embedding utility functions (cosine, find_similar, centroid, argmax_centroid).

The Ollama HTTP path (embed_texts) is exercised indirectly by the modules
that call it (distill, rules_distill, views, novelty) with requests mocked;
these tests focus on the pure-numpy utilities.
"""

from __future__ import annotations

import numpy as np
import pytest

from contemplative_agent.core.embeddings import (
    argmax_centroid,
    centroid,
    cosine,
    find_similar,
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


class TestFindSimilar:
    def test_returns_sorted_desc(self):
        target = np.array([1.0, 0.0], dtype=np.float32)
        candidates = [
            np.array([0.0, 1.0], dtype=np.float32),  # 0.0
            np.array([1.0, 0.0], dtype=np.float32),  # 1.0
            np.array([1.0, 1.0], dtype=np.float32),  # ~0.707
        ]
        result = find_similar(target, candidates)
        assert [r[0] for r in result] == [1, 2, 0]
        assert result[0][1] == pytest.approx(1.0)

    def test_threshold_filter(self):
        target = np.array([1.0, 0.0], dtype=np.float32)
        candidates = [
            np.array([0.0, 1.0], dtype=np.float32),  # 0.0 — below threshold
            np.array([1.0, 0.0], dtype=np.float32),  # 1.0
        ]
        result = find_similar(target, candidates, threshold=0.5)
        assert [r[0] for r in result] == [1]

    def test_top_k_truncation(self):
        target = np.array([1.0, 0.0], dtype=np.float32)
        candidates = [np.array([float(i + 1), 0.0], dtype=np.float32) for i in range(5)]
        result = find_similar(target, candidates, top_k=2)
        assert len(result) == 2

    def test_empty_candidates(self):
        target = np.array([1.0, 0.0], dtype=np.float32)
        assert find_similar(target, []) == []


class TestCentroid:
    def test_mean_of_vectors(self):
        vectors = [
            np.array([1.0, 0.0], dtype=np.float32),
            np.array([3.0, 0.0], dtype=np.float32),
            np.array([2.0, 6.0], dtype=np.float32),
        ]
        result = centroid(vectors)
        assert result is not None
        np.testing.assert_array_almost_equal(result, [2.0, 2.0])

    def test_empty_returns_none(self):
        assert centroid([]) is None


class TestArgmaxCentroid:
    def test_picks_closest_centroid(self):
        target = np.array([1.0, 0.0], dtype=np.float32)
        centroids = {
            "a": np.array([0.0, 1.0], dtype=np.float32),
            "b": np.array([1.0, 0.0], dtype=np.float32),
            "c": np.array([-1.0, 0.0], dtype=np.float32),
        }
        result = argmax_centroid(target, centroids)
        assert result is not None
        assert result[0] == "b"
        assert result[1] == pytest.approx(1.0)

    def test_empty_centroids_returns_none(self):
        target = np.array([1.0, 0.0], dtype=np.float32)
        assert argmax_centroid(target, {}) is None

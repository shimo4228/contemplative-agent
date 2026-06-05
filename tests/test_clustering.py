"""Tests for core.clustering — average-linkage agglomerative cosine clustering."""

from __future__ import annotations

from typing import List

import numpy as np

from contemplative_agent.core.clustering import cluster_patterns


def _pat(text: str, embedding: List[float], importance: float = 0.5) -> dict:
    """Build a minimal pattern dict compatible with effective_importance."""
    return {
        "pattern": text,
        "embedding": list(embedding),
        "importance": importance,
    }


def _axis_vec(dim: int, axis: int, weight_first: float = 0.0) -> List[float]:
    """Unit vector mostly on ``axis`` with optional weight on axis 0.

    Lets us build vectors with controlled pairwise cosine: two vectors
    sharing the same axis have cosine 1, vectors on different axes
    have cosine 0 (unless weight_first is used to pull them together).
    """
    v = np.zeros(dim, dtype=np.float32)
    if weight_first > 0:
        v[0] = weight_first
        v[axis] = float(np.sqrt(max(0.0, 1.0 - weight_first * weight_first)))
    else:
        v[axis] = 1.0
    return v.tolist()


class TestTwoClusters:
    def test_two_topic_clusters(self):
        # 3 patterns near axis 1, 3 patterns near axis 2 — should separate.
        close_a = [_pat(f"a{i}", _axis_vec(8, 1)) for i in range(3)]
        close_b = [_pat(f"b{i}", _axis_vec(8, 2)) for i in range(3)]
        clusters, singletons = cluster_patterns(
            close_a + close_b, threshold=0.7, min_size=3, max_size=10
        )
        assert len(clusters) == 2
        assert singletons == []
        cluster_sizes = sorted(len(c) for c in clusters)
        assert cluster_sizes == [3, 3]


class TestSingleCluster:
    def test_all_similar_merge(self):
        # 5 vectors on the same axis → cosine 1 pairwise → single cluster.
        pats = [_pat(f"x{i}", _axis_vec(8, 1)) for i in range(5)]
        clusters, singletons = cluster_patterns(
            pats, threshold=0.7, min_size=3, max_size=10
        )
        assert len(clusters) == 1
        assert len(clusters[0]) == 5
        assert singletons == []


class TestAllSingletons:
    def test_orthogonal_vectors_are_singletons(self):
        # 5 mutually orthogonal vectors → cosine 0 pairwise → no cluster.
        pats = [_pat(f"o{i}", _axis_vec(8, i + 1)) for i in range(5)]
        clusters, singletons = cluster_patterns(
            pats, threshold=0.7, min_size=3, max_size=10
        )
        assert clusters == []
        assert len(singletons) == 5


class TestMaxSizeCap:
    def test_large_cluster_is_sliced_to_max_size(self):
        # 15 patterns on same axis — single cluster exceeds max_size=10.
        pats = [
            _pat(f"b{i}", _axis_vec(8, 1), importance=0.9 - i * 0.05)
            for i in range(15)
        ]
        clusters, singletons = cluster_patterns(
            pats, threshold=0.7, min_size=3, max_size=10
        )
        assert len(clusters) == 1
        assert len(clusters[0]) == 10
        # Top-10 by effective_importance — highest-importance patterns kept.
        kept_texts = [p["pattern"] for p in clusters[0]]
        # Highest importance ones are b0..b9
        for i in range(10):
            assert f"b{i}" in kept_texts
        # The remaining 5 go to singletons
        assert len(singletons) == 5


class TestMinSizeFallback:
    def test_below_min_size_becomes_singletons(self):
        # 2 patterns close on axis 1 + 3 close on axis 2.
        # min_size=3 means the 2-member group becomes singletons.
        small = [_pat(f"s{i}", _axis_vec(8, 1)) for i in range(2)]
        large = [_pat(f"l{i}", _axis_vec(8, 2)) for i in range(3)]
        clusters, singletons = cluster_patterns(
            small + large, threshold=0.7, min_size=3, max_size=10
        )
        assert len(clusters) == 1
        assert len(clusters[0]) == 3
        assert len(singletons) == 2


class TestEdgeCases:
    def test_empty_input(self):
        clusters, singletons = cluster_patterns(
            [], threshold=0.7, min_size=3, max_size=10
        )
        assert clusters == []
        assert singletons == []

    def test_single_pattern(self):
        pats = [_pat("lonely", _axis_vec(8, 1))]
        clusters, singletons = cluster_patterns(
            pats, threshold=0.7, min_size=3, max_size=10
        )
        assert clusters == []
        assert singletons == pats

    def test_patterns_without_embedding_go_to_singletons(self):
        """No embedding → cannot cluster → singleton."""
        with_emb = [_pat(f"w{i}", _axis_vec(8, 1)) for i in range(3)]
        no_emb = [
            {
                "pattern": "noemb",
                "importance": 0.5,
            }
        ]
        clusters, singletons = cluster_patterns(
            with_emb + no_emb, threshold=0.7, min_size=3, max_size=10
        )
        assert len(clusters) == 1
        assert len(clusters[0]) == 3
        assert len(singletons) == 1
        assert singletons[0]["pattern"] == "noemb"


class TestClusterInternalSort:
    def test_cluster_members_sorted_by_effective_importance_desc(self):
        # 5 near-identical vectors, distinct importances.
        # _axis_vec(8, 1, weight_first=0.95) vs _axis_vec(8, 1) both on axis 1 so cosine is near 1.
        importances = [0.2, 0.9, 0.5, 0.1, 0.7]
        pats = [
            _pat(f"p{i}", _axis_vec(8, 1), importance=imp)
            for i, imp in enumerate(importances)
        ]
        clusters, _ = cluster_patterns(
            pats, threshold=0.7, min_size=3, max_size=10
        )
        assert len(clusters) == 1
        got = [p["importance"] for p in clusters[0]]
        assert got == sorted(got, reverse=True)

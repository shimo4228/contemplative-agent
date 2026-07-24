"""Tests for core.clustering — average-linkage agglomerative cosine clustering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from contemplative_agent.core.clustering import cluster_patterns


def _pat(text: str, embedding: list[float], days_old: float = 0.0) -> dict:
    """Build a minimal pattern dict compatible with effective_importance.

    ADR-0056: extraction weight is pure time decay, so ``days_old`` (how long
    ago the pattern was distilled) — not a stored importance rating — is what
    orders patterns within a cluster.
    """
    distilled = (
        datetime.now(timezone.utc) - timedelta(days=days_old)
    ).isoformat()
    return {
        "pattern": text,
        "embedding": list(embedding),
        "distilled": distilled,
    }


def _axis_vec(dim: int, axis: int, weight_first: float = 0.0) -> list[float]:
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
        # b0 is newest, b14 oldest (ADR-0056: decay orders the slice).
        pats = [
            _pat(f"b{i}", _axis_vec(8, 1), days_old=i * 0.5)
            for i in range(15)
        ]
        clusters, singletons = cluster_patterns(
            pats, threshold=0.7, min_size=3, max_size=10
        )
        assert len(clusters) == 1
        assert len(clusters[0]) == 10
        # Top-10 by effective_importance (= least decayed) — newest kept.
        kept_texts = [p["pattern"] for p in clusters[0]]
        # Freshest ones are b0..b9
        for i in range(10):
            assert f"b{i}" in kept_texts
        # The remaining 5 (oldest) go to singletons
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
    def test_cluster_members_sorted_by_decay_desc(self):
        # 5 near-identical vectors (all on axis 1 → cosine ≈ 1), distinct ages.
        # ADR-0056: intra-cluster order is effective_importance = pure decay,
        # so the freshest (smallest days_old) must come first.
        ages = [4.0, 0.5, 2.0, 7.0, 1.0]
        pats = [
            _pat(f"p{i}", _axis_vec(8, 1), days_old=age)
            for i, age in enumerate(ages)
        ]
        clusters, _ = cluster_patterns(
            pats, threshold=0.7, min_size=3, max_size=10
        )
        assert len(clusters) == 1
        got_ages = [p["distilled"] for p in clusters[0]]
        # Sorted by decay desc == sorted by distilled timestamp desc (newest first).
        assert got_ages == sorted(got_ages, reverse=True)


class TestMergeEquivalenceADR0074:
    """The vectorized Lance-Williams merge must reproduce the retired naive
    submatrix-mean agglomeration exactly (identical partitions).

    The naive port below is the pre-ADR-0074 implementation kept as a
    reference oracle; both consume the same cosine matrix.
    """

    @staticmethod
    def _naive_merge(similarity: np.ndarray, threshold: float) -> list[list[int]]:
        n = similarity.shape[0]
        clusters: list[list[int]] = [[i] for i in range(n)]
        while len(clusters) > 1:
            best_sim = -1.0
            best_i = -1
            best_j = -1
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    sub = similarity[np.ix_(clusters[i], clusters[j])]
                    s = float(sub.mean())
                    if s > best_sim:
                        best_sim = s
                        best_i, best_j = i, j
            if best_sim < threshold or best_i < 0:
                break
            clusters[best_i].extend(clusters[best_j])
            del clusters[best_j]
        return clusters

    def _assert_equivalent(self, embeddings: np.ndarray, threshold: float) -> None:
        from contemplative_agent.core.clustering import _cosine_matrix, _merge_clusters

        sim = _cosine_matrix(embeddings)
        got = {frozenset(g) for g in _merge_clusters(sim.copy(), threshold)}
        want = {frozenset(g) for g in self._naive_merge(sim, threshold)}
        assert got == want

    def test_blob_data_matches_naive(self):
        rng = np.random.default_rng(42)
        blobs = []
        for axis in range(3):
            center = np.zeros(12)
            center[axis] = 1.0
            blobs.append(center + rng.normal(0, 0.15, size=(16, 12)))
        emb = np.vstack(blobs).astype(np.float32)
        self._assert_equivalent(emb, 0.70)

    def test_homogeneous_data_matches_naive(self):
        # Echo-like corpus: one broad blob, threshold cuts mid-continuum.
        rng = np.random.default_rng(7)
        center = rng.normal(0, 1, 12)
        emb = (center + rng.normal(0, 0.55, size=(40, 12))).astype(np.float32)
        self._assert_equivalent(emb, 0.70)

    def test_mixed_scale_matches_naive(self):
        rng = np.random.default_rng(123)
        parts = []
        for axis in range(4):
            center = np.zeros(16)
            center[axis] = 1.0
            n = 5 + axis * 7
            parts.append(center + rng.normal(0, 0.25, size=(n, 16)))
        emb = np.vstack(parts).astype(np.float32)
        self._assert_equivalent(emb, 0.65)

    def test_empty_and_single(self):
        from contemplative_agent.core.clustering import _merge_clusters

        assert _merge_clusters(np.zeros((0, 0)), 0.7) == []
        assert _merge_clusters(np.ones((1, 1)), 0.7) == [[0]]

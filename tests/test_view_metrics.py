"""Tests for core.view_metrics — read-only pattern-composition instruments.

All inputs are hand-built unit vectors so every cosine is exact; no Ollama
call is involved anywhere (the fake registry returns precomputed centroids).
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pytest

from contemplative_agent.core.view_metrics import (
    CLUSTER_STATS_MAX_N,
    CONSUMED_VIEWS,
    ClusterStats,
    ViewSupply,
    compute_diversity,
    compute_view_supply,
    format_pattern_report,
    nearest_view,
)
from contemplative_agent.core.views import View


class _FakeRegistry:
    """Structural stand-in for ViewRegistry (ViewLookup protocol)."""

    def __init__(
        self,
        centroids: Dict[str, np.ndarray],
        thresholds: Optional[Dict[str, float]] = None,
    ) -> None:
        self._centroids = centroids
        self._thresholds = thresholds or {}

    def get(self, name: str) -> Optional[View]:
        if name not in self._centroids:
            return None
        return View(
            name=name,
            seed_text="seed",
            threshold=self._thresholds.get(name, 0.55),
        )

    def get_centroid(self, name: str) -> Optional[np.ndarray]:
        return self._centroids.get(name)


def _pat(embedding, gated: bool = False) -> dict:
    p: dict = {"pattern": "text", "valid_until": None}
    if embedding is not None:
        p["embedding"] = embedding
    if gated:
        p["gated"] = True
    return p


# ---------------------------------------------------------------------------
# compute_view_supply
# ---------------------------------------------------------------------------


class TestViewSupply:
    def test_counts_and_percentiles_are_exact(self) -> None:
        registry = _FakeRegistry({"self_reflection": np.array([1.0, 0.0, 0.0], dtype=np.float32)})
        patterns = [
            _pat([1.0, 0.0, 0.0]),   # cos 1.0
            _pat([0.0, 1.0, 0.0]),   # cos 0.0
            _pat([0.6, 0.8, 0.0]),   # cos 0.6
            _pat(None),              # skipped (no embedding)
        ]
        supplies = compute_view_supply(patterns, registry, views=("self_reflection",))
        assert len(supplies) == 1
        s = supplies[0]
        assert isinstance(s, ViewSupply)
        assert s.view == "self_reflection"
        assert s.threshold == 0.55
        assert s.total == 3
        assert s.passing == 2
        assert s.p50 == pytest.approx(0.6)
        assert s.p90 == pytest.approx(0.92)
        assert s.max == pytest.approx(1.0)

    def test_unknown_view_is_omitted_with_warning(self, caplog) -> None:
        registry = _FakeRegistry({})
        with caplog.at_level("WARNING", logger="contemplative_agent.core.view_metrics"):
            supplies = compute_view_supply([_pat([1.0, 0.0])], registry, views=("nope",))
        assert supplies == ()
        assert "nope" in caplog.text

    def test_empty_patterns_yield_zero_stats(self) -> None:
        registry = _FakeRegistry({"constitutional": np.array([1.0, 0.0], dtype=np.float32)})
        supplies = compute_view_supply([], registry, views=("constitutional",))
        assert supplies[0].total == 0
        assert supplies[0].passing == 0
        assert supplies[0].max == 0.0

    def test_default_views_are_the_consumed_pair(self) -> None:
        assert CONSUMED_VIEWS == ("self_reflection", "constitutional")


# ---------------------------------------------------------------------------
# compute_diversity
# ---------------------------------------------------------------------------


class TestDiversity:
    def test_pairwise_and_cluster_stats_are_exact(self) -> None:
        patterns = [
            _pat([1.0, 0.0]),
            _pat([1.0, 0.0]),
            _pat([0.0, 1.0]),
            _pat(None),  # counted as skipped
        ]
        d = compute_diversity(
            patterns, cluster_threshold=0.9, min_size=2, max_size=10
        )
        assert d.n == 3
        assert d.skipped == 1
        assert d.pairwise_mean == pytest.approx(1.0 / 3.0)
        assert d.pairwise_p50 == pytest.approx(0.0)
        assert d.pairwise_p90 == pytest.approx(0.8)
        assert d.cluster_stats == ClusterStats(
            threshold=0.9, clusters=1, clustered=2, singletons=1, largest=2
        )

    def test_cluster_stats_skipped_above_cap(self) -> None:
        patterns = [_pat([1.0, 0.0]), _pat([1.0, 0.0]), _pat([0.0, 1.0])]
        d = compute_diversity(patterns, cluster_threshold=0.9, cluster_cap=2)
        assert d.cluster_stats is None
        assert d.n == 3  # pairwise stats still computed

    @pytest.mark.parametrize("patterns", [[], [_pat([1.0, 0.0])]], ids=["empty", "single"])
    def test_fewer_than_two_embeddings_yield_zero_pairwise(self, patterns) -> None:
        d = compute_diversity(patterns)
        assert d.pairwise_mean == 0.0
        assert d.cluster_stats is None

    def test_cap_default_mirrors_insight_guard(self) -> None:
        from contemplative_agent.core.insight import FULL_RECLUSTER_WARN_N

        assert CLUSTER_STATS_MAX_N == FULL_RECLUSTER_WARN_N

    def test_malformed_embedding_value_does_not_crash(self, caplog) -> None:
        """python-reviewer 2026-07-03 CRITICAL: a non-numeric embedding value
        must degrade to a skipped row, never raise out of the instrument and
        kill the host command (insight / dry-run / report)."""
        patterns = [
            _pat([1.0, 0.0]),
            _pat([1.0, 0.0]),
            _pat("corrupted-not-a-vector"),
            _pat([["ragged"], ["nesting"]]),
        ]
        with caplog.at_level("WARNING", logger="contemplative_agent.core.view_metrics"):
            d = compute_diversity(patterns, cluster_threshold=0.9, min_size=2)
        assert d.n == 2
        assert d.skipped == 2
        registry = _FakeRegistry({"self_reflection": np.array([1.0, 0.0], dtype=np.float32)})
        assert nearest_view(_pat("corrupted"), registry) is None

    def test_pairwise_stride_sample_above_cap(self, caplog) -> None:
        """python-reviewer 2026-07-03 MEDIUM: pairwise matrix must not grow
        unbounded; above the cap a deterministic stride sample is used."""
        from contemplative_agent.core.view_metrics import PAIRWISE_STATS_MAX_N

        patterns = [_pat([1.0, 0.0]) for _ in range(PAIRWISE_STATS_MAX_N + 2)]
        with caplog.at_level("INFO", logger="contemplative_agent.core.view_metrics"):
            d = compute_diversity(patterns, cluster_cap=0)  # skip cluster stats
        assert d.n == PAIRWISE_STATS_MAX_N + 2
        assert d.pairwise_mean == pytest.approx(1.0)
        assert "stride sample" in caplog.text

    def test_mixed_embedding_dimensions_do_not_crash(self, caplog) -> None:
        """codex review P2: a legacy row from a different embedding model has
        a different dimension; the instrument must degrade (drop non-dominant
        dims, count them as skipped) instead of raising ValueError."""
        patterns = [
            _pat([1.0, 0.0]),
            _pat([1.0, 0.0]),
            _pat([0.0, 1.0, 0.0]),  # legacy 3-dim row
        ]
        with caplog.at_level("WARNING", logger="contemplative_agent.core.view_metrics"):
            d = compute_diversity(patterns, cluster_threshold=0.9, min_size=2)
        assert d.n == 2
        assert d.skipped == 1
        assert d.pairwise_mean == pytest.approx(1.0)
        assert "dim" in caplog.text

    def test_cluster_stats_exclude_gated_rows_like_insight(self) -> None:
        """codex review P2: the cluster line claims to mirror insight, and
        insight filters ``gated`` rows before clustering — so must we."""
        patterns = [
            _pat([1.0, 0.0]),
            _pat([1.0, 0.0]),
            _pat([1.0, 0.0], gated=True),  # excluded from cluster stats
            _pat([0.0, 1.0]),
        ]
        d = compute_diversity(patterns, cluster_threshold=0.9, min_size=2)
        assert d.n == 4  # pairwise homogeneity still covers the whole set
        assert d.cluster_stats is not None
        assert d.cluster_stats.clustered == 2  # the two non-gated identical rows
        assert d.cluster_stats.singletons == 1  # the orthogonal non-gated row


# ---------------------------------------------------------------------------
# nearest_view
# ---------------------------------------------------------------------------


class TestNearestView:
    def test_picks_highest_cosine_view(self) -> None:
        registry = _FakeRegistry({
            "self_reflection": np.array([1.0, 0.0], dtype=np.float32),
            "constitutional": np.array([0.0, 1.0], dtype=np.float32),
        })
        got = nearest_view(_pat([0.6, 0.8]), registry)
        assert got is not None
        name, sim = got
        assert name == "constitutional"
        assert sim == pytest.approx(0.8)

    def test_no_embedding_returns_none(self) -> None:
        registry = _FakeRegistry({"self_reflection": np.array([1.0, 0.0], dtype=np.float32)})
        assert nearest_view(_pat(None), registry) is None

    def test_no_resolvable_centroid_returns_none(self) -> None:
        registry = _FakeRegistry({})
        assert nearest_view(_pat([1.0, 0.0]), registry) is None


# ---------------------------------------------------------------------------
# format_pattern_report
# ---------------------------------------------------------------------------


class TestFormatPatternReport:
    def test_report_contains_all_sections_and_ambiguity_note(self) -> None:
        registry = _FakeRegistry({"self_reflection": np.array([1.0, 0.0], dtype=np.float32)})
        patterns = [
            _pat([1.0, 0.0]),
            _pat([0.0, 1.0]),
        ]
        text = format_pattern_report(patterns, registry, views=("self_reflection",))
        assert "Pattern Composition" in text
        assert "self_reflection: 1/2 pass @0.55" in text
        assert "pairwise" in text
        # ADR-0016 blind-spot guard: empty/low supply must be flagged as
        # ambiguous (missing patterns vs stale seed), and the instrument
        # must declare itself observability-only.
        assert "stale seed" in text
        assert "not gates" in text


class TestCalibrationDriftLine:
    """ADR-0071/0072: the pattern report surfaces an embedding-model swap
    against the calibration pin — readings are meaningless off-model."""

    def test_report_flags_swapped_model(self, monkeypatch) -> None:
        monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "swapped-model")
        registry = _FakeRegistry({"self_reflection": np.array([1.0, 0.0], dtype=np.float32)})
        text = format_pattern_report([_pat([1.0, 0.0])], registry, views=("self_reflection",))
        assert "WARNING:" in text
        assert "swapped-model" in text

    def test_report_silent_on_pinned_model(self, monkeypatch) -> None:
        monkeypatch.delenv("OLLAMA_EMBEDDING_MODEL", raising=False)
        registry = _FakeRegistry({"self_reflection": np.array([1.0, 0.0], dtype=np.float32)})
        text = format_pattern_report([_pat([1.0, 0.0])], registry, views=("self_reflection",))
        assert "calibration model" not in text

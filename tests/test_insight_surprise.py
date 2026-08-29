"""Surprise enumeration for insight candidates (ADR-0096, read-only).

TDD contract: surprise is a **material listed for the reviewer**, never a
filter. These tests assert the two properties the 2026-08-17 calibration
made non-negotiable:

1. **Determinism.** Same embeddings + same reference window → same values and
   the same ranks, with no LLM call anywhere in the path.
2. **No z-normalization.** The calibration measured a raw max-cosine spread of
   0.108–0.129 with p50 at 0.806 — the store's historical nearest-neighbour
   ceiling — meaning 78 of 78 candidates sat on top of each other. Z-scoring
   that turned it into a ~5–6 sd spread, manufacturing discrimination that the
   raw distribution does not contain. So the reported values must stay on the
   cosine scale: a collapsed input has to stay visibly collapsed in the output.

Nothing here asserts a threshold, because there is none: no candidate is
dropped, deferred or reordered by its surprise (`read-only-instruments`
invariant 1).
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

from contemplative_agent.core import insight_surprise


def _pattern(pid_text: str, vec: list[float], distilled: str) -> dict:
    return {"pattern": pid_text, "distilled": distilled, "embedding": vec}


def _spread_corpus(n: int, spread: float, dim: int = 8) -> list[dict]:
    """A reference corpus whose cosines against a probe span ~``spread``.

    Deterministic by construction: row i tilts off the probe axis by an angle
    chosen so the cosines walk linearly from 1.0 down to 1.0 - spread.
    """
    rows = []
    for i in range(n):
        target = 1.0 - spread * (i / max(1, n - 1))
        target = min(1.0, max(-1.0, target))
        vec = [target, float(np.sqrt(max(0.0, 1.0 - target * target)))] + [0.0] * (dim - 2)
        rows.append(_pattern(f"ref-{i}", vec, f"2026-08-{(i % 28) + 1:02d}T00:00:00+00:00"))
    return rows


def _probe(dim: int = 8) -> list[list[float]]:
    return [[1.0] + [0.0] * (dim - 1)]


class TestDeterminism:
    def test_same_input_same_reading(self) -> None:
        ref = _spread_corpus(20, 0.4)
        a = insight_surprise.compute_surprise(
            {"cluster-1": _probe(), "cluster-2": [[0.0, 1.0] + [0.0] * 6]}, ref, ref_k=20
        )
        b = insight_surprise.compute_surprise(
            {"cluster-1": _probe(), "cluster-2": [[0.0, 1.0] + [0.0] * 6]}, ref, ref_k=20
        )
        assert a == b

    def test_ranks_are_a_total_order_over_the_batch(self) -> None:
        ref = _spread_corpus(20, 0.4)
        out = insight_surprise.compute_surprise(
            {
                "cluster-1": _probe(),
                "cluster-2": [[0.0, 1.0] + [0.0] * 6],
                "cluster-3": [[0.7071, 0.7071] + [0.0] * 6],
            },
            ref,
            ref_k=20,
        )
        ranks = sorted(r.rank for r in out.values())
        assert ranks == [1, 2, 3]
        assert all(r.of == 3 for r in out.values())

    def test_more_distant_candidate_ranks_first(self) -> None:
        ref = _spread_corpus(20, 0.2)
        out = insight_surprise.compute_surprise(
            {"near": _probe(), "far": [[0.0, 1.0] + [0.0] * 6]}, ref, ref_k=20
        )
        assert out["far"].s_mean > out["near"].s_mean
        assert out["far"].rank == 1


class TestNoZNormalization:
    def test_collapsed_input_stays_collapsed_in_the_output(self) -> None:
        """The trap, reproduced: nearest-neighbour cosines confined to a 0.1
        band must not come out looking like a 5-sigma separation."""
        ref = _spread_corpus(60, 0.02)
        candidates = {
            f"cluster-{i}": [
                [1.0 - 0.001 * i, float(np.sqrt(max(0.0, 1 - (1 - 0.001 * i) ** 2)))] + [0.0] * 6
            ]
            for i in range(12)
        }
        out = insight_surprise.compute_surprise(candidates, ref, ref_k=60)
        reported = [r.s_mean for r in out.values()]
        assert max(reported) - min(reported) < 0.1
        # And every reported number stays on the cosine scale [0, 2].
        assert all(0.0 <= r.s_mean <= 2.0 and 0.0 <= r.s_nn <= 2.0 for r in out.values())

    def test_reading_carries_the_raw_reference_distribution(self) -> None:
        """The ambiguity note (read-only-instruments invariant 2): the reader
        must be able to see the discriminability budget the ranks came from."""
        ref = _spread_corpus(30, 0.05)
        out = insight_surprise.compute_surprise({"cluster-1": _probe()}, ref, ref_k=30)
        r = out["cluster-1"]
        assert 0.0 <= r.ref_cos_p50 <= 1.0
        assert r.ref_cos_spread == pytest.approx(0.05, abs=0.02)
        assert r.ref_k == 30

    def test_values_scale_with_the_raw_gap_not_with_the_batch_variance(self) -> None:
        """Halving the true separation must halve the reported separation. A
        z-scored reading would report the same spread for both."""
        ref = _spread_corpus(40, 0.02)

        def _pair(gap: float) -> float:
            cands = {
                "a": _probe(),
                "b": [[1.0 - gap, float(np.sqrt(max(0.0, 1 - (1 - gap) ** 2)))] + [0.0] * 6],
            }
            out = insight_surprise.compute_surprise(cands, ref, ref_k=40)
            return abs(out["a"].s_mean - out["b"].s_mean)

        wide, narrow = _pair(0.20), _pair(0.10)
        assert wide > narrow * 1.5


class TestScoping:
    def test_own_members_are_excluded_from_the_reference(self) -> None:
        """A candidate's own material sitting in the window pins max-cos to 1.0
        and flattens every reading (calibration, 2026-08-17)."""
        own = _pattern("mine", [1.0] + [0.0] * 7, "2026-08-20T00:00:00+00:00")
        others = [
            _pattern(f"o{i}", [0.7, 0.7141428] + [0.0] * 6, f"2026-08-1{i}T00:00:00+00:00")
            for i in range(5)
        ]
        ref = [own, *others]

        unmasked = insight_surprise.compute_surprise({"c": _probe()}, ref, ref_k=6)
        masked = insight_surprise.compute_surprise(
            {"c": _probe()}, ref, ref_k=6, exclude={"c": {_pid(own)}}
        )
        assert unmasked["c"].s_nn == pytest.approx(0.0, abs=1e-5)
        assert masked["c"].s_nn == pytest.approx(0.3, abs=1e-3)

    def test_a_fully_masked_window_yields_no_reading(self, caplog) -> None:
        """The degenerate case must be absent, not unmasked (2026-08-29).

        Until this fix the fully-masked branch fell back to the UNMASKED
        cosines and shipped the result as an ordinary ``rank n/m``. That is
        exactly the degeneracy masking exists to prevent, and it was not a
        corner case: on ``insight --full`` the reference window IS the run's
        own window, so every candidate took the branch and two well-separated
        clusters came out ~1e-4 apart while the gate printed confident ranks.
        """
        rows = [
            _pattern(f"r-{i}", [1.0] + [0.0] * 7, f"2026-08-{i + 1:02d}T00:00:00+00:00")
            for i in range(4)
        ]
        everything = {_pid(r) for r in rows}
        with caplog.at_level(logging.WARNING):
            out = insight_surprise.compute_surprise(
                {"c": _probe()}, rows, ref_k=4, exclude={"c": everything}
            )
        assert out == {}
        assert "owns the whole reference window" in caplog.text

    def test_ref_k_reports_the_masked_sample_not_the_window(self) -> None:
        """The evidence base the reader is shown must be the one measured.

        ``ref_k`` used to carry the pre-mask window size, so an incremental
        run masking 400 of 1000 rows advertised ``ref k=1000`` for a 600-row
        sample (code review 2026-08-29).
        """
        rows = [
            _pattern(f"r-{i}", [0.7, 0.7141428] + [0.0] * 6, f"2026-08-{i + 1:02d}T00:00:00+00:00")
            for i in range(6)
        ]
        masked = {_pid(r) for r in rows[:4]}
        out = insight_surprise.compute_surprise(
            {"c": _probe()}, rows, ref_k=6, exclude={"c": masked}
        )
        assert out["c"].ref_k == 2

    def test_empty_reference_yields_no_reading(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            out = insight_surprise.compute_surprise({"cluster-1": _probe()}, [], ref_k=10)
        assert out == {}

    def test_candidate_without_embeddings_is_skipped_not_fatal(self) -> None:
        ref = _spread_corpus(10, 0.3)
        out = insight_surprise.compute_surprise(
            {"cluster-1": _probe(), "cluster-2": []}, ref, ref_k=10
        )
        assert "cluster-2" not in out
        assert "cluster-1" in out

    def test_reference_uses_the_most_recent_k(self) -> None:
        old = [
            _pattern(f"old-{i}", [0.0, 1.0] + [0.0] * 6, f"2020-01-{i + 1:02d}T00:00:00+00:00")
            for i in range(5)
        ]
        recent = [
            _pattern(f"new-{i}", [1.0] + [0.0] * 7, f"2026-08-{i + 1:02d}T00:00:00+00:00")
            for i in range(5)
        ]
        out = insight_surprise.compute_surprise({"c": _probe()}, old + recent, ref_k=5)
        # Only the recent (aligned) rows are in scope, so surprise is ~0.
        assert out["c"].s_mean == pytest.approx(0.0, abs=1e-5)


def _pid(p: dict) -> str:
    from contemplative_agent.core.knowledge_store import pattern_id

    return pattern_id(p)

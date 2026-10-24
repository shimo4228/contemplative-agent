"""Tests for scripts/_stats.py — the interval both instruments read rates with.

These live here rather than beside either caller because the drift this module
exists to stop was a *test* drift: the coselection copy pinned four reference
intervals and the impossible-count abstain, the retrieval copy pinned neither,
and the unpinned one fed ADR-0097's `recall@5 >= 0.9` Review-when.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _stats import newcombe_diff_ci, wilson_ci  # noqa: E402  # pyright: ignore[reportMissingImports]


class TestWilson:
    def test_zero_trials_is_none_not_zero(self):
        assert wilson_ci(0, 0) is None

    @pytest.mark.parametrize(("successes", "trials"), [(5, 3), (-1, 10), (1, -1)])
    def test_impossible_counts_abstain_instead_of_raising(self, successes, trials):
        assert wilson_ci(successes, trials) is None

    @pytest.mark.parametrize(
        ("successes", "trials", "expected"),
        [
            (13, 20, [0.4329, 0.8188]),
            (27, 30, [0.7438, 0.9654]),
            (18, 20, [0.6990, 0.9721]),
            (0, 10, [0.0, 0.2775]),
            (10, 10, [0.7225, 1.0]),
        ],
    )
    def test_matches_a_reference_interval(self, successes, trials, expected):
        """Reference Wilson score intervals, computed independently."""
        assert wilson_ci(successes, trials) == expected

    def test_never_runs_outside_the_unit_interval(self):
        """The reason for Wilson over the normal approximation."""
        for successes, trials in ((0, 3), (3, 3), (1, 200), (199, 200)):
            low, high = wilson_ci(successes, trials)
            assert 0.0 <= low <= high <= 1.0

    def test_the_coselection_support_floor_justification(self):
        """`coselection_families.py`'s --min-selections 20 rationale.

        A 0.65 estimate at n=20 reaches 0.4329 (clear of the <= 0.4 sub-case
        band); at n=13 the nearest count reaches below 0.4, so the sibling and
        sub-case readings stop being distinguishable.
        """
        assert wilson_ci(13, 20)[0] > 0.4
        assert wilson_ci(8, 13)[0] < 0.4

    def test_the_retrieval_decision_floor_justification(self):
        """`retrieval_recall_measure.py`'s --min-pairs 30 rationale.

        30 is the smallest round pair count at which a measured 0.9 excludes
        0.7; at 20 it does not.
        """
        assert wilson_ci(27, 30)[0] > 0.7
        assert wilson_ci(18, 20)[0] < 0.7


class TestNewcombeDiff:
    def test_the_published_reference_interval(self):
        # Newcombe (1998) Table II, method 10: 56/70 against 48/80 -> (0.0524, 0.3339).
        assert newcombe_diff_ci(48, 80, 56, 70) == [0.0524, 0.3339]

    def test_the_sign_is_b_minus_a(self):
        low, high = newcombe_diff_ci(56, 70, 48, 80)
        assert (low, high) == (-0.3339, -0.0524)

    def test_identical_rates_straddle_zero(self):
        low, high = newcombe_diff_ci(10, 40, 10, 40)
        assert low < 0 < high

    @pytest.mark.parametrize(("a", "na", "b", "nb"), [(0, 0, 1, 2), (1, 2, 0, 0), (3, 2, 1, 2)])
    def test_an_unusable_side_abstains(self, a, na, b, nb):
        assert newcombe_diff_ci(a, na, b, nb) is None


class TestRateReadingRule:
    """P2-01.9: bands and thresholds are judged on the interval, not the point."""

    def test_under_ten_rows_is_counts_only(self):
        from _stats import COUNTS_ONLY, band_verdict, format_rate  # pyright: ignore

        assert band_verdict(1, 9, 0.0, 1.0) == COUNTS_ONLY
        assert format_rate(1, 9) == "1/9"

    def test_point_inside_band_with_interval_crossing_is_indeterminate(self):
        from _stats import INDETERMINATE, band_verdict, wilson_ci  # pyright: ignore

        # 3/12 = 25%: the point sits inside 10-30%, the interval does not.
        ci = wilson_ci(3, 12)
        assert ci is not None and ci[1] > 0.30
        assert band_verdict(3, 12, 0.10, 0.30) == INDETERMINATE

    def test_interval_wholly_inside_or_outside(self):
        from _stats import IN_BAND, OUT_OF_BAND, band_verdict  # pyright: ignore

        assert band_verdict(200, 1000, 0.10, 0.30) == IN_BAND
        assert band_verdict(500, 1000, 0.10, 0.30) == OUT_OF_BAND

    def test_threshold_needs_the_whole_interval_on_one_side(self):
        from _stats import AT_OR_ABOVE, BELOW, INDETERMINATE, threshold_verdict  # pyright: ignore

        assert threshold_verdict(10, 1000, 0.5) == BELOW
        assert threshold_verdict(900, 1000, 0.5) == AT_OR_ABOVE
        assert threshold_verdict(6, 12, 0.5) == INDETERMINATE

    def test_format_rate_carries_the_interval(self):
        from _stats import format_rate  # pyright: ignore

        assert format_rate(45, 45).startswith("45/45 = 100.0% [92.1–100.0%]")

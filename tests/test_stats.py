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
from _stats import wilson_ci  # noqa: E402  # pyright: ignore[reportMissingImports]


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

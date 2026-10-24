"""Shared interval arithmetic for the scripts/ read-only instruments.

Sibling-imported the same way as `_scan.py` and `_md.py` (the scripts/ dir is
not a package; `python3 scripts/<name>.py` puts it on sys.path), so this adds
no dependency to the bare-`python3` instruments that already import `_scan`.

One function, because an interval is the thing that stops a rate being read
without its resolution — and because two hand-written copies of it drifted in
their *tests* before they drifted in their code: the coselection copy pinned
four reference intervals and the impossible-count abstain, the retrieval copy
pinned neither, and the unpinned one is the copy feeding ADR-0097's
`recall@5 >= 0.9` Review-when. `_md.py` is the standing precedent for exactly
this shape.
"""

from __future__ import annotations

import math

# Two-sided 95%.
_Z95 = 1.959964


def wilson_ci(successes: int, trials: int) -> list[float] | None:
    """95% Wilson score interval, rounded to 4 places; None when unavailable.

    Wilson rather than the normal approximation because these instruments
    routinely report rates near 0 and 1 over small denominators, where the
    normal interval runs outside [0, 1] and reads as a wider claim than the
    data supports.

    Returns None — never a number — for a zero denominator and for an
    impossible count. An impossible count is a caller bug, and ``math.sqrt``
    of the negative variance it implies would surface as a domain error
    rather than as the abstain these instruments owe their reader.
    """
    if trials <= 0 or successes < 0 or successes > trials:
        return None
    p = successes / trials
    denom = 1.0 + _Z95 * _Z95 / trials
    centre = (p + _Z95 * _Z95 / (2 * trials)) / denom
    half = (_Z95 / denom) * math.sqrt(p * (1 - p) / trials + _Z95 * _Z95 / (4 * trials * trials))
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def newcombe_diff_ci(
    successes_a: int, trials_a: int, successes_b: int, trials_b: int
) -> list[float] | None:
    """95% Newcombe (method 10) interval for the rate difference ``b - a``.

    Built from the two Wilson intervals, so it inherits their behaviour near 0
    and 1 and over small denominators; returns None — never a number — when
    either side has no usable interval. The interval is on the *difference*:
    two overlapping Wilson intervals can still exclude zero in the difference
    and two disjoint ones can include it, which is why a before / after
    reading judges this one and not the pair (RFC-0046 S38: a point estimate
    and a row-level count both misread the same question).
    """
    ci_a = wilson_ci(successes_a, trials_a)
    ci_b = wilson_ci(successes_b, trials_b)
    if ci_a is None or ci_b is None:
        return None
    p_a = successes_a / trials_a
    p_b = successes_b / trials_b
    delta = p_b - p_a
    lower = delta - math.sqrt((p_b - ci_b[0]) ** 2 + (ci_a[1] - p_a) ** 2)
    upper = delta + math.sqrt((ci_b[1] - p_b) ** 2 + (p_a - ci_a[0]) ** 2)
    return [round(lower, 4), round(upper, 4)]


# --- The reading rule for every rate the instruments newly publish (P2-01.9) ---
#
# A rate is read together with its interval, and a band or a threshold is judged
# on the interval, not on the point: a point inside the band whose interval
# leaves it says nothing yet, and the reading must say so rather than pass.
# Consumers cite this rule in one phrase ("the interval is P2-01.9's rule")
# instead of restating it.

MIN_DENOMINATOR = 10  # below this a rate is not printed; the counts are

IN_BAND = "in-band"
OUT_OF_BAND = "out-of-band"
INDETERMINATE = "indeterminate"  # 判定不能: the interval straddles an edge
COUNTS_ONLY = "counts-only"  # denominator below MIN_DENOMINATOR (or impossible)
BELOW = "below"
AT_OR_ABOVE = "at-or-above"


def band_verdict(successes: int, trials: int, lo: float, hi: float) -> str:
    """Judge ``successes/trials`` against the band ``[lo, hi]`` on its Wilson interval.

    ``in-band`` only when the whole interval lies inside the band,
    ``out-of-band`` only when the whole interval lies outside it on one side,
    ``indeterminate`` otherwise — including a point estimate inside the band
    whose interval crosses an edge. ``counts-only`` for a denominator under
    ``MIN_DENOMINATOR`` (no rate is judged from fewer than ten rows).
    """
    ci = wilson_ci(successes, trials) if trials >= MIN_DENOMINATOR else None
    if ci is None:
        return COUNTS_ONLY
    if ci[0] >= lo and ci[1] <= hi:
        return IN_BAND
    if ci[1] < lo or ci[0] > hi:
        return OUT_OF_BAND
    return INDETERMINATE


def threshold_verdict(successes: int, trials: int, threshold: float) -> str:
    """``below`` / ``at-or-above`` only when the whole interval is on one side of ``threshold``."""
    ci = wilson_ci(successes, trials) if trials >= MIN_DENOMINATOR else None
    if ci is None:
        return COUNTS_ONLY
    if ci[1] < threshold:
        return BELOW
    if ci[0] >= threshold:
        return AT_OR_ABOVE
    return INDETERMINATE


def format_rate(successes: int, trials: int) -> str:
    """``k/n = 12.5% [lo–hi%]``, or just ``k/n`` when the denominator is under ten."""
    ci = wilson_ci(successes, trials) if trials >= MIN_DENOMINATOR else None
    if ci is None:
        return f"{successes}/{trials}"
    return (
        f"{successes}/{trials} = {100 * successes / trials:.1f}% "
        f"[{100 * ci[0]:.1f}–{100 * ci[1]:.1f}%]"
    )

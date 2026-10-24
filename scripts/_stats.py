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

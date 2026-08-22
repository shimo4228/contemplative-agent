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
this shape, and `_pct` is the repo's counterexample — three copies, the third
with a different algorithm.
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

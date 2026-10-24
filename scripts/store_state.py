#!/usr/bin/env python3
"""Operational definition of "saturated": `store_state` from three axes (ADR-0122).

Stdlib-only apart from the sibling `_stats` (numpy-free Wilson). Pure
function over four weekly records; the caller (``value_layer_due_check``)
adds the result to ``value-layer-{end}.json`` as ``store_state``.

Axes, pooled over the last 4 weeks (each a ratio of counts):

- entry  = staged / clusters           (how much of what the insight stage saw reached staging)
- exit   = archive candidates / store  (how much of the store the exit signals name)
- hub    = hub skill's selections / all selections (concentration of use)

"Below a threshold" means the **whole 95% Wilson interval** is below it
(`_stats.wilson_ci`, the P2-01.9 rule); "above" means the whole interval is
above. A point threshold flips on one count at these denominators. An axis
with fewer than ``MIN_DENOMINATOR`` pooled trials is *count only*: its
interval is not computed and the state is ``undetermined``.

Pre-registered thresholds (fixed here on 2026-10-24, before any reading; a
change is a dated amendment of ADR-0122, never an edit in place):

    saturated  = entry_hi < 0.05  and  exit_hi < 0.05  and  not hub_diffuse(hub_hi < 0.20)
    growing    = entry_lo >= 0.10 and  not (exit_lo >= 0.10)
    equilibrium = every other determined reading

Consumption plan (ADR-0101): see ADR-0122 -- (a) the owner at Saturday-gate
Step 6c reads `store_state` weekly; (b) D-P2-07-2 review (2027-02-27) adopts or
amends the three axes once, then a transition (saturated <-> growing) is read
against the RFC-0048 design points; (c) removed when entry is stopped
(D-P0-01-1 B) and the layer-1 exit has stopped retiring.
"""

from __future__ import annotations

from typing import Any

from _stats import wilson_ci

MIN_DENOMINATOR = 10
WINDOW_WEEKS = 4
ENTRY_LOW, ENTRY_HIGH = 0.05, 0.10
EXIT_LOW, EXIT_HIGH = 0.05, 0.10
HUB_DIFFUSE = 0.20

SATURATED, EQUILIBRIUM, GROWING, UNDETERMINED = (
    "saturated",
    "equilibrium",
    "growing",
    "undetermined",
)

# axis -> (numerator key, denominator key) in a weekly record
_AXES = {
    "entry": ("staged", "clusters"),
    "exit": ("archive_candidates", "store"),
    "hub": ("hub_selections", "selections"),
}


def _axis(weeks: list[dict[str, Any]], num: str, den: str) -> dict[str, Any]:
    n = sum(int(w.get(num, 0) or 0) for w in weeks)
    d = sum(int(w.get(den, 0) or 0) for w in weeks)
    ci = wilson_ci(n, d) if d >= MIN_DENOMINATOR else None
    return {"num": n, "den": d, "ci": ci}


def build_store_state(weeks: list[dict[str, Any]]) -> dict[str, Any]:
    """`store_state` block from up to the last four weekly records (oldest first)."""
    window = list(weeks)[-WINDOW_WEEKS:]
    axes = {name: _axis(window, *keys) for name, keys in _AXES.items()}
    if len(window) < WINDOW_WEEKS:
        return {
            "state": UNDETERMINED,
            "reason": "STORE_STATE_WINDOW_SHORT",
            "weeks": len(window),
            "axes": axes,
        }
    missing = [n for n, a in axes.items() if a["ci"] is None]
    if missing:
        return {
            "state": UNDETERMINED,
            "reason": "STORE_STATE_COUNT_ONLY",
            "count_only": missing,
            "weeks": len(window),
            "axes": axes,
        }
    e_lo, e_hi = axes["entry"]["ci"]
    x_lo, x_hi = axes["exit"]["ci"]
    _h_lo, h_hi = axes["hub"]["ci"]
    if e_hi < ENTRY_LOW and x_hi < EXIT_LOW and not h_hi < HUB_DIFFUSE:
        state = SATURATED
    elif e_lo >= ENTRY_HIGH and not x_lo >= EXIT_HIGH:
        state = GROWING
    else:
        state = EQUILIBRIUM
    return {"state": state, "reason": None, "weeks": len(window), "axes": axes}

"""Retrieval gate for knowledge patterns (ADR-0021 IV-2/IV-7 + ADR-0028).

A pattern is "live" and eligible for retrieval iff it is bitemporally
current (``valid_until is None``) and its ``trust_score`` passes the
trust floor. ADR-0021's additional Ebbinghaus ``strength`` factor and
``access_count`` / ``last_accessed_at`` usage tracking were retired by
ADR-0028 — the agent's hot path does not retrieve patterns per-turn, so
retrieval-frequency-based forgetting has no unit to accumulate.
"""

from __future__ import annotations

import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Retrieval trust floor. See ADR-0021 IV-7.
TRUST_FLOOR = 0.3


def is_live(pattern: Dict) -> bool:
    """True if the pattern is currently retrievable.

    Gates on bitemporal (``valid_until is None``) + trust floor. Patterns
    missing either field are treated leniently (legacy pre-ADR-0021 rows).
    """
    if pattern.get("valid_until") is not None:
        return False
    trust = float(pattern.get("trust_score", 1.0))
    if trust < TRUST_FLOOR:
        return False
    return True

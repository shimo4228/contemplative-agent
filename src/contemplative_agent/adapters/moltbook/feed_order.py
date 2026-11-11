"""The feed cycle's order record: every candidate, its place and why (RFC-0075 S54).

The feed cycle runs in two stages (``FeedManager.run_cycle``): it first scores
every candidate the two sources gave with the score4 gate, then engages the
ones at or above ``relevance_score4`` in descending P(top). This module writes
one row per candidate per cycle to ``logs/feed-order-{date}.jsonl`` so a reader
can answer "which posts did the agent pass over, and why" offline (ADR-0075):
the candidates it engaged, the ones below the cut, and the ones the cycle never
reached.

A row carries ids, numbers and closed codes only — never a post body, title or
author name. The body behind a scored post is in the relevance record
(``logs/relevance-*.jsonl``, base64), joined on ``post_id``; a reading reused
from the cross-session cache has its row in an earlier session's file.

Leaving ``audit_dir`` unset — the default — disables the writer, which is its
kill switch; the feed cycle runs the same either way. The reader is the
weekly census (``scripts/_census_registry.py``, the ``feed-order-*.jsonl`` row),
which counts ``reason`` and ``source`` week by week.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...core._io import append_jsonl_restricted, log_safe_identifier, now_iso

logger = logging.getLogger(__name__)

LOG_PREFIX = "feed-order-"

# Which feed source a candidate came from. Closed. A post both sources carry
# is the following feed's (it is gathered first; the submolt copy is a
# duplicate and dropped).
SOURCE_FOLLOWING = "following"
SOURCE_SUBMOLT = "submolt"
CANDIDATE_SOURCES: tuple[str, ...] = (SOURCE_FOLLOWING, SOURCE_SUBMOLT)

# Why a candidate ended where it did this cycle. Closed: every row carries
# exactly one of these.
# Engaged and the comment was published.
REASON_COMMENTED = "commented"
# Scored, and P(top) is under ``relevance_score4``: the gate closed it.
REASON_BELOW_THRESHOLD = "below_threshold"
# An engagement gate skipped it before scoring (promotional, own post, bad id,
# unsubscribed submolt, already commented, per-author limit, same-author
# repeat topic, or an empty body); it was never scored.
REASON_SKIPPED_GATE = "skipped_gate"
# The gate had no answer for it (the relevance record's ``enforce_reason``
# says which); nothing was engaged.
REASON_FAIL_CLOSED = "fail_closed"
# The cycle stopped before reaching it, in either stage, for the named cause.
REASON_NOT_REACHED_END_TIME = "not_reached_end_time"
REASON_NOT_REACHED_RATE_LIMITED = "not_reached_rate_limited"
REASON_NOT_REACHED_READ_BUDGET = "not_reached_read_budget"
REASON_NOT_REACHED_CIRCUIT_OPEN = "not_reached_circuit_open"
# An earlier candidate's gate had no answer, which ends the scoring stage
# (RFC-0046 cleanup 2): this one was never scored this cycle.
REASON_NOT_REACHED_FAIL_CLOSED = "not_reached_fail_closed"
# Passed the gate and handed to the engagement stage, but the comment rate
# limit (``Scheduler.can_comment``) said no; the upvote may still have landed.
REASON_COMMENT_LIMIT = "comment_limit"
# Passed the gate and handed to the engagement stage, but an existing check
# there wrote no comment: an engagement gate no longer admitted it (a comment
# earlier in this cycle reached the per-author limit, say), the generation
# came back empty, the approval was declined, or the publish failed or went
# unverified (``skill-selection-*.jsonl`` carries the publish outcome).
REASON_DECLINED_DOWNSTREAM = "declined_downstream"
FEED_ORDER_REASONS: tuple[str, ...] = (
    REASON_COMMENTED,
    REASON_BELOW_THRESHOLD,
    REASON_SKIPPED_GATE,
    REASON_FAIL_CLOSED,
    REASON_NOT_REACHED_END_TIME,
    REASON_NOT_REACHED_RATE_LIMITED,
    REASON_NOT_REACHED_READ_BUDGET,
    REASON_NOT_REACHED_CIRCUIT_OPEN,
    REASON_NOT_REACHED_FAIL_CLOSED,
    REASON_COMMENT_LIMIT,
    REASON_DECLINED_DOWNSTREAM,
)


@dataclass(frozen=True)
class CandidateRow:
    """One candidate's outcome in one feed cycle.

    ``arrival`` is its 0-based place in the gathered list (following feed
    first, then the submolt feeds) — the order the cycle engaged in before
    RFC-0075. ``rank`` is its 1-based place by P(top), descending, among the
    candidates scored this cycle (ties keep arrival order); None when it has
    no P(top). The engagement stage walks the passed candidates in rank order.
    """

    post_id: str
    source: str
    arrival: int
    p_top: float | None
    rank: int | None
    reason: str


_audit_dir: Path | None = None


def configure_feed_order(audit_dir: Path | None = None) -> None:
    """Point the writer at a log directory. ``None`` leaves it off."""
    global _audit_dir
    _audit_dir = audit_dir


def reset_feed_order() -> None:
    global _audit_dir
    _audit_dir = None


def record_cycle(rows: Sequence[CandidateRow], threshold: float | None) -> None:
    """Append one row per candidate of one cycle. Never raises.

    The rows share a ``cycle_id`` so a reader groups them without inferring
    cycles from timestamps; ``threshold`` is the ``relevance_score4`` cut the
    cycle used. ``run_id`` / ``session_id`` are stamped by the shared writer.
    """
    if _audit_dir is None or not rows:
        return
    try:
        cycle_id = uuid.uuid4().hex[:12]
        ts = now_iso("seconds")
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = _audit_dir / f"{LOG_PREFIX}{date_str}.jsonl"
        for row in rows:
            record: dict[str, Any] = {
                "ts": ts,
                "cycle_id": cycle_id,
                "post_id": log_safe_identifier(row.post_id),
                "source": row.source,
                "arrival": row.arrival,
                "rank": row.rank,
                "p_top": round(row.p_top, 6) if row.p_top is not None else None,
                "threshold": threshold,
                "reason": row.reason,
            }
            append_jsonl_restricted(path, record)
    except Exception as exc:
        logger.warning("feed order record not written (the feed cycle is unaffected): %s", exc)

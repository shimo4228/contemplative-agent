"""The reply cycle's order record: every reply candidate, its place and why (RFC-0075 S57).

The reply cycle runs in two stages (``ReplyHandler``): it first gathers every
comment a counterparty left for us this cycle and scores its text with the
score4 gate, then replies to the ones at or above ``relevance_score4`` in
descending P(top). This module writes one row per candidate per cycle to
``logs/reply-order-{date}.jsonl`` so a reader can answer "which comments did
the agent leave unanswered, and why" offline (ADR-0075): the ones it replied
to, the ones below the cut, the ones a cap or a gate closed, and the ones the
cycle never reached.

A row carries ids, numbers and closed codes only — never a comment body, a
post body, a title or a counterparty name. The comment text behind a scored
candidate is in the relevance record (``logs/relevance-*.jsonl``, base64,
``source: "reply"``), joined on ``comment_id`` (that record's ``post_id``
field holds the same id); a reading reused from the session memo has its row
earlier in the same session.

Leaving ``audit_dir`` unset — the default — disables the writer, which is its
kill switch; the reply cycle runs the same either way. The reader is the
weekly census (``scripts/_census_registry.py``, the ``reply-order-*.jsonl``
row), which counts ``reason`` and ``route`` week by week.
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

LOG_PREFIX = "reply-order-"

# Which path brought the candidate in. Closed.
# A notification: one that carries the comment text, or one without it whose
# post's comment tree was fetched because of it (``run_cycle``).
ROUTE_NOTIFICATION = "notification"
# The fallback scan of our own posts' comment trees (``check_own_post_comments``).
ROUTE_OWN_POST_SCAN = "own_post_scan"
# The /home ``activity_on_your_posts`` path (``run_cycle_from_home``) — the one
# the session uses whenever /home answered, so most rows carry it.
ROUTE_HOME_ACTIVITY = "home_activity"
REPLY_ROUTES: tuple[str, ...] = (ROUTE_NOTIFICATION, ROUTE_OWN_POST_SCAN, ROUTE_HOME_ACTIVITY)

# Why a candidate ended where it did this cycle. Closed: every row carries
# exactly one of these.
# Handed to the reply stage and the reply was published and verified.
REASON_REPLIED = "replied"
# Scored, and P(top) is under ``relevance_score4``: the gate closed it.
REASON_BELOW_THRESHOLD = "below_threshold"
# We already replied to this counterparty on this post ``THREAD_REPLY_CAP_24H``
# times in the last 24 hours (in either stage); not replied.
REASON_THREAD_CAP = "thread_cap"
# The comment (or the post it sits on) reads as promotional (``is_promotional``);
# never scored.
REASON_PROMOTIONAL = "promotional"
# The reply key is already in the dedup ledger (replied before, or a retired
# target); never scored.
REASON_ALREADY_REPLIED = "already_replied"
# The gate had no answer for it (the relevance record's ``enforce_reason``
# says which); not replied.
REASON_FAIL_CLOSED = "fail_closed"
# The cycle stopped before reaching it, in either stage, for the named cause.
REASON_NOT_REACHED_END_TIME = "not_reached_end_time"
REASON_NOT_REACHED_RATE_LIMITED = "not_reached_rate_limited"
REASON_NOT_REACHED_READ_BUDGET = "not_reached_read_budget"
REASON_NOT_REACHED_WRITE_BUDGET = "not_reached_write_budget"
# ``Scheduler.can_comment`` said no: the 20 s interval after a reply, or the
# daily cap. A reply earlier in the stage is what usually closes it, so the
# rest carry to the next cycle.
REASON_NOT_REACHED_COMMENT_LIMIT = "not_reached_comment_limit"
REASON_NOT_REACHED_CIRCUIT_OPEN = "not_reached_circuit_open"
# A gate with no answer ends the scoring stage: this one was never scored this
# cycle, or it passed but the decision backend had stopped answering
# (``enforce_backend_null``), so the reply stage did not run.
REASON_NOT_REACHED_FAIL_CLOSED = "not_reached_fail_closed"
# The cycle ended on an exception before this candidate's outcome was set.
REASON_ABORTED_EXCEPTION = "aborted_exception"
# Handed to the reply stage, but an existing check there wrote no reply: the
# generation came back empty, the approval was declined, or the publish failed
# or went unverified (``skill-selection-*.jsonl`` carries the publish outcome).
REASON_DECLINED_DOWNSTREAM = "declined_downstream"
REPLY_ORDER_REASONS: tuple[str, ...] = (
    REASON_REPLIED,
    REASON_BELOW_THRESHOLD,
    REASON_THREAD_CAP,
    REASON_PROMOTIONAL,
    REASON_ALREADY_REPLIED,
    REASON_FAIL_CLOSED,
    REASON_NOT_REACHED_END_TIME,
    REASON_NOT_REACHED_RATE_LIMITED,
    REASON_NOT_REACHED_READ_BUDGET,
    REASON_NOT_REACHED_WRITE_BUDGET,
    REASON_NOT_REACHED_COMMENT_LIMIT,
    REASON_NOT_REACHED_CIRCUIT_OPEN,
    REASON_NOT_REACHED_FAIL_CLOSED,
    REASON_ABORTED_EXCEPTION,
    REASON_DECLINED_DOWNSTREAM,
)
# The reasons that leave a candidate for a later cycle: a post on the /home
# route is marked read only when none of its candidates ended on one of these,
# so an unreached comment comes back on the next cycle.
CARRY_OVER_REASONS = frozenset(
    {
        REASON_FAIL_CLOSED,
        REASON_NOT_REACHED_END_TIME,
        REASON_NOT_REACHED_RATE_LIMITED,
        REASON_NOT_REACHED_READ_BUDGET,
        REASON_NOT_REACHED_WRITE_BUDGET,
        REASON_NOT_REACHED_COMMENT_LIMIT,
        REASON_NOT_REACHED_CIRCUIT_OPEN,
        REASON_NOT_REACHED_FAIL_CLOSED,
        REASON_ABORTED_EXCEPTION,
    }
)


@dataclass(frozen=True)
class ReplyRow:
    """One reply candidate's outcome in one reply cycle.

    ``comment_id`` is the id the reply key is built on: the comment's id, or
    on the notification route the notification's id (that payload carries no
    comment id). ``arrival`` is the 0-based place in the order the cycle
    gathered candidates — the order it replied in before RFC-0075 S57.
    ``rank`` is the 1-based place by P(top), descending, among the candidates
    scored this cycle (ties keep arrival order); None when it has no P(top).
    """

    comment_id: str
    post_id: str
    route: str
    arrival: int
    p_top: float | None
    rank: int | None
    reason: str


_audit_dir: Path | None = None


def configure_reply_order(audit_dir: Path | None = None) -> None:
    """Point the writer at a log directory. ``None`` leaves it off."""
    global _audit_dir
    _audit_dir = audit_dir


def reset_reply_order() -> None:
    global _audit_dir
    _audit_dir = None


def record_cycle(rows: Sequence[ReplyRow], threshold: float | None) -> None:
    """Append one row per candidate of one cycle. Never raises.

    The rows share a ``cycle_id``; ``threshold`` is the ``relevance_score4``
    cut the cycle used. ``run_id`` / ``session_id`` are stamped by the shared
    writer. Both ids are platform-authored, so each goes through
    ``log_safe_identifier``.
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
                "comment_id": log_safe_identifier(row.comment_id),
                "post_id": log_safe_identifier(row.post_id),
                "route": row.route,
                "arrival": row.arrival,
                "rank": row.rank,
                "p_top": round(row.p_top, 6) if row.p_top is not None else None,
                "threshold": threshold,
                "reason": row.reason,
            }
            append_jsonl_restricted(path, record)
    except Exception as exc:
        logger.warning("reply order record not written (the reply cycle is unaffected): %s", exc)

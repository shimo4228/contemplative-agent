"""Notification and reply processing for the Moltbook Agent.

A reply cycle runs in two stages (RFC-0075 S57), on each of its three routes
(``run_cycle``: notifications, then the own-post fallback;
``run_cycle_from_home``: the /home activity):

1. scoring — every comment a counterparty left (with text, not ours) is
   gathered; the dedup ledger (``already_replied``), the promotional check and
   the per-thread cap (``THREAD_REPLY_CAP_24H``) label it without a model
   call, and the rest are read by the score4 gate on the comment's text, cut
   at ``relevance_score4`` — the feed's question and cut, no threshold of its
   own;
2. replying — the candidates at or above the cut, highest P(top) first, each
   through ``_process_reply`` as before.

Both stages stop on the same column (``ReplyHandler._stop_reason``), and every
candidate's outcome goes to ``logs/reply-order-{date}.jsonl`` (``reply_order``)
with a closed reason code.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ...core._io import log_safe_identifier, sha256_text
from ...core.comment_outcomes import ObservedComment, record_comment_outcomes
from ...core.config import VALID_ID_PATTERN
from ...core.domain import DomainConfig
from ...core.llm import circuit_reading
from ...core.scheduler import Scheduler
from ...core.skill_selection import (
    PUBLISH_DECLINED,
    PUBLISH_FAILURE_PARENT_REJECTED,
    record_publish_outcome,
)
from . import reply_order
from .client import MoltbookClient
from .dedup import is_promotional
from .llm_functions import generate_internal_note, generate_reply
from .publish import (
    PublishFailure,
    PublishOutcome,
    VerificationHandler,
    client_error_guard,
    created_comment_id as _created_comment_id,
    log_published,
    passes_verification,
    publish_outcome,
    verification_of,
)
from .relevance_gate import (
    ENFORCE_BACKEND_NULL,
    SOURCE_REPLY,
    RecordedReading,
    enforce_and_record,
    resolve_enforce,
)
from .session_context import SessionContext

logger = logging.getLogger(__name__)

# Replies to one counterparty on one post within 24 hours, at most (RFC-0075
# S57, owner-approved 2026-11-21). Two lets a reply answer the counterparty's
# answer to it once; a third is where a thread turns into the back-and-forth
# that fills the day's comments without adding to the exchange. Counted from
# the ``sent`` interaction records the reply path already writes
# (``MemoryStore.count_recent_replies_on_post``), keyed on the counterparty's
# name as the feed's per-author limit is.
THREAD_REPLY_CAP_24H = 2

# Notification types that warrant a reply
_REPLY_TYPES = frozenset(
    {
        "reply",
        "comment",
        "post_comment",
        "comment_reply",
        "mention",
    }
)


def extract_agent_fields(data: dict) -> dict:
    """Extract agent identity and content fields with API format fallbacks.

    Shared by notification processing and own-post comment handling.
    """
    return {
        "id": (data.get("id") or data.get("notification_id") or data.get("comment_id", "")),
        "content": (data.get("content") or data.get("body") or data.get("text", "")),
        "agent_id": (
            data.get("agent_id")
            or data.get("agentId")
            or (data.get("author") or {}).get("id")
            or (data.get("sender") or {}).get("id", "unknown")
        ),
        "agent_name": (
            data.get("agent_name")
            or data.get("agentName")
            or (data.get("author") or {}).get("name")
            or (data.get("sender") or {}).get("name", "unknown")
        ),
    }


def build_observed_comments(
    comments: Sequence[Any], is_self: Callable[[str, str], bool]
) -> tuple[ObservedComment, ...]:
    """Normalize a fetched comment tree into the recorder's DTO (RFC-0028).

    The platform's field-name fallbacks and the "is this us" decision are
    adapter knowledge; the record schema is core's. Doing the translation
    here is what lets ``core.comment_outcomes`` record outcomes without
    importing an adapter, and keeps ``extract_agent_fields`` the one place
    that knows how a comment names its author.

    ``GET /posts/{id}/comments`` returns a tree: root comments in
    ``comments``, each carrying its own ``replies`` (Phase 0, ``skill.md``
    2026-09-09). Nodes that are not objects, and ``replies`` values that are
    not lists, are dropped rather than raising — this is untrusted external
    data on an observation path.
    """
    out: list[ObservedComment] = []
    for raw in comments:
        if not isinstance(raw, dict):
            continue
        fields = extract_agent_fields(raw)
        upvotes = raw.get("upvotes")
        nested = raw.get("replies")
        out.append(
            ObservedComment(
                comment_id=str(fields["id"] or ""),
                is_own=is_self(fields["agent_id"], fields["agent_name"]),
                upvotes=upvotes
                if isinstance(upvotes, int) and not isinstance(upvotes, bool)
                else None,
                body=str(fields["content"] or ""),
                replies=(
                    build_observed_comments(nested, is_self) if isinstance(nested, list) else ()
                ),
            )
        )
    return tuple(out)


def extract_notification_fields(notif: dict) -> dict:
    """Extract notification fields with fallback for different API formats."""
    fields = extract_agent_fields(notif)
    fields.update(
        {
            "type": (notif.get("type") or notif.get("kind") or notif.get("event_type", "")),
            "post_id": (
                notif.get("post_id")
                or notif.get("postId")
                or notif.get("relatedPostId")
                or notif.get("target_id", "")
            ),
            # The trailing `or ""` is what makes this field a ``str``, not the
            # `.get(k, "")` default: that default only fires on a *missing*
            # key, so `original_content: null` — a shape the platform does
            # send — walked the whole chain and yielded None. Readers downstream
            # take this as text (the has-a-post test calls ``.strip()``), so the
            # coercion belongs here at the parse boundary rather than in every
            # reader (T-REPLY-BLANKPOST).
            "post_content": (
                notif.get("post_content")
                or notif.get("postContent")
                or notif.get("original_content")
                or ""
            ),
        }
    )
    return fields


def _is_promotional_target(their_content: str, original_post: str) -> bool:
    """The promotional gate on a reply target: the comment, or the post it sits on.

    Whitespace-only post text is "no post" (T-REPLY-BLANKPOST), so the regex
    does not run on a body that is not there.
    """
    has_post = bool(original_post.strip())
    return is_promotional(their_content) or (has_post and is_promotional(original_post))


def _fmt_p(p_top: float | None) -> str:
    return f"{p_top:.3f}" if p_top is not None else "n/a"


@dataclass(frozen=True)
class _ReplyCandidate:
    """One counterparty comment a reply cycle gathered.

    ``target_id`` is the id the reply key is built on (the comment's id, or
    the notification's on the notification route, whose payload carries no
    comment id); ``comment_id`` is the parent the reply threads under, ""
    when unknown (notification route: a top-level reply).
    """

    route: str
    post_id: str
    reply_key: str
    target_id: str
    comment_id: str
    their_content: str
    original_post: str
    replier_id: str
    replier_name: str


class _ReplyCycle:
    """One reply cycle's candidates and their outcomes, filled by the two stages.

    Module-private and mutable on purpose: it lives inside one
    ``ReplyHandler._run_stages`` call and is folded into frozen
    ``reply_order.ReplyRow`` records at its end.
    """

    def __init__(self) -> None:
        self.candidates: list[_ReplyCandidate] = []
        self.reasons: list[str | None] = []
        self.p_tops: list[float | None] = []
        # Indexes of the candidates the gate passed, in arrival order.
        self.passed: list[int] = []
        self._keys: set[str] = set()
        # The scoring stage's stop reason, sticky once set.
        self.stop: str | None = None
        # The cycle-level ``enforce_reason`` that ended scoring, if one did.
        self.fail_closed_reason: str | None = None

    def add(self, candidate: _ReplyCandidate) -> int | None:
        """Append *candidate*; its index, or None when the cycle already holds its key."""
        if candidate.reply_key in self._keys:
            return None
        self._keys.add(candidate.reply_key)
        self.candidates.append(candidate)
        self.reasons.append(None)
        self.p_tops.append(None)
        return len(self.candidates) - 1


class ReplyHandler:
    """Handles notification-driven reply cycles for the agent.

    Every cycle runs the two stages the module docstring describes: score
    every gathered candidate, then reply best-first. ``domain`` supplies the
    cut (``relevance_threshold_score4``), the same value the feed cuts at.
    """

    def __init__(
        self,
        ctx: SessionContext,
        domain: DomainConfig,
        confirm_action: Callable[[str, str], bool],
        confirm_side_effect: Callable[[str], bool],
        handle_verification: VerificationHandler,
    ) -> None:
        self._ctx = ctx
        self._domain = domain
        self._confirm_action = confirm_action
        self._confirm_side_effect = confirm_side_effect
        self._handle_verification = handle_verification
        # Posts whose comment tree has already been fetched in the current
        # cycle. The notification path and the own-post fallback overlap by
        # construction — a comment on our own post produces a content-less
        # notification AND sits under an id in ``own_post_ids`` — so the same
        # tree was fetched twice, replied to once (the second pass is deduped
        # per comment) and recorded twice as duplicates. Cleared at each cycle
        # entry point, never across cycles.
        self._scanned_posts: set[str] = set()
        # Answered score4 readings of reply candidates, keyed on the reply key
        # and the digest of the text read: one reading per comment per session.
        # A comment the gate closed stays in its tree and is gathered again
        # every cycle, so without this it would be read again every cycle.
        # Never persisted: the cross-session relevance cache keeps one writer,
        # the feed (``feed_manager.read_relevance_gate``), and holds posts.
        self._readings: dict[tuple[str, str], RecordedReading] = {}

    def _stop_reason(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
        *,
        reading: bool,
    ) -> str | None:
        """The first stop condition that holds now, as a reply-order reason; None to go on.

        One column for every reply loop: asked before each fetch and each
        score in the scoring stage (*reading* — that stage spends GETs, so it
        also asks the read budget) and before each reply in the reply stage.
        All are side-effect-free, so position within the column is not
        load-bearing (T-REPLY-PACING).

        The breaker stop is a stop, not a backoff: generation was the loop's
        only pacer, and an open breaker returns from it in microseconds, so the
        scan ran at full speed (2026-07-12: 6,621 candidates in an hour,
        nothing published). The breaker owns the clock and the candidates carry
        to the next session, as the write-budget stop already did. The
        incident numbers live in tests/test_reply_chaos.py.
        """
        if time.time() >= end_time:
            return reply_order.REASON_NOT_REACHED_END_TIME
        if self._ctx.is_rate_limited:
            return reply_order.REASON_NOT_REACHED_RATE_LIMITED
        if not scheduler.can_comment():
            return reply_order.REASON_NOT_REACHED_COMMENT_LIMIT
        if not client.has_write_budget():
            return reply_order.REASON_NOT_REACHED_WRITE_BUDGET
        if reading and not client.has_read_budget():
            return reply_order.REASON_NOT_REACHED_READ_BUDGET
        if circuit_reading().is_open:
            return reply_order.REASON_NOT_REACHED_CIRCUIT_OPEN
        return None

    def _gather_stop(
        self,
        cycle: _ReplyCycle,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> str | None:
        """The scoring stage's stop: sticky for the cycle once set, logged once."""
        if cycle.stop is None:
            cycle.stop = self._stop_reason(client, scheduler, end_time, reading=True)
            if cycle.stop is not None:
                logger.info("Pausing reply scoring: %s", cycle.stop)
        return cycle.stop

    # ------------------------------------------------------------------
    # The two stages
    # ------------------------------------------------------------------

    def _run_stages(
        self,
        gather: Callable[[_ReplyCycle], None],
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> _ReplyCycle:
        """Gather and score with *gather*, then reply best-first; record every candidate.

        The record is written also when the cycle ends on an exception: the
        candidate in hand and every one not reached yet say
        ``aborted_exception`` instead of being dropped.
        """
        cycle = _ReplyCycle()
        try:
            gather(cycle)
            self._reply_stage(cycle, client, scheduler, end_time)
        except Exception:
            for index, reason in enumerate(cycle.reasons):
                if reason is None:
                    cycle.reasons[index] = reply_order.REASON_ABORTED_EXCEPTION
            raise
        finally:
            self._record(cycle)
        return cycle

    def _admit(
        self,
        cycle: _ReplyCycle,
        candidate: _ReplyCandidate,
        *,
        handled: bool,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """The scoring stage for one candidate: the checks that cost no call, then the gate.

        A candidate whose reply key the cycle already holds is dropped, not
        recorded twice. The dedup, promotional and thread-cap checks read only
        memory, so they label a candidate even after the stage stopped; only
        the score waits on the stop column.
        """
        index = cycle.add(candidate)
        if index is None:
            return
        if handled:
            cycle.reasons[index] = reply_order.REASON_ALREADY_REPLIED
            return
        if _is_promotional_target(candidate.their_content, candidate.original_post):
            logger.info("Skipped promotional reply target: %s", candidate.post_id[:12])
            cycle.reasons[index] = reply_order.REASON_PROMOTIONAL
            return
        if self._thread_capped(candidate):
            cycle.reasons[index] = reply_order.REASON_THREAD_CAP
            return
        stop = self._gather_stop(cycle, client, scheduler, end_time)
        if stop is not None:
            cycle.reasons[index] = stop
            return
        reading = self._score(candidate)
        cycle.p_tops[index] = reading.p_top
        outcome = reading.outcome
        target = log_safe_identifier(candidate.target_id)
        if outcome.enforce_gate is None:
            cycle.reasons[index] = reply_order.REASON_FAIL_CLOSED
            logger.info(
                "Reply target %s score4 gate fail_closed (%s%s)",
                target,
                outcome.enforce_reason,
                ", post-level: skipped" if reading.post_level_failure else "",
            )
            # RFC-0046 cleanup 2, as on the feed: a gate with no answer scores
            # nothing more this cycle (one decision timeout per remaining
            # candidate otherwise), unless the failure is tied to this text.
            if not reading.post_level_failure:
                cycle.fail_closed_reason = outcome.enforce_reason
                cycle.stop = reply_order.REASON_NOT_REACHED_FAIL_CLOSED
            return
        if not outcome.enforce_gate:
            # INFO so every verdict lands in production logs, not only the
            # passing tail (censored-distribution trap).
            logger.info(
                "Reply target %s score4 gate closed (P(top) %s)", target, _fmt_p(reading.p_top)
            )
            cycle.reasons[index] = reply_order.REASON_BELOW_THRESHOLD
            return
        logger.info("Reply target %s score4 gate passed (P(top) %s)", target, _fmt_p(reading.p_top))
        cycle.passed.append(index)

    def _score(self, candidate: _ReplyCandidate) -> RecordedReading:
        """The score4 reading of the counterparty's comment text, once per session.

        The feed's question and cut (``feed_manager.read_relevance_gate``),
        asked of the comment instead of a post, through the same recorder
        (``source: "reply"``, the row's ``post_id`` holding ``target_id``).
        The memo keeps the decision half and cuts it at today's threshold, as
        the cross-session cache does for the feed.
        """
        threshold = self._domain.relevance_threshold_score4
        key = (candidate.reply_key, sha256_text(candidate.their_content))
        memo = self._readings.get(key)
        if memo is not None and memo.decision is not None:
            return RecordedReading(resolve_enforce(memo.decision, threshold), memo.decision)
        reading = enforce_and_record(
            candidate.target_id,
            candidate.their_content,
            threshold_score4=threshold,
            source=SOURCE_REPLY,
        )
        # p_top is set only on an ``answered`` read: the one kind kept.
        if reading.p_top is not None:
            self._readings[key] = reading
        return reading

    def _thread_capped(self, candidate: _ReplyCandidate) -> bool:
        """We replied to this counterparty on this post the cap's times in the last 24 h."""
        sent = self._ctx.memory.count_recent_replies_on_post(
            candidate.replier_name, candidate.post_id, hours=24
        )
        return sent >= THREAD_REPLY_CAP_24H

    def _reply_stage(
        self,
        cycle: _ReplyCycle,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Stage 2: the passed candidates, highest P(top) first; fills their reasons.

        A stable sort, so ties keep arrival order. The thread cap is asked
        again, because a reply earlier in this stage counts toward it. When the
        decision backend stopped answering (``enforce_backend_null``) the stage
        does not run: the note and the reply call the same local Ollama, and
        the candidates carry to the next cycle, where the memo answers them.
        """
        if cycle.fail_closed_reason == ENFORCE_BACKEND_NULL:
            for index in cycle.passed:
                cycle.reasons[index] = reply_order.REASON_NOT_REACHED_FAIL_CLOSED
            return
        stop: str | None = None
        for index in sorted(cycle.passed, key=lambda i: cycle.p_tops[i] or 0.0, reverse=True):
            if stop is None:
                stop = self._stop_reason(client, scheduler, end_time, reading=False)
                if stop is not None:
                    logger.info("Pausing reply processing: %s", stop)
            if stop is not None:
                cycle.reasons[index] = stop
                continue
            candidate = cycle.candidates[index]
            if self._thread_capped(candidate):
                cycle.reasons[index] = reply_order.REASON_THREAD_CAP
                continue
            published = self._process_reply(
                client=client,
                scheduler=scheduler,
                post_id=candidate.post_id,
                reply_key=candidate.reply_key,
                their_content=candidate.their_content,
                original_post=candidate.original_post,
                replier_id=candidate.replier_id,
                replier_name=candidate.replier_name,
                comment_id=candidate.comment_id,
            )
            cycle.reasons[index] = (
                reply_order.REASON_REPLIED if published else reply_order.REASON_DECLINED_DOWNSTREAM
            )

    def _record(self, cycle: _ReplyCycle) -> None:
        """One reply-order row per candidate of this cycle (RFC-0075 S57, ADR-0075).

        Every candidate has a reason by the time this runs: one of the two
        stages set it, or ``_run_stages`` marked it ``aborted_exception``. A
        candidate without one is a broken invariant, not an outcome to guess:
        the rows that have a reason are written, and then this raises naming
        the gap (the session step logs it and the next cycle runs).
        """
        scored = [i for i, p in enumerate(cycle.p_tops) if p is not None]
        ranked = sorted(scored, key=lambda i: cycle.p_tops[i] or 0.0, reverse=True)
        rank = {index: place for place, index in enumerate(ranked, start=1)}
        rows: list[reply_order.ReplyRow] = []
        missing: list[int] = []
        for index, candidate in enumerate(cycle.candidates):
            reason = cycle.reasons[index]
            if reason is None:
                missing.append(index)
                continue
            rows.append(
                reply_order.ReplyRow(
                    comment_id=candidate.target_id,
                    post_id=candidate.post_id,
                    route=candidate.route,
                    arrival=index,
                    p_top=cycle.p_tops[index],
                    rank=rank.get(index),
                    reason=reason,
                )
            )
        reply_order.record_cycle(rows, self._domain.relevance_threshold_score4)
        if missing:
            raise RuntimeError(
                f"reply order: no reason for candidates at arrival {missing} "
                "(neither stage nor the abort path set one)"
            )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Check for and respond to replies on our posts/comments.

        One cycle over two sources: the notifications, then the own-post
        fallback; both stages run once over everything they gathered.
        """
        if not scheduler.can_comment():
            return

        self._scanned_posts.clear()

        def gather(cycle: _ReplyCycle) -> None:
            self._gather_notifications(cycle, client, scheduler, end_time)
            # Fallback: check comments on our own posts directly
            self._gather_own_posts(cycle, client, scheduler, end_time)

        self._run_stages(gather, client, scheduler, end_time)

    def _gather_notifications(
        self,
        cycle: _ReplyCycle,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """The notification route's candidates: carried text, or the post's comment tree."""
        notifications = client.get_notifications()
        logger.debug("Fetched %d notification(s) from API", len(notifications))

        for i, notif in enumerate(notifications):
            # Shape, not values. This used to dump 200 chars of the raw
            # notification JSON, which carries other agents' comment and post
            # text — external content entering `logs/agent-launchd.log`, the
            # one file the harness classifies as self-written and lets Claude
            # Code read (`~/.claude/hooks/_episode-log-common.sh`). What the
            # line is actually for is the notification's shape, and the keys
            # answer that without quoting anyone (T-LOG-DEBUG-CONTENT).
            logger.debug(
                "Notification[%d] keys: %s",
                i,
                ",".join(sorted(notif)) if isinstance(notif, dict) else type(notif).__name__,
            )

            validated = self._validated_notification(notif, i)
            if validated is None:
                continue
            fields, reply_key, handled = validated

            self._gather_notification(
                cycle, client, scheduler, fields, reply_key, handled, i, end_time
            )

    def _reply_dedup(self, post_id: str, comment_id: str) -> tuple[str, bool]:
        """Return the reply dedup key and whether it was already handled.

        A reply is "handled" if its key is in the in-session
        ``commented_posts`` set or the persistent ``has_commented_on`` cache.
        Shared by the notification path and the post-comment scan; each caller
        keeps its own logging / skip behavior.
        """
        key = f"reply:{post_id}:{comment_id}"
        handled = key in self._ctx.commented_posts or self._ctx.memory.has_commented_on(key)
        return key, handled

    def _reply_failed(
        self, outcome: PublishOutcome, failure: PublishFailure, reply_key: str
    ) -> None:
        """Record why one reply write failed, and retire a dead target (RFC-0038).

        ``parent_rejected`` is the only permanent member of the failure
        vocabulary: the platform refuses this parent comment and that answer
        does not change, so an open key costs three LLM calls, one comment
        pacing slot and a 404 POST on every later scan — 11 replays of the
        same target across 7 sessions in the 2026-09-13..18 window. Marking
        the key is what takes it out of ``_reply_dedup``. ``rate_limited`` /
        ``transport`` / ``unknown`` are conditions of the moment and the
        ``unverified`` exit never reaches here at all (it records nothing on
        purpose — ``publish.passes_verification``), so those stay retryable.

        The mark goes in the dedup ledger, which holds no publish meaning:
        what says a reply went out is the ``published`` outcome row and the
        activity episode, and this path writes neither (its row is
        ``publish_failed`` + ``parent_rejected``, ADR-0106 D3). So no audit or
        instrument reading counts a retired target as a published reply.
        ``commented_posts`` and the persistent cache are both written, as on
        the published path, because ``_reply_dedup`` reads both. Durability is
        also the published path's: a cold cache rebuild
        (``memory_repos._build_cache``) collects post ids from episodes and no
        reply keys at all, so a retired target comes back if the cache file is
        lost — the same hole published reply keys already have.

        Reached from the notification path too, where the key's second half is
        a notification id and the reply was posted top-level
        (``parent_id=None``) — a genuine parent rejection cannot arise there,
        so a code seen on that path is a false positive by construction. Left
        actuating rather than gated on ``comment_id``, because which of the two
        paths produced the observed replays is not in the RFC-0038 evidence and
        gating on an unverified guess would leave the measured loop running.
        """
        outcome.failed(failure)
        if failure.failure_reason != PUBLISH_FAILURE_PARENT_REJECTED:
            return
        # The key's second half is platform-authored and this line ends at INFO
        # in the sweep-scanned log, so it is bounded the same way a
        # counterparty's display name is (T-LOG-DEBUG-CONTENT).
        logger.info("Retiring reply target %s: parent rejected", log_safe_identifier(reply_key))
        self._ctx.commented_posts.add(reply_key)
        self._ctx.memory.record_commented(reply_key)

    def _validated_notification(self, notif: dict, i: int) -> tuple[dict, str, bool] | None:
        """Gate one notification; return (fields, reply_key, handled) or None to skip.

        Skips non-actionable types and invalid post ids. ``handled`` says the
        reply key is already in the dedup ledger — this session
        (commented_posts) or a prior session (persistent commented cache).
        Mirrors the comment path's has_commented_on check
        (feed_manager._passes_content_gates); commented_posts is rebuilt empty
        each session, so the persistent store is what dedups replies across
        sessions. A handled notification is not replied to; the caller records
        it (``already_replied``) when it carries a counterparty's text.
        """
        fields = extract_notification_fields(notif)
        notif_type = fields["type"]

        if notif_type not in _REPLY_TYPES:
            logger.debug(
                "Notification[%d] skipped: type=%r not actionable",
                i,
                notif_type,
            )
            return None

        post_id = fields["post_id"]
        if not post_id or not VALID_ID_PATTERN.match(post_id):
            logger.debug("Notification[%d] skipped: invalid post_id=%r", i, post_id)
            return None

        reply_key, handled = self._reply_dedup(post_id, fields["id"])
        if handled:
            logger.debug(
                "Notification[%d] already handled key=%s",
                i,
                reply_key,
            )
        return fields, reply_key, handled

    def _handle_notification(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        fields: dict,
        reply_key: str,
        i: int,
        end_time: float,
    ) -> None:
        """Both stages for one validated, unhandled notification alone.

        The cycle (``run_cycle``) gathers every notification into one cycle
        first; this is the same work for a single one.
        """
        self._run_stages(
            lambda cycle: self._gather_notification(
                cycle, client, scheduler, fields, reply_key, False, i, end_time
            ),
            client,
            scheduler,
            end_time,
        )

    def _gather_notification(
        self,
        cycle: _ReplyCycle,
        client: MoltbookClient,
        scheduler: Scheduler,
        fields: dict,
        reply_key: str,
        handled: bool,
        i: int,
        end_time: float,
    ) -> None:
        """One notification's candidates: its own text, or its post's comment tree."""
        post_id = fields["post_id"]
        their_content = fields["content"]

        # If notification lacks comment body (e.g. post_comment type),
        # fetch comments from the post and gather the unhandled ones
        if not their_content:
            if handled:
                return
            if self._gather_stop(cycle, client, scheduler, end_time) is not None:
                return
            logger.debug(
                "Notification[%d] has no content; fetching comments for %s",
                i,
                post_id[:12],
            )
            self._gather_post_comments(
                cycle, client, scheduler, post_id, reply_order.ROUTE_NOTIFICATION, end_time
            )
            return

        replier_id = fields["agent_id"]
        replier_name = fields["agent_name"]

        # Skip our own comments to avoid self-reply loops (name-keyed:
        # notification data carries agent_name but agent_id="unknown")
        if self._ctx.is_self(replier_id, replier_name):
            logger.debug("Notification[%d] skipped: own comment", i)
            return

        self._admit(
            cycle,
            _ReplyCandidate(
                route=reply_order.ROUTE_NOTIFICATION,
                post_id=post_id,
                reply_key=reply_key,
                target_id=str(fields["id"] or ""),
                comment_id="",  # notification payload has no comment id
                their_content=their_content,
                original_post=fields["post_content"],
                replier_id=replier_id,
                replier_name=replier_name,
            ),
            handled=handled,
            client=client,
            scheduler=scheduler,
            end_time=end_time,
        )

    def _process_reply(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        post_id: str,
        reply_key: str,
        their_content: str,
        original_post: str,
        replier_id: str,
        replier_name: str,
        comment_id: str = "",
    ) -> bool:
        """Generate and send a reply to a comment, recording interactions.

        True only when the reply was published and verified — the reply
        stage's ``replied``; every other exit is its ``declined_downstream``.

        ``comment_id`` is the id of the comment being replied to, when known
        (the comment-scan path supplies it). The notification path passes ""
        because the notification payload carries no comment id — see the
        courtesy-upvote guard below.
        """
        # Where whitespace becomes absence for everything this function decides
        # (T-REPLY-BLANKPOST). _gather_post_comments passes original_post=""
        # (no body fetched there), and a body of " \n " is empty in every sense
        # that matters here, so both read as "no post". Only the decision is
        # normalized: the raw value is what reaches generate_internal_note,
        # generate_reply and the episode record, since a real post must not have
        # its own whitespace edited on the way to the model. generate_reply
        # applies the same .strip() test to its `Original post:` section, so the
        # note and the reply never disagree about whether a post exists. The
        # raw body persists into the episode record, so the distill render
        # downstream still gates on its own truthiness test — out of scope here.
        has_post = bool(original_post.strip())

        # Promotional gate. The scoring stage asks the same question first and
        # records ``promotional``; this one keeps the function safe to call on
        # its own.
        if _is_promotional_target(their_content, original_post):
            logger.info("Skipped promotional reply target: %s", post_id[:12])
            return False

        ctx = self._ctx

        # Pre-action reflection (ADR-0045): note what we noticed in their
        # comment (and the post it sits on) before composing a reply.
        note_context = f"{original_post}\n\n{their_content}" if has_post else their_content
        note = generate_internal_note(note_context)

        generated = generate_reply(
            original_post=original_post,
            their_comment=their_content,
        )
        reply = generated.text
        if reply is None:
            return False
        # RFC-0028: the selection this reply was generated under. Recorded at
        # every exit below, so "never published" is a reason code rather than
        # an absent row.
        selection_id = generated.selection_id
        # RFC-0049: every reply row names its target, so the rows of one target
        # can be counted. Raw here; the writer keeps a digest of the key and
        # the parent id only if it is a valid id. "" (notification path) is
        # "no parent", recorded as null.
        parent_comment_id = comment_id or None

        if not self._confirm_action(f"Reply to {replier_name} on post {post_id}", reply):
            record_publish_outcome(
                selection_id,
                comment_id=None,
                publish_status=PUBLISH_DECLINED,
                reply_key=reply_key,
                parent_comment_id=parent_comment_id,
            )
            return False

        # Record the incoming comment first (chronological order)
        ctx.memory.record_interaction(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_id=replier_id,
            agent_name=replier_name,
            post_id=post_id,
            direction="received",
            content=their_content,
            interaction_type="reply",
        )

        scheduler.wait_for_comment()
        # Set once the reply is live and verified; the guard below may still
        # swallow a client error raised after that (the courtesy upvote).
        published = False
        # publish_outcome OUTSIDE the guard: the guard swallows the client
        # error, so only an exit outside it can tell "never published" from
        # "published and recorded".
        with (
            publish_outcome(
                selection_id, reply_key=reply_key, parent_comment_id=parent_comment_id
            ) as outcome,
            client_error_guard(
                f"reply on {post_id}",
                on_rate_limited=ctx.set_rate_limited,
                # Reads ``outcome`` bound by the item above: with-items are
                # entered left to right. The guard is the last place the error
                # is visible, so this is also where a permanently rejected
                # target can leave the queue (RFC-0038).
                on_failure=lambda failure: self._reply_failed(outcome, failure, reply_key),
            ),
        ):
            # post_comment verifies the response envelope (audit H2): a
            # body-level failure raises and never reaches the records below.
            # parent_id threads the reply under the comment being answered when
            # known (comment-scan path); the notification path has no comment id
            # so it posts a top-level comment (parent_id=None).
            created = client.post_comment(post_id, reply, parent_id=comment_id or None)
            scheduler.record_comment()
            outcome.created(_created_comment_id(created))
            # The inbound "received" interaction above stays recorded even when
            # the handshake fails — it happened regardless of our visibility.
            if not passes_verification(
                verification_of(created),
                self._handle_verification,
                description=f"Reply on {post_id[:12]}",
                action="reply",
                target_id=post_id,
            ):
                outcome.unverified()
                return False
            # Recorded as soon as the reply is live and verified — see
            # feed_manager: the records that follow can be interrupted.
            outcome.published()
            published = True
            ctx.commented_posts.add(reply_key)
            # Persist cross-session so a later session does not re-reply to the
            # same target (mirrors feed_manager._post_comment_and_record's
            # record_commented). Dedup only covers reply keys actually recorded:
            # the episode-scan fallback (memory_repos._build_cache, reached from
            # _load_cache) collects ep["data"]["post_id"], never reply keys.
            ctx.memory.record_commented(reply_key)
            # The counterparty's display name is as attacker-controlled as the
            # body was, and both of its consumers below end at INFO in the
            # sweep-scanned log — so dropping `-v` does not cover it
            # (T-LOG-DEBUG-CONTENT, security review). `actions_taken` is
            # replayed line by line at session end (agent.py _print_report).
            safe_replier = log_safe_identifier(replier_name)
            ctx.actions_taken.append(f"Replied to {safe_replier} on {post_id}")
            # Preview only: full bodies in *.log become anomaly-sweep noise
            # and cross the self-written-log trust boundary (F1.1 2026-07-11).
            # Canonical full text: episode log below + comment-reports. No
            # full-body log path remains at any level — the DEBUG branch that
            # produced one is gone, parameters included (T-LOG-DEBUG-CONTENT);
            # tests/test_publish_logging.py is what holds that now.
            log_published(
                ">> Reply to %s on %s: %d chars: %s",
                safe_replier,
                post_id[:12],
                body=reply,
            )
            ctx.memory.episodes.append(
                "activity",
                {
                    "action": "reply",
                    "post_id": post_id,
                    "content": reply,
                    "target_agent": replier_name,
                    "target_agent_id": replier_id,
                    "their_comment": their_content,
                    "original_post": original_post,
                    "internal_note": note,
                    "thinking": generated.thinking,
                },
            )
            ctx.memory.record_interaction(
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent_id=replier_id,
                agent_name=replier_name,
                post_id=post_id,
                direction="sent",
                content=reply,
                interaction_type="reply",
            )
            # Upvote their comment as a courtesy — only when we actually hold
            # the comment id. The notification path keys reply_key on the
            # notification id (not a comment id), so deriving the id from
            # reply_key there upvotes the wrong target: a failing
            # POST /comments/{notification_id}/upvote that wastes write budget.
            if (
                comment_id
                and comment_id not in ("", "unknown")
                and self._confirm_side_effect(f"Upvote comment {comment_id}")
            ):
                client.upvote_comment(comment_id)
        return published

    def _handle_post_comments(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        post_id: str,
        end_time: float,
        route: str = reply_order.ROUTE_OWN_POST_SCAN,
    ) -> None:
        """Both stages for one post's comment tree alone.

        The routes gather many trees into one cycle first; this is the same
        work for a single post.
        """
        self._run_stages(
            lambda cycle: self._gather_post_comments(
                cycle, client, scheduler, post_id, route, end_time
            ),
            client,
            scheduler,
            end_time,
        )

    def _gather_post_comments(
        self,
        cycle: _ReplyCycle,
        client: MoltbookClient,
        scheduler: Scheduler,
        post_id: str,
        route: str,
        end_time: float,
    ) -> None:
        """Fetch comments on a post and gather the counterparties' ones into *cycle*.

        A post already scanned in this cycle is skipped rather than refetched:
        the second pass can only see what the first did (plus our own replies,
        which it skips), so the refetch bought a duplicate GET and a second
        pass of ``record_comment_outcomes`` whose rows all land as duplicates.
        """
        if post_id in self._scanned_posts:
            logger.debug("Post %s already scanned this cycle; not refetching", post_id[:12])
            return
        self._scanned_posts.add(post_id)
        comments = client.get_post_comments(post_id)
        logger.debug("Post %s has %d comment(s)", post_id[:12], len(comments))

        # RFC-0028: record what the platform returned about our own comments
        # in this tree — replies, their depth, upvotes. The tree is already
        # fetched for the reply loop below, so this costs no request and adds
        # no field to the /home allowlist. Read-only in effect: nothing it
        # writes is read back by the agent.
        scan = record_comment_outcomes(
            post_id, build_observed_comments(comments, self._ctx.is_self)
        )
        if scan.reasons:
            logger.info(
                "comment outcomes on %s: %d written, %d duplicate, reasons=%s",
                post_id[:12],
                scan.written,
                scan.duplicates,
                ",".join(scan.reasons),
            )

        for comment in comments:
            fields = extract_agent_fields(comment)

            # Skip our own comments to avoid self-reply loops (name-keyed:
            # comment data carries agent_name but agent_id="unknown")
            if self._ctx.is_self(fields["agent_id"], fields["agent_name"]):
                continue

            if not fields["content"]:
                continue

            reply_key, handled = self._reply_dedup(post_id, fields["id"])
            self._admit(
                cycle,
                _ReplyCandidate(
                    route=route,
                    post_id=post_id,
                    reply_key=reply_key,
                    target_id=str(fields["id"] or ""),
                    comment_id=fields["id"],  # real comment id on this path
                    their_content=fields["content"],
                    original_post="",
                    replier_id=fields["agent_id"],
                    replier_name=fields["agent_name"],
                ),
                handled=handled,
                client=client,
                scheduler=scheduler,
                end_time=end_time,
            )

    def run_cycle_from_home(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
        home_data: dict,
    ) -> None:
        """Process replies using /home activity_on_your_posts data.

        This avoids individual notification + comment fetches by using
        the pre-fetched home dashboard data. A fetched post's notifications are
        marked read after the reply stage, and only when none of its
        candidates was left for a later cycle (``CARRY_OVER_REASONS``): a
        marked post has no new activity on the next /home, so its unreached
        comments would never be gathered again.
        """
        self._scanned_posts.clear()
        activity = home_data.get("activity_on_your_posts", [])
        if not activity:
            logger.debug("No activity on own posts from /home data")
            return

        fetched: list[str] = []

        def gather(cycle: _ReplyCycle) -> None:
            for item in activity:
                if self._gather_stop(cycle, client, scheduler, end_time) is not None:
                    break

                post_id = item.get("post_id", "")
                if not post_id or not VALID_ID_PATTERN.match(post_id):
                    continue

                new_count = item.get("new_notification_count", 0)
                if new_count == 0:
                    continue

                # Fetch comments for this post and gather unhandled ones
                self._gather_post_comments(
                    cycle, client, scheduler, post_id, reply_order.ROUTE_HOME_ACTIVITY, end_time
                )
                fetched.append(post_id)

        cycle = self._run_stages(gather, client, scheduler, end_time)

        carried = {
            candidate.post_id
            for candidate, reason in zip(cycle.candidates, cycle.reasons, strict=True)
            if reason in reply_order.CARRY_OVER_REASONS
        }
        for post_id in fetched:
            if post_id in carried:
                continue
            # Mark notifications as read for this post
            if self._confirm_side_effect(f"Mark notifications read for post {post_id}"):
                client.mark_notifications_read_by_post(post_id)

    def check_own_post_comments(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Fallback: fetch comments on our own posts and reply to new ones (both stages)."""
        self._run_stages(
            lambda cycle: self._gather_own_posts(cycle, client, scheduler, end_time),
            client,
            scheduler,
            end_time,
        )

    def _gather_own_posts(
        self,
        cycle: _ReplyCycle,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """The own-post fallback's candidates: every tracked own post's comment tree."""
        if not self._ctx.own_post_ids:
            logger.debug("No own post IDs tracked; skipping comment check")
            return

        for post_id in list(self._ctx.own_post_ids):
            if self._gather_stop(cycle, client, scheduler, end_time) is not None:
                break

            self._gather_post_comments(
                cycle, client, scheduler, post_id, reply_order.ROUTE_OWN_POST_SCAN, end_time
            )

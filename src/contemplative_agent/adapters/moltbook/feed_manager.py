"""Feed fetching and engagement logic for the Moltbook Agent."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from ...core._io import log_safe_identifier
from ...core.config import VALID_ID_PATTERN
from ...core.domain import DomainConfig
from ...core.llm import circuit_reading
from ...core.scheduler import Scheduler
from ...core.skill_selection import (
    PUBLISH_DECLINED,
    PUBLISH_FAILED,
    PUBLISH_ID_UNKNOWN,
    PUBLISH_PUBLISHED,
    PUBLISH_UNVERIFIED,
    record_publish_outcome,
)
from . import relevance_cache
from .client import MoltbookClient, MoltbookClientError
from .config import (
    COMMENT_PACING_MAX_SECONDS,
    COMMENT_PACING_MIN_SECONDS,
    FEED_CONTENT_PREVIEW_LEN,
)
from .content import ContentManager
from .dedup import is_promotional, is_repeat_target_for_author
from .llm_functions import (
    generate_internal_note,
    seed_author_name,
)
from .publish import (
    PublishFailure,
    VerificationHandler,
    client_error_guard,
    created_comment_id as _created_comment_id,
    log_published,
    passes_verification,
    verification_of,
)
from .relevance_shadow import (
    CONFIGURATION_REASONS,
    SOURCE_FEED,
    RecordedReading,
    enforce_and_record,
    resolve_enforce,
)
from .session_context import SessionContext

logger = logging.getLogger(__name__)

# Cache TTL for feed: posts don't change quickly
_FEED_CACHE_TTL = 600.0


def read_relevance_gate(
    post_id: str,
    post_text: str,
    threshold: float | None,
    *,
    source: str = SOURCE_FEED,
) -> RecordedReading:
    """The score4 gate for one post's text, and the reading behind it. Never raises.

    The one gate reader: the feed and self-post seed selection (ADR-0043,
    ADR-0113 amendment 2) both come through here, cut at the same
    ``relevance_score4`` *threshold*. First the cross-session cache (RFC-0046
    S38): a hit reuses the remembered *value* and cuts it at today's threshold
    (``resolve_enforce``); it asks no model and writes no relevance row — the
    row of the reading it reuses already holds the value (joined on
    ``post_id`` + ``content_sha256``) — and carries ``cached_at``. Otherwise
    one fresh read and one row naming *source*.

    Only the feed writes the cache (the store's single writer). Seed
    selection reads it but never remembers: it judges the 500-char submolt
    preview while the feed may judge a fuller body, so a seed entry would
    replace the feed's for the same post every session (the S38 re-judging
    back) and turn a later feed sight into a "cross-session hit" that has no
    feed row. Seed selection keeps its own per-session memo instead.
    """
    content_sha = relevance_cache.content_sha256(post_text)
    pin = relevance_cache.relevance_pin()
    cached = relevance_cache.lookup(post_id, content_sha, pin)
    if cached is not None:
        return RecordedReading(
            resolve_enforce(cached.decision, threshold), cached.decision, cached.judged_at
        )
    reading = enforce_and_record(post_id, post_text, threshold_score4=threshold, source=source)
    # p_top is set only on an ``answered`` read: the one kind kept.
    if source == SOURCE_FEED and reading.p_top is not None:
        relevance_cache.remember(post_id, content_sha, pin, reading.decision)
    return reading


@dataclass(frozen=True)
class _PostJudgment:
    """What this session decided about one post, computed once (RFC-0032).

    ``passed`` is the score4 gate's verdict (RFC-0046: the only relevance
    judgment the feed acts on). Only a passed post costs anything more: the
    full-body fetch, the pre-action note, the upvote and the comment path all
    follow the gate, so ``post_text`` is the full body and ``note`` the
    reflection only when ``passed``. ``p_top`` is the P(directly on-topic) the
    gate cut, kept for the logs and the comment episode.

    ``fail_closed_reason`` is set when the gate had no answer to cut (the
    record row's ``enforce_reason``): then ``passed`` is False, nothing is
    engaged, and the judgment is never memoized — the next cycle asks again.
    ``post_level_failure`` says that failure came from this post's text alone
    (the feed then skips the post instead of ending the cycle).
    """

    passed: bool
    p_top: float | None
    post_text: str
    note: str
    fail_closed_reason: str | None = None
    post_level_failure: bool = False


def _fmt_p(p_top: float | None) -> str:
    return "n/a" if p_top is None else f"{p_top:.2f}"


def _extend_unseen(posts: list[dict], seen_ids: set[str], incoming: Iterable[dict]) -> None:
    """Append the posts carrying an id not seen yet, in arrival order."""
    for post in incoming:
        pid = post.get("id", "")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            posts.append(post)


class FeedManager:
    """Fetches feeds, scores relevance, and engages with posts.

    Handles the feed → score → comment/upvote pipeline, with
    multi-source feed aggregation (following, submolts, search).
    """

    def __init__(
        self,
        ctx: SessionContext,
        domain: DomainConfig,
        get_content: Callable[[], ContentManager],
        confirm_action: Callable[[str, str], bool],
        confirm_side_effect: Callable[[str], bool],
        handle_verification: VerificationHandler,
    ) -> None:
        self._ctx = ctx
        self._domain = domain
        self._get_content = get_content
        self._confirm_action = confirm_action
        self._confirm_side_effect = confirm_side_effect
        self._handle_verification = handle_verification
        self._upvoted_posts: set[str] = set()
        self._judged_posts: dict[str, _PostJudgment] = {}
        # RFC-0046: posts whose ``answered`` reading is already in the
        # relevance record, with the gate outcome that row carries. The
        # judgment memo only keeps *settled* judgments (a preview fallback or
        # an empty note is retried next cycle), so it cannot be the
        # once-per-post guard for the record on its own; reusing the reading
        # keeps the outcome that acts on a retry the one the row says acted,
        # without asking again.
        self._relevance_recorded: dict[str, RecordedReading] = {}
        # The fail-closed reason of the post just judged; run_cycle ends the
        # cycle on it (RFC-0046 cleanup 2: no answer, no engagement this cycle).
        self._fail_closed_reason: str | None = None
        # Configuration-level fail-closed reasons already warned about: the
        # cause is the same for every post, so it is said once per session.
        self._fail_closed_warned: set[str] = set()
        self._rejudges_skipped = 0
        self._relevance_cache_hits = 0
        # RFC-0046 S38: posts whose relevance this session already resolved,
        # freshly or from the cache — so a hit is counted and logged once per
        # post, and only when the reading came from an earlier session (an
        # unsettled judgment comes back every cycle and hits the entry this
        # session just wrote).
        self._relevance_resolved: set[str] = set()
        self._cached_feed: list[dict] = []
        self._feed_fetched_at: float = 0.0

    @property
    def rejudges_skipped(self) -> int:
        """How many re-judgements the session memo avoided (RFC-0032).

        Read by the session-end episode: the skip has no log file of its own,
        so this counter is the audit surface for "the judgment was reused".
        """
        return self._rejudges_skipped

    @property
    def relevance_cache_hits(self) -> int:
        """How many posts this session took their relevance reading from an earlier one.

        RFC-0046 S38: counted once per post, on its first sight this session.
        A hit asks neither model and writes no relevance row, so this counter
        (read by the session-end episode) and the INFO line with reason code
        ``relevance_cached`` are its audit surface.
        """
        return self._relevance_cache_hits

    # ------------------------------------------------------------------
    # Feed fetching
    # ------------------------------------------------------------------

    def fetch_feed(self, client: MoltbookClient) -> list[dict]:
        """Fetch recent posts from subscribed submolt feeds."""
        seen_ids: set[str] = set()
        posts: list[dict] = []
        for submolt in self._domain.subscribed_submolts:
            try:
                _extend_unseen(posts, seen_ids, client.get_submolt_feed(submolt))
            except MoltbookClientError as exc:
                logger.warning("Failed to fetch feed for %s: %s", submolt, exc)
        logger.debug(
            "Fetched %d posts from %d submolt feeds",
            len(posts),
            len(self._domain.subscribed_submolts),
        )
        return posts

    def get_feed(
        self,
        client: MoltbookClient,
        max_age: float = _FEED_CACHE_TTL,
    ) -> list[dict]:
        """Return cached feed if fresh, otherwise fetch anew."""
        if time.time() - self._feed_fetched_at < max_age and self._cached_feed:
            return self._cached_feed
        self._cached_feed = self.fetch_feed(client)
        self._feed_fetched_at = time.time()
        return self._cached_feed

    # ------------------------------------------------------------------
    # Feed cycle
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Fetch from multiple sources and engage with posts.

        Sources (in priority order):
        1. Following feed (1 GET, skipped when the read budget is low)
        2. Submolt feeds (cached)

        Content verification (math challenge) is handled at create time inside
        the comment path (``_post_comment_and_record``), not here: the current
        API returns the challenge in the create-response, never as a
        ``verification_challenge`` field on a fetched feed post.
        """
        if circuit_reading().is_open:
            # Entry guard, before the two source fetches: engagement is gated
            # on the score4 read, which answers ``circuit_open`` while the
            # breaker is open, so every post the fetches pay for would fail
            # closed. The loop below carries the same reading for a breaker
            # that opens mid-scan (T-FEED-PACING).
            logger.info("Circuit breaker open, skipping feed cycle")
            return

        self._fail_closed_reason = None
        for post in self._gather_feed_posts(client):
            if time.time() >= end_time or self._ctx.is_rate_limited:
                break
            if not client.has_read_budget():
                logger.info("Read budget low, pausing feed engagement")
                break
            # The relevance read is this loop's pacer, and an open breaker
            # makes it answer ``circuit_open`` in microseconds — a fail-closed
            # outcome, so nothing downstream fires (no full-body fetch, no
            # note, no upvote). The break forfeits no work, and the posts
            # carry to the next cycle as the read-budget break above already
            # lets them. Same line and same reasoning as the reply cycle's
            # guard column; see reply_handler.run_cycle for the incident this
            # repairs (T-REPLY-PACING / T-FEED-PACING).
            if circuit_reading().is_open:
                logger.info("Circuit breaker open, pausing feed engagement")
                break
            self.engage_with_post(post, client, scheduler)
            # RFC-0046 cleanup 2 (fail-closed): a gate with no answer engages
            # with nothing this cycle. The decision read never writes the
            # breaker, so an Ollama outage would otherwise cost one timeout
            # per remaining post; the posts carry to the next cycle unmemoized.
            # A failure tied to one post's text does not set the flag
            # (``_fail_closed``): that post is skipped and the scan goes on.
            if self._fail_closed_reason is not None:
                logger.info(
                    "Relevance gate fail_closed (%s), ending this feed cycle",
                    self._fail_closed_reason,
                )
                break

    def _gather_feed_posts(self, client: MoltbookClient) -> list[dict]:
        """Both sources, deduplicated by post id, following feed first.

        The following feed is skipped entirely when the read budget is low —
        it costs a GET, while the submolt feed is served from cache.
        """
        seen_ids: set[str] = set()
        all_posts: list[dict] = []

        # Source 1: Following feed
        if client.has_read_budget():
            _extend_unseen(all_posts, seen_ids, client.get_following_feed(limit=25))

        # Source 2: Submolt feeds (cached)
        _extend_unseen(all_posts, seen_ids, self.get_feed(client))
        return all_posts

    # ------------------------------------------------------------------
    # Post engagement
    # ------------------------------------------------------------------

    def engage_with_post(
        self,
        post: dict,
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> bool:
        """Score and potentially comment on a post."""
        post_text = post.get("content", "")
        post_id = post.get("id", "")
        author = post.get("author") or {}
        author_id = author.get("id", "")
        # Live feed posts carry author.name but typically not author.id, so the
        # per-author history gates key on the name (the reliable field).
        author_name = seed_author_name(post)
        if (
            not post_text
            or not post_id
            or not self._passes_engagement_gates(post, post_text, post_id, author_id, author_name)
        ):
            return False

        judgment = self._judge_post(post_text, post_id, client)
        p_top, post_text, note = judgment.p_top, judgment.post_text, judgment.note
        if judgment.fail_closed_reason is not None:
            self._fail_closed(
                post_id, judgment.fail_closed_reason, end_cycle=not judgment.post_level_failure
            )
            return False
        # RFC-0046 cleanup 2: the score4 gate is the only relevance judgment.
        # A closed post gets nothing — no upvote, no note, no full-body GET
        # (the upvote-only band below the comment gate was, by Jev's labels,
        # almost all off-topic: S35 2 of 67 rows, S36 0 of 71).
        if not judgment.passed:
            # INFO so every verdict lands in production logs, not only the
            # passing tail (censored-distribution trap).
            logger.info("Post %s score4 gate closed (P(top) %s)", post_id[:12], _fmt_p(p_top))
            return False
        logger.info("Post %s score4 gate passed (P(top) %s)", post_id[:12], _fmt_p(p_top))

        self._upvote_relevant(post_id, p_top, note, client)

        if not scheduler.can_comment():
            logger.info("Comment rate limit reached")
            return False

        # post_text carries whatever the fetch in _judge_post produced for this
        # passed post, so no second GET belongs here. It is the full body when
        # the fetch got one; a preview-length body means it fell back (read
        # budget low, or nothing longer came back) and that judgment is not
        # memoized — the same case _judge_post guards against freezing. That
        # single earlier fetch is the only source, so the public comment and
        # the recorded original_post use its result as-is.
        generated = self._get_content().create_comment(post_text)
        comment = generated.text
        if comment is None:
            return False

        if not self._confirm_action(
            f"Comment on post {post_id} (relevance P(top): {_fmt_p(p_top)})", comment
        ):
            record_publish_outcome(
                generated.selection_id, comment_id=None, publish_status=PUBLISH_DECLINED
            )
            return False

        scheduler.wait_for_comment()
        return self._post_comment_and_record(
            post,
            post_id,
            post_text,
            p_top,
            note,
            comment,
            generated.thinking,
            client,
            scheduler,
            selection_id=generated.selection_id,
        )

    def _judge_post(
        self,
        post_text: str,
        post_id: str,
        client: MoltbookClient,
    ) -> _PostJudgment:
        """Gate / full body / note for this post — computed once per session.

        The submolt feed cache (``_FEED_CACHE_TTL``, 600s) outlives the cycle
        wait (``base_cycle_wait``, 60s) by ~10x, so the same post dict reaches
        ``engage_with_post`` about ten times. Only the *actions* were
        deduplicated (``_upvoted_posts`` / ``commented_posts``); the
        *judgments* were recomputed every cycle and thrown away — up to two
        Ollama calls and a GET against the 60/min read quota per repeat. Post
        bodies do not change, so the memo asks the same question of the same
        text (RFC-0032; the author decided the repeat series is a bug, not an
        observation, so nothing records the discarded re-judgements).

        Only *settled* judgments — every part a real answer — are memoized: a
        memoized failure would never be retried, and the next cycle is what
        recovers from one. A fail-closed gate (no answer) is never settled.
        """
        cached = self._judged_posts.get(post_id)
        if cached is not None:
            self._rejudges_skipped += 1
            logger.info(
                "Post %s already_judged this session, reusing P(top) %s",
                post_id[:12],
                _fmt_p(cached.p_top),
            )
            return cached

        reading = self._read_relevance(post_text, post_id)
        outcome = reading.outcome
        if outcome.enforce_gate is None:
            return _PostJudgment(
                False,
                reading.p_top,
                post_text,
                "",
                fail_closed_reason=outcome.enforce_reason,
                post_level_failure=reading.post_level_failure,
            )
        if not outcome.enforce_gate:
            return self._remember(
                post_id, _PostJudgment(False, reading.p_top, post_text, ""), settled=True
            )

        # Fetch the full body BEFORE we read the post for real, for the note
        # and the comment. The gate runs on every post and stays on the
        # 500-char submolt preview, but the note and the comment must read the
        # whole post: a mid-word preview cut was read by the note's
        # contemplative register as a deliberate pause rather than clipping,
        # and wrap_untrusted_content labelled the 500-char preview "complete"
        # because it is under max_input (weekly-2026-06-21 F1.1).
        # Following-feed posts are already full (len != preview), so this is a
        # no-op then; it also respects the read budget.
        full_text = self._fetch_full_if_truncated(post_id, post_text, client)
        # A preview-length body means the fetch fell back (read budget low, or
        # nothing longer came back), not that the full body arrived — memoizing
        # it would hand the comment path a mid-word 500-char preview on a later
        # cycle, the exact failure the comment above records.
        settled = len(full_text) != FEED_CONTENT_PREVIEW_LEN
        # Pre-action reflection (ADR-0045): note what we noticed reading this
        # post before acting. Generated once per passed post and shared across
        # the upvote/comment episodes below. A separate, single-responsibility
        # LLM call — not piggybacked on the relevance read. Returns "" on
        # failure, which is likewise not worth freezing.
        note = generate_internal_note(full_text)
        settled = settled and note != ""
        return self._remember(post_id, _PostJudgment(True, reading.p_top, full_text, note), settled)

    def _read_relevance(self, post_text: str, post_id: str) -> RecordedReading:
        """The score4 reading for this text, and the gate outcome it gives.

        ``read_relevance_gate`` does the reading (cache first, RFC-0046 S38: a
        post the gate dropped is never marked commented, so it came back and
        was scored again every session it stayed in the feed — and near the
        cut a re-score flipped the verdict). This adds the session's
        bookkeeping: the cache-hit count, and a per-session memo of answered
        reads for when the cache is off. One row per post per session once it
        is answered; every failed reading (an abstain, a breaker) is its own
        event and row.
        """
        first_this_session = post_id not in self._relevance_resolved
        self._relevance_resolved.add(post_id)
        memo = self._relevance_recorded.get(post_id)
        if memo is not None:
            return memo
        reading = read_relevance_gate(post_id, post_text, self._domain.relevance_threshold_score4)
        if reading.cached_at is not None:
            # A later sight this session (an unsettled judgment retried) reuses
            # it too, but is neither a cross-session reuse nor news.
            if first_this_session:
                self._relevance_cache_hits += 1
                logger.info(
                    "Post %s relevance_cached (judged %s), reusing P(top) %s",
                    post_id[:12],
                    reading.cached_at,
                    _fmt_p(reading.p_top),
                )
            return reading
        if reading.p_top is not None:
            self._relevance_recorded[post_id] = reading
        return reading

    def _fail_closed(self, post_id: str, reason: str, *, end_cycle: bool) -> None:
        """Log one fail-closed post, and flag the cycle to end (RFC-0046 cleanup 2).

        The reason is the record row's ``enforce_reason``. *end_cycle* is
        False only for a failure tied to this post's text
        (``POST_LEVEL_DECISION_REASONS``): ending the cycle on it would starve
        every later post for as long as it stays in the feed, so the feed
        skips it and goes on; it is asked again next cycle. A configuration
        reason (``DECISION_ENFORCE`` lacks ``relevance``, no
        ``relevance_score4`` threshold) closes every post for the whole
        session, so it is also one WARNING per session — the feed engaging
        with nothing must not pass as a quiet feed.
        """
        if end_cycle:
            self._fail_closed_reason = reason
        logger.info(
            "Post %s score4 gate fail_closed (%s%s)",
            post_id[:12],
            reason,
            "" if end_cycle else ", post-level: skipped",
        )
        if reason in CONFIGURATION_REASONS and reason not in self._fail_closed_warned:
            self._fail_closed_warned.add(reason)
            logger.warning(
                "Relevance gate fails closed (%s): the feed engages with no post this "
                "session — set DECISION_ENFORCE=relevance and thresholds.relevance_score4",
                reason,
            )

    def _remember(self, post_id: str, judgment: _PostJudgment, settled: bool) -> _PostJudgment:
        """Memoize *judgment* when every part of it is a real answer.

        Same lifetime as ``_upvoted_posts``: per-session, never persisted. An
        unsettled judgment is returned but not stored, so the next cycle
        recomputes it exactly as it did before the memo existed — failure
        recovery stays on the cycle, where it already was.
        """
        if settled:
            self._judged_posts[post_id] = judgment
        return judgment

    def _passes_engagement_gates(
        self,
        post: dict,
        post_text: str,
        post_id: str,
        author_id: str,
        author_name: str,
    ) -> bool:
        """Run the skip-gate chain; True when the post may be engaged.

        Gate order is load-bearing (cheap static checks before memory
        lookups); this method is the only place the order is written down.
        """
        return self._passes_content_gates(
            post, post_text, post_id, author_id, author_name
        ) and self._passes_author_history_gates(author_name, post_text, post_id)

    def _passes_content_gates(
        self,
        post: dict,
        post_text: str,
        post_id: str,
        author_id: str,
        author_name: str,
    ) -> bool:
        """Static gates: promo, own post, ID format, submolt, already-commented."""
        ctx = self._ctx

        # Promotional content gate: defanged URLs and explicit CTAs.
        # Conservative regex — see dedup._PROMO_RE. Catches inbed.ai /
        # agentflex.vip class spam that the LLM relevance scorer treats as
        # genuine philosophical inquiry.
        if is_promotional(post_text):
            logger.info("Skipped promotional post: %s", post_id[:12])
            return False

        # Skip our own posts — keyed on name (live feed lacks author.id,
        # ADR-0055 precedent); id compare retained as belt-and-braces.
        if ctx.is_self(author_id, author_name):
            logger.debug("Skipped own post %s", post_id[:12])
            return False

        # Validate post_id to prevent path traversal
        if not VALID_ID_PATTERN.match(post_id):
            logger.warning("Invalid post_id format: %s", post_id[:50])
            return False

        # Skip posts from submolts we're not subscribed to
        post_submolt = post.get("submolt_name", "")
        if post_submolt and post_submolt not in self._domain.subscribed_submolts:
            logger.debug(
                "Post %s in submolt %r not in subscribed list, skipping",
                post_id[:12],
                post_submolt,
            )
            return False

        # Skip posts we already commented on (session + cross-session)
        if post_id in ctx.commented_posts or ctx.memory.has_commented_on(post_id):
            logger.debug("Already commented on %s, skipping", post_id[:12])
            return False

        return True

    def _passes_author_history_gates(self, author_name: str, post_text: str, post_id: str) -> bool:
        """Memory-backed gates: per-author 24h limit, same-author repeat topic.

        Keyed on the author *name*: live feed posts carry author.name but not
        author.id, so the previous id-keyed version of these gates never fired.

        Accepted risk (bug-audit 2026-07-06 M6): two distinct agents sharing
        a display name merge into one history bucket, so a prolific "Aria"
        can rate-limit an unrelated "Aria". Structurally unfixable at this
        layer until the feed carries author ids; the skip logs below name the
        author so a collision is at least attributable post-hoc.
        """
        ctx = self._ctx

        # Skip gating when the counterparty is unknown — otherwise every
        # unattributed post would collapse into a single bucket and over-gate.
        if not author_name or author_name == "unknown":
            return True

        # Per-author 24h rate limit: prevent the '15 replies to the same
        # linguistics post' phenomenon. The same author flooding the feed
        # with template-generated content (or genuine reposts) gets engaged
        # at most 3 times per 24h regardless of relevance score.
        # First of the two because it reads the in-memory interaction list,
        # while the repeat-topic gate below re-parses 7 days of episode JSONL
        # — the cheap-before-expensive order this chain documents.
        if ctx.memory.count_recent_comments_by_author(author_name, hours=24) >= 3:
            logger.info(
                "Skipped post %s: author %s rate-limited (3+ comments/24h)",
                post_id[:12],
                log_safe_identifier(author_name),
            )
            return False

        # Same-author repeat-topic gate: even if the post_id is new and the
        # 24h count is under 3, an author that paraphrases the same thesis
        # across many posts (the 30+ Armenian-linguistics replays in the
        # 2026-04-12 weekly report) will trigger this. Body Jaccard against
        # the past 7 days of original_post bodies we commented on for this
        # author.
        prior_targets = ctx.memory.get_prior_comment_targets(author_name, days=7, limit=7)
        if prior_targets:
            is_repeat, sim = is_repeat_target_for_author(post_text, prior_targets)
            if is_repeat:
                logger.info(
                    "Skipped post %s: same-author repeat topic (jaccard=%.2f)",
                    post_id[:12],
                    sim,
                )
                return False

        return True

    def _upvote_relevant(
        self, post_id: str, p_top: float | None, note: str, client: MoltbookClient
    ) -> None:
        """Confirm + upvote + record the canonical "activity"/"upvote" episode.

        Only a post the score4 gate passed reaches here, whether or not it is
        then commented on (RFC-0046 cleanup 2 removed the upvote-only band
        below the gate).
        """
        if (
            post_id not in self._upvoted_posts
            and client.has_write_budget()
            and self._confirm_side_effect(f"Upvote post {post_id}")
            and client.upvote_post(post_id)
        ):
            self._upvoted_posts.add(post_id)
            self._ctx.memory.episodes.append(
                "activity",
                {
                    "action": "upvote",
                    "post_id": post_id,
                    "internal_note": note,
                },
            )
            logger.info("Upvoted post %s (P(top) %s)", post_id[:12], _fmt_p(p_top))

    def _post_comment_and_record(
        self,
        post: dict,
        post_id: str,
        post_text: str,
        p_top: float | None,
        note: str,
        comment: str,
        thinking: str | None,
        client: MoltbookClient,
        scheduler: Scheduler,
        *,
        selection_id: str | None = None,
    ) -> bool:
        """Post the comment, record it in memory/episodes, and pace.

        ``thinking`` is the reasoning trace (None unless the comment was
        generated with ``think=True``); recorded alongside ``internal_note``
        on the episode for later inspection (comment report), never published.

        ``p_top`` is the gate's P(directly on-topic). The episode carries it as
        ``relevance_p_top`` and writes no ``relevance`` key: that key held the
        free-generated 0-1 score up to 2026-10-07, a different scale, and the
        longitudinal record must not change a key's scale silently (RFC-0046
        cleanup 2, g2).

        ``selection_id`` names the selection record this comment's generation
        ran under (RFC-0028). Every exit below records an outcome for it —
        published with an id, published with no usable id, unverified, or
        failed — so the reading can tell those four apart instead of reading
        the last three as one silence.
        """
        ctx = self._ctx
        posted = False
        publish_status = PUBLISH_FAILED
        published_comment_id: str | None = None
        recorded = False
        # Appended by the guard when the write raised; read by the fallback row
        # below, which is the only exit that can see the swallowed error
        # (RFC-0029). A list because the guard's callback cannot rebind a local.
        failures: list[PublishFailure] = []
        with client_error_guard(
            f"comment on {post_id[:12]}",
            on_rate_limited=ctx.set_rate_limited,
            on_failure=failures.append,
        ):
            # post_comment verifies the response envelope (audit H2): a
            # body-level failure raises and never reaches the records below.
            created = client.post_comment(post_id, comment)
            scheduler.record_comment()
            published_comment_id = _created_comment_id(created)
            publish_status = PUBLISH_PUBLISHED if published_comment_id else PUBLISH_ID_UNKNOWN
            if not passes_verification(
                verification_of(created),
                self._handle_verification,
                description=f"Comment on {post_id[:12]}",
                action="comment",
                target_id=post_id,
            ):
                record_publish_outcome(
                    selection_id,
                    comment_id=published_comment_id,
                    publish_status=PUBLISH_UNVERIFIED,
                )
                recorded = True
                return False
            # Recorded here, not after the pacing sleep below: the comment is
            # live on the platform from this point, and a session killed
            # during that sleep would otherwise lose the selection→comment
            # link for a comment that exists (code review 2026-09-09).
            record_publish_outcome(
                selection_id,
                comment_id=published_comment_id,
                publish_status=publish_status,
            )
            recorded = True
            # Record the dedup hash only now that the comment is actually posted
            # AND visible (verified) — a gate-rejected, failed, or unverified
            # comment must not poison a legitimate same-session retry.
            self._get_content().mark_posted(comment)
            ctx.commented_posts.add(post_id)
            ctx.memory.record_commented(post_id)
            ctx.actions_taken.append(f"Commented on {post_id} (relevance P(top): {_fmt_p(p_top)})")
            # Preview only: full bodies in *.log become anomaly-sweep noise
            # and cross the self-written-log trust boundary (F1.1 2026-07-11).
            # Canonical full text: episode log below + comment-reports. No
            # full-body log path remains at any level — the DEBUG branch that
            # produced one is gone, parameters included (T-LOG-DEBUG-CONTENT);
            # tests/test_publish_logging.py is what holds that now.
            log_published(
                ">> Comment on %s: %d chars: %s",
                post_id[:12],
                body=comment,
            )
            author = post.get("author") or {}
            # Live feed posts carry author.name but typically not author.id
            # (the codebase originally assumed both). The name is the reliable
            # counterparty key, so write it as target_agent — symmetric with
            # the reply path — and keep target_agent_id when an id is present.
            agent_name = seed_author_name(post) or "unknown"
            agent_id = (
                author.get("id") or post.get("author_id") or post.get("authorId") or "unknown"
            )
            ctx.memory.episodes.append(
                "activity",
                {
                    "action": "comment",
                    "post_id": post_id,
                    "content": comment,
                    "original_post": post_text,
                    "relevance_p_top": round(p_top, 4) if p_top is not None else None,
                    "target_agent": agent_name,
                    "target_agent_id": agent_id,
                    "internal_note": note,
                    "thinking": thinking,
                },
            )
            ctx.memory.record_interaction(
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent_id=agent_id,
                agent_name=agent_name,
                post_id=post_id,
                direction="sent",
                content=comment,
                interaction_type="comment",
            )
            # Pacing: random wait before next engagement
            extra_wait = random.uniform(COMMENT_PACING_MIN_SECONDS, COMMENT_PACING_MAX_SECONDS)
            logger.info("Pacing: waiting %.0fs before next engagement", extra_wait)
            time.sleep(extra_wait)
            posted = True
        if not recorded:
            # Reached only when the guard swallowed a client error: the
            # default PUBLISH_FAILED is what says the generation never
            # reached the platform.
            # Reason columns on the failed row only, like PublishOutcome._record:
            # a row saying "published" and carrying a failure reason is one the
            # reading can read two ways (ADR-0106 D3).
            failure = failures[0] if failures and publish_status == PUBLISH_FAILED else None
            record_publish_outcome(
                selection_id,
                comment_id=published_comment_id,
                publish_status=publish_status,
                http_status=failure.http_status if failure else None,
                failure_reason=failure.failure_reason if failure else None,
            )
        return posted

    def _fetch_full_if_truncated(self, post_id: str, post_text: str, client: MoltbookClient) -> str:
        """Return the full post body when ``post_text`` looks truncated.

        Submolt feeds clamp ``content`` to ``FEED_CONTENT_PREVIEW_LEN`` chars;
        a body of exactly that length is a truncation candidate. Falls back to
        the preview when read budget is low or the fetch yields nothing longer,
        so engagement never stalls on this.
        """
        if len(post_text) != FEED_CONTENT_PREVIEW_LEN:
            return post_text  # already full, or genuinely short
        if not client.has_read_budget():
            return post_text  # budget low — keep the preview
        full = client.get_post(post_id)
        if full:
            full_text = full.get("content", "")
            if len(full_text) > len(post_text):
                return full_text
        return post_text

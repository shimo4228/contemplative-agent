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
from .client import MoltbookClient, MoltbookClientError
from .config import (
    ADAPTIVE_BACKOFF,
    COMMENT_PACING_MAX_SECONDS,
    COMMENT_PACING_MIN_SECONDS,
    FEED_CONTENT_PREVIEW_LEN,
)
from .content import ContentManager
from .dedup import is_promotional, is_repeat_target_for_author
from .llm_functions import generate_internal_note, score_relevance_detailed, seed_author_name
from .publish import (
    PublishFailure,
    VerificationHandler,
    client_error_guard,
    created_comment_id as _created_comment_id,
    log_published,
    passes_verification,
    verification_of,
)
from .session_context import SessionContext

logger = logging.getLogger(__name__)

# Cache TTL for feed: posts don't change quickly
_FEED_CACHE_TTL = 600.0


@dataclass(frozen=True)
class _PostJudgment:
    """What this session decided about one post, computed once (RFC-0032).

    ``engaged`` records whether the engage bar was cleared when the judgment
    was taken: ``post_text`` is the full body and ``note`` the pre-action
    reflection only then. The bar is ``min(upvote_only_threshold, threshold)``
    and ``threshold`` drops once we have interacted with the author, so a
    judgment taken below the bar can still need its body and note later — the
    score never needs recomputing.
    """

    score: float
    post_text: str
    note: str
    engaged: bool


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
        self._rejudges_skipped = 0
        self._cached_feed: list[dict] = []
        self._feed_fetched_at: float = 0.0

    @property
    def rejudges_skipped(self) -> int:
        """How many re-judgements the session memo avoided (RFC-0032).

        Read by the session-end episode: the skip has no log file of its own,
        so this counter is the audit surface for "the judgment was reused".
        """
        return self._rejudges_skipped

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
            # on score_relevance, so an open breaker means every post the
            # fetches pay for would be scored 0.0 and skipped. The loop below
            # carries the same reading for a breaker that opens mid-scan
            # (T-FEED-PACING).
            logger.info("Circuit breaker open, skipping feed cycle")
            return

        for post in self._gather_feed_posts(client):
            if time.time() >= end_time or self._ctx.is_rate_limited:
                break
            if not client.has_read_budget():
                logger.info("Read budget low, pausing feed engagement")
                break
            # score_relevance was this loop's only pacer, and an open breaker
            # returns its 0.0 sentinel in microseconds. That 0.0 is below
            # upvote_only_threshold, so nothing downstream fires either (no
            # full-body fetch, no note, no upvote) — the break forfeits no
            # work, and the posts carry to the next cycle as the read-budget
            # break above already lets them. Same line and same reasoning as
            # the reply cycle's guard column; see reply_handler.run_cycle for
            # the incident this repairs (T-REPLY-PACING / T-FEED-PACING).
            if circuit_reading().is_open:
                logger.info("Circuit breaker open, pausing feed engagement")
                break
            self.engage_with_post(post, client, scheduler)

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

        threshold = self._relevance_threshold(author_id)
        judgment = self._judge_post(post, post_text, post_id, threshold, client)
        score, post_text, note = judgment.score, judgment.post_text, judgment.note
        if score < threshold:
            self._handle_below_threshold(post_id, score, threshold, note, client)
            return False
        logger.info(
            "Post %s relevance %.2f passed threshold %.2f",
            post_id[:12],
            score,
            threshold,
        )

        self._upvote_relevant(post_id, score, note, client)

        if not scheduler.can_comment():
            logger.info("Comment rate limit reached")
            return False

        # post_text carries whatever the engage-bar fetch above produced: that
        # fetch runs whenever score clears min(upvote_only_threshold,
        # threshold), and the comment path is only reached when score >=
        # threshold (>= that bar), so no second GET belongs here. It is the
        # full body when the fetch got one; a preview-length body means it fell
        # back (read budget low, or nothing longer came back) and that judgment
        # is not memoized — the same case _judge_post guards against freezing.
        # That single earlier fetch is the only source, so the public comment
        # and the recorded original_post use its result as-is.
        generated = self._get_content().create_comment(post_text)
        comment = generated.text
        if comment is None:
            return False

        if not self._confirm_action(f"Comment on post {post_id} (relevance: {score:.2f})", comment):
            record_publish_outcome(
                generated.selection_id, comment_id=None, publish_status=PUBLISH_DECLINED
            )
            return False

        scheduler.wait_for_comment()
        return self._post_comment_and_record(
            post,
            post_id,
            post_text,
            score,
            note,
            comment,
            generated.thinking,
            client,
            scheduler,
            selection_id=generated.selection_id,
        )

    def _judge_post(
        self,
        post: dict,
        post_text: str,
        post_id: str,
        threshold: float,
        client: MoltbookClient,
    ) -> _PostJudgment:
        """Score / full body / note for this post — computed once per session.

        The submolt feed cache (``_FEED_CACHE_TTL``, 600s) outlives the cycle
        wait (``base_cycle_wait``, 60s) by ~10x, so the same post dict reaches
        ``engage_with_post`` about ten times. Only the *actions* were
        deduplicated (``_upvoted_posts`` / ``commented_posts``); the
        *judgments* were recomputed every cycle and thrown away — up to two
        Ollama calls and a GET against the 60/min read quota per repeat. Post
        bodies do not change, so the memo asks the same question of the same
        text (RFC-0032; the author decided the repeat series is a bug, not an
        observation, so nothing records the discarded re-judgements).
        """
        engage_bar = min(ADAPTIVE_BACKOFF.upvote_only_threshold, threshold)
        cached = self._judged_posts.get(post_id)
        if cached is not None and (cached.engaged or cached.score < engage_bar):
            self._rejudges_skipped += 1
            logger.info(
                "Post %s already_judged this session, reusing relevance %.2f",
                post_id[:12],
                cached.score,
            )
            return cached

        # Either first sight, or the engage bar dropped under a score we had
        # already taken (the author became known) — re-scoring would ask the
        # same question of the same text, so only the bar-gated half reruns.
        # ``settled`` carries whether every part below is a real answer: only
        # those are memoized, because a memoized failure would never be retried
        # and the next cycle is what recovers from one today.
        if cached is not None:
            score, settled = cached.score, True
        else:
            reading = score_relevance_detailed(post_text)
            # Four distinct events all return 0.0 and only ``scored`` is a
            # judgment (RelevanceScore's docstring). Freezing an
            # ``llm_unavailable`` 0.0 would blacklist for the whole session
            # every post a transient Ollama stall touched.
            score, settled = reading.score, reading.reason == "scored"
        if score < engage_bar:
            return self._remember(
                post_id, _PostJudgment(score, post_text, "", engaged=False), settled
            )

        # Fetch the full body BEFORE we read the post for real — for the note
        # (score >= upvote_only_threshold) or the comment (score >= threshold),
        # whichever bar is lower. Scoring is a cheap gate that runs on every
        # post and stays on the 500-char submolt preview, but the note and the
        # comment must read the whole post: a mid-word preview cut was read by
        # the note's contemplative register as a deliberate pause rather than
        # clipping, and wrap_untrusted_content labelled the 500-char preview
        # "complete" because it is under max_input (weekly-2026-06-21 F1.1).
        # Following-feed posts are already full (len != preview), so this is a
        # no-op then; it also respects the read budget.
        full_text = self._fetch_full_if_truncated(post, post_text, client)
        # A preview-length body means the fetch fell back (read budget low, or
        # nothing longer came back), not that the full body arrived — memoizing
        # it would hand the comment path a mid-word 500-char preview on a later
        # cycle, the exact failure the comment above records.
        settled = settled and len(full_text) != FEED_CONTENT_PREVIEW_LEN
        # Pre-action reflection (ADR-0045): note what we noticed reading this
        # post before acting. Generated once for any post we may engage with
        # and shared across the upvote/comment episodes below. A separate,
        # single-responsibility LLM call — not piggybacked on the relevance
        # score. Returns "" on failure, which is likewise not worth freezing.
        wants_note = score >= ADAPTIVE_BACKOFF.upvote_only_threshold
        note = generate_internal_note(full_text) if wants_note else ""
        settled = settled and (note != "" or not wants_note)
        return self._remember(post_id, _PostJudgment(score, full_text, note, engaged=True), settled)

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

    def _relevance_threshold(self, author_id: str) -> float:
        """Comment threshold; lower for agents we've previously interacted with."""
        if author_id and self._ctx.memory.has_interacted_with(author_id):
            return self._domain.known_agent_threshold
        return self._domain.relevance_threshold

    def _handle_below_threshold(
        self,
        post_id: str,
        score: float,
        threshold: float,
        note: str,
        client: MoltbookClient,
    ) -> None:
        """Upvote-only for near-threshold posts; log the score otherwise."""
        upvoted = score >= ADAPTIVE_BACKOFF.upvote_only_threshold and self._do_upvote(
            post_id, score, note, client, below_threshold=True
        )
        if not upvoted:
            # INFO so skipped scores land in production logs: the relevance
            # threshold retune (audit fix #2 follow-up) needs the FULL score
            # distribution, not just the passing tail — debug was discarded
            # at the production INFO level (censored-distribution trap).
            logger.info(
                "Post %s relevance %.2f below threshold %.2f",
                post_id[:12],
                score,
                threshold,
            )

    def _upvote_relevant(
        self, post_id: str, score: float, note: str, client: MoltbookClient
    ) -> None:
        """Upvote relevant posts (regardless of whether we comment)."""
        self._do_upvote(post_id, score, note, client, below_threshold=False)

    def _do_upvote(
        self,
        post_id: str,
        score: float,
        note: str,
        client: MoltbookClient,
        *,
        below_threshold: bool,
    ) -> bool:
        """Confirm + upvote + record the canonical "activity"/"upvote" episode.

        Single source of truth for the upvote side-effect shared by
        ``_handle_below_threshold`` and ``_upvote_relevant``. Returns True when
        the budget/dedup/confirm guard passed (the upvote path was entered), so
        ``_handle_below_threshold`` can fall back to its below-threshold score
        log only when the guard was not satisfied — preserving the original
        full-score-distribution logging behaviour.
        """
        if (
            post_id not in self._upvoted_posts
            and client.has_write_budget()
            and self._confirm_side_effect(f"Upvote post {post_id}")
        ):
            if client.upvote_post(post_id):
                self._upvoted_posts.add(post_id)
                self._ctx.memory.episodes.append(
                    "activity",
                    {
                        "action": "upvote",
                        "post_id": post_id,
                        "internal_note": note,
                    },
                )
                suffix = ", below comment threshold" if below_threshold else ""
                logger.info(
                    "Upvoted post %s (relevance: %.2f%s)",
                    post_id[:12],
                    score,
                    suffix,
                )
            return True
        return False

    def _post_comment_and_record(
        self,
        post: dict,
        post_id: str,
        post_text: str,
        score: float,
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
            ctx.actions_taken.append(f"Commented on {post_id} (relevance: {score:.2f})")
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
                    "relevance": f"{score:.2f}",
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

    def _fetch_full_if_truncated(self, post: dict, post_text: str, client: MoltbookClient) -> str:
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
        full = client.get_post(post.get("id", ""))
        if full:
            full_text = full.get("content", "")
            if len(full_text) > len(post_text):
                return full_text
        return post_text

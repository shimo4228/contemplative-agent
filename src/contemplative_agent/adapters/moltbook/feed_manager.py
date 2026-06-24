"""Feed fetching and engagement logic for the Moltbook Agent."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Callable, List, Set

from .client import MoltbookClient, MoltbookClientError
from .config import (
    ADAPTIVE_BACKOFF,
    COMMENT_PACING_MAX_SECONDS,
    COMMENT_PACING_MIN_SECONDS,
    FEED_CONTENT_PREVIEW_LEN,
)
from .content import ContentManager
from .dedup import is_promotional, is_repeat_target_for_author
from .llm_functions import generate_internal_note, score_relevance
from .session_context import SessionContext
from ...core.config import VALID_ID_PATTERN
from ...core.domain import DomainConfig
from ...core.scheduler import Scheduler

logger = logging.getLogger(__name__)

# Cache TTL for feed: posts don't change quickly
_FEED_CACHE_TTL = 600.0


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
    ) -> None:
        self._ctx = ctx
        self._domain = domain
        self._get_content = get_content
        self._confirm_action = confirm_action
        self._confirm_side_effect = confirm_side_effect
        self._upvoted_posts: Set[str] = set()
        self._cached_feed: List[dict] = []
        self._feed_fetched_at: float = 0.0

    # ------------------------------------------------------------------
    # Feed fetching
    # ------------------------------------------------------------------

    def fetch_feed(self, client: MoltbookClient) -> List[dict]:
        """Fetch recent posts from subscribed submolt feeds."""
        seen_ids: set[str] = set()
        posts: List[dict] = []
        for submolt in self._domain.subscribed_submolts:
            try:
                resp = client.get(f"/submolts/{submolt}/feed")
                for post in resp.json().get("posts", []):
                    pid = post.get("id", "")
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        posts.append(post)
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
    ) -> List[dict]:
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
        handle_verification: Callable[[dict], bool],
    ) -> None:
        """Fetch from multiple sources and engage with posts.

        Sources (in priority order):
        1. Following feed (always, 1 GET)
        2. Submolt feeds (cached)
        """
        seen_ids: set[str] = set()
        all_posts: List[dict] = []

        # Source 1: Following feed
        if client.has_read_budget(ADAPTIVE_BACKOFF.read_budget_reserve):
            for post in client.get_following_feed(limit=25):
                pid = post.get("id", "")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_posts.append(post)

        # Source 2: Submolt feeds (cached)
        for post in self.get_feed(client):
            pid = post.get("id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_posts.append(post)

        for post in all_posts:
            if time.time() >= end_time or self._ctx.is_rate_limited:
                break
            if not client.has_read_budget(ADAPTIVE_BACKOFF.read_budget_reserve):
                logger.info("Read budget low, pausing feed engagement")
                break
            challenge = post.get("verification_challenge")
            if challenge:
                handle_verification(challenge)
                continue
            self.engage_with_post(post, client, scheduler)

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
        author_name = (
            author.get("name")
            or post.get("agent_name")
            or post.get("agentName")
            or ""
        )
        if (
            not post_text
            or not post_id
            or not self._passes_engagement_gates(
                post, post_text, post_id, author_id, author_name
            )
        ):
            return False

        score = score_relevance(post_text)
        threshold = self._relevance_threshold(author_id)
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
        engage_bar = min(ADAPTIVE_BACKOFF.upvote_only_threshold, threshold)
        if score >= engage_bar:
            post_text = self._fetch_full_if_truncated(post, post_text, client)
        # Pre-action reflection (ADR-0045): note what we noticed reading this
        # post before acting. Generated once for any post we may engage with
        # and shared across the upvote/comment episodes below. A separate,
        # single-responsibility LLM call — not piggybacked on score_relevance.
        note = (
            generate_internal_note(post_text)
            if score >= ADAPTIVE_BACKOFF.upvote_only_threshold
            else ""
        )
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

        # post_text is already the full body here: the engage-bar fetch above
        # runs whenever score clears min(upvote_only_threshold, threshold), and
        # the comment path is only reached when score >= threshold (>= that
        # bar). The earlier fetch is the single source of the full body, so the
        # public comment and the recorded original_post use it.
        comment = self._get_content().create_comment(post_text)
        if comment is None:
            return False

        if not self._confirm_action(
            f"Comment on post {post_id} (relevance: {score:.2f})", comment
        ):
            return False

        scheduler.wait_for_comment()
        return self._post_comment_and_record(
            post, post_id, post_text, score, note, comment, client, scheduler
        )

    def _passes_engagement_gates(
        self, post: dict, post_text: str, post_id: str, author_id: str,
        author_name: str,
    ) -> bool:
        """Run the skip-gate chain; True when the post may be engaged.

        Gate order is load-bearing (cheap static checks before memory
        lookups) — keep it in sync with the Data Flow section of
        docs/CODEMAPS/architecture.md when it changes.
        """
        return self._passes_content_gates(
            post, post_text, post_id, author_id
        ) and self._passes_author_history_gates(author_name, post_text, post_id)

    def _passes_content_gates(
        self, post: dict, post_text: str, post_id: str, author_id: str
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

        # Skip our own posts
        if ctx.own_agent_id and author_id == ctx.own_agent_id:
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

    def _passes_author_history_gates(
        self, author_name: str, post_text: str, post_id: str
    ) -> bool:
        """Memory-backed gates: same-author repeat topic, per-author 24h limit.

        Keyed on the author *name*: live feed posts carry author.name but not
        author.id, so the previous id-keyed version of these gates never fired.
        """
        ctx = self._ctx

        # Skip gating when the counterparty is unknown — otherwise every
        # unattributed post would collapse into a single bucket and over-gate.
        if not author_name or author_name == "unknown":
            return True

        # Same-author repeat-topic gate: even if the post_id is new and the
        # 24h count is under 3, an author that paraphrases the same thesis
        # across many posts (the 30+ Armenian-linguistics replays in the
        # 2026-04-12 weekly report) will trigger this. Body Jaccard against
        # the past 7 days of original_post bodies we commented on for this
        # author.
        prior_targets = ctx.memory.get_prior_comment_targets(
            author_name, days=7, limit=7
        )
        if prior_targets:
            is_repeat, sim = is_repeat_target_for_author(
                post_text, prior_targets
            )
            if is_repeat:
                logger.info(
                    "Skipped post %s: same-author repeat topic "
                    "(jaccard=%.2f)",
                    post_id[:12], sim,
                )
                return False

        # Per-author 24h rate limit: prevent the '15 replies to the same
        # linguistics post' phenomenon. The same author flooding the feed
        # with template-generated content (or genuine reposts) gets engaged
        # at most 3 times per 24h regardless of relevance score.
        if ctx.memory.count_recent_comments_by_author(
            author_name, hours=24
        ) >= 3:
            logger.info(
                "Skipped post %s: author %s rate-limited (3+ comments/24h)",
                post_id[:12], author_name,
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
        upvoted = (
            score >= ADAPTIVE_BACKOFF.upvote_only_threshold
            and self._do_upvote(
                post_id, score, note, client, below_threshold=True
            )
        )
        if not upvoted:
            # INFO so skipped scores land in production logs: the relevance
            # threshold retune (audit fix #2 follow-up) needs the FULL score
            # distribution, not just the passing tail — debug was discarded
            # at the production INFO level (censored-distribution trap).
            logger.info(
                "Post %s relevance %.2f below threshold %.2f",
                post_id[:12], score, threshold,
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
            and client.has_write_budget(ADAPTIVE_BACKOFF.write_budget_reserve)
            and self._confirm_side_effect(f"Upvote post {post_id}")
        ):
            if client.upvote_post(post_id):
                self._upvoted_posts.add(post_id)
                self._ctx.memory.episodes.append("activity", {
                    "action": "upvote",
                    "post_id": post_id,
                    "internal_note": note,
                })
                suffix = ", below comment threshold" if below_threshold else ""
                logger.info(
                    "Upvoted post %s (relevance: %.2f%s)",
                    post_id[:12], score, suffix,
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
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> bool:
        """Post the comment, record it in memory/episodes, and pace."""
        ctx = self._ctx
        try:
            # post_comment verifies the response envelope (audit H2): a
            # body-level failure raises and never reaches the records below.
            client.post_comment(post_id, comment)
            # Record the dedup hash only now that the comment is actually
            # posted (not at generation time) — a gate-rejected or failed
            # comment must not poison a legitimate same-session retry.
            self._get_content().mark_posted(comment)
            scheduler.record_comment()
            ctx.commented_posts.add(post_id)
            ctx.memory.record_commented(post_id)
            ctx.actions_taken.append(
                f"Commented on {post_id} (relevance: {score:.2f})"
            )
            logger.info(">> Comment on %s:\n%s", post_id[:12], comment)
            author = post.get("author") or {}
            # Live feed posts carry author.name but typically not author.id
            # (the codebase originally assumed both). The name is the reliable
            # counterparty key, so write it as target_agent — symmetric with
            # the reply path — and keep target_agent_id when an id is present.
            agent_name = (
                author.get("name")
                or post.get("agent_name")
                or post.get("agentName")
                or "unknown"
            )
            agent_id = (
                author.get("id")
                or post.get("author_id")
                or post.get("authorId")
                or "unknown"
            )
            ctx.memory.episodes.append("activity", {
                "action": "comment",
                "post_id": post_id,
                "content": comment,
                "original_post": post_text,
                "relevance": f"{score:.2f}",
                "target_agent": agent_name,
                "target_agent_id": agent_id,
                "internal_note": note,
            })
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
            extra_wait = random.uniform(
                COMMENT_PACING_MIN_SECONDS, COMMENT_PACING_MAX_SECONDS
            )
            logger.info(
                "Pacing: waiting %.0fs before next engagement", extra_wait
            )
            time.sleep(extra_wait)
            return True
        except MoltbookClientError as exc:
            logger.error("Failed to comment on %s: %s", post_id[:12], exc)
            if exc.status_code == 429:
                ctx.set_rate_limited()
            return False

    def _fetch_full_if_truncated(
        self, post: dict, post_text: str, client: MoltbookClient
    ) -> str:
        """Return the full post body when ``post_text`` looks truncated.

        Submolt feeds clamp ``content`` to ``FEED_CONTENT_PREVIEW_LEN`` chars;
        a body of exactly that length is a truncation candidate. Falls back to
        the preview when read budget is low or the fetch yields nothing longer,
        so engagement never stalls on this.
        """
        if len(post_text) != FEED_CONTENT_PREVIEW_LEN:
            return post_text  # already full, or genuinely short
        if not client.has_read_budget(ADAPTIVE_BACKOFF.read_budget_reserve):
            return post_text  # budget low — keep the preview
        full = client.get_post(post.get("id", ""))
        if full:
            full_text = full.get("content", "")
            if len(full_text) > len(post_text):
                return full_text
        return post_text

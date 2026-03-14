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
)
from .content import ContentManager
from .llm_functions import score_relevance
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
    ) -> None:
        self._ctx = ctx
        self._domain = domain
        self._get_content = get_content
        self._confirm_action = confirm_action
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
        3. Search (topic_keywords rotation, 1 GET/cycle)
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

        # Source 3: Search with rotating topic keyword
        if (
            client.has_read_budget(ADAPTIVE_BACKOFF.read_budget_reserve)
            and self._domain.topic_keywords
        ):
            keyword = self._domain.topic_keywords[
                int(time.time()) % len(self._domain.topic_keywords)
            ]
            for result in client.search(keyword, search_type="posts", limit=10):
                pid = result.get("id", "") or result.get("post_id", "")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_posts.append(result)

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
        ctx = self._ctx

        post_text = post.get("content", "")
        post_id = post.get("id", "")
        if not post_text or not post_id:
            return False

        # Skip our own posts
        author_id = (post.get("author") or {}).get("id", "")
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
            logger.debug("Already commented on %s, skipping", post_id)
            return False

        score = score_relevance(post_text)
        # Lower threshold for agents we've previously interacted with
        threshold = (
            self._domain.known_agent_threshold
            if author_id and ctx.memory.has_interacted_with(author_id)
            else self._domain.relevance_threshold
        )
        if score < threshold:
            logger.debug(
                "Post %s relevance %.2f below threshold %.2f",
                post_id,
                score,
                threshold,
            )
            return False
        logger.info(
            "Post %s relevance %.2f passed threshold %.2f",
            post_id,
            score,
            threshold,
        )

        # Upvote relevant posts (regardless of whether we comment)
        if (
            post_id not in self._upvoted_posts
            and client.has_write_budget(ADAPTIVE_BACKOFF.write_budget_reserve)
        ):
            if client.upvote_post(post_id):
                self._upvoted_posts.add(post_id)
                ctx.memory.episodes.append("activity", {
                    "action": "upvote",
                    "post_id": post_id,
                })
                logger.info(
                    "Upvoted post %s (relevance: %.2f)", post_id[:12], score
                )

        if not scheduler.can_comment():
            logger.info("Comment rate limit reached")
            return False

        comment = self._get_content().create_comment(post_text)
        if comment is None:
            return False

        if not self._confirm_action(
            f"Comment on post {post_id} (relevance: {score:.2f})", comment
        ):
            return False

        scheduler.wait_for_comment()
        try:
            client.post(
                f"/posts/{post_id}/comments",
                json={"content": comment},
            )
            scheduler.record_comment()
            ctx.commented_posts.add(post_id)
            ctx.memory.record_commented(post_id)
            ctx.actions_taken.append(
                f"Commented on {post_id} (relevance: {score:.2f})"
            )
            logger.info(">> Comment on %s:\n%s", post_id[:12], comment)
            ctx.memory.episodes.append("activity", {
                "action": "comment",
                "post_id": post_id,
                "content": comment[:200],
                "original_post": post_text[:500],
                "relevance": f"{score:.2f}",
            })
            # Record interaction in memory
            author = post.get("author") or {}
            agent_name = author.get("name", "unknown")
            agent_id = author.get("id", "unknown")
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
            logger.error("Failed to comment on %s: %s", post_id, exc)
            if exc.status_code == 429:
                ctx.set_rate_limited()
            return False

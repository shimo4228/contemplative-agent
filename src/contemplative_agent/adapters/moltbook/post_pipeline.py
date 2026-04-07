"""Post generation and session insight pipeline for the Moltbook Agent."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, List

from .client import MoltbookClient, MoltbookClientError
from .config import ADAPTIVE_BACKOFF
from .content import ContentManager, _content_hash
from .dedup import is_duplicate_title, is_test_content
from .llm_functions import (
    check_topic_novelty,
    extract_topics,
    generate_post_title,
    generate_session_insight,
    select_submolt,
    summarize_post_topic,
)
from .session_context import SessionContext
from ...core.config import VALID_SUBMOLT_PATTERN
from ...core.domain import DomainConfig
from ...core.scheduler import Scheduler

logger = logging.getLogger(__name__)


class PostPipeline:
    """Handles dynamic post creation and session insight generation.

    Extracts topics from the feed, checks novelty, generates content,
    selects a submolt, and publishes. Also generates end-of-session insights.
    """

    def __init__(
        self,
        ctx: SessionContext,
        domain: DomainConfig,
        get_content: Callable[[], ContentManager],
        get_feed: Callable[[], List[dict]],
        confirm_action: Callable[[str, str], bool],
    ) -> None:
        self._ctx = ctx
        self._domain = domain
        self._get_content = get_content
        self._get_feed = get_feed
        self._confirm_action = confirm_action

    def run_cycle(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> None:
        """Post new content if rate limit allows."""
        if not scheduler.can_post():
            return
        if not client.has_write_budget(reserve=ADAPTIVE_BACKOFF.write_budget_reserve):
            logger.info("Rate limit budget low, skipping post cycle")
            return
        self._run_dynamic_post(client, scheduler)

    def _run_dynamic_post(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> None:
        """Generate and publish a post based on current feed topics."""
        ctx = self._ctx
        posts = self._get_feed()
        topics = extract_topics(posts)
        if not topics:
            return

        # Check novelty against recent post topic summaries
        recent_topics = ctx.memory.get_recent_post_topics(limit=5)
        if not check_topic_novelty(topics, recent_topics):
            logger.info("Topics not novel enough, skipping post")
            return

        recent_insights = ctx.memory.get_recent_insights(limit=3)
        content = self._get_content().create_cooperation_post(
            topics, recent_insights=recent_insights or None,
        )
        if content is None:
            return

        title = generate_post_title(topics) or f"Contemplative Note — {topics[:40]}"

        # --- Deterministic gates ---
        # These complement (not replace) the LLM-based check_topic_novelty
        # gate above. The LLM gate is too lax in practice — see weekly
        # report 2026-04-05, where 40 near-identical self-posts slipped
        # through over 7 days. The gates here are silent: when blocked we
        # `return` without retry so the agent does not learn to evade them
        # by swapping synonyms.

        # Test-content gate: catches leftover scaffold output like
        # "Test Title" / "Dynamic content" that leaked in Mar 30–31.
        if is_test_content(title, content):
            logger.warning("Blocked test-content self-post: %r", title)
            return

        # Jaccard self-post dedup gate: token-set similarity over
        # (title ∪ topic_summary) against the past ~50 self-posts.
        # draft_summary is reused below at record_post time to avoid a
        # second LLM call on the same content.
        draft_summary = summarize_post_topic(content)
        recent_posts = ctx.memory.get_recent_posts(limit=50)
        is_dup, sim, prior_title = is_duplicate_title(
            title, draft_summary, recent_posts,
        )
        if is_dup:
            # INFO, not WARNING — this is steady-state behavior of the
            # gate (its whole purpose). WARNING is reserved for the
            # test-content gate above, which fires only on anomalies.
            logger.info(
                "Blocked duplicate self-post (jaccard=%.2f vs %r): %r",
                sim, prior_title, title,
            )
            return

        if not self._confirm_action(f"Dynamic Post: {title}", content):
            return

        # Re-check rate limit right before posting (another session may have posted)
        if not scheduler.can_post():
            logger.info("Post rate limit hit after content generation (concurrent session?)")
            return

        selected = select_submolt(content, self._domain.subscribed_submolts)
        if selected and not VALID_SUBMOLT_PATTERN.match(selected):
            logger.warning("select_submolt returned invalid name %r, using default", selected)
            selected = None
        submolt = selected or self._domain.default_submolt

        scheduler.wait_for_post()
        try:
            resp = client.post(
                "/posts",
                json={
                    "title": title,
                    "content": content,
                    "submolt": submolt,
                },
            )
            scheduler.record_post()
            post_id = resp.json().get("id", "")
            if post_id:
                ctx.own_post_ids.add(post_id)
            ctx.actions_taken.append(f"Posted: {title}")
            logger.info(">> New post [%s] (id=%s):\n%s", title, post_id, content)
            ctx.memory.episodes.append("activity", {
                "action": "post", "post_id": post_id,
                "content": content, "title": title,
            })

            # Record post in memory. Reuse draft_summary computed for the
            # dedup gate above instead of calling summarize_post_topic
            # twice on the same content.
            topic_summary = draft_summary or title
            content_hash = _content_hash(content)
            ctx.memory.record_post(
                timestamp=datetime.now(timezone.utc).isoformat(),
                post_id=post_id,
                title=title,
                topic_summary=topic_summary,
                content_hash=content_hash,
            )
        except MoltbookClientError as exc:
            logger.error("Failed to post dynamic content: %s", exc)

    def generate_session_insights(self) -> None:
        """Generate and record insights at the end of a session."""
        ctx = self._ctx
        if not ctx.actions_taken:
            return

        recent_topics = ctx.memory.get_recent_post_topics(limit=5)

        # Check if topics were repetitive among recent posts
        post_actions = [a for a in ctx.actions_taken if a.startswith("Posted:")]
        insight_type = "topic_saturation" if len(post_actions) == 0 else "session_summary"

        observation = generate_session_insight(
            actions=ctx.actions_taken,
            recent_topics=recent_topics,
        )
        if observation:
            ctx.memory.record_insight(
                timestamp=datetime.now(timezone.utc).isoformat(),
                observation=observation,
                insight_type=insight_type,
            )
            logger.info("Session insight recorded: %s", observation)

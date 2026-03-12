"""Notification and reply processing for the Moltbook Agent."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .client import MoltbookClient, MoltbookClientError
from .config import ADAPTIVE_BACKOFF
from .llm_functions import generate_reply
from ...core.config import VALID_ID_PATTERN
from ...core.scheduler import Scheduler

if TYPE_CHECKING:
    from .agent import Agent

logger = logging.getLogger(__name__)

# Notification types that warrant a reply
_REPLY_TYPES = frozenset({
    "reply", "comment",
    "post_comment", "comment_reply",
    "mention",
})


def extract_agent_fields(data: dict) -> dict:
    """Extract agent identity and content fields with API format fallbacks.

    Shared by notification processing and own-post comment handling.
    """
    return {
        "id": (
            data.get("id")
            or data.get("notification_id")
            or data.get("comment_id", "")
        ),
        "content": (
            data.get("content")
            or data.get("body")
            or data.get("text", "")
        ),
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


def extract_notification_fields(notif: dict) -> dict:
    """Extract notification fields with fallback for different API formats."""
    fields = extract_agent_fields(notif)
    fields.update({
        "type": (
            notif.get("type")
            or notif.get("kind")
            or notif.get("event_type", "")
        ),
        "post_id": (
            notif.get("post_id")
            or notif.get("postId")
            or notif.get("relatedPostId")
            or notif.get("target_id", "")
        ),
        "post_content": (
            notif.get("post_content")
            or notif.get("postContent")
            or notif.get("original_content", "")
        ),
    })
    return fields


class ReplyHandler:
    """Handles notification-driven reply cycles for the agent.

    Processes notifications, generates replies, and manages comment
    deduplication across the session.
    """

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    def run_cycle(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Check for and respond to replies on our posts/comments."""
        if not scheduler.can_comment():
            return

        notifications = client.get_notifications()
        logger.debug(
            "Fetched %d notification(s) from API", len(notifications)
        )

        for i, notif in enumerate(notifications):
            logger.debug(
                "Notification[%d] raw: %.200s",
                i,
                json.dumps(notif, ensure_ascii=False, default=str),
            )

            if time.time() >= end_time or self._agent.is_rate_limited:
                break
            if not scheduler.can_comment():
                break
            if not client.has_write_budget(ADAPTIVE_BACKOFF.write_budget_reserve):
                logger.info("Rate limit budget low, pausing reply processing")
                break

            fields = extract_notification_fields(notif)
            notif_type = fields["type"]

            if notif_type not in _REPLY_TYPES:
                logger.debug(
                    "Notification[%d] skipped: type=%r not actionable",
                    i,
                    notif_type,
                )
                continue

            post_id = fields["post_id"]
            if not post_id or not VALID_ID_PATTERN.match(post_id):
                logger.debug(
                    "Notification[%d] skipped: invalid post_id=%r", i, post_id
                )
                continue

            # Skip if already handled this session
            reply_key = f"reply:{post_id}:{fields['id']}"
            if reply_key in self._agent._commented_posts:
                logger.debug(
                    "Notification[%d] skipped: already handled key=%s",
                    i,
                    reply_key,
                )
                continue

            their_content = fields["content"]
            original_post = fields["post_content"]

            # If notification lacks comment body (e.g. post_comment type),
            # fetch comments from the post and process unhandled ones
            if not their_content and post_id:
                logger.debug(
                    "Notification[%d] has no content; fetching comments for %s",
                    i, post_id[:12],
                )
                self._handle_post_comments(
                    client, scheduler, post_id, end_time
                )
                continue

            if not their_content:
                logger.debug("Notification[%d] skipped: empty content", i)
                continue

            replier_id = fields["agent_id"]
            replier_name = fields["agent_name"]

            # Skip our own comments to avoid self-reply loops
            if self._agent._own_agent_id and replier_id == self._agent._own_agent_id:
                logger.debug("Notification[%d] skipped: own comment", i)
                continue

            self._process_reply(
                client=client,
                scheduler=scheduler,
                post_id=post_id,
                reply_key=reply_key,
                their_content=their_content,
                original_post=original_post,
                replier_id=replier_id,
                replier_name=replier_name,
            )

        # Fallback: check comments on our own posts directly
        self.check_own_post_comments(client, scheduler, end_time)

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
    ) -> None:
        """Generate and send a reply to a comment, recording interactions."""
        agent = self._agent
        history = agent._memory.get_history_with(replier_id, limit=5)
        history_summaries = [h.content_summary for h in history]
        knowledge_ctx = agent._memory.knowledge.get_context_string() or None

        reply = generate_reply(
            original_post=original_post,
            their_comment=their_content,
            conversation_history=history_summaries,
            knowledge_context=knowledge_ctx,
        )
        if reply is None:
            return

        if not agent._confirm_action(
            f"Reply to {replier_name} on post {post_id}", reply
        ):
            return

        # Record the incoming comment first (chronological order)
        agent._memory.record_interaction(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_id=replier_id,
            agent_name=replier_name,
            post_id=post_id,
            direction="received",
            content=their_content,
            interaction_type="reply",
        )

        scheduler.wait_for_comment()
        try:
            client.post(
                f"/posts/{post_id}/comments",
                json={"content": reply},
            )
            scheduler.record_comment()
            agent._commented_posts.add(reply_key)
            agent._actions_taken.append(
                f"Replied to {replier_name} on {post_id}"
            )
            logger.info(
                ">> Reply to %s on %s:\n%s", replier_name, post_id[:12], reply
            )
            agent._memory.episodes.append("activity", {
                "action": "reply", "post_id": post_id,
                "content": reply[:200], "target_agent": replier_name,
            })
            agent._memory.record_interaction(
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent_id=replier_id,
                agent_name=replier_name,
                post_id=post_id,
                direction="sent",
                content=reply,
                interaction_type="reply",
            )
            # Upvote their comment as a courtesy
            comment_id = (
                reply_key.split(":")[-1] if reply_key else ""
            )
            if comment_id and comment_id not in ("", "unknown"):
                client.upvote_comment(comment_id)
        except MoltbookClientError as exc:
            logger.error("Failed to reply on %s: %s", post_id, exc)
            if exc.status_code == 429:
                agent.set_rate_limited()

    def _handle_post_comments(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        post_id: str,
        end_time: float,
    ) -> None:
        """Fetch comments on a post and reply to unhandled ones."""
        comments = client.get_post_comments(post_id)
        logger.debug(
            "Post %s has %d comment(s)", post_id[:12], len(comments)
        )

        for comment in comments:
            if time.time() >= end_time or self._agent.is_rate_limited:
                break
            if not scheduler.can_comment():
                break
            if not client.has_write_budget(ADAPTIVE_BACKOFF.write_budget_reserve):
                logger.info("Rate limit budget low, pausing comment processing")
                break

            fields = extract_agent_fields(comment)
            reply_key = f"reply:{post_id}:{fields['id']}"
            if reply_key in self._agent._commented_posts:
                continue

            # Skip our own comments to avoid self-reply loops
            if self._agent._own_agent_id and fields["agent_id"] == self._agent._own_agent_id:
                continue

            if not fields["content"]:
                continue

            self._process_reply(
                client=client,
                scheduler=scheduler,
                post_id=post_id,
                reply_key=reply_key,
                their_content=fields["content"],
                original_post="",
                replier_id=fields["agent_id"],
                replier_name=fields["agent_name"],
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
        the pre-fetched home dashboard data.
        """
        activity = home_data.get("activity_on_your_posts", [])
        if not activity:
            logger.debug("No activity on own posts from /home data")
            return

        for item in activity:
            if time.time() >= end_time or self._agent.is_rate_limited:
                break
            if not scheduler.can_comment():
                break
            if not client.has_write_budget(ADAPTIVE_BACKOFF.write_budget_reserve):
                logger.info("Write budget low, pausing home-based reply processing")
                break

            post_id = item.get("post_id", "")
            if not post_id or not VALID_ID_PATTERN.match(post_id):
                continue

            new_count = item.get("new_notification_count", 0)
            if new_count == 0:
                continue

            # Fetch comments for this post and process unhandled ones
            self._handle_post_comments(client, scheduler, post_id, end_time)

            # Mark notifications as read for this post
            client.mark_notifications_read_by_post(post_id)

    def check_own_post_comments(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Fallback: fetch comments on our own posts and reply to new ones."""
        if not self._agent._own_post_ids:
            logger.debug("No own post IDs tracked; skipping comment check")
            return

        for post_id in list(self._agent._own_post_ids):
            if time.time() >= end_time or self._agent.is_rate_limited:
                break
            if not scheduler.can_comment():
                break
            if not client.has_write_budget(ADAPTIVE_BACKOFF.write_budget_reserve):
                logger.info("Rate limit budget low, pausing own post comment check")
                break

            self._handle_post_comments(client, scheduler, post_id, end_time)

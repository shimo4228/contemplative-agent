"""Notification and reply processing for the Moltbook Agent."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from ...core._io import log_safe_identifier
from ...core.comment_outcomes import ObservedComment, record_comment_outcomes
from ...core.config import VALID_ID_PATTERN
from ...core.llm import circuit_reading
from ...core.scheduler import Scheduler
from ...core.skill_selection import PUBLISH_DECLINED, record_publish_outcome
from .client import MoltbookClient
from .dedup import is_promotional
from .llm_functions import generate_internal_note, generate_reply
from .publish import (
    VerificationHandler,
    client_error_guard,
    created_comment_id as _created_comment_id,
    log_published,
    passes_verification,
    publish_outcome,
    verification_of,
)
from .session_context import SessionContext

logger = logging.getLogger(__name__)

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


class ReplyHandler:
    """Handles notification-driven reply cycles for the agent.

    Processes notifications, generates replies, and manages comment
    deduplication across the session.
    """

    def __init__(
        self,
        ctx: SessionContext,
        confirm_action: Callable[[str, str], bool],
        confirm_side_effect: Callable[[str], bool],
        handle_verification: VerificationHandler,
    ) -> None:
        self._ctx = ctx
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

    def _pause_reason(
        self, client: MoltbookClient, scheduler: Scheduler, end_time: float
    ) -> str | None:
        """Why this scan must stop now, or None to continue.

        One column for the four reply loops, which all broke on the same four
        conditions with four different log wordings. All four are
        side-effect-free and all break, so position within the column is not
        load-bearing (T-REPLY-PACING).

        The breaker break is a break, not a backoff: generation was the loop's
        only pacer, and an open breaker returns from it in microseconds, so the
        scan ran at full speed (2026-07-12: 6,621 candidates in an hour,
        nothing published). The breaker owns the clock and the candidates carry
        to the next session, as the write-budget break already did. The
        incident numbers live in tests/test_reply_chaos.py.
        """
        if time.time() >= end_time or self._ctx.is_rate_limited:
            return "session window closed"
        if not scheduler.can_comment():
            return "comment schedule"
        if not client.has_write_budget():
            return "write budget low"
        if circuit_reading().is_open:
            return "circuit breaker open"
        return None

    def run_cycle(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Check for and respond to replies on our posts/comments."""
        if not scheduler.can_comment():
            return

        self._scanned_posts.clear()
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

            pause = self._pause_reason(client, scheduler, end_time)
            if pause is not None:
                logger.info("Pausing reply processing: %s", pause)
                break

            validated = self._validated_notification(notif, i)
            if validated is None:
                continue
            fields, reply_key = validated

            self._handle_notification(client, scheduler, fields, reply_key, i, end_time)

        # Fallback: check comments on our own posts directly
        self.check_own_post_comments(client, scheduler, end_time)

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

    def _validated_notification(self, notif: dict, i: int) -> tuple[dict, str] | None:
        """Gate one notification; return (fields, reply_key) or None to skip.

        Skips non-actionable types, invalid post ids, and already-handled
        replies — this session (commented_posts) or a prior session
        (persistent commented cache). Mirrors the comment path's
        has_commented_on check (feed_manager.engage_with_post);
        commented_posts is rebuilt empty each session, so the persistent
        store is what dedups replies across sessions.
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
                "Notification[%d] skipped: already handled key=%s",
                i,
                reply_key,
            )
            return None

        return fields, reply_key

    def _handle_notification(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        fields: dict,
        reply_key: str,
        i: int,
        end_time: float,
    ) -> None:
        """Reply to one validated notification (or scan its comments)."""
        post_id = fields["post_id"]
        their_content = fields["content"]
        original_post = fields["post_content"]

        # If notification lacks comment body (e.g. post_comment type),
        # fetch comments from the post and process unhandled ones
        if not their_content and post_id:
            logger.debug(
                "Notification[%d] has no content; fetching comments for %s",
                i,
                post_id[:12],
            )
            self._handle_post_comments(client, scheduler, post_id, end_time)
            return

        if not their_content:
            logger.debug("Notification[%d] skipped: empty content", i)
            return

        replier_id = fields["agent_id"]
        replier_name = fields["agent_name"]

        # Skip our own comments to avoid self-reply loops (name-keyed:
        # notification data carries agent_name but agent_id="unknown")
        if self._ctx.is_self(replier_id, replier_name):
            logger.debug("Notification[%d] skipped: own comment", i)
            return

        self._process_reply(
            client=client,
            scheduler=scheduler,
            post_id=post_id,
            reply_key=reply_key,
            their_content=their_content,
            original_post=original_post,
            replier_id=replier_id,
            replier_name=replier_name,
            comment_id="",  # notification payload has no comment id
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
    ) -> None:
        """Generate and send a reply to a comment, recording interactions.

        ``comment_id`` is the id of the comment being replied to, when known
        (the comment-scan path supplies it). The notification path passes ""
        because the notification payload carries no comment id — see the
        courtesy-upvote guard below.
        """
        # Where whitespace becomes absence for everything this function decides
        # (T-REPLY-BLANKPOST). _handle_post_comments passes original_post=""
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

        # Promotional gate — guard against running the regex on a body that is
        # not there just to return False.
        if is_promotional(their_content) or (has_post and is_promotional(original_post)):
            logger.info("Skipped promotional reply target: %s", post_id[:12])
            return

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
            return
        # RFC-0028: the selection this reply was generated under. Recorded at
        # every exit below, so "never published" is a reason code rather than
        # an absent row.
        selection_id = generated.selection_id

        if not self._confirm_action(f"Reply to {replier_name} on post {post_id}", reply):
            record_publish_outcome(selection_id, comment_id=None, publish_status=PUBLISH_DECLINED)
            return

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
        # publish_outcome OUTSIDE the guard: the guard swallows the client
        # error, so only an exit outside it can tell "never published" from
        # "published and recorded".
        with (
            publish_outcome(selection_id) as outcome,
            client_error_guard(
                f"reply on {post_id}",
                on_rate_limited=ctx.set_rate_limited,
                on_failure=outcome.failed,
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
                return
            # Recorded as soon as the reply is live and verified — see
            # feed_manager: the records that follow can be interrupted.
            outcome.published()
            ctx.commented_posts.add(reply_key)
            # Persist cross-session so a later session does not re-reply to the
            # same target (mirrors feed_manager.engage_with_post's
            # record_commented). Takes effect for replies made after this ships;
            # the episode-scan fallback in _build_commented_cache stores post_ids,
            # not reply keys, so it does not dedup against pre-change replies.
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

    def _handle_post_comments(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        post_id: str,
        end_time: float,
    ) -> None:
        """Fetch comments on a post and reply to unhandled ones.

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
            pause = self._pause_reason(client, scheduler, end_time)
            if pause is not None:
                logger.info("Pausing comment processing: %s", pause)
                break

            fields = extract_agent_fields(comment)
            reply_key, handled = self._reply_dedup(post_id, fields["id"])
            if handled:
                continue

            # Skip our own comments to avoid self-reply loops (name-keyed:
            # comment data carries agent_name but agent_id="unknown")
            if self._ctx.is_self(fields["agent_id"], fields["agent_name"]):
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
                comment_id=fields["id"],  # real comment id on this path
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
        self._scanned_posts.clear()
        activity = home_data.get("activity_on_your_posts", [])
        if not activity:
            logger.debug("No activity on own posts from /home data")
            return

        for item in activity:
            pause = self._pause_reason(client, scheduler, end_time)
            if pause is not None:
                logger.info("Pausing home-based reply processing: %s", pause)
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
            if self._confirm_side_effect(f"Mark notifications read for post {post_id}"):
                client.mark_notifications_read_by_post(post_id)

    def check_own_post_comments(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Fallback: fetch comments on our own posts and reply to new ones."""
        if not self._ctx.own_post_ids:
            logger.debug("No own post IDs tracked; skipping comment check")
            return

        for post_id in list(self._ctx.own_post_ids):
            pause = self._pause_reason(client, scheduler, end_time)
            if pause is not None:
                logger.info("Pausing own post comment check: %s", pause)
                break

            self._handle_post_comments(client, scheduler, post_id, end_time)

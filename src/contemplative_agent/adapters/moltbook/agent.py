"""Main orchestrator for the Contemplative Moltbook Agent."""

import enum
import json
import logging
import random
import re
import signal
import time
from datetime import datetime, timezone
from typing import List, Optional, Set

from .auth import check_claim_status, load_credentials, register_agent
from .client import MoltbookClient, MoltbookClientError
from .config import (
    COMMENTED_CACHE_PATH,
    COMMENT_PACING_MAX_SECONDS,
    COMMENT_PACING_MIN_SECONDS,
    EPISODE_LOG_DIR,
    IDENTITY_PATH,
    KNOWLEDGE_PATH,
    LEGACY_MEMORY_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    RATE_LIMITS,
    RATE_STATE_PATH,
)
from .content import ContentManager, _content_hash
from .llm_functions import (
    check_topic_novelty,
    extract_topics,
    generate_post_title,
    generate_reply,
    generate_session_insight,
    score_relevance,
    select_submolt,
    summarize_post_topic,
)
from .verification import (
    VerificationTracker,
    solve_challenge,
    submit_verification,
)
from ...core.config import (
    FORBIDDEN_SUBSTRING_PATTERNS,
    FORBIDDEN_WORD_PATTERNS,
    MAX_POST_LENGTH,
    VALID_ID_PATTERN,
    VALID_SUBMOLT_PATTERN,
)
from ...core.domain import DomainConfig, get_domain_config
from ...core.llm import configure as configure_llm
from ...core.memory import MemoryStore
from ...core.scheduler import Scheduler

logger = logging.getLogger(__name__)

# Notification types that warrant a reply
_REPLY_TYPES = frozenset({
    "reply", "comment",
    "post_comment", "comment_reply",
    "mention",
})

# Cache TTL for feed: fetching from N submolts is expensive; posts don't change quickly
_FEED_CACHE_TTL = 600.0

# ANSI escape sequence pattern for terminal output sanitization
_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class AutonomyLevel(str, enum.Enum):
    APPROVE = "approve"
    GUARDED = "guarded"
    AUTO = "auto"


class Agent:
    """Contemplative Moltbook Agent orchestrator.

    Manages the autonomous loop: read feed -> judge relevance ->
    comment/post -> respect rate limits -> report.
    """

    def __init__(
        self,
        autonomy: AutonomyLevel = AutonomyLevel.APPROVE,
        memory: Optional[MemoryStore] = None,
        domain_config: Optional[DomainConfig] = None,
    ) -> None:
        self._autonomy = autonomy
        self._domain = domain_config or get_domain_config()
        self._content = ContentManager()
        self._verification = VerificationTracker()
        self._client: Optional[MoltbookClient] = None
        self._scheduler: Optional[Scheduler] = None
        self._actions_taken: List[str] = []
        self._commented_posts: Set[str] = set()
        self._own_post_ids: Set[str] = set()
        self._rate_limited: bool = False
        self._memory = memory or MemoryStore(
            path=LEGACY_MEMORY_PATH,
            log_dir=EPISODE_LOG_DIR,
            knowledge_path=KNOWLEDGE_PATH,
            commented_cache_path=COMMENTED_CACHE_PATH,
        )
        configure_llm(
            identity_path=IDENTITY_PATH,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_MODEL,
        )
        self._memory.load()
        self._shutdown_requested: bool = False
        self._cached_feed: List[dict] = []
        self._feed_fetched_at: float = 0.0
        self._own_agent_id: str = ""

    def _fetch_own_agent_id(self, client: MoltbookClient) -> None:
        """Fetch and cache our own agent ID to avoid self-replies.

        Also serves as an API key validity check at session start.
        Logs a critical warning if the key appears revoked or invalid
        (e.g. after a Moltbook DB breach / credential rotation).
        """
        try:
            resp = client.get("/agents/me")
            agent_data = resp.json().get("agent", {})
            self._own_agent_id = agent_data.get("id", "")
            if self._own_agent_id:
                logger.info("Own agent ID: %s", self._own_agent_id[:12])
        except MoltbookClientError as exc:
            if exc.status_code in (401, 403):
                logger.critical(
                    "API key rejected (HTTP %d). Key may be revoked or "
                    "compromised. Rotate credentials immediately.",
                    exc.status_code,
                )
            else:
                logger.warning("Failed to fetch own agent ID: %s", exc)
        except ValueError as exc:
            logger.warning("Failed to parse /agents/me response: %s", exc)
        if not self._own_agent_id:
            logger.warning("Self-reply protection DEGRADED: own agent ID unknown")

    def _ensure_subscriptions(self, client: MoltbookClient) -> None:
        """Subscribe to all configured submolts (idempotent)."""
        results = [client.subscribe_submolt(name) for name in self._domain.subscribed_submolts]
        if not any(results):
            logger.warning("All submolt subscription attempts failed")

    def _ensure_client(self) -> MoltbookClient:
        if self._client is not None:
            return self._client

        api_key = load_credentials()
        if api_key is None:
            raise RuntimeError(
                "No API key found. Run 'contemplative-agent register' first."
            )
        self._client = MoltbookClient(api_key)
        self._scheduler = Scheduler(
            state_path=RATE_STATE_PATH,
            limits=RATE_LIMITS,
        )
        return self._client

    def _get_scheduler(self) -> Scheduler:
        """Return scheduler, raising if not initialized."""
        if self._scheduler is None:
            raise RuntimeError("Scheduler not initialized. Call _ensure_client() first.")
        return self._scheduler

    @staticmethod
    def _passes_content_filter(content: str) -> bool:
        """Check content against safety filters for GUARDED mode.

        Returns True if content passes all filters.
        """
        if len(content) > MAX_POST_LENGTH:
            logger.warning("Content exceeds max length (%d > %d)", len(content), MAX_POST_LENGTH)
            return False
        content_lower = content.lower()
        for pattern in FORBIDDEN_SUBSTRING_PATTERNS:
            if pattern.lower() in content_lower:
                logger.warning("Content contains forbidden pattern: %s", pattern)
                return False
        for pattern in FORBIDDEN_WORD_PATTERNS:
            if re.search(r"\b" + re.escape(pattern) + r"\b", content, re.IGNORECASE):
                logger.warning("Content contains forbidden pattern: %s", pattern)
                return False
        if not content.strip():
            logger.warning("Content is empty or whitespace-only")
            return False
        return True

    def _confirm_action(self, description: str, content: str) -> bool:
        """Ask for user confirmation based on autonomy level."""
        if self._autonomy is AutonomyLevel.AUTO:
            return True
        if self._autonomy is AutonomyLevel.GUARDED:
            if not self._passes_content_filter(content):
                logger.info("GUARDED mode: content rejected by filter for: %s", description)
                return False
            return True

        # APPROVE mode: interactive confirmation
        print(f"\n--- {description} ---")
        print(_ANSI_ESCAPE.sub("", content[:500]))
        if len(content) > 500:
            print(f"... ({len(content)} chars total)")
        print("---")
        response = input("Post this? [y/N]: ").strip().lower()
        return response == "y"

    def do_register(self) -> dict:
        """Register a new agent on Moltbook."""
        client = MoltbookClient(api_key=None)
        result = register_agent(client)
        claim_url = result.get("claim_url", "")
        if claim_url:
            print(f"Claim your agent at: {claim_url}")
        return result

    def do_status(self) -> dict:
        """Check current agent status."""
        client = self._ensure_client()
        return check_claim_status(client)

    def do_introduce(self) -> Optional[str]:
        """Post the introduction template."""
        client = self._ensure_client()
        scheduler = self._get_scheduler()

        content = self._content.get_introduction()
        if content is None:
            print("Introduction already posted.")
            return None

        if not self._confirm_action("Introduction Post", content):
            print("Skipped.")
            return None

        scheduler.wait_for_post()
        try:
            resp = client.post(
                "/posts",
                json={
                    "title": "Introducing Contemplative Agent",
                    "content": content,
                    "submolt": self._domain.default_submolt,
                },
            )
            scheduler.record_post()
            self._actions_taken.append("Posted introduction")
            result = resp.json()
            post_id = result.get("id")
            if post_id:
                self._own_post_ids.add(post_id)
            print(f"Introduction posted. ID: {post_id or 'unknown'}")
            return post_id
        except MoltbookClientError as exc:
            logger.error("Failed to post introduction: %s", exc)
            return None

    def do_solve(self, text: str) -> Optional[str]:
        """Solve a verification challenge (for testing)."""
        answer = solve_challenge(text)
        if answer:
            print(f"Answer: {answer}")
        else:
            print("Failed to solve challenge.")
        return answer

    def _fetch_feed(self) -> List[dict]:
        """Fetch recent posts from subscribed submolt feeds."""
        client = self._ensure_client()
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
        logger.debug("Fetched %d posts from %d submolt feeds",
                      len(posts), len(self._domain.subscribed_submolts))
        return posts

    def _get_feed(self, max_age: float = _FEED_CACHE_TTL) -> List[dict]:
        """Return cached feed if fresh, otherwise fetch anew."""
        if time.time() - self._feed_fetched_at < max_age and self._cached_feed:
            return self._cached_feed
        self._cached_feed = self._fetch_feed()
        self._feed_fetched_at = time.time()
        return self._cached_feed

    def _handle_verification(self, challenge: dict) -> bool:
        """Solve and submit a verification challenge."""
        if self._verification.should_stop:
            logger.error("Too many verification failures. Stopping.")
            return False

        challenge_text = challenge.get("text", "")
        challenge_id = challenge.get("id", "")

        if not challenge_id or not VALID_ID_PATTERN.match(challenge_id):
            logger.warning("Invalid challenge_id format, skipping: %r", challenge_id[:50])
            self._verification.record_failure()
            return False

        answer = solve_challenge(challenge_text)
        if answer is None:
            self._verification.record_failure()
            return False

        client = self._ensure_client()
        try:
            result = submit_verification(client, challenge_id, answer)
            if result.get("success"):
                self._verification.record_success()
                return True
            self._verification.record_failure()
            return False
        except MoltbookClientError as exc:
            logger.error("Verification submission failed: %s", exc)
            self._verification.record_failure()
            return False

    def _engage_with_post(self, post: dict) -> bool:
        """Score and potentially comment on a post."""
        scheduler = self._get_scheduler()
        client = self._ensure_client()

        post_text = post.get("content", "")
        post_id = post.get("id", "")
        if not post_text or not post_id:
            return False

        # Skip our own posts
        author_id = (post.get("author") or {}).get("id", "")
        if self._own_agent_id and author_id == self._own_agent_id:
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
                post_id[:12], post_submolt,
            )
            return False

        # Skip posts we already commented on (session + cross-session)
        if post_id in self._commented_posts or self._memory.has_commented_on(post_id):
            logger.debug("Already commented on %s, skipping", post_id)
            return False

        score = score_relevance(post_text)
        # Lower threshold for agents we've previously interacted with
        threshold = (
            self._domain.known_agent_threshold
            if author_id and self._memory.has_interacted_with(author_id)
            else self._domain.relevance_threshold
        )
        if score < threshold:
            logger.debug("Post %s relevance %.2f below threshold %.2f", post_id, score, threshold)
            return False
        logger.info("Post %s relevance %.2f passed threshold %.2f", post_id, score, threshold)

        if not scheduler.can_comment():
            logger.info("Comment rate limit reached")
            return False

        comment = self._content.create_comment(post_text)
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
            self._commented_posts.add(post_id)
            self._memory.record_commented(post_id)
            self._actions_taken.append(
                f"Commented on {post_id} (relevance: {score:.2f})"
            )
            logger.info(">> Comment on %s:\n%s", post_id[:12], comment)
            self._memory.episodes.append("activity", {
                "action": "comment", "post_id": post_id,
                "content": comment[:200], "relevance": f"{score:.2f}",
            })
            # Record interaction in memory
            author = post.get("author") or {}
            agent_name = author.get("name", "unknown")
            agent_id = author.get("id", "unknown")
            self._memory.record_interaction(
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
            logger.info("Pacing: waiting %.0fs before next engagement", extra_wait)
            time.sleep(extra_wait)
            return True
        except MoltbookClientError as exc:
            logger.error("Failed to comment on %s: %s", post_id, exc)
            if exc.status_code == 429:
                self._rate_limited = True
            return False

    def _auto_follow(self, client: MoltbookClient) -> None:
        """Follow agents we've interacted with frequently."""
        candidates = self._memory.get_agents_to_follow(min_interactions=3)
        for _agent_id, agent_name in candidates:
            if client.follow_agent(agent_name):
                self._memory.record_follow(agent_name)
                self._actions_taken.append(f"Followed {agent_name}")
                self._memory.episodes.append("activity", {
                    "action": "follow", "target_agent": agent_name,
                })

    def run_session(self, duration_minutes: int = 60) -> List[str]:
        """Run an autonomous engagement session."""
        client = self._ensure_client()
        scheduler = self._get_scheduler()

        end_time = time.time() + (duration_minutes * 60)
        self._actions_taken = []
        self._shutdown_requested = False

        # Install graceful shutdown handlers
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)

        def _shutdown_handler(signum: int, _frame: object) -> None:
            logger.info("Shutdown signal received (signal %d). Finishing current cycle...", signum)
            self._shutdown_requested = True

        signal.signal(signal.SIGTERM, _shutdown_handler)
        signal.signal(signal.SIGINT, _shutdown_handler)

        logger.info(
            "Starting %d-minute session (autonomy: %s)",
            duration_minutes,
            self._autonomy.value,
        )

        try:
            try:
                self._fetch_own_agent_id(client)
                self._ensure_subscriptions(client)
                self._auto_follow(client)
            except Exception:
                logger.exception("Error during session setup")

            while time.time() < end_time and not self._shutdown_requested:
                if self._verification.should_stop:
                    logger.error("Verification failure limit reached. Ending session.")
                    break

                if self._rate_limited:
                    logger.info("Rate limited by server. Ending session early.")
                    break

                try:
                    self._run_reply_cycle(client, scheduler, end_time)
                    self._run_feed_cycle(end_time)
                    self._run_post_cycle(client, scheduler)
                except Exception:
                    logger.exception("Error in session cycle, continuing...")

                # Wait before next cycle
                wait = min(
                    scheduler.seconds_until_comment(),
                    scheduler.seconds_until_post(),
                    60.0,
                )
                if wait > 0 and time.time() + wait < end_time and not self._shutdown_requested:
                    logger.info("Next cycle in %.0fs", wait)
                    time.sleep(wait)

            if self._shutdown_requested:
                logger.info("Graceful shutdown: saving memory before exit")

            self._generate_session_insights()
            self._memory.save()
            self._print_report()
        finally:
            # Always restore original signal handlers
            signal.signal(signal.SIGTERM, original_sigterm)
            signal.signal(signal.SIGINT, original_sigint)

        return list(self._actions_taken)

    @staticmethod
    def _extract_agent_fields(data: dict) -> dict:
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

    @staticmethod
    def _extract_notification_fields(notif: dict) -> dict:
        """Extract notification fields with fallback for different API formats."""
        fields = Agent._extract_agent_fields(notif)
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

    def _run_reply_cycle(
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

            if time.time() >= end_time or self._rate_limited:
                break
            if not scheduler.can_comment():
                break

            fields = self._extract_notification_fields(notif)
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
            if reply_key in self._commented_posts:
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
            if self._own_agent_id and replier_id == self._own_agent_id:
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
        self._check_own_post_comments(client, scheduler, end_time)

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
        history = self._memory.get_history_with(replier_id, limit=5)
        history_summaries = [h.content_summary for h in history]
        knowledge_ctx = self._memory.knowledge.get_context_string() or None

        reply = generate_reply(
            original_post=original_post,
            their_comment=their_content,
            conversation_history=history_summaries,
            knowledge_context=knowledge_ctx,
        )
        if reply is None:
            return

        if not self._confirm_action(
            f"Reply to {replier_name} on post {post_id}", reply
        ):
            return

        # Record the incoming comment first (chronological order)
        self._memory.record_interaction(
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
            self._commented_posts.add(reply_key)
            self._actions_taken.append(
                f"Replied to {replier_name} on {post_id}"
            )
            logger.info(
                ">> Reply to %s on %s:\n%s", replier_name, post_id[:12], reply
            )
            self._memory.episodes.append("activity", {
                "action": "reply", "post_id": post_id,
                "content": reply[:200], "target_agent": replier_name,
            })
            self._memory.record_interaction(
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent_id=replier_id,
                agent_name=replier_name,
                post_id=post_id,
                direction="sent",
                content=reply,
                interaction_type="reply",
            )
        except MoltbookClientError as exc:
            logger.error("Failed to reply on %s: %s", post_id, exc)
            if exc.status_code == 429:
                self._rate_limited = True

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
            if time.time() >= end_time or self._rate_limited:
                break
            if not scheduler.can_comment():
                break

            fields = self._extract_agent_fields(comment)
            reply_key = f"reply:{post_id}:{fields['id']}"
            if reply_key in self._commented_posts:
                continue

            # Skip our own comments to avoid self-reply loops
            if self._own_agent_id and fields["agent_id"] == self._own_agent_id:
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

    def _check_own_post_comments(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Fallback: fetch comments on our own posts and reply to new ones."""
        if not self._own_post_ids:
            logger.debug("No own post IDs tracked; skipping comment check")
            return

        for post_id in list(self._own_post_ids):
            if time.time() >= end_time or self._rate_limited:
                break
            if not scheduler.can_comment():
                break

            self._handle_post_comments(client, scheduler, post_id, end_time)

    def _run_feed_cycle(
        self,
        end_time: float,
    ) -> None:
        """Fetch and engage with posts from the feed."""
        posts = self._get_feed()
        for post in posts:
            if time.time() >= end_time or self._rate_limited:
                break
            challenge = post.get("verification_challenge")
            if challenge:
                self._handle_verification(challenge)
                continue
            self._engage_with_post(post)

    def _run_post_cycle(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> None:
        """Post new content if rate limit allows."""
        if not scheduler.can_post():
            return

        self._run_dynamic_post(client, scheduler)

    def _run_dynamic_post(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> None:
        """Generate and publish a post based on current feed topics."""
        posts = self._get_feed()
        topics = extract_topics(posts)
        if not topics:
            return

        # Check novelty against recent post topics
        recent_topics = self._memory.get_recent_post_topics(limit=5)
        if not check_topic_novelty(topics, recent_topics):
            logger.info("Topics not novel enough, skipping post")
            return

        recent_insights = self._memory.get_recent_insights(limit=3)
        knowledge_ctx = self._memory.knowledge.get_context_string() or None
        content = self._content.create_cooperation_post(
            topics, recent_insights=recent_insights or None,
            knowledge_context=knowledge_ctx,
        )
        if content is None:
            return

        title = generate_post_title(topics) or f"Contemplative Note — {topics[:40]}"

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
                self._own_post_ids.add(post_id)
            self._actions_taken.append(f"Posted: {title}")
            logger.info(">> New post [%s] (id=%s):\n%s", title, post_id, content)
            self._memory.episodes.append("activity", {
                "action": "post", "post_id": post_id,
                "content": content[:200], "title": title,
            })

            # Record post in memory
            topic_summary = summarize_post_topic(content) or title
            content_hash = _content_hash(content)
            self._memory.record_post(
                timestamp=datetime.now(timezone.utc).isoformat(),
                post_id=post_id,
                title=title,
                topic_summary=topic_summary,
                content_hash=content_hash,
            )
        except MoltbookClientError as exc:
            logger.error("Failed to post dynamic content: %s", exc)

    def _generate_session_insights(self) -> None:
        """Generate and record insights at the end of a session."""
        if not self._actions_taken:
            return

        recent_topics = self._memory.get_recent_post_topics(limit=5)

        # Check if topics were repetitive among recent posts
        post_actions = [a for a in self._actions_taken if a.startswith("Posted:")]
        insight_type = "topic_saturation" if len(post_actions) == 0 else "session_summary"

        observation = generate_session_insight(
            actions=self._actions_taken,
            recent_topics=recent_topics,
        )
        if observation:
            self._memory.record_insight(
                timestamp=datetime.now(timezone.utc).isoformat(),
                observation=observation,
                insight_type=insight_type,
            )
            logger.info("Session insight recorded: %s", observation)

    def _print_report(self) -> None:
        """Print session summary."""
        print("\n=== Session Report ===")
        print(f"Actions taken: {len(self._actions_taken)}")
        for action in self._actions_taken:
            print(f"  - {action}")
        if self._scheduler:
            print(f"Comments remaining today: {self._scheduler.comments_remaining_today}")
        print(f"Comment:Post ratio: {self._content.comment_to_post_ratio:.1f}")
        print(f"Memory: {self._memory.interaction_count()} interactions, "
              f"{self._memory.unique_agent_count()} agents known")
        print("======================\n")

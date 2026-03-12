"""Main orchestrator for the Contemplative Moltbook Agent."""

import enum
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
    ADAPTIVE_BACKOFF,
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
from .content import ContentManager
from .llm_functions import score_relevance
from .post_pipeline import PostPipeline
from .reply_handler import (
    ReplyHandler,
    extract_agent_fields,
    extract_notification_fields,
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
)
from ...core.domain import DomainConfig, get_domain_config
from ...core.llm import configure as configure_llm
from ...core.memory import MemoryStore
from ...core.scheduler import Scheduler

logger = logging.getLogger(__name__)

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

    Delegates reply handling to ReplyHandler and post generation
    to PostPipeline to keep this file focused on orchestration.
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
        self._rate_limited: bool = False  # use set_rate_limited() from collaborators
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
        self._upvoted_posts: Set[str] = set()
        self._home_data: dict = {}
        self._cycle_wait: float = ADAPTIVE_BACKOFF.base_cycle_wait
        self._consecutive_429_cycles: int = 0

        # Collaborators
        self._reply_handler = ReplyHandler(self)
        self._post_pipeline = PostPipeline(self)

    # ------------------------------------------------------------------
    # Public interface for collaborators
    # ------------------------------------------------------------------

    @property
    def is_rate_limited(self) -> bool:
        return self._rate_limited

    def set_rate_limited(self) -> None:
        """Signal that a 429 was received. Called by collaborators."""
        self._rate_limited = True

    # ------------------------------------------------------------------
    # Client / scheduler lifecycle
    # ------------------------------------------------------------------

    def _fetch_home_data(self, client: MoltbookClient) -> None:
        """Fetch /home dashboard and extract own agent ID.

        Replaces the old _fetch_own_agent_id (which called /agents/me)
        with a single /home call that also provides activity data.
        """
        home = client.get_home()
        self._home_data = home

        # Extract agent ID from your_account
        account = home.get("your_account", {})
        agent_id = account.get("id", "")
        agent_name = account.get("name", "")
        if agent_id:
            self._own_agent_id = agent_id
            logger.info("Own agent ID: %s (name: %s)", agent_id[:12], agent_name)
        elif not self._own_agent_id:
            # Fallback to /agents/me if /home didn't return an ID
            self._fetch_own_agent_id_fallback(client)

    def _fetch_own_agent_id_fallback(self, client: MoltbookClient) -> None:
        """Fallback: fetch agent ID from /agents/me."""
        try:
            resp = client.get("/agents/me")
            agent_data = resp.json().get("agent", {})
            self._own_agent_id = agent_data.get("id", "")
            if self._own_agent_id:
                logger.info("Own agent ID (fallback): %s", self._own_agent_id[:12])
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

    # ------------------------------------------------------------------
    # Adaptive backoff
    # ------------------------------------------------------------------

    def _adaptive_cycle_wait(self) -> float:
        """Compute the next cycle wait based on rate limit state.

        Three-layer defense:
        1. Exponential backoff on 429 responses (reactive)
        2. Decay toward base_cycle_wait on clean cycles
        3. Proactive wait when remaining quota is low
        """
        client = self._ensure_client()
        cfg = ADAPTIVE_BACKOFF

        # Layer 1 & 2: backoff or decay based on recent 429s
        if client.recent_429_count > 0:
            self._consecutive_429_cycles += 1
            self._cycle_wait = min(
                self._cycle_wait * cfg.backoff_multiplier,
                cfg.max_cycle_wait,
            )
            logger.warning(
                "429 detected (%d this cycle). Backing off: next cycle in %.0fs",
                client.recent_429_count,
                self._cycle_wait,
            )
        else:
            if self._consecutive_429_cycles > 0:
                self._consecutive_429_cycles = 0
            self._cycle_wait = max(
                self._cycle_wait * cfg.decay_factor,
                cfg.base_cycle_wait,
            )

        wait = self._cycle_wait

        # Layer 3: proactive wait when remaining quota is low
        remaining = client.rate_limit_remaining
        if remaining is not None and remaining <= cfg.remaining_threshold:
            reset_at = client.rate_limit_reset
            if reset_at is not None and reset_at > time.time():
                proactive = reset_at - time.time()
            else:
                proactive = cfg.proactive_wait_seconds
            wait = max(wait, proactive)
            logger.info(
                "Rate limit remaining=%d <= %d. Proactive wait: %.0fs",
                remaining,
                cfg.remaining_threshold,
                wait,
            )

        client.reset_429_count()
        return wait

    # ------------------------------------------------------------------
    # Content filters and confirmation
    # ------------------------------------------------------------------

    @staticmethod
    def _passes_content_filter(content: str) -> bool:
        """Check content against safety filters for GUARDED mode."""
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

    # ------------------------------------------------------------------
    # CLI commands
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Feed management
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Feed engagement
    # ------------------------------------------------------------------

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

        # Upvote relevant posts (regardless of whether we comment)
        if (
            post_id not in self._upvoted_posts
            and client.has_write_budget(ADAPTIVE_BACKOFF.write_budget_reserve)
        ):
            if client.upvote_post(post_id):
                self._upvoted_posts.add(post_id)
                self._memory.episodes.append("activity", {
                    "action": "upvote", "post_id": post_id,
                })
                logger.info("Upvoted post %s (relevance: %.2f)", post_id[:12], score)

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

    # ------------------------------------------------------------------
    # Session loop
    # ------------------------------------------------------------------

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
                self._fetch_home_data(client)
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
                    # Refresh /home data each cycle for latest activity
                    self._fetch_home_data(client)

                    # Use /home-based reply cycle if data available, else fallback
                    if self._home_data:
                        self._reply_handler.run_cycle_from_home(
                            client, scheduler, end_time, self._home_data,
                        )
                    else:
                        self._run_reply_cycle(client, scheduler, end_time)
                    self._run_feed_cycle(end_time)
                    self._run_post_cycle(client, scheduler)
                except Exception:
                    logger.exception("Error in session cycle, continuing...")

                # Wait before next cycle: respect both scheduler and adaptive backoff
                adaptive_wait = self._adaptive_cycle_wait()
                wait = max(
                    min(scheduler.seconds_until_comment(), scheduler.seconds_until_post()),
                    adaptive_wait,
                )
                wait = min(wait, max(0.0, end_time - time.time()))
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

    # ------------------------------------------------------------------
    # Backward-compatible delegation methods (used by tests)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_agent_fields(data: dict) -> dict:
        """Delegate to reply_handler.extract_agent_fields."""
        return extract_agent_fields(data)

    @staticmethod
    def _extract_notification_fields(notif: dict) -> dict:
        """Delegate to reply_handler.extract_notification_fields."""
        return extract_notification_fields(notif)

    def _run_reply_cycle(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Delegate to ReplyHandler.run_cycle."""
        self._reply_handler.run_cycle(client, scheduler, end_time)

    def _check_own_post_comments(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        end_time: float,
    ) -> None:
        """Delegate to ReplyHandler.check_own_post_comments."""
        self._reply_handler.check_own_post_comments(client, scheduler, end_time)

    def _handle_post_comments(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        post_id: str,
        end_time: float,
    ) -> None:
        """Delegate to ReplyHandler._handle_post_comments."""
        self._reply_handler._handle_post_comments(client, scheduler, post_id, end_time)

    def _run_post_cycle(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> None:
        """Delegate to PostPipeline.run_cycle."""
        self._post_pipeline.run_cycle(client, scheduler)

    def _run_dynamic_post(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> None:
        """Delegate to PostPipeline._run_dynamic_post."""
        self._post_pipeline._run_dynamic_post(client, scheduler)

    def _generate_session_insights(self) -> None:
        """Delegate to PostPipeline.generate_session_insights."""
        self._post_pipeline.generate_session_insights()

    # ------------------------------------------------------------------
    # Cycle helpers
    # ------------------------------------------------------------------

    def _run_feed_cycle(self, end_time: float) -> None:
        """Fetch from multiple sources and engage with posts.

        Sources (in priority order):
        1. Following feed (always, 1 GET)
        2. Submolt feeds (existing)
        3. Search (topic_keywords rotation, 1 GET/cycle)
        """
        client = self._ensure_client()
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
        for post in self._get_feed():
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
            if time.time() >= end_time or self._rate_limited:
                break
            if not client.has_read_budget(ADAPTIVE_BACKOFF.read_budget_reserve):
                logger.info("Read budget low, pausing feed engagement")
                break
            challenge = post.get("verification_challenge")
            if challenge:
                self._handle_verification(challenge)
                continue
            self._engage_with_post(post)

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

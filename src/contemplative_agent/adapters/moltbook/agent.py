"""Main orchestrator for the Contemplative Moltbook Agent."""

import enum
import logging
import re
import signal
import time
from collections.abc import Callable
from typing import Any

from ...core._io import log_safe_identifier
from ...core.config import (
    FORBIDDEN_SUBSTRING_PATTERNS,
    FORBIDDEN_WORD_PATTERNS,
)
from ...core.domain import DomainConfig, get_domain_config
from ...core.episode_embeddings import EpisodeEmbeddingStore
from ...core.llm import configure as configure_llm
from ...core.memory import MemoryStore
from ...core.scheduler import Scheduler
from .auth import check_claim_status, load_credentials, register_agent
from .client import MoltbookClient, MoltbookClientError
from .config import (
    ADAPTIVE_BACKOFF,
    AGENTS_PATH,
    COMMENTED_CACHE_PATH,
    EPISODE_EMBEDDINGS_PATH,
    EPISODE_LOG_DIR,
    IDENTITY_PATH,
    KNOWLEDGE_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    RATE_LIMITS,
    RATE_STATE_PATH,
)
from .content import ContentManager
from .feed_manager import FeedManager
from .novelty import NoveltyGate
from .post_pipeline import PostPipeline
from .reply_handler import ReplyHandler
from .session_context import SessionContext
from .submolt_scope import SubmoltScopeScan, scan_submolt_scope
from .verification import (
    VerificationTracker,
    _sanitize_audit_error,
    record_verification_audit,
    solve_challenge,
    solve_challenge_result,
    submit_verification,
    unsolved_result,
)

logger = logging.getLogger(__name__)

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
        memory: MemoryStore | None = None,
        domain_config: DomainConfig | None = None,
        *,
        client: MoltbookClient | None = None,
        scheduler: Scheduler | None = None,
        content: ContentManager | None = None,
        verification: VerificationTracker | None = None,
        novelty_gate: NoveltyGate | None = None,
    ) -> None:
        """Compose the agent from its collaborators.

        The keyword-only parameters are injection seams for tests: each
        defaults to the production collaborator when omitted. Injecting
        ``client`` bypasses credential loading in ``_ensure_client``, so a
        caller that injects ``client`` is responsible for injecting
        ``scheduler`` too when the exercised paths need one.
        """
        self._autonomy = autonomy
        self._domain = domain_config or get_domain_config()
        self._content = content if content is not None else ContentManager()
        self._verification = verification if verification is not None else VerificationTracker()
        self._client: MoltbookClient | None = client
        self._scheduler: Scheduler | None = scheduler
        self._memory = memory or MemoryStore(
            log_dir=EPISODE_LOG_DIR,
            knowledge_path=KNOWLEDGE_PATH,
            commented_cache_path=COMMENTED_CACHE_PATH,
            agents_path=AGENTS_PATH,
        )
        configure_llm(
            identity_path=IDENTITY_PATH,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_MODEL,
        )
        self._memory.load()
        self._shutdown_requested: bool = False
        self._home_data: dict = {}
        self._cycle_wait: float = ADAPTIVE_BACKOFF.base_cycle_wait
        self._consecutive_429_cycles: int = 0

        # Shared session state for collaborators
        self._ctx = SessionContext(memory=self._memory)

        # Collaborators — receive explicit context instead of Agent reference
        self._feed_manager = FeedManager(
            ctx=self._ctx,
            domain=self._domain,
            get_content=lambda: self._content,
            confirm_action=self._confirm_action,
            confirm_side_effect=self._confirm_side_effect,
            handle_verification=self._handle_verification,
        )
        self._reply_handler = ReplyHandler(
            ctx=self._ctx,
            confirm_action=self._confirm_action,
            confirm_side_effect=self._confirm_side_effect,
            handle_verification=self._handle_verification,
        )
        self._novelty_gate = (
            novelty_gate
            if novelty_gate is not None
            else NoveltyGate(
                embed_store=EpisodeEmbeddingStore(EPISODE_EMBEDDINGS_PATH),
                memory=self._memory,
            )
        )
        self._post_pipeline = PostPipeline(
            ctx=self._ctx,
            domain=self._domain,
            get_content=lambda: self._content,
            get_feed=lambda: self._feed_manager.get_feed(self._ensure_client()),
            confirm_action=self._confirm_action,
            novelty_gate=self._novelty_gate,
            handle_verification=self._handle_verification,
        )

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

        # Extract agent ID and name from your_account. The name is the
        # operative self-identification key on live data (feed posts and
        # notifications carry author.name but not author.id — ADR-0055).
        account = home.get("your_account", {})
        agent_id = account.get("id", "")
        self._store_own_agent_name(account.get("name", ""))
        if agent_id:
            self._ctx.own_agent_id = agent_id
            logger.info(
                "Own agent ID: %s (name: %s)",
                agent_id[:12],
                self._ctx.own_agent_name,
            )
        if not self._ctx.own_agent_id or not self._ctx.own_agent_name:
            # Fallback to /agents/me when /home left either identity field
            # unset — the name is required for the self-gates on live data
            # (cross-model review 2026-07-18: id-only /home responses would
            # otherwise leave the name-keyed gates dead).
            self._fetch_own_agent_id_fallback(client)
        self._log_self_identification_state()

    def _store_own_agent_name(self, name: str) -> None:
        """Store the own account name; reject sentinel values.

        "unknown" is the extract_agent_fields default for absent counterparty
        names — accepting it as our OWN name would make is_self's
        `author_name != "unknown"` clause suppress every name match and
        silently kill the gate (security review 2026-07-18).
        """
        if name and name != "unknown":
            self._ctx.own_agent_name = name

    def _log_self_identification_state(self) -> None:
        """Surface degraded self-identification (no silent fallback).

        The name is the operative key on live data (author ids are absent —
        ADR-0055), so a missing own name degrades the self-gates even when
        the id is known.
        """
        if not self._ctx.own_agent_id and not self._ctx.own_agent_name:
            logger.warning("Self-reply protection DEGRADED: own agent ID and name unknown")
        elif not self._ctx.own_agent_name:
            logger.warning(
                "Self-reply protection DEGRADED: own agent name unknown "
                "(name is the operative key; live data lacks author ids)"
            )
        elif not self._ctx.own_agent_id:
            logger.info("Own agent ID unknown; self-identification keyed on name only")

    def _fetch_own_agent_id_fallback(self, client: MoltbookClient) -> None:
        """Fallback: fetch agent ID (and name) from /agents/me."""
        try:
            resp = client.get("/agents/me")
            agent_data = resp.json().get("agent", {})
            fallback_id = agent_data.get("id", "")
            if fallback_id:
                # Only overwrite on a truthy value: this path also runs
                # name-only (id already set from /home) and must not clear it.
                self._ctx.own_agent_id = fallback_id
            self._store_own_agent_name(agent_data.get("name", ""))
            if self._ctx.own_agent_id:
                logger.info(
                    "Own agent ID (fallback): %s (name: %s)",
                    self._ctx.own_agent_id[:12],
                    self._ctx.own_agent_name,
                )
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

    def _ensure_subscriptions(self, client: MoltbookClient) -> None:
        """Subscribe to all configured submolts (idempotent)."""
        names = [
            name
            for name in self._domain.subscribed_submolts
            if self._confirm_side_effect(f"Subscribe to submolt {name}")
        ]
        if not names:
            return
        results = [client.subscribe_submolt(name) for name in names]
        if not any(results):
            logger.warning("All submolt subscription attempts failed")

    def _ensure_client(self) -> MoltbookClient:
        if self._client is not None:
            return self._client

        api_key = load_credentials()
        if api_key is None:
            raise RuntimeError("No API key found. Run 'contemplative-agent register' first.")
        self._client = MoltbookClient(api_key)
        if self._scheduler is None:
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
        """Check content against safety filters for GUARDED mode.

        ADR-0018 amendment (2026-05-04): length enforcement moved to
        ``_sanitize_output()`` (one cap per artifact, ADR-0030); this filter
        only checks forbidden patterns and emptiness.
        """
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

    def _confirm_action(self, description: str, content: str, *, title: str | None = None) -> bool:
        """Ask for user confirmation based on autonomy level.

        ``title`` is the agent's own LLM-generated post title (post path only).
        It is filtered alongside ``content`` in GUARDED mode — without this a
        forbidden pattern in the title bypassed the gate, since the title was
        only embedded in the human-readable ``description`` and the description
        also carries external data (agent names / post ids) that must NOT be
        filtered (it would false-reject on legitimate external content).
        """
        if self._autonomy is AutonomyLevel.AUTO:
            return True
        if self._autonomy is AutonomyLevel.GUARDED:
            if title is not None and not self._passes_content_filter(title):
                logger.info("GUARDED mode: title rejected by filter for: %s", description)
                return False
            if not self._passes_content_filter(content):
                logger.info("GUARDED mode: content rejected by filter for: %s", description)
                return False
            return True

        # APPROVE mode: interactive confirmation. The description embeds
        # external data (post ids, agent names) — strip ANSI so a malicious
        # account name cannot inject terminal escapes into the prompt.
        print(f"\n--- {_ANSI_ESCAPE.sub('', description)} ---")
        print(_ANSI_ESCAPE.sub("", content[:500]))
        if len(content) > 500:
            print(f"... ({len(content)} chars total)")
        print("---")
        try:
            response = input("Post this? [y/N]: ").strip().lower()
        except EOFError:
            # Non-TTY stdin: reject rather than crash the session.
            return False
        return response == "y"

    def _confirm_side_effect(self, description: str) -> bool:
        """Confirm a contentless external side effect (audit H1).

        The approval gate was keyed on "produces text" (comment / reply /
        post), not "produces an external side effect": upvote / follow /
        unfollow / subscribe / mark-read bypassed APPROVE entirely.
        APPROVE now confirms every external write. GUARDED deliberately
        default-allows contentless actions — its content filter has
        nothing to inspect, preserving pre-fix behavior. AUTO passes
        everything through.
        """
        if self._autonomy is not AutonomyLevel.APPROVE:
            return True
        # Strip ANSI: description embeds external data (agent names from
        # API responses) — block terminal escape injection into the prompt.
        print(f"\n--- {_ANSI_ESCAPE.sub('', description)} ---")
        try:
            response = input("Proceed? [y/N]: ").strip().lower()
        except EOFError:
            # Non-TTY stdin: reject rather than act unsupervised.
            return False
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

    def do_submolt_scan(self, sample_size: int) -> SubmoltScopeScan:
        """Run one read-only submolt-scope sweep (ADR-0086).

        Deliberately not part of ``run_session``: the sweep is ~20 feed reads
        and a few hundred local LLM calls, which would compete with the
        session's own work on one Ollama. It has its own schedule, and it
        changes nothing the session depends on.
        """
        client = self._ensure_client()
        return scan_submolt_scope(client, self._domain, sample_size=sample_size)

    def do_solve(self, text: str) -> str | None:
        """Solve a verification challenge (for testing)."""
        answer = solve_challenge(text)
        if answer:
            print(f"Answer: {answer}")
        else:
            print("Failed to solve challenge.")
        return answer

    # ------------------------------------------------------------------
    # Feed management (delegated to FeedManager)
    # ------------------------------------------------------------------

    def _get_feed(self) -> list[dict]:
        """Return cached feed (delegates to FeedManager)."""
        return self._feed_manager.get_feed(self._ensure_client())

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _handle_verification(self, verification: dict) -> bool:
        """Solve and submit a content-verification challenge.

        ``verification`` is the object Moltbook embeds in a create-response
        (post / comment / submolt) when the agent is not trusted: it carries
        ``challenge_text`` (the obfuscated math problem) and
        ``verification_code`` (the opaque submission handle). Returns True
        when the content was verified (or no action was needed); False when
        solving or submission failed (caller leaves the content unrecorded).

        Deliberately NOT routed through _confirm_side_effect (audit H1):
        verification is a platform anti-bot handshake required for created
        content to become visible, not a social action — gating it would
        leave the post invisible rather than supervise it.
        """
        if self._verification.should_stop:
            logger.error("Too many verification failures. Stopping.")
            return False

        # Coerce, don't trust: a malformed object can carry null / non-string
        # values ("challenge_text": null), which must land in the malformed
        # branch below rather than crash unsolved_result's hashing
        # (codex review 2026-07-10).
        raw_challenge = verification.get("challenge_text")
        raw_code = verification.get("verification_code")
        challenge_text = raw_challenge if isinstance(raw_challenge, str) else ""
        verification_code = raw_code if isinstance(raw_code, str) else ""

        if not challenge_text or not verification_code:
            # Key names are server-controlled — sanitize before they touch
            # the plain application log or the audit error field.
            keys_repr = _sanitize_audit_error(",".join(map(str, sorted(verification.keys()))))[:150]
            logger.warning(
                "Verification object missing challenge_text/verification_code (keys=%s)",
                keys_repr,
            )
            # Audit-log the abstain: this branch trips the failure tracker
            # (and can auto-stop the session), so without a record a
            # server-side shape change would be indistinguishable in
            # verification-audit.jsonl from verification not happening at all.
            record_verification_audit(
                challenge_text=challenge_text,
                verification_code=verification_code,
                solve_result=unsolved_result(challenge_text),
                verify_success=False,
                error="malformed_verification_object keys=" + keys_repr,
            )
            self._verification.record_failure()
            return False

        solve_result = solve_challenge_result(challenge_text)
        answer = solve_result.answer
        if answer is None:
            record_verification_audit(
                challenge_text=challenge_text,
                verification_code=verification_code,
                solve_result=solve_result,
                verify_success=False,
                error=solve_result.abstain_reason or "solve_failed",
            )
            self._verification.record_failure()
            return False

        client = self._ensure_client()
        try:
            result = submit_verification(client, verification_code, answer)
            if result.get("success"):
                record_verification_audit(
                    challenge_text=challenge_text,
                    verification_code=verification_code,
                    solve_result=solve_result,
                    verify_success=True,
                )
                self._verification.record_success()
                logger.info("Verification submitted and accepted")
                return True
            # error is server-generated; strip non-printable to avoid log
            # injection in agent-launchd.log (same care as client.py).
            safe_error = _sanitize_audit_error(str(result.get("error", "")))
            logger.warning("Verification rejected: %s", safe_error)
            record_verification_audit(
                challenge_text=challenge_text,
                verification_code=verification_code,
                solve_result=solve_result,
                verify_success=False,
                error=safe_error or "verify_rejected",
            )
            self._verification.record_failure()
            return False
        except (MoltbookClientError, ValueError) as exc:
            logger.error("Verification submission failed: %s", exc)
            record_verification_audit(
                challenge_text=challenge_text,
                verification_code=verification_code,
                solve_result=solve_result,
                verify_success=False,
                error=str(exc),
            )
            self._verification.record_failure()
            return False

    def _auto_follow(self, client: MoltbookClient) -> None:
        """Maintain a stable following list based on interaction count.

        Hysteresis: an agent is followed once it enters the top FOLLOW_RANK
        and only unfollowed once it falls past KEEP_RANK. Agents we already
        follow that sit in the grey zone (FOLLOW_RANK..KEEP_RANK) are kept, so
        rank wobble around the boundary no longer causes follow/unfollow
        churn. Follows are applied in rank order (most-interacted first) so
        the limited per-session budget goes to the strongest relationships.
        Our own agent is excluded so we never attempt to follow ourselves.
        """
        FOLLOW_RANK = 20
        KEEP_RANK = 30
        # Per-direction budget (not a shared total): up to 3 follows AND up to
        # 3 unfollows per session. Hysteresis makes unfollows rare (only genuine
        # drop-outs past KEEP_RANK), so the two budgets rarely both fire and the
        # worst case stays well under the 30/min write limit.
        MAX_CHANGES_PER_SESSION = 3

        own_id = self._ctx.own_agent_id
        exclude_ids = {own_id} if own_id else set()
        top_agents = self._memory.get_top_interacted_agents(
            limit=KEEP_RANK, exclude_ids=exclude_ids
        )
        follow_ranked = [name for _, name in top_agents[:FOLLOW_RANK]]
        keep_names = {name for _, name in top_agents}
        currently_followed = self._memory.get_followed_agents()

        # Unfollow agents who fell past the keep rank (out of the grey zone).
        # These dropped out of the top-30 entirely, so no rank info remains to
        # prioritise them; sorted() gives a stable, deterministic order and the
        # per-session cap bounds the impact.
        to_unfollow = sorted(currently_followed - keep_names)
        unfollowed = 0
        for name in to_unfollow:
            if unfollowed >= MAX_CHANGES_PER_SESSION:
                break
            if not self._confirm_side_effect(f"Unfollow agent {name}"):
                continue
            if client.unfollow_agent(name):
                self._memory.record_unfollow(name)
                # actions_taken is replayed at INFO by _print_report, so an
                # externally-chosen name goes into the sweep-scanned log
                # (T-LOG-DEBUG-CONTENT). The episode payload below keeps the
                # exact name — that store is already treated as untrusted.
                self._ctx.actions_taken.append(f"Unfollowed {log_safe_identifier(name)}")
                self._memory.episodes.append(
                    "activity",
                    {
                        "action": "unfollow",
                        "target_agent": name,
                    },
                )
                unfollowed += 1

        # Follow agents who entered the top FOLLOW_RANK, highest-ranked first.
        followed = 0
        for name in follow_ranked:
            if followed >= MAX_CHANGES_PER_SESSION:
                break
            if name in currently_followed:
                continue
            if not self._confirm_side_effect(f"Follow agent {name}"):
                continue
            if client.follow_agent(name):
                self._memory.record_follow(name)
                self._ctx.actions_taken.append(f"Followed {log_safe_identifier(name)}")
                self._memory.episodes.append(
                    "activity",
                    {
                        "action": "follow",
                        "target_agent": name,
                    },
                )
                followed += 1

        logger.info(
            "Auto-follow: follow<=%d keep<=%d, followed %d, unfollowed %d (currently: %d)",
            FOLLOW_RANK,
            KEEP_RANK,
            followed,
            unfollowed,
            len(currently_followed) - unfollowed + followed,
        )

    # ------------------------------------------------------------------
    # Session loop
    # ------------------------------------------------------------------

    def run_session(
        self,
        duration_minutes: int = 60,
        session_meta: dict[str, Any] | None = None,
    ) -> list[str]:
        """Run an autonomous engagement session."""
        client = self._ensure_client()
        scheduler = self._get_scheduler()

        end_time = time.time() + (duration_minutes * 60)
        self._ctx.actions_taken.clear()
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

        # Log session start with configuration metadata
        # Internal fields are applied last to prevent caller from overwriting them
        start_data: dict[str, Any] = dict(session_meta) if session_meta else {}
        start_data.update(
            {
                "event": "start",
                "duration_minutes": duration_minutes,
                "autonomy": self._autonomy.value,
            }
        )
        self._memory.episodes.append("session", start_data)

        # Restore own post ids from prior sessions so the own-post comment
        # fallback covers posts made before this process started (H3).
        try:
            self._ctx.seed_own_post_ids()
        except Exception:
            logger.exception("Failed to seed own post ids from episode log")

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

                if self._ctx.is_rate_limited:
                    logger.info("Rate limited by server. Ending session early.")
                    break

                try:
                    self._run_session_cycle(client, scheduler, end_time)
                except Exception:
                    logger.exception("Error in session cycle, continuing...")

                self._wait_for_next_cycle(scheduler, end_time)

            if self._shutdown_requested:
                logger.info("Graceful shutdown: saving memory before exit")

            self._log_session_end(duration_minutes)

            self._memory.save()
            self._generate_activity_report()
            self._print_report()
        finally:
            # Always restore original signal handlers
            signal.signal(signal.SIGTERM, original_sigterm)
            signal.signal(signal.SIGINT, original_sigint)

        return list(self._ctx.actions_taken)

    def _run_session_cycle(
        self, client: MoltbookClient, scheduler: Scheduler, end_time: float
    ) -> None:
        """One engagement cycle: replies, feed, then the post pipeline.

        Each step is isolated (bug-audit 2026-07-06 H4): an uncaught error
        in the reply step must not silently skip feed engagement and the
        post pipeline for the whole cycle — a persistently malformed
        notification would otherwise stop posting indefinitely behind a
        generic outer-loop warning that names neither the failing step nor
        the skipped ones.
        """
        # Refresh /home data each cycle for latest activity
        self._run_cycle_step("home_refresh", lambda: self._fetch_home_data(client))

        def _reply_step() -> None:
            # Use /home-based reply cycle if data available, else fallback
            if self._home_data:
                self._reply_handler.run_cycle_from_home(
                    client,
                    scheduler,
                    end_time,
                    self._home_data,
                )
            else:
                self._reply_handler.run_cycle(client, scheduler, end_time)

        self._run_cycle_step("replies", _reply_step)
        self._run_cycle_step("feed", lambda: self._run_feed_cycle(end_time))
        self._run_cycle_step(
            "post_pipeline",
            lambda: self._post_pipeline.run_cycle(client, scheduler),
        )

    def _run_cycle_step(self, step: str, fn: Callable[[], None]) -> None:
        """Run one session-cycle step; log-and-continue on failure (H4)."""
        try:
            fn()
        except Exception:
            logger.exception(
                "Error in session-cycle step %r; continuing with next step",
                step,
            )

    def _wait_for_next_cycle(self, scheduler: Scheduler, end_time: float) -> None:
        """Wait before next cycle: respect both scheduler and adaptive backoff."""
        adaptive_wait = self._adaptive_cycle_wait()
        wait = max(
            min(scheduler.seconds_until_comment(), scheduler.seconds_until_post()),
            adaptive_wait,
        )
        wait = min(wait, max(0.0, end_time - time.time()))
        if wait > 0 and time.time() + wait < end_time and not self._shutdown_requested:
            logger.info("Next cycle in %.0fs", wait)
            time.sleep(wait)

    def _log_session_end(self, duration_minutes: int) -> None:
        """Log session end with action counts."""
        actions = self._ctx.actions_taken
        self._memory.episodes.append(
            "session",
            {
                "event": "end",
                "duration_minutes": duration_minutes,
                "actions_count": len(actions),
                "comments": sum(1 for a in actions if a.startswith("Commented")),
                "replies": sum(1 for a in actions if a.startswith("Replied")),
                "posts": sum(1 for a in actions if a.startswith("Posted")),
                "follows": sum(1 for a in actions if a.startswith("Followed")),
            },
        )

    # ------------------------------------------------------------------
    # Cycle helpers
    # ------------------------------------------------------------------

    def _run_feed_cycle(self, end_time: float) -> None:
        """Fetch from multiple sources and engage with posts (delegates to FeedManager)."""
        self._feed_manager.run_cycle(
            client=self._ensure_client(),
            scheduler=self._get_scheduler(),
            end_time=end_time,
        )

    def _generate_activity_report(self) -> None:
        """Generate daily activity report from episode logs."""
        try:
            from ...core.report import generate_report
            from .config import REPORTS_DIR

            output_dir = REPORTS_DIR
            result = generate_report(
                log_dir=EPISODE_LOG_DIR,
                output_dir=output_dir,
            )
            if result:
                logger.info("Activity report saved: %s", result)
        except Exception:
            logger.warning("Failed to generate activity report", exc_info=True)

    def _print_report(self) -> None:
        """Log session summary."""
        logger.info("=== Session Report ===")
        logger.info("Actions taken: %d", len(self._ctx.actions_taken))
        for action in self._ctx.actions_taken:
            logger.info("  - %s", action)
        if self._scheduler:
            logger.info(
                "Comments remaining today: %d",
                self._scheduler.comments_remaining_today,
            )
        logger.info(
            "Comment:Post ratio: %.1f",
            self._content.comment_to_post_ratio,
        )
        logger.info(
            "Memory: %d interactions, %d agents known",
            self._memory.interaction_count(),
            self._memory.unique_agent_count(),
        )
        logger.info("======================")

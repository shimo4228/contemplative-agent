"""Persistent conversation memory for cross-session context.

3-layer architecture:
  - EpisodeLog: append-only JSONL logs per day
  - KnowledgeStore: distilled learned patterns as JSON
  - MemoryStore: facade preserving the original public API
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Tuple

from ._io import parse_aware_utc, truncate, write_text_atomic
from .episode_log import EpisodeLog
from .knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)

MAX_INTERACTIONS = 1000
MAX_POST_HISTORY = 50

# Schema-level cap for PostRecord.topic_summary. The single source of truth
# for the 100-char invariant; adapters that produce summaries normalize to
# this value before passing in (the dedup gate's token-set Jaccard is
# largely cap-invariant after prefix-5 stemming, but the LLM-fallback path
# in summarize_post_topic uses raw post content as the summary, where the
# cap is load-bearing for set symmetry).
POST_TOPIC_SUMMARY_MAX = 100

# Re-export for backward compatibility — all external code imports from here
__all__ = [
    "EpisodeLog",
    "Interaction",
    "KnowledgeStore",
    "MAX_INTERACTIONS",
    "MAX_POST_HISTORY",
    "MemoryStore",
    "POST_TOPIC_SUMMARY_MAX",
    "PostRecord",
    "truncate",
]


@dataclass(frozen=True)
class Interaction:
    """Record of a single interaction with another agent."""

    timestamp: str
    agent_id: str
    agent_name: str
    post_id: str
    direction: Literal["sent", "received"]
    content_summary: str
    interaction_type: Literal["comment", "reply", "post"]


@dataclass(frozen=True)
class PostRecord:
    """Record of a post made by this agent."""

    timestamp: str
    post_id: str
    title: str
    topic_summary: str  # 1-line summary of what the post was about
    content_hash: str  # first 16 chars of SHA-256
    # True only for posts that completed the visibility-verification handshake
    # (ADR-0063). Defaults False so pre-fix "post" episodes — written before the
    # handshake worked, all stuck verification_status=pending and invisible —
    # deserialize as unverified and are excluded from the NoveltyGate comparison
    # (deduping a new post against content nobody ever saw kept the agent silent).
    verified: bool = False


# Session insight (the ``Insight`` dataclass, type="insight" episodes) was
# retired by ADR-0052: insights were LLM session summaries whose re-ingestion
# created summary-of-summary patterns and an ungated self-continuity channel.
# Historical insight records remain in the episode log as plain JSONL —
# nothing loads them into memory anymore.

# ---------------------------------------------------------------------------
# Facade: MemoryStore — preserves original public API
# ---------------------------------------------------------------------------


class MemoryStore:
    """Facade managing EpisodeLog + KnowledgeStore + agents.json.

    The public API is fully backward-compatible with the original MemoryStore.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        knowledge_path: Optional[Path] = None,
        commented_cache_path: Optional[Path] = None,
        agents_path: Optional[Path] = None,
    ) -> None:
        # When path is given (e.g. tests), derive sibling paths from it
        if path is not None:
            base_dir = path.parent
            log_dir = log_dir or base_dir / "logs"
            knowledge_path = knowledge_path or base_dir / "knowledge.json"
            commented_cache_path = commented_cache_path or base_dir / "commented_cache.json"
            agents_path = agents_path or base_dir / "agents.json"
        self._episodes = EpisodeLog(log_dir=log_dir)
        self._knowledge = KnowledgeStore(path=knowledge_path)
        self._commented_cache_path = commented_cache_path
        self._agents_path = agents_path
        self._interactions: List[Interaction] = []
        self._interacted_ids: set[str] = set()
        self._post_history: List[PostRecord] = []
        self._commented_cache: Optional[set] = None
        # Known agents: agent_id -> name (populated from JSONL)
        self._known_agents: Dict[str, str] = {}
        # Followed agent names (persisted in agents.json)
        self._followed: set[str] = set()

    @property
    def known_agents(self) -> Dict[str, str]:
        return dict(self._known_agents)

    @property
    def episodes(self) -> EpisodeLog:
        return self._episodes

    @property
    def knowledge(self) -> KnowledgeStore:
        return self._knowledge

    def load(self) -> None:
        """Load memory from knowledge store, agents.json, and episode logs."""
        if self._knowledge.has_persisted_file():
            self._knowledge.load()
        self._load_agents_json()
        self._load_episodes_into_memory()

        logger.info(
            "Loaded memory: %d interactions, %d known agents, %d post records",
            len(self._interactions),
            len(self._known_agents),
            len(self._post_history),
        )

    def _load_agents_json(self) -> None:
        """Load followed agents from agents.json."""
        from .config import FORBIDDEN_SUBSTRING_PATTERNS

        if self._agents_path is None or not self._agents_path.exists():
            return
        try:
            text = self._agents_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read agents.json: %s", exc)
            return

        # Validate against forbidden patterns (consistent with knowledge.json)
        text_lower = text.lower()
        for pat in FORBIDDEN_SUBSTRING_PATTERNS:
            if pat.lower() in text_lower:
                logger.warning(
                    "agents.json contains forbidden pattern: %s — skipping load", pat
                )
                return

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                followed = data.get("followed", [])
                if isinstance(followed, list):
                    self._followed = set(followed)
                    logger.debug("Loaded %d followed agents", len(self._followed))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse agents.json: %s", exc)

    def _save_agents_json(self) -> None:
        """Persist followed agents to agents.json."""
        if self._agents_path is None:
            return
        self._agents_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {"followed": sorted(self._followed)},
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        try:
            write_text_atomic(self._agents_path, content)
        except OSError as exc:
            logger.error("Failed to save agents.json: %s", exc)
            raise

    def _load_episodes_into_memory(self) -> None:
        """Load recent episode log entries into in-memory lists.

        A ``TypeError`` from ``Interaction(**data)`` / ``PostRecord(**data)``
        means the persisted record does not match the current dataclass — the
        hazard being a schema change (a new required field, or a rename)
        without a default, which would silently drop EVERY legacy record while
        the test suite stays green. The per-record warning alone hides that;
        an aggregate WARNING with the drop ratio makes a mass-drop observable.
        """
        records = self._episodes.read_range(days=7)
        seen = {"interaction": 0, "post": 0}
        dropped = {"interaction": 0, "post": 0}
        for record in records:
            record_type = record.get("type", "")
            data = record.get("data", {})
            if record_type == "interaction":
                seen["interaction"] += 1
                try:
                    interaction = Interaction(**data)
                    self._interactions.append(interaction)
                    self._interacted_ids.add(interaction.agent_id)
                    # Build known agents from JSONL
                    self._known_agents[interaction.agent_id] = interaction.agent_name
                except TypeError:
                    dropped["interaction"] += 1
                    logger.warning("Skipping malformed interaction in episode log")
            elif record_type == "post":
                seen["post"] += 1
                try:
                    self._post_history.append(PostRecord(**data))
                except TypeError:
                    dropped["post"] += 1
                    logger.warning("Skipping malformed post record in episode log")
            # type="insight" records (retired by ADR-0052) are intentionally
            # not loaded — they stay in the log as historical research data.
        for kind in ("interaction", "post"):
            if dropped[kind]:
                logger.warning(
                    "Dropped %d/%d %s records during episode load — possible "
                    "schema drift (a new required field added without a "
                    "default drops every legacy record)",
                    dropped[kind], seen[kind], kind,
                )

    def save(self) -> None:
        """Persist knowledge store, agents.json, and commented cache."""
        self._knowledge.save()
        self._save_agents_json()
        self._save_commented_cache()

    def record_interaction(
        self,
        timestamp: str,
        agent_id: str,
        agent_name: str,
        post_id: str,
        direction: Literal["sent", "received"],
        content: str,
        interaction_type: Literal["comment", "reply", "post"],
    ) -> Interaction:
        """Record an interaction and update known agents."""
        interaction = Interaction(
            timestamp=timestamp,
            agent_id=agent_id,
            agent_name=agent_name,
            post_id=post_id,
            direction=direction,
            content_summary=truncate(content),
            interaction_type=interaction_type,
        )
        self._interactions.append(interaction)
        self._interacted_ids.add(agent_id)
        self._known_agents[agent_id] = agent_name

        # Append to episode log immediately
        self._episodes.append("interaction", asdict(interaction))

        # Trim in-memory list
        if len(self._interactions) > MAX_INTERACTIONS:
            self._interactions = self._interactions[-MAX_INTERACTIONS:]

        return interaction

    def has_interacted_with(self, agent_id: str) -> bool:
        """Check if we have any history with this agent (O(1) lookup)."""
        return agent_id in self._interacted_ids

    def unique_agent_count(self) -> int:
        """Count unique agents we've interacted with."""
        return len(self._known_agents)

    def interaction_count(self) -> int:
        """Total number of recorded interactions."""
        return len(self._interactions)

    def interaction_count_with(self, agent_id: str) -> int:
        """Count total interactions with a specific agent."""
        return sum(1 for i in self._interactions if i.agent_id == agent_id)

    def record_follow(self, agent_name: str) -> None:
        """Mark an agent as followed."""
        self._followed.add(agent_name)

    def record_unfollow(self, agent_name: str) -> None:
        """Mark an agent as unfollowed."""
        self._followed.discard(agent_name)

    def get_followed_agents(self) -> set:
        """Return set of followed agent names."""
        return set(self._followed)

    _TEST_AGENT_NAMES = frozenset({
        "Agent0", "Agent1", "Agent2", "Agent3", "Agent4",
        "Bob", "TestAgent", "unknown", "Agent1 Updated",
    })

    def get_top_interacted_agents(
        self, limit: int = 20, exclude_ids: Optional[Iterable[str]] = None
    ) -> List[Tuple[str, str]]:
        """Return top N (agent_id, agent_name) pairs by interaction count.

        ``exclude_ids`` drops specific agent ids before ranking (e.g. our own
        agent id, so we never try to follow ourselves). Exclusion happens
        before the limit slice, so excluding self never shrinks the returned
        count below ``limit`` when enough other agents exist.
        """
        excluded = set(exclude_ids or ())
        counts = Counter(i.agent_id for i in self._interactions)
        ranked = []
        for agent_id, agent_name in self._known_agents.items():
            if agent_id in excluded:
                continue
            if agent_name in self._TEST_AGENT_NAMES:
                continue
            count = counts.get(agent_id, 0)
            if count > 0:
                ranked.append((agent_id, agent_name, count))
        ranked.sort(key=lambda x: x[2], reverse=True)
        return [(aid, aname) for aid, aname, _ in ranked[:limit]]

    def record_post(
        self,
        timestamp: str,
        post_id: str,
        title: str,
        topic_summary: str,
        content_hash: str,
        verified: bool = True,
    ) -> PostRecord:
        """Record a post made by this agent.

        ``verified`` defaults True because the post pipeline now records only
        after the visibility-verification handshake succeeds (ADR-0063); the
        flag scopes the NoveltyGate comparison to visible posts.
        """
        record = PostRecord(
            timestamp=timestamp,
            post_id=post_id,
            title=title,
            topic_summary=truncate(topic_summary, POST_TOPIC_SUMMARY_MAX),
            content_hash=content_hash[:16],
            verified=verified,
        )
        self._post_history.append(record)
        self._episodes.append("post", asdict(record))

        if len(self._post_history) > MAX_POST_HISTORY:
            self._post_history = self._post_history[-MAX_POST_HISTORY:]

        return record

    def get_recent_posts(
        self, limit: int = 50, verified_only: bool = False
    ) -> List[PostRecord]:
        """Return recent self-post records (oldest→newest), capped at `limit`.

        Used by the NoveltyGate comparison and body-hash dedup in post_pipeline.
        The default of 50 covers roughly the past week at the agent's post-volume
        ceiling and is bounded by MAX_POST_HISTORY anyway.

        ``verified_only=True`` returns only posts that passed the visibility
        handshake (ADR-0063), so dedup compares a draft against content that was
        actually published — not against pre-fix pending posts nobody saw. Filter
        first, then cap, so the limit counts verified posts (not slots consumed
        by skipped pending ones).
        """
        records = (
            [r for r in self._post_history if r.verified]
            if verified_only
            else self._post_history
        )
        return list(records[-limit:])

    @staticmethod
    def _count_within(
        items: Iterable[Any],
        cutoff: datetime,
        predicate: Callable[[Any], bool],
    ) -> int:
        """Count items matching *predicate* whose timestamp is >= *cutoff*.

        Shared trailing-window counter for the post-rate and per-author
        comment-rate limiters: parse each item's ``timestamp`` (skipping
        malformed values), coerce tz-naive to UTC, and tally those at or
        after the cutoff.
        """
        n = 0
        for x in items:
            if not predicate(x):
                continue
            try:
                ts = parse_aware_utc(x.timestamp)
            except ValueError:
                continue
            if ts >= cutoff:
                n += 1
        return n

    def get_post_rate_7d(self) -> float:
        """Self-post rate (posts/day) over a fixed 7-day trailing window.

        Used by the rate-deficit Lagrangian term in NoveltyGate (ADR-0039):
        when the rate falls below the target, the admit threshold is loosened
        so the gate cannot silently silence the agent.

        Fixed 7-day window (not "since first post") so the regulariser
        semantics stay stable in the cold-start case. Malformed timestamps
        are skipped (same pattern as count_recent_comments_by_author).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return self._count_within(self._post_history, cutoff, lambda _p: True) / 7.0

    def count_recent_comments_by_author(
        self, agent_name: str, hours: int = 24
    ) -> int:
        """Count outgoing interactions sent to `agent_name` within the last
        `hours` hours.

        Keyed on the counterparty *name*: live feed posts carry author.name
        but not author.id (interaction records store agent_id="unknown"), so
        the previous id-keyed count never matched. Used by the per-author
        rate limiter in feed_manager to prevent the '15 replies to the same
        linguistics post' phenomenon. Walks the in-memory _interactions list,
        which load() restores from the past 7 days of episode logs at startup.
        """
        if not agent_name or agent_name == "unknown":
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return self._count_within(
            self._interactions,
            cutoff,
            lambda it: it.direction == "sent" and it.agent_name == agent_name,
        )

    def get_prior_comment_targets(
        self, agent_name: str, days: int = 7, limit: int = 7
    ) -> List[str]:
        """Return original_post texts of recent comments sent to agent_name.

        Reads activity records (action="comment") from the episode log and
        returns the original_post bodies of those targeting agent_name. Used
        by feed_manager.engage_with_post to detect same-author repeat-topic
        posts (the 30+ Armenian-linguistics replays the 2026-04-12 weekly
        report flagged).

        Keyed on the counterparty *name*: live feed posts carry author.name
        but not author.id, so the previous target_agent_id match never fired.
        Older records (pre-target_agent field on comments, before this fix)
        carry no target_agent and are silently filtered out.
        """
        if not agent_name or agent_name == "unknown":
            return []
        episodes = self.episodes.read_range(days=days, record_type="activity")
        targets: List[str] = []
        for ep in episodes:
            data = ep.get("data") or {}
            if data.get("action") != "comment":
                continue
            if data.get("target_agent") != agent_name:
                continue
            op = data.get("original_post")
            if isinstance(op, str) and op:
                targets.append(op)
        return targets[-limit:]

    def has_commented_on(self, post_id: str) -> bool:
        """Check if we've commented on this post in the last 30 days."""
        if self._commented_cache is None:
            self._commented_cache = self._load_commented_cache()
        return post_id in self._commented_cache

    def record_commented(self, post_id: str) -> None:
        """Record that we commented on a post (in-memory + persistent cache)."""
        if self._commented_cache is None:
            self._commented_cache = self._load_commented_cache()
        self._commented_cache.add(post_id)

    def _load_commented_cache(self) -> set:
        """Load commented cache from file, falling back to JSONL scan."""
        if self._commented_cache_path is not None and self._commented_cache_path.exists():
            try:
                data = json.loads(
                    self._commented_cache_path.read_text(encoding="utf-8")
                )
                if isinstance(data, list):
                    logger.debug("Loaded commented cache: %d entries", len(data))
                    return set(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load commented cache: %s", exc)
        return self._build_commented_cache()

    def _build_commented_cache(self) -> set:
        """Build cache of post_ids we've commented on from episode logs."""
        episodes = self._episodes.read_range(days=30)
        return {
            ep["data"]["post_id"]
            for ep in episodes
            if ep.get("type") == "interaction"
            and ep.get("data", {}).get("direction") == "sent"
            and ep.get("data", {}).get("post_id")
        }

    def _save_commented_cache(self) -> None:
        """Persist commented cache to JSON file (atomic write)."""
        if self._commented_cache is None or self._commented_cache_path is None:
            return
        self._commented_cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            write_text_atomic(
                self._commented_cache_path,
                json.dumps(sorted(self._commented_cache), ensure_ascii=False),
            )
        except OSError as exc:
            logger.warning("Failed to save commented cache: %s", exc)

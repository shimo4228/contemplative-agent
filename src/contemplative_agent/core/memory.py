"""Persistent conversation memory for cross-session context.

3-layer architecture:
  - EpisodeLog: append-only JSONL logs per day
  - KnowledgeStore: distilled learned patterns as JSON
  - MemoryStore: facade preserving the original public API
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Tuple

from ._io import truncate
from .episode_log import EpisodeLog
from .knowledge_store import KnowledgeStore
from .memory_repos import (
    MAX_INTERACTIONS,
    MAX_POST_HISTORY,
    POST_TOPIC_SUMMARY_MAX,
    CommentLedger,
    FollowState,
    InteractionIndex,
    PostHistory,
)

logger = logging.getLogger(__name__)

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
    """Facade over the episode log, knowledge store, and the four stores in
    :mod:`.memory_repos` (interaction index, follow state, post history,
    comment ledger).

    The public API is fully backward-compatible with the original MemoryStore;
    what changed is that each storage surface and retention policy now has one
    owner behind this facade instead of all of them living in this class.
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
        self._interaction_index = InteractionIndex(self._episodes, Interaction)
        self._follows = FollowState(agents_path)
        self._posts = PostHistory(self._episodes, PostRecord)
        self._comments = CommentLedger(
            self._episodes, commented_cache_path, self._interaction_index
        )

    @property
    def known_agents(self) -> Dict[str, str]:
        return self._interaction_index.known_agents

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
        self._follows.load()
        self._load_episodes_into_memory()

        logger.info(
            "Loaded memory: %d interactions, %d known agents, %d post records",
            self._interaction_index.count(),
            self._interaction_index.unique_agent_count(),
            len(self._posts),
        )

    def _load_episodes_into_memory(self) -> None:
        """Replay recent episode records into the in-memory stores.

        A record that fails to deserialize means the persisted shape does not
        match the current dataclass — the hazard being a schema change (a new
        required field, or a rename) without a default, which would silently
        drop EVERY legacy record while the test suite stays green. The
        per-record warning alone hides that; an aggregate WARNING with the drop
        ratio makes a mass-drop observable.
        """
        records = self._episodes.read_range(days=7)
        seen = {"interaction": 0, "post": 0}
        dropped = {"interaction": 0, "post": 0}
        for record in records:
            record_type = record.get("type", "")
            data = record.get("data", {})
            if record_type == "interaction":
                seen["interaction"] += 1
                if not self._interaction_index.ingest(data):
                    dropped["interaction"] += 1
                    logger.warning("Skipping malformed interaction in episode log")
            elif record_type == "post":
                seen["post"] += 1
                if not self._posts.ingest(data):
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
                    dropped[kind],
                    seen[kind],
                    kind,
                )

    def save(self) -> None:
        """Persist knowledge store, agents.json, and commented cache."""
        self._knowledge.save()
        self._follows.save()
        self._comments.save()

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
        return self._interaction_index.record(
            timestamp,
            agent_id,
            agent_name,
            post_id,
            direction,
            content,
            interaction_type,
        )

    def has_interacted_with(self, agent_id: str) -> bool:
        """Check if we have any history with this agent (O(1) lookup)."""
        return self._interaction_index.has_interacted_with(agent_id)

    def unique_agent_count(self) -> int:
        """Count unique agents we've interacted with."""
        return self._interaction_index.unique_agent_count()

    def interaction_count(self) -> int:
        """Total number of recorded interactions."""
        return self._interaction_index.count()

    def record_follow(self, agent_name: str) -> None:
        """Mark an agent as followed."""
        self._follows.add(agent_name)

    def record_unfollow(self, agent_name: str) -> None:
        """Mark an agent as unfollowed."""
        self._follows.remove(agent_name)

    def get_followed_agents(self) -> set:
        """Return set of followed agent names."""
        return self._follows.names()

    def get_top_interacted_agents(
        self, limit: int = 20, exclude_ids: Optional[Iterable[str]] = None
    ) -> List[Tuple[str, str]]:
        """Return top N (agent_id, agent_name) pairs by interaction count."""
        return self._interaction_index.top(limit, exclude_ids)

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
        return self._posts.record(
            timestamp, post_id, title, topic_summary, content_hash, verified
        )

    def get_recent_posts(self, limit: int = 50, verified_only: bool = False) -> List[PostRecord]:
        """Return recent self-post records (oldest→newest), capped at ``limit``.

        Used by the NoveltyGate comparison and body-hash dedup in post_pipeline.
        The default of 50 covers roughly the past week at the agent's post-volume
        ceiling and is bounded by MAX_POST_HISTORY anyway.
        """
        return self._posts.recent(limit, verified_only)

    def get_post_rate_7d(self) -> float:
        """Self-post rate (posts/day) over a fixed 7-day trailing window."""
        return self._posts.rate_7d()

    def count_recent_comments_by_author(self, agent_name: str, hours: int = 24) -> int:
        """Count outgoing interactions sent to ``agent_name`` in the last *hours*."""
        return self._comments.count_recent_by_author(agent_name, hours)

    def get_prior_comment_targets(
        self, agent_name: str, days: int = 7, limit: int = 7
    ) -> List[str]:
        """Return original_post texts of recent comments sent to agent_name."""
        return self._comments.prior_comment_targets(agent_name, days, limit)

    def has_commented_on(self, post_id: str) -> bool:
        """Check if we've commented on this post in the last 30 days."""
        return self._comments.has_commented_on(post_id)

    def record_commented(self, post_id: str) -> None:
        """Record that we commented on a post (in-memory + persistent cache)."""
        self._comments.record_commented(post_id)

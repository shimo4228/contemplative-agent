"""Persistent conversation memory for cross-session context.

3-layer architecture:
  - EpisodeLog: append-only JSONL logs per day
  - KnowledgeStore: distilled knowledge as Markdown
  - MemoryStore: facade preserving the original public API
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from ._io import SUMMARY_MAX_LENGTH, truncate, write_restricted
from .episode_log import EpisodeLog
from .knowledge_store import (
    KNOWLEDGE_CONTEXT_MAX,
    MAX_INSIGHTS,
    MAX_POST_HISTORY,
    KnowledgeStore,
)

logger = logging.getLogger(__name__)

MAX_INTERACTIONS = 1000

# Re-export for backward compatibility — all external code imports from here
__all__ = [
    "EpisodeLog",
    "Interaction",
    "Insight",
    "KnowledgeStore",
    "MAX_INSIGHTS",
    "MAX_INTERACTIONS",
    "MAX_POST_HISTORY",
    "MemoryStore",
    "PostRecord",
    "SUMMARY_MAX_LENGTH",
    "KNOWLEDGE_CONTEXT_MAX",
    "truncate",
    "write_restricted",
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


@dataclass(frozen=True)
class Insight:
    """Session-end reflection."""

    timestamp: str
    observation: str
    insight_type: str  # "topic_saturation", "engagement_low", "new_direction", etc.


# ---------------------------------------------------------------------------
# Facade: MemoryStore — preserves original public API
# ---------------------------------------------------------------------------


class MemoryStore:
    """Facade managing EpisodeLog + KnowledgeStore.

    The public API is fully backward-compatible with the original MemoryStore.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        knowledge_path: Optional[Path] = None,
        commented_cache_path: Optional[Path] = None,
    ) -> None:
        # When path is given (e.g. tests), derive sibling paths from it
        if path is not None:
            base_dir = path.parent
            log_dir = log_dir or base_dir / "logs"
            knowledge_path = knowledge_path or base_dir / "knowledge.md"
            commented_cache_path = commented_cache_path or base_dir / "commented_cache.json"
        self._episodes = EpisodeLog(log_dir=log_dir)
        self._knowledge = KnowledgeStore(path=knowledge_path)
        self._commented_cache_path = commented_cache_path
        self._interactions: List[Interaction] = []
        self._interacted_ids: set[str] = set()
        self._post_history: List[PostRecord] = []
        self._insights_list: List[Insight] = []
        self._commented_cache: Optional[set] = None

    @property
    def interactions(self) -> Tuple[Interaction, ...]:
        return tuple(self._interactions)

    @property
    def known_agents(self) -> Dict[str, str]:
        return self._knowledge.agents

    @property
    def episodes(self) -> EpisodeLog:
        return self._episodes

    @property
    def knowledge(self) -> KnowledgeStore:
        return self._knowledge

    def load(self) -> None:
        """Load memory from knowledge store and episode logs."""
        if self._knowledge.has_persisted_file():
            self._knowledge.load()
        self._load_episodes_into_memory()

        logger.info(
            "Loaded memory: %d interactions, %d known agents, "
            "%d post records, %d insights",
            len(self._interactions),
            len(self._knowledge.agents),
            len(self._post_history),
            len(self._insights_list),
        )

    def _load_episodes_into_memory(self) -> None:
        """Load recent episode log entries into in-memory lists."""
        records = self._episodes.read_range(days=7)
        for record in records:
            record_type = record.get("type", "")
            data = record.get("data", {})
            if record_type == "interaction":
                try:
                    interaction = Interaction(**data)
                    self._interactions.append(interaction)
                    self._interacted_ids.add(interaction.agent_id)
                except TypeError:
                    logger.warning("Skipping malformed interaction in episode log")
            elif record_type == "post":
                try:
                    self._post_history.append(PostRecord(**data))
                except TypeError:
                    logger.warning("Skipping malformed post record in episode log")
            elif record_type == "insight":
                try:
                    self._insights_list.append(Insight(**data))
                except TypeError:
                    logger.warning("Skipping malformed insight in episode log")

    def save(self) -> None:
        """Persist knowledge store and commented cache. Episodes are saved on append."""
        self._knowledge.save()
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
        self._knowledge.record_agent(agent_id, agent_name)

        # Append to episode log immediately
        self._episodes.append("interaction", asdict(interaction))

        # Trim in-memory list
        if len(self._interactions) > MAX_INTERACTIONS:
            self._interactions = self._interactions[-MAX_INTERACTIONS:]

        return interaction

    def get_history_with(
        self, agent_id: str, limit: int = 10
    ) -> List[Interaction]:
        """Get recent interactions with a specific agent."""
        matches = [i for i in self._interactions if i.agent_id == agent_id]
        return matches[-limit:]

    def get_recent(self, limit: int = 50) -> List[Interaction]:
        """Get most recent interactions across all agents."""
        return self._interactions[-limit:]

    def has_interacted_with(self, agent_id: str) -> bool:
        """Check if we have any history with this agent (O(1) lookup)."""
        return agent_id in self._interacted_ids

    def unique_agent_count(self) -> int:
        """Count unique agents we've interacted with."""
        return len(self._knowledge.agents)

    def interaction_count(self) -> int:
        """Total number of recorded interactions."""
        return len(self._interactions)

    def interaction_count_with(self, agent_id: str) -> int:
        """Count total interactions with a specific agent."""
        return sum(1 for i in self._interactions if i.agent_id == agent_id)

    def is_followed(self, agent_name: str) -> bool:
        """Check if we've already followed this agent."""
        return self._knowledge.is_followed(agent_name)

    def record_follow(self, agent_name: str) -> None:
        """Mark an agent as followed."""
        self._knowledge.record_follow(agent_name)

    def record_unfollow(self, agent_name: str) -> None:
        """Mark an agent as unfollowed."""
        self._knowledge.record_unfollow(agent_name)

    def get_followed_agents(self) -> set:
        """Return set of followed agent names."""
        return self._knowledge.followed_agents

    _TEST_AGENT_NAMES = frozenset({
        "Agent0", "Agent1", "Agent2", "Agent3", "Agent4",
        "Bob", "TestAgent", "unknown", "Agent1 Updated",
    })

    def get_top_interacted_agents(self, limit: int = 20) -> List[Tuple[str, str]]:
        """Return top N (agent_id, agent_name) pairs by interaction count."""
        ranked = []
        for agent_id, agent_name in self._knowledge.agents.items():
            if agent_name in self._TEST_AGENT_NAMES:
                continue
            count = self.interaction_count_with(agent_id)
            if count > 0:
                ranked.append((agent_id, agent_name, count))
        ranked.sort(key=lambda x: x[2], reverse=True)
        return [(aid, aname) for aid, aname, _ in ranked[:limit]]

    def get_agents_to_follow(self, min_interactions: int = 5) -> List[Tuple[str, str]]:
        """Return (agent_id, agent_name) pairs for agents we interact with
        frequently but haven't followed yet, sorted by interaction count."""
        candidates = []
        for agent_id, agent_name in self._knowledge.agents.items():
            if self.is_followed(agent_name):
                continue
            count = self.interaction_count_with(agent_id)
            if count >= min_interactions:
                candidates.append((agent_id, agent_name, count))
        candidates.sort(key=lambda x: x[2], reverse=True)
        return [(aid, aname) for aid, aname, _ in candidates]

    def record_post(
        self,
        timestamp: str,
        post_id: str,
        title: str,
        topic_summary: str,
        content_hash: str,
    ) -> PostRecord:
        """Record a post made by this agent."""
        record = PostRecord(
            timestamp=timestamp,
            post_id=post_id,
            title=title,
            topic_summary=truncate(topic_summary, 100),
            content_hash=content_hash[:16],
        )
        self._post_history.append(record)
        self._episodes.append("post", asdict(record))
        self._knowledge.add_post_topic(record.topic_summary)

        if len(self._post_history) > MAX_POST_HISTORY:
            self._post_history = self._post_history[-MAX_POST_HISTORY:]

        return record

    def record_insight(
        self,
        timestamp: str,
        observation: str,
        insight_type: str,
    ) -> Insight:
        """Record a session-end insight."""
        insight = Insight(
            timestamp=timestamp,
            observation=truncate(observation),
            insight_type=insight_type,
        )
        self._insights_list.append(insight)
        self._episodes.append("insight", asdict(insight))
        self._knowledge.add_insight(insight.observation)

        if len(self._insights_list) > MAX_INSIGHTS:
            self._insights_list = self._insights_list[-MAX_INSIGHTS:]

        return insight

    def get_recent_post_topics(self, limit: int = 5) -> List[str]:
        """Return topic_summaries of recent posts."""
        return [p.topic_summary for p in self._post_history[-limit:]]

    def get_recent_insights(self, limit: int = 3) -> List[str]:
        """Return observation strings of recent insights."""
        return [i.observation for i in self._insights_list[-limit:]]

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
        tmp_path = self._commented_cache_path.with_suffix(".json.tmp")
        try:
            write_restricted(
                tmp_path,
                json.dumps(sorted(self._commented_cache), ensure_ascii=False),
            )
            os.replace(str(tmp_path), str(self._commented_cache_path))
        except OSError as exc:
            logger.warning("Failed to save commented cache: %s", exc)
            tmp_path.unlink(missing_ok=True)

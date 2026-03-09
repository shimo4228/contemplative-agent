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
import re
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from .config import (
    COMMENTED_CACHE_PATH,
    EPISODE_LOG_DIR,
    EPISODE_RETENTION_DAYS,
    FORBIDDEN_SUBSTRING_PATTERNS,
    KNOWLEDGE_PATH,
    LEGACY_MEMORY_PATH,
)

logger = logging.getLogger(__name__)

MAX_INTERACTIONS = 1000
MAX_POST_HISTORY = 50
MAX_INSIGHTS = 30
SUMMARY_MAX_LENGTH = 200
KNOWLEDGE_CONTEXT_MAX = 500


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


def _truncate(text: str, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _set_file_permissions(path: Path) -> None:
    """Set file permissions to 0600 (owner read/write only)."""
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


# ---------------------------------------------------------------------------
# Layer 1: EpisodeLog — append-only daily JSONL
# ---------------------------------------------------------------------------


class EpisodeLog:
    """Append-only episode log stored as daily JSONL files.

    Each line: {"ts": "ISO8601", "type": "interaction|post|activity|insight", "data": {...}}
    """

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self._log_dir = log_dir or EPISODE_LOG_DIR

    def _today_path(self) -> Path:
        return self._log_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"

    def _path_for_date(self, date_str: str) -> Path:
        return self._log_dir / f"{date_str}.jsonl"

    def append(self, record_type: str, data: Dict[str, Any]) -> None:
        """Append a record immediately to today's log file."""
        self._log_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": record_type,
            "data": data,
        }
        path = self._today_path()
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            _set_file_permissions(path)
        except OSError as exc:
            logger.warning("Failed to write episode log: %s", exc)

    def read_today(self) -> List[Dict[str, Any]]:
        """Read all records from today's log."""
        return self._read_file(self._today_path())

    def read_range(self, days: int = 1) -> List[Dict[str, Any]]:
        """Read records from the last N days."""
        records: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            records.extend(self._read_file(self._path_for_date(date_str)))
        return records

    def cleanup(self, retention_days: Optional[int] = None) -> int:
        """Delete log files older than retention_days. Returns count deleted."""
        retention = retention_days if retention_days is not None else EPISODE_RETENTION_DAYS
        if not self._log_dir.exists():
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
        deleted = 0
        for path in self._log_dir.glob("*.jsonl"):
            match = re.match(r"(\d{4}-\d{2}-\d{2})\.jsonl", path.name)
            if not match:
                continue
            try:
                file_date = datetime.strptime(match.group(1), "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                if file_date < cutoff:
                    path.unlink()
                    deleted += 1
                    logger.debug("Deleted old log: %s", path.name)
            except ValueError:
                continue
        return deleted

    @staticmethod
    def _read_file(path: Path) -> List[Dict[str, Any]]:
        """Read all JSON lines from a single file."""
        if not path.exists():
            return []
        records = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed log line in %s", path.name)
        except OSError as exc:
            logger.warning("Failed to read log file %s: %s", path.name, exc)
        return records


# ---------------------------------------------------------------------------
# Layer 2: KnowledgeStore — distilled Markdown
# ---------------------------------------------------------------------------


class KnowledgeStore:
    """Manages distilled knowledge as a Markdown file.

    Sections:
      ## Agent Relationships
      ## Recent Post Topics
      ## Insights
      ## Learned Patterns
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or KNOWLEDGE_PATH
        self._agents: Dict[str, str] = {}  # agent_id -> name
        self._followed: set[str] = set()
        self._post_topics: List[str] = []
        self._insights: List[str] = []
        self._learned_patterns: List[str] = []

    @property
    def agents(self) -> Dict[str, str]:
        return dict(self._agents)

    @property
    def followed_agents(self) -> set[str]:
        return set(self._followed)

    def record_agent(self, agent_id: str, agent_name: str) -> None:
        self._agents[agent_id] = agent_name

    def record_follow(self, agent_name: str) -> None:
        self._followed.add(agent_name)

    def is_followed(self, agent_name: str) -> bool:
        return agent_name in self._followed

    def add_post_topic(self, topic: str) -> None:
        self._post_topics.append(topic)
        if len(self._post_topics) > MAX_POST_HISTORY:
            self._post_topics = self._post_topics[-MAX_POST_HISTORY:]

    def get_post_topics(self, limit: int = 5) -> List[str]:
        return self._post_topics[-limit:]

    def add_insight(self, observation: str) -> None:
        self._insights.append(observation)
        if len(self._insights) > MAX_INSIGHTS:
            self._insights = self._insights[-MAX_INSIGHTS:]

    def get_insights(self, limit: int = 3) -> List[str]:
        return self._insights[-limit:]

    def add_learned_pattern(self, pattern: str) -> None:
        self._learned_patterns.append(pattern)

    def get_context_string(self) -> str:
        """Return a summary string for LLM context injection (max 500 chars)."""
        parts = []
        if self._agents:
            agent_names = list(self._agents.values())[-5:]
            parts.append(f"Known agents: {', '.join(agent_names)}")
        if self._post_topics:
            recent = self._post_topics[-3:]
            parts.append(f"Recent topics: {'; '.join(recent)}")
        if self._insights:
            parts.append(f"Last insight: {self._insights[-1]}")
        if self._learned_patterns:
            parts.append(f"Pattern: {self._learned_patterns[-1]}")
        result = "\n".join(parts)
        return result[:KNOWLEDGE_CONTEXT_MAX]

    def load(self) -> None:
        """Load knowledge from Markdown file.

        Validates content against forbidden patterns to detect
        tainted data that may have been injected via compromised
        external content during distillation.
        """
        if not self._path.exists():
            logger.debug("No knowledge file at %s", self._path)
            return
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read knowledge file: %s", exc)
            return

        # Validate against forbidden patterns (same as identity.md)
        text_lower = text.lower()
        for pattern in FORBIDDEN_SUBSTRING_PATTERNS:
            if pattern.lower() in text_lower:
                logger.warning(
                    "Knowledge file contains forbidden pattern: %s — "
                    "file may be tainted, skipping load",
                    pattern,
                )
                return

        self._parse_markdown(text)

    def save(self) -> None:
        """Persist knowledge to Markdown file using atomic write."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Knowledge Base\n"]

        lines.append("\n## Agent Relationships\n")
        for agent_id, name in sorted(self._agents.items()):
            followed_mark = " [followed]" if name in self._followed else ""
            lines.append(f"- {name} ({agent_id}){followed_mark}")

        lines.append("\n## Recent Post Topics\n")
        for topic in self._post_topics:
            lines.append(f"- {topic}")

        lines.append("\n## Insights\n")
        for insight in self._insights:
            lines.append(f"- {insight}")

        lines.append("\n## Learned Patterns\n")
        for pattern in self._learned_patterns:
            lines.append(f"- {pattern}")

        content = "\n".join(lines) + "\n"
        tmp_path = self._path.with_suffix(".md.tmp")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            _set_file_permissions(tmp_path)
            os.replace(str(tmp_path), str(self._path))
        except OSError:
            # Clean up temp file on failure
            tmp_path.unlink(missing_ok=True)
            raise

    def _parse_markdown(self, text: str) -> None:
        """Parse sections from the Markdown knowledge file."""
        current_section = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                current_section = stripped[3:].strip()
                continue
            if not stripped.startswith("- "):
                continue
            item = stripped[2:].strip()
            if not item:
                continue

            if current_section == "Agent Relationships":
                self._parse_agent_line(item)
            elif current_section == "Recent Post Topics":
                self._post_topics.append(item)
            elif current_section == "Insights":
                self._insights.append(item)
            elif current_section == "Learned Patterns":
                self._learned_patterns.append(item)

    def _parse_agent_line(self, item: str) -> None:
        """Parse 'AgentName (agent_id) [followed]' format."""
        followed = item.endswith("[followed]")
        if followed:
            item = item[: -len("[followed]")].strip()
        match = re.match(r"^(.+?)\s*\(([^)]+)\)$", item)
        if match:
            name, agent_id = match.group(1).strip(), match.group(2).strip()
            self._agents[agent_id] = name
            if followed:
                self._followed.add(name)


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
            self._legacy_path = path
            log_dir = log_dir or base_dir / "logs"
            knowledge_path = knowledge_path or base_dir / "knowledge.md"
            commented_cache_path = commented_cache_path or base_dir / "commented_cache.json"
        else:
            self._legacy_path = LEGACY_MEMORY_PATH
        self._episodes = EpisodeLog(log_dir=log_dir)
        self._knowledge = KnowledgeStore(path=knowledge_path)
        self._commented_cache_path = commented_cache_path or COMMENTED_CACHE_PATH
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
        """Load memory: try new format first, fall back to legacy migration."""
        knowledge_exists = self._knowledge._path.exists()

        if self._legacy_path.exists() and not knowledge_exists:
            # Legacy file exists but no knowledge.md yet — migrate
            # Migration already populates in-memory lists, so skip episode loading
            self._migrate_legacy()
        else:
            if knowledge_exists:
                self._knowledge.load()
            # Load recent episodes into in-memory interactions for backward compat
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
                    pass
            elif record_type == "post":
                try:
                    self._post_history.append(PostRecord(**data))
                except TypeError:
                    pass
            elif record_type == "insight":
                try:
                    self._insights_list.append(Insight(**data))
                except TypeError:
                    pass

    def _migrate_legacy(self) -> None:
        """Migrate legacy memory.json to 3-layer format."""
        logger.info("Migrating legacy memory.json to 3-layer format")
        try:
            raw = json.loads(self._legacy_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read legacy memory for migration: %s", exc)
            return

        # Migrate known_agents and followed_agents to KnowledgeStore
        for agent_id, name in raw.get("known_agents", {}).items():
            self._knowledge.record_agent(agent_id, name)
        for agent_name in raw.get("followed_agents", []):
            self._knowledge.record_follow(agent_name)

        # Migrate interactions to episode log
        for item in raw.get("interactions", []):
            try:
                interaction = Interaction(**item)
                self._episodes.append("interaction", asdict(interaction))
                self._interactions.append(interaction)
                self._interacted_ids.add(interaction.agent_id)
            except TypeError:
                logger.warning("Skipping malformed interaction during migration")

        # Migrate post_history
        for item in raw.get("post_history", []):
            try:
                record = PostRecord(**item)
                self._episodes.append("post", asdict(record))
                self._post_history.append(record)
                self._knowledge.add_post_topic(record.topic_summary)
            except TypeError:
                logger.warning("Skipping malformed post record during migration")

        # Migrate insights
        for item in raw.get("insights", []):
            try:
                insight = Insight(**item)
                self._episodes.append("insight", asdict(insight))
                self._insights_list.append(insight)
                self._knowledge.add_insight(insight.observation)
            except TypeError:
                logger.warning("Skipping malformed insight during migration")

        # Save knowledge and rename legacy file
        self._knowledge.save()
        backup_path = self._legacy_path.with_suffix(".json.bak")
        self._legacy_path.rename(backup_path)
        logger.info("Legacy migration complete. Backup at %s", backup_path)

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
            content_summary=_truncate(content),
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

    def get_agents_to_follow(self, min_interactions: int = 3) -> List[Tuple[str, str]]:
        """Return (agent_id, agent_name) pairs for agents we interact with
        frequently but haven't followed yet."""
        candidates = []
        for agent_id, agent_name in self._knowledge.agents.items():
            if self.is_followed(agent_name):
                continue
            if self.interaction_count_with(agent_id) >= min_interactions:
                candidates.append((agent_id, agent_name))
        return candidates

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
            topic_summary=_truncate(topic_summary, 100),
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
            observation=_truncate(observation),
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
        if self._commented_cache_path.exists():
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
        if self._commented_cache is None:
            return
        self._commented_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._commented_cache_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(sorted(self._commented_cache), ensure_ascii=False),
                encoding="utf-8",
            )
            _set_file_permissions(tmp_path)
            os.replace(str(tmp_path), str(self._commented_cache_path))
        except OSError as exc:
            logger.warning("Failed to save commented cache: %s", exc)
            tmp_path.unlink(missing_ok=True)

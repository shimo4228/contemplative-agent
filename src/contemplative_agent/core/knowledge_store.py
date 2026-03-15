"""Layer 2: KnowledgeStore — distilled knowledge as Markdown."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from ._io import archive_before_write, write_restricted
from .config import FORBIDDEN_SUBSTRING_PATTERNS

logger = logging.getLogger(__name__)

MAX_POST_HISTORY = 50
MAX_INSIGHTS = 30
KNOWLEDGE_CONTEXT_MAX = 500


class KnowledgeStore:
    """Manages distilled knowledge as a Markdown file.

    Sections:
      ## Agent Relationships
      ## Recent Post Topics
      ## Insights
      ## Learned Patterns
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path
        self._agents: Dict[str, str] = {}  # agent_id -> name
        self._followed: set[str] = set()
        self._post_topics: List[str] = []
        self._insights: List[str] = []
        self._learned_patterns: List[str] = []

    def has_persisted_file(self) -> bool:
        """Check whether the backing Markdown file exists on disk."""
        return self._path is not None and self._path.exists()

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

    def record_unfollow(self, agent_name: str) -> None:
        self._followed.discard(agent_name)

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

    def replace_learned_pattern(self, index: int, pattern: str) -> None:
        """Replace an existing learned pattern at the given index."""
        if 0 <= index < len(self._learned_patterns):
            self._learned_patterns[index] = pattern

    def get_learned_patterns(self) -> List[str]:
        """Return a copy of the learned patterns list."""
        return list(self._learned_patterns)

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
        if self._path is None or not self._path.exists():
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
        if self._path is None:
            logger.debug("No knowledge path configured, skipping save")
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        history_dir = self._path.parent / "history" / "knowledge"
        archive_before_write(self._path, history_dir)
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
            write_restricted(tmp_path, content)
            os.replace(str(tmp_path), str(self._path))
        except OSError as exc:
            logger.error("Failed to save knowledge file: %s", exc)
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

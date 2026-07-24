"""The four stores behind the :class:`~.memory.MemoryStore` facade.

``MemoryStore`` owned four storage surfaces at once — the episode JSONL log,
``knowledge.json``, ``agents.json`` and ``commented_cache.json`` — plus the
in-memory interaction index, post history and comment ledger built on top of
them. Any change to one retention policy meant reading a class that also
answered rate-window queries and social-graph questions.

Each class here owns one surface and one policy. The facade keeps the public
API; these are what it delegates to. They are constructible on their own, which
matches how the CLI subcommands already use ``EpisodeLog`` / ``KnowledgeStore``
directly rather than through the facade.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import (
    Any,
    Literal,
)

from ._io import parse_aware_utc, truncate, write_text_atomic
from .episode_log import EpisodeLog

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


def count_within(
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


class InteractionIndex:
    """In-memory index of who we have talked to, backed by the episode log.

    Owns the interaction list, the O(1) "have we met" set, and the agent-id ->
    name map. Writes go to the episode log immediately; the in-memory list is a
    bounded tail of it.
    """

    _TEST_AGENT_NAMES = frozenset(
        {
            "Agent0",
            "Agent1",
            "Agent2",
            "Agent3",
            "Agent4",
            "Bob",
            "TestAgent",
            "unknown",
            "Agent1 Updated",
        }
    )

    def __init__(self, episodes: EpisodeLog, interaction_cls: type) -> None:
        self._episodes = episodes
        self._interaction_cls = interaction_cls
        self._interactions: list[Any] = []
        self._interacted_ids: set[str] = set()
        self._known_agents: dict[str, str] = {}

    @property
    def known_agents(self) -> dict[str, str]:
        return dict(self._known_agents)

    @property
    def interactions(self) -> list[Any]:
        """The bounded in-memory tail, for window queries by other stores."""
        return self._interactions

    def ingest(self, data: dict) -> bool:
        """Restore one persisted interaction. False when it fails to deserialize."""
        try:
            interaction = self._interaction_cls(**data)
        except TypeError:
            return False
        self._interactions.append(interaction)
        self._interacted_ids.add(interaction.agent_id)
        self._known_agents[interaction.agent_id] = interaction.agent_name
        return True

    def record(
        self,
        timestamp: str,
        agent_id: str,
        agent_name: str,
        post_id: str,
        direction: Literal["sent", "received"],
        content: str,
        interaction_type: Literal["comment", "reply", "post"],
    ) -> Any:
        interaction = self._interaction_cls(
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
        return agent_id in self._interacted_ids

    def unique_agent_count(self) -> int:
        return len(self._known_agents)

    def count(self) -> int:
        return len(self._interactions)

    def top(
        self, limit: int = 20, exclude_ids: Iterable[str] | None = None
    ) -> list[tuple[str, str]]:
        """Top N (agent_id, agent_name) pairs by interaction count.

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


class FollowState:
    """Followed agent names, persisted in ``agents.json``.

    The forbidden-pattern check on load is a trust boundary, not a schema
    check: ``agents.json`` is agent-writable state that ends up shaping later
    prompts, so a file carrying an injection pattern is refused wholesale and
    the in-memory set stays at its safe default rather than partially loading.
    """

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._followed: set[str] = set()

    def load(self) -> None:
        from .config import FORBIDDEN_SUBSTRING_PATTERNS

        if self._path is None or not self._path.exists():
            return
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read agents.json: %s", exc)
            return

        # Validate against forbidden patterns (consistent with knowledge.json)
        text_lower = text.lower()
        for pat in FORBIDDEN_SUBSTRING_PATTERNS:
            if pat.lower() in text_lower:
                logger.warning("agents.json contains forbidden pattern: %s — skipping load", pat)
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

    def save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            json.dumps({"followed": sorted(self._followed)}, ensure_ascii=False, indent=2) + "\n"
        )
        try:
            write_text_atomic(self._path, content)
        except OSError as exc:
            logger.error("Failed to save agents.json: %s", exc)
            raise

    def add(self, agent_name: str) -> None:
        self._followed.add(agent_name)

    def remove(self, agent_name: str) -> None:
        self._followed.discard(agent_name)

    def names(self) -> set:
        return set(self._followed)


class PostHistory:
    """This agent's own posts: a bounded tail plus the self-post rate."""

    def __init__(self, episodes: EpisodeLog, post_record_cls: type) -> None:
        self._episodes = episodes
        self._post_record_cls = post_record_cls
        self._history: list[Any] = []

    def __len__(self) -> int:
        return len(self._history)

    @property
    def history(self) -> list[Any]:
        """The live in-memory tail, for callers that seed or inspect it."""
        return self._history

    def ingest(self, data: dict) -> bool:
        """Restore one persisted post record. False when it fails to deserialize."""
        try:
            self._history.append(self._post_record_cls(**data))
        except TypeError:
            return False
        return True

    def record(
        self,
        timestamp: str,
        post_id: str,
        title: str,
        topic_summary: str,
        content_hash: str,
        verified: bool = True,
    ) -> Any:
        record = self._post_record_cls(
            timestamp=timestamp,
            post_id=post_id,
            title=title,
            topic_summary=truncate(topic_summary, POST_TOPIC_SUMMARY_MAX),
            content_hash=content_hash[:16],
            verified=verified,
        )
        self._history.append(record)
        self._episodes.append("post", asdict(record))

        if len(self._history) > MAX_POST_HISTORY:
            self._history = self._history[-MAX_POST_HISTORY:]

        return record

    def recent(self, limit: int = 50, verified_only: bool = False) -> list[Any]:
        """Recent self-post records (oldest→newest), capped at ``limit``.

        ``verified_only=True`` returns only posts that passed the visibility
        handshake (ADR-0063), so dedup compares a draft against content that was
        actually published — not against pre-fix pending posts nobody saw. Filter
        first, then cap, so the limit counts verified posts (not slots consumed
        by skipped pending ones).
        """
        records = [r for r in self._history if r.verified] if verified_only else self._history
        return list(records[-limit:])

    def rate_7d(self) -> float:
        """Self-post rate (posts/day) over a fixed 7-day trailing window.

        Used by the rate-deficit Lagrangian term in NoveltyGate (ADR-0039):
        when the rate falls below the target, the admit threshold is loosened
        so the gate cannot silently silence the agent.

        Fixed 7-day window (not "since first post") so the regulariser
        semantics stay stable in the cold-start case.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return count_within(self._history, cutoff, lambda _p: True) / 7.0


class CommentLedger:
    """What we have already commented on, and how often, per counterparty.

    Keyed on the counterparty *name* throughout: live feed posts carry
    ``author.name`` but not ``author.id`` (interaction records store
    ``agent_id="unknown"``), so an id-keyed lookup never matched.
    """

    def __init__(
        self,
        episodes: EpisodeLog,
        cache_path: Path | None,
        interactions: InteractionIndex,
    ) -> None:
        self._episodes = episodes
        self._cache_path = cache_path
        self._interactions = interactions
        self._cache: set | None = None

    def count_recent_by_author(self, agent_name: str, hours: int = 24) -> int:
        """Outgoing interactions sent to ``agent_name`` within the last *hours*.

        Feeds the per-author rate limiter in feed_manager that prevents the
        '15 replies to the same linguistics post' phenomenon.
        """
        if not agent_name or agent_name == "unknown":
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return count_within(
            self._interactions.interactions,
            cutoff,
            lambda it: it.direction == "sent" and it.agent_name == agent_name,
        )

    def prior_comment_targets(self, agent_name: str, days: int = 7, limit: int = 7) -> list[str]:
        """``original_post`` bodies of recent comments sent to *agent_name*.

        Used to detect same-author repeat-topic posts (the 30+ Armenian-
        linguistics replays the 2026-04-12 weekly report flagged). Records
        predating the ``target_agent`` field on comments carry no target and
        are silently filtered out.
        """
        if not agent_name or agent_name == "unknown":
            return []
        episodes = self._episodes.read_range(days=days, record_type="activity")
        targets: list[str] = []
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
        """Whether we commented on this post in the last 30 days."""
        return post_id in self._loaded_cache()

    def record_commented(self, post_id: str) -> None:
        self._loaded_cache().add(post_id)

    def save(self) -> None:
        if self._cache is None or self._cache_path is None:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            write_text_atomic(
                self._cache_path,
                json.dumps(sorted(self._cache), ensure_ascii=False),
            )
        except OSError as exc:
            logger.warning("Failed to save commented cache: %s", exc)

    def _loaded_cache(self) -> set:
        if self._cache is None:
            self._cache = self._load_cache()
        return self._cache

    def _load_cache(self) -> set:
        """Load from the cache file, falling back to a JSONL scan."""
        if self._cache_path is not None and self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    logger.debug("Loaded commented cache: %d entries", len(data))
                    return set(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load commented cache: %s", exc)
        return self._build_cache()

    def _build_cache(self) -> set:
        """Rebuild the commented-post set from the episode log."""
        episodes = self._episodes.read_range(days=30)
        return {
            ep["data"]["post_id"]
            for ep in episodes
            if ep.get("type") == "interaction"
            and ep.get("data", {}).get("direction") == "sent"
            and ep.get("data", {}).get("post_id")
        }

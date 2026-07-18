"""Shared session state for agent collaborators.

Provides an explicit contract between the Agent orchestrator and its
collaborators (ReplyHandler, PostPipeline), replacing direct access
to Agent's private attributes.
"""

from __future__ import annotations

import logging
from typing import List, Set

from ...core.config import VALID_ID_PATTERN
from ...core.memory import MemoryStore

logger = logging.getLogger(__name__)

# Bug-audit 2026-07-06 H3: how far back / how many own posts to restore at
# session start. The limit bounds the read-budget cost of the own-post
# comment fallback, which issues one GET per tracked id each cycle.
OWN_POST_SEED_DAYS = 7
OWN_POST_SEED_LIMIT = 10


class SessionContext:
    """Mutable session state shared between Agent and its collaborators.

    Agent creates this at initialization and passes it to ReplyHandler
    and PostPipeline. All shared mutable state lives here so that the
    interface between Agent and collaborators is explicit.
    """

    __slots__ = (
        "memory",
        "commented_posts",
        "own_post_ids",
        "own_agent_id",
        "own_agent_name",
        "actions_taken",
        "_rate_limited",
    )

    def __init__(
        self,
        memory: MemoryStore,
        own_agent_id: str = "",
        own_agent_name: str = "",
    ) -> None:
        self.memory: MemoryStore = memory
        self.commented_posts: Set[str] = set()
        self.own_post_ids: Set[str] = set()
        self.own_agent_id: str = own_agent_id
        self.own_agent_name: str = own_agent_name
        self.actions_taken: List[str] = []
        self._rate_limited: bool = False

    def is_self(self, author_id: str, author_name: str) -> bool:
        """True when the counterparty is this agent (id or name match).

        Live feed/notification data carries the author *name* but not the
        author *id* (ADR-0055: 271/271 records with agent_id="unknown"), so
        the name compare is the operative key; the id compare is kept as
        belt-and-braces for a future API that ships ids. Sentinel values
        never match: a counterparty ""/"unknown" (extract_agent_fields
        default) and empty own fields each make the corresponding clause a
        no-op. Exact match by design — normalization would widen the false
        self-match surface (silently muting a distinct agent). Accepted
        risk, same as the author-history gates: a stranger sharing this
        agent's display name is skipped (bug-audit 2026-07-06 M6).
        """
        if self.own_agent_id and author_id and author_id == self.own_agent_id:
            return True
        return bool(
            self.own_agent_name
            and author_name
            and author_name != "unknown"
            and author_name == self.own_agent_name
        )

    def seed_own_post_ids(
        self,
        days: int = OWN_POST_SEED_DAYS,
        limit: int = OWN_POST_SEED_LIMIT,
    ) -> int:
        """Restore own post ids from the episode log at session start.

        ``own_post_ids`` previously started empty every session (a plain
        in-memory set), so the own-post comment fallback had zero coverage
        of posts made in prior sessions — a reply landing on an older post
        was never discovered when the /home activity feed missed it
        (bug-audit 2026-07-06 H3). Seeds the most recent *limit* post ids
        from the last *days* days of "activity" episodes.

        Returns the number of ids seeded.
        """
        records = self.memory.episodes.read_range(days=days, record_type="activity")
        # read_range interleaves days (today's file first, chronological
        # within each file) — sort by ISO timestamp to pick the true most
        # recent posts before applying the limit.
        posts: List[tuple[str, str]] = []
        for rec in records:
            data = rec.get("data") or {}
            if data.get("action") != "post":
                continue
            post_id = data.get("post_id")
            # Episode logs are an untrusted-data boundary (project threat
            # model): re-validate ids locally instead of trusting that every
            # writer of "post" records already did (security review
            # 2026-07-06 — defense in depth).
            if isinstance(post_id, str) and post_id and VALID_ID_PATTERN.match(post_id):
                posts.append((str(rec.get("ts") or ""), post_id))
        posts.sort(reverse=True)
        seeded: List[str] = []
        for _ts, post_id in posts:
            if post_id not in seeded:
                seeded.append(post_id)
            if len(seeded) >= limit:
                break
        self.own_post_ids.update(seeded)
        if seeded:
            logger.info(
                "Restored %d own post id(s) from episode log (last %dd)",
                len(seeded),
                days,
            )
        return len(seeded)

    @property
    def is_rate_limited(self) -> bool:
        return self._rate_limited

    def set_rate_limited(self) -> None:
        self._rate_limited = True
        logger.warning("Rate limited — pausing write operations")

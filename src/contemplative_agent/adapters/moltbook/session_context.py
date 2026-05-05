"""Shared session state for agent collaborators.

Provides an explicit contract between the Agent orchestrator and its
collaborators (ReplyHandler, PostPipeline), replacing direct access
to Agent's private attributes.
"""

from __future__ import annotations

import logging
from typing import List, Set

from ...core.memory import MemoryStore

logger = logging.getLogger(__name__)


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
        "actions_taken",
        "_rate_limited",
    )

    def __init__(
        self,
        memory: MemoryStore,
        own_agent_id: str = "",
    ) -> None:
        self.memory: MemoryStore = memory
        self.commented_posts: Set[str] = set()
        self.own_post_ids: Set[str] = set()
        self.own_agent_id: str = own_agent_id
        self.actions_taken: List[str] = []
        self._rate_limited: bool = False

    @property
    def is_rate_limited(self) -> bool:
        return self._rate_limited

    def set_rate_limited(self) -> None:
        self._rate_limited = True
        logger.warning("Rate limited — pausing write operations")

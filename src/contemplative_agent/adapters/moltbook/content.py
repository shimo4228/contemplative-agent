"""Content templates and generation for Moltbook posts."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional, Set

from .llm_functions import generate_comment, generate_cooperation_post

logger = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    """SHA-256 hash of content for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class ContentManager:
    """Manages content generation and deduplication."""

    def __init__(self) -> None:
        self._posted_hashes: Set[str] = set()
        self._comment_count = 0
        self._post_count = 0

    @property
    def comment_to_post_ratio(self) -> float:
        if self._post_count == 0:
            return float(self._comment_count)
        return self._comment_count / self._post_count

    def is_duplicate(self, content: str) -> bool:
        """Read-only dedup check. Does NOT record the hash.

        Recording is deferred to ``mark_posted`` on the confirmed-and-posted
        success path, so a comment/post that is rejected by the approval gate or
        fails to publish does not poison the in-session cache and silently drop a
        legitimate same-session retry of the same text.
        """
        return _content_hash(content) in self._posted_hashes

    def mark_posted(self, content: str) -> None:
        """Record content as posted, so a later identical text is deduped."""
        self._posted_hashes.add(_content_hash(content))

    def create_comment(self, post_text: str) -> Optional[str]:
        comment = generate_comment(post_text)
        if comment is None:
            return None
        if self.is_duplicate(comment):
            logger.info("Duplicate comment skipped")
            return None
        self._comment_count += 1
        return comment

    def create_cooperation_post(
        self,
        feed_seeds: list[dict],
    ) -> Optional[str]:
        post = generate_cooperation_post(feed_seeds)
        if post is None:
            return None
        if self.is_duplicate(post):
            logger.info("Duplicate cooperation post skipped")
            return None
        self._post_count += 1
        return post

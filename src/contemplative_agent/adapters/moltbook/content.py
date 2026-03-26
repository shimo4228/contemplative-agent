"""Content templates and generation for Moltbook posts."""

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

    def _is_duplicate(self, content: str) -> bool:
        h = _content_hash(content)
        if h in self._posted_hashes:
            return True
        self._posted_hashes.add(h)
        return False

    def create_comment(self, post_text: str) -> Optional[str]:
        comment = generate_comment(post_text)
        if comment is None:
            return None
        if self._is_duplicate(comment):
            logger.info("Duplicate comment skipped")
            return None
        self._comment_count += 1
        return comment

    def create_cooperation_post(
        self,
        feed_topics: str,
        recent_insights: Optional[list[str]] = None,
    ) -> Optional[str]:
        post = generate_cooperation_post(
            feed_topics, recent_insights=recent_insights,
        )
        if post is None:
            return None
        if self._is_duplicate(post):
            logger.info("Duplicate cooperation post skipped")
            return None
        self._post_count += 1
        return post

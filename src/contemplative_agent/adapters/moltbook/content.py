"""Content templates and generation for Moltbook posts."""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Set

from ...core.domain import DomainConfig, get_domain_config, get_rules, resolve_prompt
from .llm_functions import generate_comment, generate_cooperation_post

logger = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    """SHA-256 hash of content for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _resolve_introduction(domain_config: DomainConfig) -> str:
    """Resolve placeholders in the introduction template."""
    rules = get_rules()
    return resolve_prompt(rules.introduction, domain_config)


# ---------------------------------------------------------------------------
# Backward-compatible module-level constant (lazy-loaded)
# ---------------------------------------------------------------------------

class _LazyContent:
    """Lazy proxy for INTRODUCTION_TEMPLATE."""

    def __init__(self) -> None:
        self._loaded = False
        self._introduction: str = ""

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            domain_config = get_domain_config()
            self._introduction = _resolve_introduction(domain_config)
            self._loaded = True

    @property
    def introduction(self) -> str:
        self._ensure_loaded()
        return self._introduction


_lazy_content = _LazyContent()


def _get_introduction_template() -> str:
    return _lazy_content.introduction


# Module-level backward-compatible access
def __getattr__(name: str) -> object:
    if name == "INTRODUCTION_TEMPLATE":
        return _get_introduction_template()
    raise AttributeError(f"module 'content' has no attribute {name!r}")


class ContentManager:
    """Manages content generation and deduplication."""

    def __init__(
        self,
        rules_dir: Optional[Path] = None,
        domain_config: Optional[DomainConfig] = None,
    ) -> None:
        self._posted_hashes: Set[str] = set()
        self._comment_count = 0
        self._post_count = 0

        # Load rules and resolve introduction
        if rules_dir is not None or domain_config is not None:
            from ...core.domain import load_rules

            rules = load_rules(rules_dir) if rules_dir else get_rules()
            config = domain_config or get_domain_config()
            self._introduction = resolve_prompt(rules.introduction, config)
        else:
            self._introduction = _get_introduction_template()

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

    def get_introduction(self) -> Optional[str]:
        if self._is_duplicate(self._introduction):
            logger.info("Introduction already posted")
            return None
        self._post_count += 1
        return self._introduction

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
        knowledge_context: Optional[str] = None,
    ) -> Optional[str]:
        post = generate_cooperation_post(
            feed_topics, recent_insights=recent_insights,
            knowledge_context=knowledge_context,
        )
        if post is None:
            return None
        if self._is_duplicate(post):
            logger.info("Duplicate cooperation post skipped")
            return None
        self._post_count += 1
        return post

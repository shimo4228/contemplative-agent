"""Content templates and generation for Moltbook posts."""

import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional, Set

from ...domain import DomainConfig, RulesContent, get_domain_config, get_rules, resolve_prompt
from .llm_functions import generate_comment, generate_cooperation_post

logger = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    """SHA-256 hash of content for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _resolve_rules_content(
    rules: RulesContent, domain_config: DomainConfig
) -> tuple[str, Dict[str, str]]:
    """Resolve placeholders in rules content, returning (introduction, axioms)."""
    introduction = resolve_prompt(rules.introduction, domain_config)
    axiom_templates = {
        key: resolve_prompt(template, domain_config)
        for key, template in rules.axiom_templates.items()
    }
    return introduction, axiom_templates


# ---------------------------------------------------------------------------
# Backward-compatible module-level constants (lazy-loaded)
# ---------------------------------------------------------------------------

class _LazyContent:
    """Lazy proxy for INTRODUCTION_TEMPLATE and AXIOM_TEMPLATES."""

    def __init__(self) -> None:
        self._loaded = False
        self._introduction: str = ""
        self._axiom_templates: Dict[str, str] = {}

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            rules = get_rules()
            domain_config = get_domain_config()
            self._introduction, self._axiom_templates = _resolve_rules_content(
                rules, domain_config
            )
            self._loaded = True

    @property
    def introduction(self) -> str:
        self._ensure_loaded()
        return self._introduction

    @property
    def axiom_templates(self) -> Dict[str, str]:
        self._ensure_loaded()
        return self._axiom_templates


_lazy_content = _LazyContent()


def _get_introduction_template() -> str:
    return _lazy_content.introduction


def _get_axiom_templates() -> Dict[str, str]:
    return _lazy_content.axiom_templates


# Module-level backward-compatible access
def __getattr__(name: str) -> object:
    if name == "INTRODUCTION_TEMPLATE":
        return _get_introduction_template()
    if name == "AXIOM_TEMPLATES":
        return _get_axiom_templates()
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

        # Load rules and resolve placeholders
        if rules_dir is not None or domain_config is not None:
            from ...domain import load_rules

            rules = load_rules(rules_dir) if rules_dir else get_rules()
            config = domain_config or get_domain_config()
            self._introduction, self._axiom_templates = _resolve_rules_content(
                rules, config
            )
        else:
            self._introduction = _get_introduction_template()
            self._axiom_templates = _get_axiom_templates()

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

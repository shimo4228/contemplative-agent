"""Prompt templates for LLM interactions.

Templates are loaded from config/prompts/*.md files via the domain module.
Module-level constants are preserved as lazy-loading properties for
backward compatibility.
"""

from __future__ import annotations


def _load_template(attr: str) -> str:
    """Lazy-load a prompt template from config/prompts/."""
    from .domain import get_prompt_templates

    templates = get_prompt_templates()
    return getattr(templates, attr)


class _LazyPrompts:
    """Module-level proxy that lazy-loads prompt templates on first access."""

    _ATTR_MAP = {
        "SYSTEM_PROMPT": "system",
        "RELEVANCE_PROMPT": "relevance",
        "COMMENT_PROMPT": "comment",
        "COOPERATION_POST_PROMPT": "cooperation_post",
        "REPLY_PROMPT": "reply",
        "POST_TITLE_PROMPT": "post_title",
        "TOPIC_EXTRACTION_PROMPT": "topic_extraction",
        "TOPIC_NOVELTY_PROMPT": "topic_novelty",
        "TOPIC_SUMMARY_PROMPT": "topic_summary",
        "SUBMOLT_SELECTION_PROMPT": "submolt_selection",
        "SESSION_INSIGHT_PROMPT": "session_insight",
        "DISTILL_PROMPT": "distill",
        "EVAL_PROMPT": "eval",
    }

    def __getattr__(self, name: str) -> str:
        if name in self._ATTR_MAP:
            value = _load_template(self._ATTR_MAP[name])
            # Cache on the instance to avoid repeated loading
            object.__setattr__(self, name, value)
            return value
        raise AttributeError(f"module 'prompts' has no attribute {name!r}")


_lazy = _LazyPrompts()

# Expose all prompt constants as module-level attributes via __getattr__
def __getattr__(name: str) -> str:
    return getattr(_lazy, name)

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
        "IDENTITY_DISTILL_PROMPT": "identity_distill",
        "INSIGHT_EXTRACTION_PROMPT": "insight_extraction",
        "MEDITATION_INTERPRET_PROMPT": "meditation_interpret",
        "DISTILL_REFINE_PROMPT": "distill_refine",
        "DISTILL_IMPORTANCE_PROMPT": "distill_importance",
        "IDENTITY_REFINE_PROMPT": "identity_refine",
        "RULES_DISTILL_PROMPT": "rules_distill",
        "RULES_DISTILL_REFINE_PROMPT": "rules_distill_refine",
        "DISTILL_DEDUP_PROMPT": "distill_dedup",
        "DISTILL_CLASSIFY_PROMPT": "distill_classify",
        "DISTILL_CONSTITUTIONAL_PROMPT": "distill_constitutional",
        "CONSTITUTION_AMEND_PROMPT": "constitution_amend",
        "STOCKTAKE_SKILLS_PROMPT": "stocktake_skills",
        "STOCKTAKE_RULES_PROMPT": "stocktake_rules",
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

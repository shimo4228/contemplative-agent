"""Prompt templates for LLM interactions.

Templates are loaded from config/prompts/*.md files via the domain module.
Module-level constants are preserved as lazy-loading properties for
backward compatibility.
"""

from __future__ import annotations

# The constant name IS the field name: ``<FIELD>_PROMPT`` uppercased. These two
# predate that rule and keep their own spelling; everything else is derived, so
# a new prompt is declared once (the PromptTemplates field) rather than three
# times.
_ATTR_ALIASES = {
    "STOCKTAKE_DESC_PROMPT": "stocktake_description",
    "STOCKTAKE_DESC_SYSTEM_PROMPT": "stocktake_description_system",
}

_cache: dict[str, str] = {}


def _template_attr(name: str) -> str | None:
    """The ``PromptTemplates`` field a module constant names, else ``None``.

    Derivation is checked against the dataclass so the exported set stays
    closed: an unknown ``FOO_PROMPT`` raises AttributeError here rather than
    reaching ``getattr`` on the templates.
    """
    from dataclasses import fields

    from .domain import PromptTemplates

    alias = _ATTR_ALIASES.get(name)
    if alias is not None:
        return alias
    if not name.endswith("_PROMPT"):
        return None
    attr = name[: -len("_PROMPT")].lower()
    return attr if attr in {f.name for f in fields(PromptTemplates)} else None


def __getattr__(name: str) -> str:
    """Lazy-load a prompt template from config/prompts/ on first access."""
    cached = _cache.get(name)
    if cached is not None:
        return cached
    attr = _template_attr(name)
    if attr is None:
        raise AttributeError(f"module 'prompts' has no attribute {name!r}")

    from .domain import get_prompt_templates

    value: str = getattr(get_prompt_templates(), attr)
    _cache[name] = value
    return value

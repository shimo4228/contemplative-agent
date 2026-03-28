"""Domain configuration and prompt template loading.

Loads domain-specific settings from JSON and prompt templates from .md files,
enabling domain switching by pointing to different config directories.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .config import FORBIDDEN_SUBSTRING_PATTERNS

logger = logging.getLogger(__name__)

# Default config directory relative to the package root (overridable via env var).
# config/ holds templates only (prompts, domain.json, templates/).
# Runtime data (identity, knowledge, constitution, ...) lives in MOLTBOOK_HOME.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CONFIG_DIR_OVERRIDE = os.environ.get("CONTEMPLATIVE_CONFIG_DIR")
DEFAULT_CONFIG_DIR = Path(_CONFIG_DIR_OVERRIDE) if _CONFIG_DIR_OVERRIDE else _PROJECT_ROOT / "config"
DEFAULT_DOMAIN_CONFIG_PATH = DEFAULT_CONFIG_DIR / "domain.json"
DEFAULT_PROMPTS_DIR = DEFAULT_CONFIG_DIR / "prompts"


@dataclass(frozen=True)
class DomainConfig:
    """Domain-specific configuration loaded from domain.json."""

    name: str
    description: str
    topic_keywords: Tuple[str, ...]
    subscribed_submolts: Tuple[str, ...]
    default_submolt: str
    relevance_threshold: float
    known_agent_threshold: float
    repo_url: str

    @property
    def topic_keywords_str(self) -> str:
        """Format topic keywords for prompt insertion."""
        return ", ".join(self.topic_keywords)


@dataclass(frozen=True)
class PromptTemplates:
    """All prompt templates loaded from .md files."""

    system: str
    relevance: str
    comment: str
    cooperation_post: str
    reply: str
    post_title: str
    topic_extraction: str
    topic_novelty: str
    topic_summary: str
    submolt_selection: str
    session_insight: str
    distill: str
    identity_distill: str = ""
    insight_extraction: str = ""
    insight_eval: str = ""
    meditation_interpret: str = ""
    distill_refine: str = ""
    distill_importance: str = ""
    identity_refine: str = ""
    rules_distill: str = ""
    rules_distill_refine: str = ""
    distill_dedup: str = ""
    distill_classify: str = ""
    distill_constitutional: str = ""
    constitution_amend: str = ""
    stocktake_skills: str = ""
    stocktake_rules: str = ""



def load_domain_config(path: Optional[Path] = None) -> DomainConfig:
    """Load and validate domain configuration from JSON.

    Args:
        path: Path to domain.json. Defaults to config/domain.json.

    Returns:
        Validated DomainConfig instance.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If required fields are missing or invalid.
    """
    config_path = path or DEFAULT_DOMAIN_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Domain config not found: {config_path}")

    raw = config_path.read_text(encoding="utf-8")

    # Validate against forbidden patterns
    raw_lower = raw.lower()
    for pattern in FORBIDDEN_SUBSTRING_PATTERNS:
        if pattern.lower() in raw_lower:
            raise ValueError(
                f"Domain config contains forbidden pattern: {pattern}"
            )

    data = json.loads(raw)

    required_keys = ("name", "description", "topic_keywords", "submolts", "thresholds")
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise ValueError(f"Domain config missing required keys: {missing}")

    submolts = data["submolts"]
    thresholds = data["thresholds"]

    return DomainConfig(
        name=data["name"],
        description=data["description"],
        topic_keywords=tuple(data["topic_keywords"]),
        subscribed_submolts=tuple(submolts.get("subscribed", [])),
        default_submolt=submolts.get("default", "alignment"),
        relevance_threshold=float(thresholds.get("relevance", 0.82)),
        known_agent_threshold=float(thresholds.get("known_agent", 0.65)),
        repo_url=data.get("repo_url", ""),
    )


def _read_md_file(path: Path, required: bool = True) -> str:
    """Read a markdown file and return its content stripped."""
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Prompt template not found: {path}")
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if not content and required:
        raise ValueError(f"Prompt template is empty: {path}")
    return content


def load_prompt_templates(prompts_dir: Optional[Path] = None) -> PromptTemplates:
    """Load all prompt templates from a directory of .md files.

    Args:
        prompts_dir: Directory containing prompt .md files.
                     Defaults to config/prompts/.

    Returns:
        PromptTemplates with all templates loaded.

    Raises:
        FileNotFoundError: If directory or required files don't exist.
    """
    directory = prompts_dir or DEFAULT_PROMPTS_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Prompts directory not found: {directory}")

    return PromptTemplates(
        system=_read_md_file(directory / "system.md"),
        relevance=_read_md_file(directory / "relevance.md"),
        comment=_read_md_file(directory / "comment.md"),
        cooperation_post=_read_md_file(directory / "cooperation_post.md"),
        reply=_read_md_file(directory / "reply.md"),
        post_title=_read_md_file(directory / "post_title.md"),
        topic_extraction=_read_md_file(directory / "topic_extraction.md"),
        topic_novelty=_read_md_file(directory / "topic_novelty.md"),
        topic_summary=_read_md_file(directory / "topic_summary.md"),
        submolt_selection=_read_md_file(directory / "submolt_selection.md"),
        session_insight=_read_md_file(directory / "session_insight.md"),
        distill=_read_md_file(directory / "distill.md"),
        identity_distill=_read_md_file(directory / "identity_distill.md", required=False),
        insight_extraction=_read_md_file(directory / "insight_extraction.md", required=False),
        insight_eval=_read_md_file(directory / "insight_eval.md", required=False),
        meditation_interpret=_read_md_file(directory / "meditation_interpret.md", required=False),
        distill_refine=_read_md_file(directory / "distill_refine.md", required=False),
        distill_importance=_read_md_file(directory / "distill_importance.md", required=False),
        identity_refine=_read_md_file(directory / "identity_refine.md", required=False),
        rules_distill=_read_md_file(directory / "rules_distill.md", required=False),
        rules_distill_refine=_read_md_file(directory / "rules_distill_refine.md", required=False),
        distill_dedup=_read_md_file(directory / "distill_dedup.md", required=False),
        distill_classify=_read_md_file(directory / "distill_classify.md", required=False),
        distill_constitutional=_read_md_file(directory / "distill_constitutional.md", required=False),
        constitution_amend=_read_md_file(directory / "constitution_amend.md", required=False),
    )


def load_constitution(constitution_dir: Optional[Path] = None) -> str:
    """Load constitutional clauses from a constitution directory.

    Loads contemplative-axioms.md (CCAI Appendix C) with forbidden-pattern
    validation. Constitution is separate from rules: rules are behavioral
    and measurable; constitution is attitudinal and provides a cognitive lens.

    Args:
        constitution_dir: Directory containing constitution .md files.
                         No default — caller must provide the path.

    Returns:
        Constitutional clauses as a string (empty if not found).

    Raises:
        ValueError: If clauses contain forbidden patterns.
    """
    if constitution_dir is None:
        return ""
    directory = constitution_dir
    if not directory.is_dir():
        return ""

    clauses_path = directory / "contemplative-axioms.md"
    if not clauses_path.exists():
        return ""

    raw = clauses_path.read_text(encoding="utf-8").strip()
    if not raw:
        return ""

    raw_lower = raw.lower()
    for pattern in FORBIDDEN_SUBSTRING_PATTERNS:
        if pattern.lower() in raw_lower:
            raise ValueError(
                f"Constitutional clauses contain forbidden pattern: {pattern}"
            )
    return raw


def resolve_prompt(
    template: str,
    domain_config: DomainConfig,
    **extra_vars: str,
) -> str:
    """Expand domain placeholders in a prompt template.

    Replaces {domain_name}, {topic_keywords}, {repo_url} with values
    from the DomainConfig. Additional variables can be passed as kwargs.

    Uses str.format_map with a defaulting dict so that unresolved
    placeholders (like {post_content}) are left intact for later formatting.
    """

    class _DefaultDict(dict):
        """Dict that returns the key wrapped in braces for missing keys."""
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    variables = _DefaultDict(
        domain_name=domain_config.name,
        topic_keywords=domain_config.topic_keywords_str,
        repo_url=domain_config.repo_url,
    )
    variables.update(extra_vars)
    return template.format_map(variables)


# ---------------------------------------------------------------------------
# Module-level lazy singletons for backward compatibility
# ---------------------------------------------------------------------------

_cached_domain_config: Optional[DomainConfig] = None
_cached_prompt_templates: Optional[PromptTemplates] = None


def get_domain_config(path: Optional[Path] = None) -> DomainConfig:
    """Get or load the domain config (cached singleton)."""
    global _cached_domain_config
    if _cached_domain_config is None:
        _cached_domain_config = load_domain_config(path)
    return _cached_domain_config


def get_prompt_templates(prompts_dir: Optional[Path] = None) -> PromptTemplates:
    """Get or load prompt templates (cached singleton)."""
    global _cached_prompt_templates
    if _cached_prompt_templates is None:
        _cached_prompt_templates = load_prompt_templates(prompts_dir)
    return _cached_prompt_templates


def set_domain_config_cache(config: DomainConfig) -> None:
    """Set the cached domain config directly. Used by CLI for --domain-config override."""
    global _cached_domain_config
    _cached_domain_config = config


def reset_caches() -> None:
    """Reset all cached singletons. Useful for testing."""
    global _cached_domain_config, _cached_prompt_templates
    _cached_domain_config = None
    _cached_prompt_templates = None

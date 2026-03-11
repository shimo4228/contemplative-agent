"""Domain configuration and prompt template loading.

Loads domain-specific settings from JSON and prompt templates from .md files,
enabling domain switching by pointing to different config directories.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .config import FORBIDDEN_SUBSTRING_PATTERNS

logger = logging.getLogger(__name__)

# Default config directory relative to the package root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_CONFIG_DIR = _PROJECT_ROOT / "config"
DEFAULT_DOMAIN_CONFIG_PATH = DEFAULT_CONFIG_DIR / "domain.json"
DEFAULT_PROMPTS_DIR = DEFAULT_CONFIG_DIR / "prompts"
DEFAULT_RULES_DIR = DEFAULT_CONFIG_DIR / "rules" / "contemplative"


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
    eval: str


@dataclass(frozen=True)
class RulesContent:
    """Domain-specific rule/content templates loaded from rules directory."""

    introduction: str
    constitutional_clauses: str = ""


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


def _read_md_file(path: Path) -> str:
    """Read a markdown file and return its content stripped."""
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
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
        eval=_read_md_file(directory / "eval.md"),
    )


def load_rules(rules_dir: Optional[Path] = None) -> RulesContent:
    """Load domain-specific rule templates from a rules directory.

    The directory should contain .md files. 'introduction.md' is loaded
    separately; all other .md files are treated as axiom/topic templates.

    Args:
        rules_dir: Directory containing rule .md files.
                   Defaults to config/rules/contemplative/.

    Returns:
        RulesContent with introduction and axiom templates.

    Raises:
        FileNotFoundError: If directory doesn't exist.
    """
    directory = rules_dir or DEFAULT_RULES_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Rules directory not found: {directory}")

    introduction_path = directory / "introduction.md"
    introduction = ""
    if introduction_path.exists():
        introduction = introduction_path.read_text(encoding="utf-8").strip()

    # Load CCAI constitutional clauses (Appendix C) with forbidden-pattern validation
    clauses = ""
    clauses_path = directory / "contemplative-axioms.md"
    if clauses_path.exists():
        raw = clauses_path.read_text(encoding="utf-8").strip()
        if raw:
            raw_lower = raw.lower()
            for pattern in FORBIDDEN_SUBSTRING_PATTERNS:
                if pattern.lower() in raw_lower:
                    raise ValueError(
                        f"Constitutional clauses contain forbidden pattern: {pattern}"
                    )
            clauses = raw

    return RulesContent(
        introduction=introduction,
        constitutional_clauses=clauses,
    )


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
_cached_rules: Optional[RulesContent] = None


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


def get_rules(rules_dir: Optional[Path] = None) -> RulesContent:
    """Get or load rules content (cached singleton)."""
    global _cached_rules
    if _cached_rules is None:
        _cached_rules = load_rules(rules_dir)
    return _cached_rules


def set_domain_config_cache(config: DomainConfig) -> None:
    """Set the cached domain config directly. Used by CLI for --domain-config override."""
    global _cached_domain_config
    _cached_domain_config = config


def set_rules_cache(rules: RulesContent) -> None:
    """Set the cached rules directly. Used by CLI for --rules-dir override."""
    global _cached_rules
    _cached_rules = rules


def reset_caches() -> None:
    """Reset all cached singletons. Useful for testing."""
    global _cached_domain_config, _cached_prompt_templates, _cached_rules
    _cached_domain_config = None
    _cached_prompt_templates = None
    _cached_rules = None

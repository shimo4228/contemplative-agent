"""Domain configuration and prompt template loading.

Loads domain-specific settings from JSON and prompt templates from .md files,
enabling domain switching by pointing to different config directories.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import MISSING, dataclass, fields
from pathlib import Path

from ._io import strip_to_printable
from .config import first_forbidden_substring

logger = logging.getLogger(__name__)

# Default config directory relative to the package root (overridable via env var).
# config/ holds templates only (prompts, domain.json, templates/).
# Runtime data (identity, knowledge, constitution, ...) lives in MOLTBOOK_HOME.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CONFIG_DIR_OVERRIDE = os.environ.get("CONTEMPLATIVE_CONFIG_DIR")
DEFAULT_CONFIG_DIR = (
    Path(_CONFIG_DIR_OVERRIDE) if _CONFIG_DIR_OVERRIDE else _PROJECT_ROOT / "config"
)
DEFAULT_DOMAIN_CONFIG_PATH = DEFAULT_CONFIG_DIR / "domain.json"
DEFAULT_PROMPTS_DIR = DEFAULT_CONFIG_DIR / "prompts"


@dataclass(frozen=True)
class DomainConfig:
    """Domain-specific configuration loaded from domain.json."""

    name: str
    description: str
    subscribed_submolts: tuple[str, ...]
    default_submolt: str
    relevance_threshold: float
    known_agent_threshold: float
    repo_url: str


@dataclass(frozen=True)
class PromptTemplates:
    """All prompt templates loaded from .md files."""

    system: str
    relevance: str
    comment: str
    cooperation_post: str
    reply: str
    reply_post_block: str
    post_title: str
    topic_summary: str
    submolt_selection: str
    internal_note: str = ""
    identity_distill: str = ""
    insight_extraction: str = ""
    insight_novelty: str = ""
    insight_novelty_system: str = ""
    meditation_interpret: str = ""
    distill_episode: str = ""
    distill_postgate: str = ""
    constitution_amend: str = ""
    constitution_synthesize: str = ""
    stocktake_merge_rules: str = ""
    stocktake_description: str = ""
    untrusted_wrapper: str = ""
    untrusted_marker_complete: str = ""
    untrusted_marker_truncated: str = ""
    stocktake_description_system: str = ""
    dialogue: str = ""
    verification_solve_extract_system: str = ""
    learned_skills_framing: str = ""
    learned_rules_framing: str = ""
    skill_selection: str = ""
    insight_revision_reason: str = ""
    insight_revision_generation: str = ""


def _warn_unknown_keys(section: str, mapping: object, allowed: set[str]) -> None:
    """WARN on unrecognized sub-keys in a domain-config section (H7).

    Keys are sanitized before logging (security review 2026-07-06): a shared
    or downloaded domain config could otherwise smuggle control characters /
    newlines into WARNING lines that log_anomaly_sweep consumes.
    """
    if not isinstance(mapping, dict):
        return
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        safe_keys = [strip_to_printable(k, 80) for k in unknown]
        logger.warning(
            "Domain config %r has unknown key(s) %s (allowed: %s) — "
            "misspelled keys silently fall back to packaged defaults",
            section,
            safe_keys,
            sorted(allowed),
        )


def load_domain_config(path: Path | None = None) -> DomainConfig:
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
    found = first_forbidden_substring(raw)
    if found is not None:
        raise ValueError(f"Domain config contains forbidden pattern: {found}")

    data = json.loads(raw)

    required_keys = ("name", "description", "submolts", "thresholds")
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise ValueError(f"Domain config missing required keys: {missing}")

    submolts = data["submolts"]
    thresholds = data["thresholds"]

    # Bug-audit 2026-07-06 H7: a typo'd sub-key ("relevence", "defualt", …)
    # previously fell back to the packaged default with zero signal, so the
    # agent's live engagement gates silently diverged from the reviewed
    # config. Unknown sub-keys are almost certainly misspellings — warn
    # loudly (log_anomaly_sweep catches WARNING-level lines).
    _warn_unknown_keys("thresholds", thresholds, {"relevance", "known_agent"})
    _warn_unknown_keys("submolts", submolts, {"subscribed", "default"})

    return DomainConfig(
        name=data["name"],
        description=data["description"],
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


def _resolve_home_prompts_dir() -> Path | None:
    """Return ``$MOLTBOOK_HOME/prompts/`` if it exists, else None.

    A non-existent home directory means no override layer is active and
    callers should read from the packaged defaults.
    """
    home = os.environ.get("MOLTBOOK_HOME")
    if not home:
        return None
    candidate = Path(home) / "prompts"
    return candidate if candidate.is_dir() else None


def _read_prompt_with_fallback(
    name: str,
    base_dir: Path,
    home_dir: Path | None,
    *,
    required: bool = True,
) -> str:
    """Read a prompt, preferring the home override when present.

    Precedence: ``$MOLTBOOK_HOME/prompts/<name>`` → ``base_dir/<name>``.

    Home overrides are validated against the forbidden-pattern list so a
    tampered override cannot inject system-prompt-level instructions
    outside the security boundary (same check that ``identity.md``
    content passes through in ``core/llm.py``). A failed validation
    logs a warning and falls back to the packaged default.
    """
    if home_dir is not None:
        override = home_dir / name
        if override.is_file():
            try:
                content = _read_md_file(override, required=required)
            except ValueError:
                logger.warning(
                    "Home prompt override %s is empty; using packaged default",
                    override,
                )
            else:
                # Lazy import to avoid circular dependency: core.llm imports from core.config.
                from .llm import validate_identity_content

                if content and not validate_identity_content(content):
                    logger.warning(
                        "Home prompt override %s failed pattern validation; using packaged default",
                        override,
                    )
                else:
                    return content
    return _read_md_file(base_dir / name, required=required)


def load_prompt_templates(prompts_dir: Path | None = None) -> PromptTemplates:
    """Load all prompt templates from a directory of .md files.

    Precedence for each template:

    1. ``prompts_dir/<name>.md`` if the caller passed an explicit dir
       (tests / advanced embedding)
    2. ``$MOLTBOOK_HOME/prompts/<name>.md`` when the caller did not
       override ``prompts_dir`` — per-file override populated by ``init``
    3. ``DEFAULT_PROMPTS_DIR/<name>.md`` — packaged fallback

    Args:
        prompts_dir: Explicit directory to read from. When set, the
            per-home override layer is skipped; useful for tests that
            want a fully isolated prompt set.

    Returns:
        PromptTemplates with all templates loaded.

    Raises:
        FileNotFoundError: If directory or required files don't exist.
    """
    base_dir = prompts_dir or DEFAULT_PROMPTS_DIR
    if not base_dir.is_dir():
        raise FileNotFoundError(f"Prompts directory not found: {base_dir}")

    home_dir = _resolve_home_prompts_dir() if prompts_dir is None else None

    def read(name: str, *, required: bool = True) -> str:
        return _read_prompt_with_fallback(name, base_dir, home_dir, required=required)

    # Derived from the dataclass rather than restated: the field name IS the
    # file stem, and "required" IS "the field has no default". A new prompt is
    # then declared once, and a typo cannot silently yield "" for it.
    return PromptTemplates(
        **{
            f.name: read(f"{f.name}.md", required=f.default is MISSING)
            for f in fields(PromptTemplates)
        }
    )


def load_constitution(constitution_dir: Path | None = None) -> str:
    """Load constitutional clauses from a constitution directory.

    Loads all .md files from the constitution directory with forbidden-pattern
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

    axiom_files = sorted(directory.glob("*.md"))
    if not axiom_files:
        return ""

    contents = [f.read_text(encoding="utf-8").strip() for f in axiom_files]
    raw = "\n\n".join(c for c in contents if c)
    if not raw:
        return ""

    found = first_forbidden_substring(raw)
    if found is not None:
        raise ValueError(f"Constitutional clauses contain forbidden pattern: {found}")
    return raw


class _DefaultDict(dict):
    """Dict that returns the key wrapped in braces for missing keys."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def resolve_prompt(
    template: str,
    domain_config: DomainConfig,
    **extra_vars: str,
) -> str:
    """Expand domain placeholders in a prompt template.

    Replaces {domain_name}, {repo_url} with values from the DomainConfig.
    Additional variables can be passed as kwargs.

    Uses str.format_map with a defaulting dict so that unresolved
    placeholders (like {post_content}) are left intact for later formatting.
    """
    variables = _DefaultDict(
        domain_name=domain_config.name,
        repo_url=domain_config.repo_url,
    )
    variables.update(extra_vars)
    return template.format_map(variables)


# ---------------------------------------------------------------------------
# Module-level lazy singletons for backward compatibility
# ---------------------------------------------------------------------------

_cached_domain_config: DomainConfig | None = None
_cached_prompt_templates: PromptTemplates | None = None


def get_domain_config(path: Path | None = None) -> DomainConfig:
    """Get or load the domain config (cached singleton)."""
    global _cached_domain_config
    if _cached_domain_config is None:
        _cached_domain_config = load_domain_config(path)
    return _cached_domain_config


def get_prompt_templates(prompts_dir: Path | None = None) -> PromptTemplates:
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

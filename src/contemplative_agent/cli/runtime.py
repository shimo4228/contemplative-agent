"""Session runtime setup: logging, LLM/domain configuration, dry-run detection.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ..adapters.moltbook import config
from ..adapters.moltbook.submolt_scope import configure_submolt_scope
from ..core.domain import (
    DomainConfig,
    load_constitution,
    load_domain_config,
    reset_caches,
    set_domain_config_cache,
)
from ..core.llm import configure as configure_llm
from ..core.llm import configure_untrusted_guard
from ..core.skill_selection import configure_skill_selection

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    """Repository root (the directory containing ``src/``).

    The former single-file cli.py used ``Path(__file__).resolve().parents[2]``
    inline at three call sites; inside the ``cli/`` package the depth is one
    level greater, so the resolution lives here once instead of as a
    depth-sensitive expression scattered across submodules (ADR-0079).
    """
    return Path(__file__).resolve().parents[3]


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _is_dry_run(args: argparse.Namespace) -> bool:
    """Check if --dry-run was passed."""
    return getattr(args, "dry_run", False)


def _configure_llm_runtime() -> None:
    """Apply per-call telemetry shared by full and Tier 1.5 command setup.

    Shared by full command setup (``_configure_llm_and_domain``) and the Tier
    1.5 stocktake path so telemetry applies consistently. Deliberately does NOT
    load skills/rules/axioms: stocktake passes its own explicit system prompts
    and must keep a clean prompt environment, so this runtime config is the
    subset that is always safe.

    Generation runs on the default Ollama path. An external package (e.g.
    ``contemplative-agent-cloud``) injects an alternative backend out-of-band
    via ``configure(backend=...)`` through the ``LLMBackend`` protocol;
    embeddings always stay on Ollama via ``OLLAMA_BASE_URL``.
    """
    # Per-call telemetry (llm-calls-{date}.jsonl) alongside the episode log.
    configure_llm(telemetry_dir=config.EPISODE_LOG_DIR)
    # Calibration drift guard (ADR-0071/0072): a same-dimension embedding
    # model swap invalidates every calibrated similarity threshold while
    # passing all shape checks — surface it loudly, never gate on it.
    from ..core.embeddings import calibration_drift_note

    drift = calibration_drift_note()
    if drift:
        logger.warning("%s", drift)


def _configure_llm_and_domain(args: argparse.Namespace) -> DomainConfig | None:
    """Load domain config, constitution, skills, and rules into LLM.

    Returns the domain_config (or None) for Agent construction.
    """
    domain_config: DomainConfig | None = None
    if args.domain_config is not None:
        reset_caches()
        domain_config = load_domain_config(args.domain_config)
        set_domain_config_cache(domain_config)

    if not args.no_axioms:
        clauses = load_constitution(args.constitution_dir or config.CONSTITUTION_DIR)
        if clauses:
            configure_llm(axiom_prompt=clauses)

    if config.SKILLS_DIR.is_dir():
        configure_llm(skills_dir=config.SKILLS_DIR)
        # ADR-0076/0081: pass-1 skill selection for content generations.
        # Records selections to logs/skill-selection-*.jsonl AND decides
        # injection — a judged selection makes pass 2 carry only the
        # selected bodies (unconditional since the 2026-08-08 flag
        # retirement). This call is therefore the whole of what determines
        # the injection regime, which is why the eval stopped comparing its
        # pin against the launchd plist. Leaving audit_dir unset disables
        # the selector; note it is gated on the same skills-dir condition as
        # configure_llm above, so it cannot be unset while a corpus is
        # still configured for injection.
        configure_skill_selection(skills_dir=config.SKILLS_DIR, audit_dir=config.EPISODE_LOG_DIR)
    # ADR-0086: the submolt-scope instrument. Read-only — it samples feeds and
    # scores them, and is wired to no gate. Leaving audit_dir unset disables it
    # outright, which is the kill switch.
    configure_submolt_scope(audit_dir=config.EPISODE_LOG_DIR)
    # T-OBS-INJ: injection-token removals inside wrap_untrusted_content. Wired
    # unconditionally, unlike the selector above — the reading this log exists
    # for is "is the guard still on the path", and a conditional wire makes a
    # run of zeroes mean either "no attacks" or "not configured this time",
    # which is the ambiguity the log was added to remove. nonce_source stays
    # unset so production draws from the system CSPRNG.
    configure_untrusted_guard(audit_dir=config.EPISODE_LOG_DIR)
    if config.RULES_DIR.is_dir():
        configure_llm(rules_dir=config.RULES_DIR)

    _configure_llm_runtime()

    return domain_config


def _llm_session_meta() -> dict[str, str]:
    """Return backend/model metadata for the session start episode.

    Per-call telemetry records the exact served model on every request via the
    ``LLMBackend.model`` contract. The session-level metadata reuses the same
    canonical resolver (``served_model()``) so it never drifts to a stale
    literal — both record whatever model is actually serving generation.
    """
    from ..core.llm import served_model

    model = served_model()
    return {
        "llm_backend": "ollama",
        "llm_model": model,
        # Legacy field retained so older report consumers that know this key
        # keep working.
        "ollama_model": model,
    }


def _exit_with(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)

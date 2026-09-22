"""Session runtime setup: logging, LLM/domain configuration, dry-run detection.

Also the cross-cutting session wiring three command modules share: the view
registry, the pivot snapshot, and the run's reasoning trace. They lived in
``memory_cmds`` until ``stocktake_cmd`` and ``session_cmds`` began importing
them, which put one command module's internals in another's import list.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from ..core.views import ViewRegistry

from ..adapters.moltbook import config
from ..adapters.moltbook.submolt_scope import configure_submolt_scope
from ..core.comment_outcomes import configure_comment_outcomes
from ..core.domain import (
    DomainConfig,
    load_constitution,
    load_domain_config,
    reset_caches,
    set_domain_config_cache,
)
from ..core.llm import (
    OllamaLogprobsDecisionBackend,
    configure as configure_llm,
    configure_untrusted_guard,
    served_model,
)
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
    # T-OBS-INJ: injection-token removals inside wrap_untrusted_content. It
    # belongs in this shared subset rather than in _configure_llm_and_domain
    # for the same reason the log exists at all: Tier.LLM_RUNTIME_ONLY skips
    # that function, and `skill-stocktake` is that tier
    # while core/stocktake.py wraps two untrusted fields per skill. Wiring it
    # one tier up left exactly the blind spot the reading was added to
    # remove — a run of zeroes that could mean "no attacks" or "this command
    # never configured the guard". nonce_source stays unset so production
    # draws from the system CSPRNG.
    configure_untrusted_guard(audit_dir=config.EPISODE_LOG_DIR)
    # Calibration drift guard (ADR-0071/0072): a same-dimension embedding
    # model swap invalidates every calibrated similarity threshold while
    # passing all shape checks — surface it loudly, never gate on it.
    from ..core.embeddings import calibration_drift_note

    drift = calibration_drift_note()
    if drift:
        logger.warning("%s", drift)


_DEFAULT_DECISION_BUDGET_S = 120.0


def _decision_budget_s() -> float:
    """Wall-clock budget one decision batch may spend (``DECISION_BUDGET_S``).

    An unreadable or non-positive value falls back to the default with a
    WARNING rather than aborting startup: this is an observability path, and a
    typo in an env var must not be the reason a scheduled session does not
    run. Loud, not silent — the operator sees which value was ignored.
    """
    raw = os.environ.get("DECISION_BUDGET_S")
    if raw is None:
        return _DEFAULT_DECISION_BUDGET_S
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    # ``nan``/``inf`` parse as floats and pass a ``<= 0`` test, and either one
    # makes every "elapsed >= budget" comparison False — a budget that never
    # fires, which is the failure it exists to prevent.
    if not math.isfinite(value) or value <= 0:
        logger.warning(
            "DECISION_BUDGET_S=%r is not a positive number of seconds; using %.0f",
            raw,
            _DEFAULT_DECISION_BUDGET_S,
        )
        return _DEFAULT_DECISION_BUDGET_S
    return value


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
    # ADR-0112: the decision seam, observed in shadow beside the selection
    # above. Constructed ONLY when DECISION_MODEL names a model, which is the
    # kill switch: with the variable unset nothing is called, recorded or
    # timed, and a run is byte-for-byte the current behaviour. A model that is
    # not the served generation model makes the batch exclusive — it evicts
    # gemma before it starts and itself at the end, because 16 GB does not
    # hold two (ADR-0067).
    decision_model = os.environ.get("DECISION_MODEL")
    if decision_model:
        configure_llm(
            decision_backend=OllamaLogprobsDecisionBackend(
                model=decision_model,
                exclusive=decision_model != served_model(),
                batch_budget_s=_decision_budget_s(),
            )
        )
    # RFC-0028: the comment-outcome recorder. Writes only
    # logs/comment-outcomes.jsonl, from the comment tree the reply cycle
    # already fetched; leaving audit_dir unset disables it, same kill switch
    # as the selector above.
    configure_comment_outcomes(audit_dir=config.EPISODE_LOG_DIR)
    # ADR-0086: the submolt-scope instrument. Read-only — it samples feeds and
    # scores them, and is wired to no gate. Leaving audit_dir unset disables it
    # outright, which is the kill switch.
    configure_submolt_scope(audit_dir=config.EPISODE_LOG_DIR)
    if config.RULES_DIR.is_dir():
        configure_llm(rules_dir=config.RULES_DIR)

    _configure_llm_runtime()

    return domain_config


def _llm_session_meta() -> dict[str, Any]:
    """Return backend/model metadata for the session start episode.

    Per-call telemetry records the exact served model on every request via the
    ``LLMBackend.model`` contract. The session-level metadata reuses the same
    canonical resolver (``served_model()``) so it never drifts to a stale
    literal — both record whatever model is actually serving generation.
    """
    from ..core.llm import served_model, serving_environment

    model = served_model()
    return {
        "llm_backend": "ollama",
        "llm_model": model,
        # Legacy field retained so older report consumers that know this key
        # keep working.
        "ollama_model": model,
        # Weight digests + Ollama build (ADR-0069 addendum 2026-09-06): the
        # name above is a mutable tag; only the digest pins which weights
        # this session's output came from.
        **serving_environment(),
    }


def _resolve_views_dir() -> Path:
    """Prefer the user-customised config.VIEWS_DIR, fall back to packaged template."""
    if config.VIEWS_DIR.exists():
        return config.VIEWS_DIR
    repo_root = _repo_root()
    packaged = repo_root / "config" / "views"
    if packaged.exists():
        return packaged
    return config.VIEWS_DIR


def _load_view_registry(
    args: argparse.Namespace | None = None,
) -> ViewRegistry:
    """Load the view registry, preferring user-customised views.

    Passes ``${CONSTITUTION_DIR}`` to seed_from resolution so views can
    inject live constitution content (honours ``--constitution-dir``).
    """
    from ..core.views import ViewRegistry

    constitution_dir = (
        getattr(args, "constitution_dir", None) if args is not None else None
    ) or config.CONSTITUTION_DIR
    registry = ViewRegistry(
        views_dir=_resolve_views_dir(),
        # The KEY is the ``${CONSTITUTION_DIR}`` placeholder name used inside
        # view files' seed_from — it is a template variable, not a Python
        # reference, and must stay exactly "CONSTITUTION_DIR" (codex P1,
        # ADR-0079 Phase 4: a mechanical rename here silently falls back to
        # the generic seed for every CLI-loaded registry).
        path_vars={"CONSTITUTION_DIR": constitution_dir},
    )
    registry.load_views()
    return registry


def _take_snapshot(
    args: argparse.Namespace,
    command: str,
    view_registry: ViewRegistry | None = None,
    *,
    think: bool = False,
) -> Path | None:
    """Write a pivot snapshot at the start of a behavior-producing command.

    Skipped when the caller passes ``--dry-run`` (only ``distill`` still
    accepts that flag after ADR-0035; the other approval-gated callers
    rely on the approval prompt to discard). Returns None if
    snapshotting fails — callers must not treat a missing snapshot as
    an error (ADR-0020: snapshots are observability, not correctness).

    ``think`` (ADR-0069) records the run's think state in the manifest beside
    the generation model (``served_model()``); the value-layer pipelines that
    run think-ON pass ``think=True`` so the manifest distinguishes their runs
    from the think-OFF autonomous ``distill``.
    """
    if _is_dry_run(args):
        return None
    from ..core.llm import served_model, serving_environment
    from ..core.snapshot import SnapshotCommand, write_snapshot

    return write_snapshot(
        command=cast(SnapshotCommand, command),
        views_dir=_resolve_views_dir(),
        constitution_dir=getattr(args, "constitution_dir", None) or config.CONSTITUTION_DIR,
        snapshots_dir=config.SNAPSHOTS_DIR,
        prompts_dir=config.PROMPTS_DIR if config.PROMPTS_DIR.is_dir() else None,
        skills_dir=config.SKILLS_DIR if config.SKILLS_DIR.is_dir() else None,
        rules_dir=config.RULES_DIR if config.RULES_DIR.is_dir() else None,
        identity_path=config.IDENTITY_PATH if config.IDENTITY_PATH.is_file() else None,
        view_registry=view_registry,
        generation_model=served_model(),
        think=think,
        serving_env=serving_environment(),
    )


# Why no reasoning.md was written. Deliberately NOT the core layer's trace
# reason codes: this layer sees only empty strings and cannot tell trace_absent
# from trace_blank, so reusing one here would assert more than it can support.
_REASONING_SKIP_NO_SECTIONS = "no_think_calls"  # the command made no think-ON call
_REASONING_SKIP_ALL_EMPTY = "all_traces_empty"  # calls ran, every trace came back empty


def _write_reasoning(
    snapshot_path: Path | None,
    sections: Sequence[tuple[str, str | None]],
) -> None:
    """Persist the run's reasoning trace(s) to ``reasoning.md`` in the snapshot.

    ADR-0069: think-ON value-layer pipelines capture the model's reasoning;
    it is written beside the run's input snapshot (durable, per-run, co-located
    with the input state that produced it) rather than in the input manifest,
    keeping the manifest's single responsibility. Each section is
    ``(title, trace)``; identical traces are de-duplicated (a batch trace may be
    shared across several artifacts), empty traces skipped, and nothing is
    written when no section has content. Traces are already secret-scrubbed
    (``GenerationOutput.thinking``); URL-defanged here like the episode report,
    since the trace is untrusted model output.
    """
    if snapshot_path is None:
        return
    from ..core.report import defang_urls

    if not sections:
        # Not a fault: a think-ON command can legitimately make no think-ON
        # call (skill-stocktake with nothing to merge). Said out loud because
        # the resulting absence of reasoning.md is byte-identical to the
        # failure case below, and the operator sees only the directory.
        logger.info(
            "No reasoning sections for %s: reason=%s", snapshot_path, _REASONING_SKIP_NO_SECTIONS
        )
        return
    blocks: list[str] = []
    seen: set[str] = set()
    for title, trace in sections:
        if not trace or trace in seen:
            continue
        seen.add(trace)
        blocks.append(f"## {title}\n\n{defang_urls(trace)}")
    if not blocks:
        # Calls ran and every trace came back empty. Which channel failed and
        # why is per-call knowledge this layer does not have (it sees only
        # empty strings) — that is on the llm-calls row, hence the pointer
        # rather than a core reason code reused at the wrong altitude.
        logger.warning(
            "No reasoning trace to write under %s: reason=%s "
            "(per-call reason in logs/llm-calls-*.jsonl)",
            snapshot_path,
            _REASONING_SKIP_ALL_EMPTY,
        )
        return
    try:
        (snapshot_path / "reasoning.md").write_text(
            "# Reasoning trace (ADR-0069)\n\n" + "\n\n".join(blocks) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to write reasoning.md under %s: %s", snapshot_path, exc)


def _exit_with(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)

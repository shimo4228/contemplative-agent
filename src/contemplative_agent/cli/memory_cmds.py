"""Memory-pipeline subcommands: distill / enrich / insight / rules-distill / amend-constitution.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from ..core.insight import SkillResult
    from ..core.views import ViewRegistry

from ..adapters.moltbook import config
from ..core._io import (
    acquire_run_lock,
    write_run_marker,
)
from . import adopt, approval, runtime, staging
from .registry import CommandSpec, Tier
from .staging import StageItem

logger = logging.getLogger(__name__)


# ADR-0075: one record per novelty-gate judge run (prompt + raw output as
# base64+sha256) so a covered→drop decision is replayable offline.
INSIGHT_NOVELTY_AUDIT_PATH = config.MOLTBOOK_DATA_DIR / "logs" / "insight-novelty.jsonl"


def _handle_distill(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from ..core.distill import distill
    from ..core.memory import EpisodeLog, KnowledgeStore

    log_dir = config.MOLTBOOK_DATA_DIR / "logs"
    log_files = args.log_files
    if log_files:
        for f in log_files:
            if not f.exists():
                parser.error(f"File not found: {f}")
            if f.suffix != ".jsonl":
                parser.error(f"Not a JSONL file: {f}")
    # Blocking lock (audit M5): wait for an active run session to finish
    # rather than skip — a skipped daily distill loses its --days window
    # (the next scheduled run reads a later window). Manual commands
    # (meditate / dialogue / insight) are deliberately NOT lock-gated:
    # they are operator-driven and making them queue behind a scheduled
    # session would be surprising.
    logger.info("Acquiring run lock (waits if a session is active)")
    with acquire_run_lock(config.RUN_LOCK_PATH, blocking=True):
        episode_log = EpisodeLog(log_dir=log_dir)
        knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
        view_registry = _load_view_registry(args)
        knowledge_store.load()
        _take_snapshot(args, "distill", view_registry)
        result = distill(
            days=args.days,
            dry_run=args.dry_run,
            episode_log=episode_log,
            knowledge_store=knowledge_store,
            log_files=log_files,
            instrument_views=view_registry,
        )
        print(result)


def _resolve_views_dir() -> Path:
    """Prefer the user-customised config.VIEWS_DIR, fall back to packaged template."""
    if config.VIEWS_DIR.exists():
        return config.VIEWS_DIR
    repo_root = runtime._repo_root()
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
    if runtime._is_dry_run(args):
        return None
    from ..core.llm import served_model
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
    )


def _write_reasoning(
    snapshot_path: Path | None,
    sections: Sequence[tuple[str, str | None]],
) -> None:
    """Persist the run's reasoning trace(s) to ``reasoning.md`` in the snapshot.

    ADR-0069: think-ON value-layer pipelines capture the model's reasoning;
    it is written beside the run's input snapshot (durable, per-run, co-located
    with the input state that produced it) rather than in the input manifest,
    keeping the manifest's single responsibility. Each section is
    ``(title, trace)``; identical traces are de-duplicated (rules-distill shares
    one batch trace across its rules), empty traces skipped, and nothing is
    written when no section has content. Traces are already secret-scrubbed
    (``GenerationOutput.thinking``); URL-defanged here like the episode report,
    since the trace is untrusted model output.
    """
    if snapshot_path is None:
        return
    from ..core.report import defang_urls

    blocks: list[str] = []
    seen: set[str] = set()
    for title, trace in sections:
        if not trace or trace in seen:
            continue
        seen.add(trace)
        blocks.append(f"## {title}\n\n{defang_urls(trace)}")
    if not blocks:
        return
    try:
        (snapshot_path / "reasoning.md").write_text(
            "# Reasoning trace (ADR-0069)\n\n" + "\n\n".join(blocks) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to write reasoning.md under %s: %s", snapshot_path, exc)


def _handle_enrich(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..core.distill import enrich
    from ..core.memory import KnowledgeStore

    knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
    knowledge_store.load()

    sub_count = enrich(knowledge_store, dry_run=args.dry_run)
    print(f"Subcategorized: {sub_count}")


def _handle_single_result(
    result: Any,
    *,
    command: str,
    reasoning_label: str,
    snapshot_path: Path | None,
    stage: bool,
    stage_filename: str | None = None,
) -> bool:
    """Print / stage / approve-write a single value-layer result.

    Shared tail for the distill-identity and amend-constitution handlers:
    handle the string-error short-circuit, write the reasoning trace, stage
    when requested, then run the ADR-0012 approval gate and write on approval.
    Returns ``True`` only when the result was approved and written to its
    target, so callers can run a post-write hook (e.g. the constitution
    last-amend marker). ``stage_filename`` defaults to the target's own name.
    """
    if isinstance(result, str):
        print(result)
        return False
    print(result.text)
    _write_reasoning(snapshot_path, [(reasoning_label, result.thinking)])
    if stage:
        staging._stage_results(
            [
                StageItem(
                    stage_filename or result.target_path.name,
                    result.text,
                    result.target_path,
                    source_ids=list(result.pattern_ids),
                    epistemic_counts=dict(result.epistemic_counts),
                )
            ],
            command=command,
        )
        return False
    if result.thinking:
        print(f"\n--- Reasoning ---\n{result.thinking}")
    approved = approval._approve_write(result.target_path)
    approval._log_approval(
        command,
        result.target_path,
        approved,
        result.text,
        snapshot_path=snapshot_path,
        source_ids=result.pattern_ids,
        epistemic_counts=result.epistemic_counts,
    )
    if not approved:
        print("Discarded.")
        return False
    from ..core._io import write_restricted as _wr

    _wr(result.target_path, result.text + "\n")
    return True


def _handle_distill_identity(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..core.distill import distill_identity
    from ..core.memory import KnowledgeStore

    knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
    view_registry = _load_view_registry(args)
    knowledge_store.load()
    snapshot_path = _take_snapshot(args, "distill-identity", view_registry, think=True)
    result = distill_identity(
        knowledge_store=knowledge_store,
        identity_path=config.IDENTITY_PATH,
        view_registry=view_registry,
    )
    _handle_single_result(
        result,
        command="distill-identity",
        reasoning_label="identity",
        snapshot_path=snapshot_path,
        stage=getattr(args, "stage", False),
        stage_filename="identity.md",
    )


def _append_insight_ledger(skills: Sequence[SkillResult]) -> None:
    """Record each staged/reviewed insight candidate in the theme ledger.

    ADR-0074: the ledger is decision-agnostic — a candidate counts as
    "considered" once it reached review, so the novelty gate stops
    re-surfacing the same theme even when the human rejected it.

    Deliberately NOT best-effort (unlike the other audit writers): the append
    is part of the "ledger first, marker last" transaction (codex review
    2026-07-09) — a write failure must abort BEFORE write_last_insight so the
    window stays unconsumed rather than consumed-but-unremembered.
    """
    from ..core._io import append_jsonl_restricted, now_iso
    from ..core.insight import skill_theme

    for s in skills:
        name, description = skill_theme(s.text, fallback_name=Path(s.filename).stem)
        append_jsonl_restricted(
            adopt.INSIGHT_STAGED_LEDGER_PATH,
            {
                "ts": now_iso(),
                "name": name,
                "description": description,
                "filename": s.filename,
            },
        )


def _handle_insight(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..core.insight import extract_insight, write_last_insight
    from ..core.memory import KnowledgeStore

    # ADR-0074 fast-fail: extraction burns one LLM call per cluster, so
    # check the pending-staging guard BEFORE any expensive work rather
    # than letting staging._stage_results refuse after the fact.
    pending = staging._pending_staged_count() if getattr(args, "stage", False) else 0
    if pending:
        print(
            f"Staging holds {pending} unreviewed item(s) — "
            "skipping this insight run (ADR-0074). Review with "
            "`contemplative-agent adopt-staged` first."
        )
        return

    knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
    view_registry = _load_view_registry(args)
    snapshot_path = _take_snapshot(args, "insight", view_registry, think=True)
    result = extract_insight(
        knowledge_store=knowledge_store,
        skills_dir=config.SKILLS_DIR,
        full=args.full,
        instrument_views=view_registry,
        staged_ledger_path=adopt.INSIGHT_STAGED_LEDGER_PATH,
        novelty_audit_path=INSIGHT_NOVELTY_AUDIT_PATH,
    )
    if isinstance(result, str):
        print(result)
        return
    _write_reasoning(snapshot_path, [(s.filename, s.thinking) for s in result.skills])

    if not result.skills:
        # Every cluster was already covered. The window WAS considered, so
        # the marker still advances (ADR-0074) — otherwise the incremental
        # window would grow without bound across quiet weeks.
        write_last_insight(config.SKILLS_DIR)
        print(f"\n--- Summary: 0 novel clusters ({result.skipped_known} already covered) ---")
        return

    if getattr(args, "stage", False):
        staged = staging._stage_results(
            [
                StageItem(
                    s.filename,
                    s.text,
                    s.target_path,
                    source_ids=list(s.pattern_ids),
                    epistemic_counts=dict(s.epistemic_counts),
                )
                for s in result.skills
            ],
            command="insight",
        )
        if staged:
            # Ledger first, marker last (codex review 2026-07-09): a failure
            # between the two must leave the window unconsumed rather than
            # consumed-but-unremembered. Marker advances at staging time, not
            # adoption time (ADR-0074): approval decides skill adoption, not
            # pattern re-processing.
            _append_insight_ledger(result.skills)
            write_last_insight(config.SKILLS_DIR)
        return
    written = approval._run_approval_loop(
        result.skills,
        command="insight",
        target_dir=config.SKILLS_DIR,
        snapshot_path=snapshot_path,
    )
    # ADR-0074: the interactive loop is the review — patterns were
    # considered regardless of how many candidates were accepted.
    # Ledger first, marker last (same ordering rationale as the stage path).
    _append_insight_ledger(result.skills)
    write_last_insight(config.SKILLS_DIR)
    print(
        f"\n--- Summary: {written} written, {len(result.skills) - written} skipped, "
        f"{result.dropped_count} dropped, {result.skipped_known} already covered ---"
    )


def _handle_rules_distill(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..core.rules_distill import _write_last_run, distill_rules

    snapshot_path = _take_snapshot(args, "rules-distill", _load_view_registry(args), think=True)
    result = distill_rules(
        skills_dir=config.SKILLS_DIR,
        rules_dir=config.RULES_DIR,
        full=args.full,
    )
    if isinstance(result, str):
        print(result)
        return
    _write_reasoning(snapshot_path, [(r.filename, r.thinking) for r in result.rules])
    if getattr(args, "stage", False):
        staging._stage_results(
            [
                StageItem(
                    r.filename,
                    r.text,
                    r.target_path,
                    source_ids=list(r.source_ids),
                )
                for r in result.rules
            ],
            command="rules-distill",
        )
        return
    written = approval._run_approval_loop(
        result.rules,
        command="rules-distill",
        target_dir=config.RULES_DIR,
        snapshot_path=snapshot_path,
    )
    if written > 0:
        _write_last_run(config.RULES_DIR)
    print(
        f"\n--- Summary: {written} written, {len(result.rules) - written} skipped, {result.dropped_count} dropped ---"
    )


def _handle_amend_constitution(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..core.constitution import amend_constitution
    from ..core.memory import KnowledgeStore

    knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
    constitution_dir = args.constitution_dir or config.CONSTITUTION_DIR
    view_registry = _load_view_registry(args)
    snapshot_path = _take_snapshot(args, "amend-constitution", think=True)
    result = amend_constitution(
        knowledge_store=knowledge_store,
        constitution_dir=constitution_dir,
        view_registry=view_registry,
    )
    wrote = _handle_single_result(
        result,
        command="amend-constitution",
        reasoning_label="constitution amendment",
        snapshot_path=snapshot_path,
        stage=getattr(args, "stage", False),
    )
    # ``wrote`` is True only on the approved-write path, where ``result`` is
    # the amendment object (never the string-error short-circuit); the
    # isinstance narrows the type for the marker write.
    if wrote and not isinstance(result, str):
        write_run_marker(result.marker_dir, ".last_constitution_amend")


def _add_distill_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--days", type=int, default=1, help="Days of episodes to process (default: 1)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show results without writing")
    parser.add_argument(
        "--file",
        type=Path,
        nargs="+",
        dest="log_files",
        help="Explicit JSONL log file(s) to process (overrides --days)",
    )


def _add_stage_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stage",
        action="store_true",
        help="Write to staging dir instead of interactive approval (for coding agents)",
    )


def _add_full_and_stage_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--full", action="store_true", help="Process all patterns (not just new ones)"
    )
    _add_stage_argument(parser)


def _add_insight_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--full", action="store_true", help="Process all patterns (default: new only)"
    )
    _add_stage_argument(parser)


def _add_enrich_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="Show results without writing")


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="distill",
        help="Distill recent episodes into learned patterns",
        handler=_handle_distill,
        tier=Tier.LLM_FULL,
        add_arguments=_add_distill_arguments,
    ),
    CommandSpec(
        name="distill-identity",
        help="Distill knowledge into identity (without pattern distillation)",
        handler=_handle_distill_identity,
        tier=Tier.LLM_FULL,
        add_arguments=_add_stage_argument,
    ),
    CommandSpec(
        name="rules-distill",
        help="Distill universal behavioral rules from skill files",
        handler=_handle_rules_distill,
        tier=Tier.LLM_FULL,
        add_arguments=_add_full_and_stage_arguments,
    ),
    CommandSpec(
        name="amend-constitution",
        help="Propose amendments to the constitution from accumulated ethical experience",
        handler=_handle_amend_constitution,
        tier=Tier.LLM_FULL,
        add_arguments=_add_stage_argument,
    ),
    CommandSpec(
        name="insight",
        help="Extract behavioral skill from accumulated knowledge",
        handler=_handle_insight,
        tier=Tier.LLM_FULL,
        add_arguments=_add_insight_arguments,
    ),
    CommandSpec(
        name="enrich",
        help=(
            "(deprecated, no-op since ADR-0019) formerly enriched patterns "
            "with subcategories; subcategorisation is now query-time via views"
        ),
        handler=_handle_enrich,
        tier=Tier.LLM_FULL,
        add_arguments=_add_enrich_arguments,
    ),
)

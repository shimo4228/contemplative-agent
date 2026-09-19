"""Memory-pipeline subcommands: distill / insight / amend-constitution.

(``rules-distill`` was retired by ADR-0097.)

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.constitution import AmendmentResult
    from ..core.distill import IdentityResult
    from ..core.insight import SkillResult

from ..adapters.moltbook import config
from ..core._io import (
    acquire_run_lock,
    write_restricted,
    write_run_marker,
)
from . import adopt, approval, runtime, staging
from .registry import CommandSpec, Tier
from .staging import StageItem

logger = logging.getLogger(__name__)


# ADR-0075: one record per novelty-gate judge run (prompt + raw output as
# base64+sha256) so a covered→drop decision is replayable offline.
INSIGHT_NOVELTY_AUDIT_PATH = config.MOLTBOOK_DATA_DIR / "logs" / "insight-novelty.jsonl"

# RFC-0042 items 2-4. A separate file from insight-novelty.jsonl on purpose:
# that log's readers resolve a kind-less legacy row structurally (
# ``insight_novelty.is_novelty_judge_record``), a rule that only works while
# the file holds the two families it was written for. These records are
# per-cluster and per-candidate rather than per-chunk and carry a different
# field set, so they get their own file and their own census registry row.
INSIGHT_STAGES_AUDIT_PATH = config.MOLTBOOK_DATA_DIR / "logs" / "insight-stages.jsonl"


def _handle_distill(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from ..core.distill import distill
    from ..core.memory import EpisodeLog, KnowledgeStore

    log_dir = config.EPISODES_DIR
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
        # distill() loads the store itself, and load() re-reads unconditionally
        # — a second load here parsed the ~190 MB knowledge.json twice per run.
        knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
        view_registry = runtime._load_view_registry(args)
        runtime._take_snapshot(args, "distill", view_registry)
        result = distill(
            days=args.days,
            dry_run=args.dry_run,
            episode_log=episode_log,
            knowledge_store=knowledge_store,
            log_files=log_files,
            instrument_views=view_registry,
        )
        print(result)


def _handle_single_result(
    result: str | IdentityResult | AmendmentResult,
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
    runtime._write_reasoning(snapshot_path, [(reasoning_label, result.thinking)])
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
    write_restricted(result.target_path, result.text + "\n")
    return True


def _handle_distill_identity(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..core.distill import distill_identity
    from ..core.memory import KnowledgeStore

    # ADR-0074 fast-fail (see staging._refuse_if_pending): the staging write
    # lives in _handle_single_result, which runs after distill_identity has
    # already spent its LLM call.
    if getattr(args, "stage", False) and staging._refuse_if_pending("distill-identity"):
        return

    # Same as the distill path: distill_identity() owns the load.
    knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
    view_registry = runtime._load_view_registry(args)
    snapshot_path = runtime._take_snapshot(args, "distill-identity", view_registry, think=True)
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
    from ..core.text_utils import skill_theme

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
    from ..core import insight as insight_mod
    from ..core.insight import extract_insight, write_last_insight
    from ..core.memory import KnowledgeStore

    # ADR-0074 fast-fail: extraction burns one LLM call per cluster, so
    # check the pending-staging guard BEFORE any expensive work rather
    # than letting staging._stage_results refuse after the fact.
    if getattr(args, "stage", False) and staging._refuse_if_pending("insight"):
        return

    knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
    view_registry = runtime._load_view_registry(args)
    snapshot_path = runtime._take_snapshot(args, "insight", view_registry, think=True)
    result = extract_insight(
        knowledge_store=knowledge_store,
        skills_dir=config.SKILLS_DIR,
        full=args.full,
        instrument_views=view_registry,
        staged_ledger_path=adopt.INSIGHT_STAGED_LEDGER_PATH,
        novelty_audit_path=INSIGHT_NOVELTY_AUDIT_PATH,
        stage_audit_path=INSIGHT_STAGES_AUDIT_PATH,
    )
    if isinstance(result, str):
        print(result)
        return
    runtime._write_reasoning(snapshot_path, [(s.filename, s.thinking) for s in result.skills])

    if not result.skills:
        # Every cluster was already covered, or every novel one declined in-band
        # (ADR-0096 Decision 1). Either way the window WAS considered, so
        # the marker still advances (ADR-0074) — otherwise the incremental
        # window would grow without bound across quiet weeks. A fault-bearing
        # run never reaches here: extract_insight returns an error string.
        write_last_insight(config.SKILLS_DIR)
        # Named per reason, not summed (RFC-0042): "nothing came through" and
        # "everything reconfirmed an existing skill" are different weeks, and
        # the Saturday gate reads this line to tell them apart.
        verdicts = ", ".join(
            f"{result.abstained[reason]} {reason}" for reason in insight_mod.VERDICT_ABSTAIN_REASONS
        )
        print(
            f"\n--- Summary: 0 candidates ({result.skipped_known} already covered; {verdicts}) ---"
        )
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
                    surprise=s.surprise.as_dict() if s.surprise else {},
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
        f"{result.abstained[insight_mod.ABSTAIN_NOTHING_PROMOTABLE]} not promotable, "
        f"{result.fault_count} dropped on a fault, "
        f"{result.skipped_known} already covered ---"
    )


def _handle_amend_constitution(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..core.constitution import amend_constitution
    from ..core.memory import KnowledgeStore

    # ADR-0074 fast-fail (see staging._refuse_if_pending). Rare in practice —
    # amendment is a human-attended deliberation event — but it shares the
    # _handle_single_result staging tail with distill-identity.
    if getattr(args, "stage", False) and staging._refuse_if_pending("amend-constitution"):
        return

    knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
    constitution_dir = args.constitution_dir or config.CONSTITUTION_DIR
    view_registry = runtime._load_view_registry(args)
    snapshot_path = runtime._take_snapshot(args, "amend-constitution", think=True)
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


def _handle_shadow_constitution(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Read-only shadow synthesis (ADR-0092): no approval gate, no staging.

    The command never writes to the constitution — its only write is the
    append-only instrument record — so the ADR-0012 gate machinery that wraps
    the other value-layer handlers deliberately does not appear here.
    """
    from ..core.constitution_shadow import synthesize_shadow_constitution
    from ..core.memory import KnowledgeStore

    knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
    constitution_dir = args.constitution_dir or config.CONSTITUTION_DIR
    view_registry = runtime._load_view_registry(args)
    result = synthesize_shadow_constitution(
        knowledge_store=knowledge_store,
        constitution_dir=constitution_dir,
        view_registry=view_registry,
        log_path=config.EPISODE_LOG_DIR / "constitution-shadow.jsonl",
    )
    if isinstance(result, str):
        print(result)
        return
    if not result.validation_passed:
        # Flag BEFORE the body so a reader (or a pipe) meets the warning first.
        print("[validation_failed] Recorded as instrument data; text shown for reading only.\n")
    print(result.text)
    print("\n--- Divergence reading ---")
    if result.cosine_vs_current is not None:
        print(
            f"cosine vs current constitution: {result.cosine_vs_current:.3f} "
            f"(current sha256 {result.current_sha256[:12]})"
        )
    else:
        print(f"unavailable ({result.cosine_reason})")
    # Instrument ambiguity note (ADR-0071 discipline): carried in the output
    # itself so a reader cannot mistake convergence for independent support.
    print(
        "note: input patterns were formed under the live constitution "
        "(action-time axioms), selected by a view seeded from it, and "
        "rendered under the same shape constraints the amend prompt imposes, "
        "so convergence is partially circular — divergent clauses are the "
        "primary signal (ADR-0092)."
    )
    print(
        "note: this text is an instrument reading, NOT an amendment candidate — "
        "adoption goes only through amend-constitution (approval lineage, ADR-0012/0050)."
    )
    if result.thinking:
        print(f"\n--- Reasoning ---\n{result.thinking}")


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


def _add_insight_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--full", action="store_true", help="Process all patterns (default: new only)"
    )
    _add_stage_argument(parser)


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
        name="amend-constitution",
        help="Propose amendments to the constitution from accumulated ethical experience",
        handler=_handle_amend_constitution,
        tier=Tier.LLM_FULL,
        add_arguments=_add_stage_argument,
    ),
    CommandSpec(
        name="shadow-constitution",
        help=(
            "Synthesize a patterns-only shadow constitution (current one NOT injected) "
            "and record its divergence from the live text — read-only instrument, ADR-0092"
        ),
        handler=_handle_shadow_constitution,
        tier=Tier.LLM_FULL,
    ),
    CommandSpec(
        name="insight",
        help="Extract behavioral skill from accumulated knowledge",
        handler=_handle_insight,
        tier=Tier.LLM_FULL,
        add_arguments=_add_insight_arguments,
    ),
)

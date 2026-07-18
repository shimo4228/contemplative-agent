"""skill-stocktake / rules-stocktake rendering and phase drivers.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    from ..core.stocktake import MergeGroup, QualityIssue, StocktakeResult

from ..adapters.moltbook import config
from . import approval, memory_cmds, staging
from .staging import StageItem

logger = logging.getLogger(__name__)


def _render_merged_group(
    group_items: list[tuple[str, str]],
    merge_prompt: str,
    fallback_title: str,
    trace_sink: Optional[list[str]] = None,
) -> tuple[str, str] | None:
    """Run the LLM merge for one group; return (filename, merged_text).

    Returns None when the LLM call fails or the model rejects the merge
    (candidates judged not actually redundant). ``trace_sink`` (ADR-0069)
    collects the merge reasoning trace when provided.
    """
    from datetime import date

    from ..core.stocktake import is_merge_rejected, merge_group
    from ..core.text_utils import extract_title, slugify

    merged_text = merge_group(group_items, merge_prompt, trace_sink)
    if merged_text is None:
        print("  Merge failed (LLM error). Skipping.")
        return None

    if is_merge_rejected(merged_text):
        print(f"  LLM rejected merge: {merged_text.strip()}")
        print("  Skipping (candidates judged not actually redundant).")
        return None

    print(merged_text)

    title = extract_title(merged_text) or fallback_title
    slug = slugify(title) or fallback_title
    filename = f"{slug}-{date.today().strftime('%Y%m%d')}.md"
    return filename, merged_text


def _delete_merged_originals(target_dir: Path, target_path: Path, filenames: Sequence[str]) -> None:
    """Delete the source files consumed by an approved merge.

    Self-delete guard: when the merged title slugifies to one of the source
    filenames, target_path collides with an original. The guard skips the
    matching name so we don't delete the file we just wrote. See commit
    542f0b2 for the bug history.
    """
    try:
        target_resolved = target_path.resolve()
    except OSError:
        target_resolved = target_path
    for name in filenames:
        original = target_dir / name
        try:
            same_as_target = original.resolve() == target_resolved
        except OSError:
            same_as_target = original == target_path
        if same_as_target:
            continue
        if original.exists():
            original.unlink()
            print(f"  Deleted {name}")


def _stocktake_merge_phase(
    merge_groups: Sequence[MergeGroup],
    items_dict: dict[str, str],
    *,
    target_dir: Path,
    merge_prompt: str,
    command_prefix: str,
    fallback_title: str,
    stage: bool,
    staged_batch: list[StageItem],
    trace_sink: Optional[list[str]] = None,
    trace_labels: Optional[list[str]] = None,
    snapshot_path: Optional[Path] = None,
) -> set[str]:
    """Merge duplicate groups; return the filenames consumed by a merge.

    ``trace_sink`` (ADR-0069) collects each group's merge reasoning trace;
    ``trace_labels`` receives the console group number for each collected
    trace (round-2 R2-L1: positional numbering misattributed traces once a
    group was skipped mid-run); ``snapshot_path`` is threaded into the
    approval audit so an adopted merge points back at the run's manifest +
    reasoning.
    """
    from ..core._io import write_restricted

    consumed_names: set[str] = set()

    print(f"\n{'=' * 60}")
    print(f"Merging {len(merge_groups)} group(s)...")

    merged = 0
    for i, group in enumerate(merge_groups, 1):
        group_items = [(name, items_dict[name]) for name in group.filenames if name in items_dict]
        if len(group_items) < 2:
            continue

        print(f"\n{'=' * 60}")
        print(f"[Group {i}/{len(merge_groups)}] {', '.join(group.filenames)}")
        print(f"  Reason: {group.reason}")

        n_before = len(trace_sink) if trace_sink is not None else 0
        rendered = _render_merged_group(group_items, merge_prompt, fallback_title, trace_sink)
        # Label the trace with the group number shown above ("[Group i/N]")
        # even when the render is rejected — a CANNOT_MERGE trace is still
        # reasoning worth attributing to the right group (R2-L1).
        if trace_sink is not None and trace_labels is not None and len(trace_sink) > n_before:
            trace_labels.append(f"group {i}")
        if rendered is None:
            continue
        filename, merged_text = rendered
        target_path = target_dir / filename

        if stage:
            # Record original filenames so adopt-staged can delete them on approval.
            staged_batch.append(
                StageItem(
                    filename=filename,
                    text=merged_text,
                    target_path=target_path,
                    sources=list(group.filenames),
                )
            )
            consumed_names.update(group.filenames)
            continue

        # ADR-0069: show this merge's reasoning before its approval gate.
        if trace_sink is not None and len(trace_sink) > n_before:
            print(f"\n--- Reasoning ---\n{trace_sink[-1]}")
        # H5 collision guard — exempt when the merged file deliberately
        # reuses one of the group's own names (merge-into-source overwrite,
        # matched by _delete_merged_originals' self-delete guard).
        if target_path.name not in group.filenames:
            target_path = approval._collision_free_path(target_path, merged_text)
        approved = approval._approve_write(target_path)
        approval._log_approval(
            command_prefix,
            target_path,
            approved,
            merged_text,
            snapshot_path=snapshot_path,
        )
        if approved:
            target_dir.mkdir(parents=True, exist_ok=True)
            write_restricted(target_path, merged_text)
            _delete_merged_originals(target_dir, target_path, group.filenames)
            merged += 1
            consumed_names.update(group.filenames)
        else:
            print("  Skipped.")

    if not stage:
        print(f"\n--- Merge summary: {merged} merged, {len(merge_groups) - merged} skipped ---")

    return consumed_names


def _stocktake_drop_phase(
    quality_issues: Sequence[QualityIssue],
    items_dict: dict[str, str],
    *,
    target_dir: Path,
    drop_command: str,
    stage: bool,
    staged_batch: list[StageItem],
    snapshot_path: Optional[Path] = None,
) -> None:
    """Delete (or stage for deferred approval) files flagged as low quality."""
    print(f"\n{'=' * 60}")
    print(f"Low-quality files: {len(quality_issues)}")

    dropped = 0
    for issue in quality_issues:
        target_path = target_dir / issue.filename
        if not target_path.exists():
            continue
        body = items_dict.get(issue.filename, "")
        if not body:
            # Defensive: quality_issues and items both come from
            # _read_files, so they should agree. Skip rather than
            # stage an empty artifact if they ever drift.
            print(f"  Skipped (empty body): {issue.filename}")
            continue

        print(f"\n{'=' * 60}")
        print(f"[Drop candidate] {issue.filename}")
        print(f"  Reason: {issue.reason}")
        print(body[:500])

        if stage:
            staged_batch.append(
                StageItem(
                    filename=issue.filename,
                    text=body,
                    target_path=target_path,
                    action="drop",
                    command=drop_command,
                )
            )
            continue

        approved = approval._approve_delete(target_path)
        approval._log_approval(
            drop_command, target_path, approved, body, snapshot_path=snapshot_path
        )
        if approved:
            target_path.unlink()
            print(f"  Deleted {issue.filename}")
            dropped += 1
        else:
            print("  Kept.")

    if not stage:
        print(f"\n--- Drop summary: {dropped} deleted, {len(quality_issues) - dropped} kept ---")


def _clean_one_skill(
    name: str,
    body: str,
    target_path: Path,
    clean_prompt: str,
    trace_sink: Optional[list[str]] = None,
) -> str | None:
    """Clean one skill's triggers and re-attach its original frontmatter.

    Returns the final text to write, or None when the LLM call fails or the
    triggers are already at structural altitude (CLEAN_NOOP). ``trace_sink``
    (ADR-0069) collects the clean reasoning trace when provided.
    """
    from ..core.stocktake import clean_skill_triggers, is_clean_noop
    from ..core.text_utils import split_frontmatter, synthesize_frontmatter

    cleaned_text = clean_skill_triggers((name, body), clean_prompt, trace_sink)
    if cleaned_text is None:
        print(f"  Clean failed (LLM error): {name}")
        return None
    if is_clean_noop(cleaned_text):
        return None  # triggers already at structural altitude

    # The cleaned body comes from a frontmatter-stripped source
    # (result.items strips it), so re-attach the skill's original
    # frontmatter — name / description / origin and any reflection
    # bookkeeping — before writing. Without this, a cleaned singleton
    # would silently lose its metadata. Legacy skills that predate
    # frontmatter emission get a synthesized block instead.
    try:
        original = target_path.read_text(encoding="utf-8")
    except OSError:
        original = ""
    _, cleaned_body = split_frontmatter(cleaned_text)
    # split_frontmatter only lstrips the body when it consumed a
    # frontmatter block; for the common frontmatter-less clean output
    # a stray leading newline from the model would yield a triple-blank
    # gap under the re-attached frontmatter, so strip it here.
    cleaned_body = cleaned_body.lstrip("\n")
    frontmatter, _ = split_frontmatter(original)
    if not frontmatter:
        frontmatter = synthesize_frontmatter(cleaned_body)
    return f"{frontmatter}\n\n{cleaned_body}"


def _stocktake_clean_phase(
    items: Sequence[tuple[str, str]],
    *,
    target_dir: Path,
    command_prefix: str,
    clean_prompt: str,
    skip_names: set[str],
    stage: bool,
    staged_batch: list[StageItem],
    trace_sink: Optional[list[str]] = None,
    trace_labels: Optional[list[str]] = None,
    snapshot_path: Optional[Path] = None,
) -> None:
    """Clean singleton triggers (skills only).

    A merged skill is rewritten at structural altitude by the merge prompt,
    but a skill with no twin never goes through a merge and keeps its
    original episode-derived triggers (proper nouns, timestamp windows, the
    saturated relevance score). This pass cleans those survivors so every
    surviving skill ends up with reusable triggers. Files consumed by a
    merge or flagged for drop are excluded; CLEAN_NOOP keeps it idempotent.
    """
    from ..core._io import write_restricted

    clean_command = f"{command_prefix}-clean"
    clean_targets = [(name, body) for name, body in items if name not in skip_names]
    if not clean_targets:
        return

    print(f"\n{'=' * 60}")
    print(f"Cleaning triggers for {len(clean_targets)} skill(s)...")

    cleaned = 0
    for name, body in clean_targets:
        target_path = target_dir / name
        n_before = len(trace_sink) if trace_sink is not None else 0
        final_text = _clean_one_skill(name, body, target_path, clean_prompt, trace_sink)
        # Label the trace with the skill filename (R2-L1) — recorded even on
        # CLEAN_NOOP so reasoning.md attribution survives skipped files.
        if trace_sink is not None and trace_labels is not None and len(trace_sink) > n_before:
            trace_labels.append(name)
        if final_text is None:
            continue

        print(f"\n{'=' * 60}")
        print(f"[Clean] {name}")
        print(final_text)

        if stage:
            # Self-source (2026-07-10 fix): a clean rewrite targets its own
            # original, so list it in `sources` to ride the merge-into-source
            # collision exemption in _adopt_write_item — without it the H5
            # guard treated every staged rewrite as a collision and minted
            # `-2.md` duplicates. The self-delete guard in
            # _delete_adopted_sources keeps the freshly written file.
            staged_batch.append(
                StageItem(
                    filename=name,
                    text=final_text,
                    target_path=target_path,
                    sources=[name],
                    command=clean_command,
                )
            )
            continue

        # ADR-0069: show this clean's reasoning before its approval gate.
        if trace_sink is not None and len(trace_sink) > n_before:
            print(f"\n--- Reasoning ---\n{trace_sink[-1]}")
        approved = approval._approve_write(target_path)
        approval._log_approval(
            clean_command,
            target_path,
            approved,
            final_text,
            snapshot_path=snapshot_path,
        )
        if approved:
            write_restricted(target_path, final_text)
            cleaned += 1
            print(f"  Cleaned {name}")
        else:
            print("  Skipped.")

    if not stage:
        print(
            f"\n--- Clean summary: {cleaned} cleaned, "
            f"{len(clean_targets) - cleaned} unchanged/skipped ---"
        )


def _labeled_sections(
    prefix: str, labels: list[str], traces: list[str]
) -> list[tuple[str, Optional[str]]]:
    """Pair reasoning traces with their operation labels for reasoning.md.

    Traces were previously numbered by list position, so a group skipped
    mid-run (LLM failure / CANNOT_MERGE / CLEAN_NOOP) shifted every later
    trace onto the wrong group number (round-2 R2-L1). Labels are recorded
    at call time; on a length mismatch (future plumbing bug) fall back to
    positional numbering rather than silently dropping traces via ``zip``.
    """
    if len(labels) != len(traces):
        return [(f"{prefix} {i}", t) for i, t in enumerate(traces, 1)]
    return [(f"{prefix} {label}", t) for label, t in zip(labels, traces, strict=True)]


def _handle_stocktake_result(
    args: argparse.Namespace,
    result: StocktakeResult,
    *,
    target_dir: Path,
    label: str,
    merge_prompt: str,
    command_prefix: str,
    fallback_title: str,
    clean_prompt: str | None = None,
    snapshot_path: Optional[Path] = None,
) -> None:
    """Shared body for _handle_skill_stocktake and _handle_rules_stocktake.

    Both handlers diff only in:
      - target_dir       (config.SKILLS_DIR vs config.RULES_DIR)
      - label            ("Skill" vs "Rules")
      - merge_prompt     (skill vs rules merge prompt template)
      - command_prefix   ("skill-stocktake" vs "rules-stocktake")
      - fallback_title   ("merged-skill" vs "merged-rule")

    Drop items use `f"{command_prefix}-drop"` for audit/meta consistency.

    Single staging batch for merge + drop + clean: `staging._stage_results` wipes
    STAGED_DIR on every call, so calling it once per phase would erase the
    earlier batches. Per-item `command` lets us mix "<prefix>",
    "<prefix>-drop", and "<prefix>-clean" in one batch.
    """
    from ..core.stocktake import format_stocktake_report

    print(format_stocktake_report(result, label))

    # With a clean_prompt (skills), the clean phase may rewrite singleton
    # triggers even when there is nothing to merge or drop, so don't short-
    # circuit. Rules pass no clean_prompt and keep the original early return.
    if not result.merge_groups and not result.quality_issues and clean_prompt is None:
        # Nothing to merge/drop/clean, but the grouping call still reasoned
        # about the corpus — persist that trace (ADR-0069) before returning.
        memory_cmds._write_reasoning(snapshot_path, [("duplicate grouping", result.thinking)])
        return

    items_dict = dict(result.items)
    stage = getattr(args, "stage", False)
    staged_batch: list[StageItem] = []
    # ADR-0069: collect per-phase reasoning traces (stocktake runs think-ON).
    # The grouping trace rides on result.thinking; merge / clean traces are
    # gathered per operation via these sinks and aggregated into reasoning.md.
    merge_traces: list[str] = []
    merge_trace_labels: list[str] = []
    clean_traces: list[str] = []
    clean_trace_labels: list[str] = []

    # Filenames consumed by a successful merge (their originals get deleted on
    # adopt) and filenames flagged for drop. The clean phase skips both so it
    # only rewrites surviving singletons: merged skills are already cleaned by
    # the merge prompt, and dropped files don't need cleaning.
    consumed_names: set[str] = set()
    if result.merge_groups:
        consumed_names = _stocktake_merge_phase(
            result.merge_groups,
            items_dict,
            target_dir=target_dir,
            merge_prompt=merge_prompt,
            command_prefix=command_prefix,
            fallback_title=fallback_title,
            stage=stage,
            staged_batch=staged_batch,
            trace_sink=merge_traces,
            trace_labels=merge_trace_labels,
            snapshot_path=snapshot_path,
        )

    if result.quality_issues:
        _stocktake_drop_phase(
            result.quality_issues,
            items_dict,
            target_dir=target_dir,
            drop_command=f"{command_prefix}-drop",
            stage=stage,
            staged_batch=staged_batch,
            snapshot_path=snapshot_path,
        )

    if clean_prompt is not None:
        dropped_names = {issue.filename for issue in result.quality_issues}
        _stocktake_clean_phase(
            result.items,
            target_dir=target_dir,
            command_prefix=command_prefix,
            clean_prompt=clean_prompt,
            skip_names=consumed_names | dropped_names,
            stage=stage,
            staged_batch=staged_batch,
            trace_sink=clean_traces,
            trace_labels=clean_trace_labels,
            snapshot_path=snapshot_path,
        )

    if stage and staged_batch:
        staging._stage_results(staged_batch, command=command_prefix)

    # ADR-0069: persist the run's reasoning — grouping (the main judgment) plus
    # each merge / clean operation — to reasoning.md beside the snapshot.
    sections: list[tuple[str, Optional[str]]] = [("duplicate grouping", result.thinking)]
    sections += _labeled_sections("merge", merge_trace_labels, merge_traces)
    sections += _labeled_sections("clean", clean_trace_labels, clean_traces)
    memory_cmds._write_reasoning(snapshot_path, sections)


def _handle_skill_stocktake(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Audit skills and merge duplicates / drop low-quality files."""
    from ..core import prompts
    from ..core.stocktake import run_skill_stocktake

    snapshot_path = memory_cmds._take_snapshot(args, "skill-stocktake", think=True)
    result = run_skill_stocktake(skills_dir=config.SKILLS_DIR)
    _handle_stocktake_result(
        args,
        result,
        target_dir=config.SKILLS_DIR,
        label="Skill",
        merge_prompt=prompts.STOCKTAKE_MERGE_PROMPT,
        command_prefix="skill-stocktake",
        fallback_title="merged-skill",
        clean_prompt=prompts.STOCKTAKE_CLEAN_PROMPT,
        snapshot_path=snapshot_path,
    )


def _handle_rules_stocktake(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Audit rules and merge duplicates / drop low-quality files.

    Uses STOCKTAKE_MERGE_RULES_PROMPT (Practice/Rationale structure) instead
    of the skill-oriented STOCKTAKE_MERGE_PROMPT. All other behavior is
    shared via `_handle_stocktake_result`.
    """
    from ..core import prompts
    from ..core.stocktake import run_rules_stocktake

    snapshot_path = memory_cmds._take_snapshot(args, "rules-stocktake", think=True)
    result = run_rules_stocktake(rules_dir=config.RULES_DIR)
    _handle_stocktake_result(
        args,
        result,
        target_dir=config.RULES_DIR,
        label="Rules",
        merge_prompt=prompts.STOCKTAKE_MERGE_RULES_PROMPT,
        command_prefix="rules-stocktake",
        fallback_title="merged-rule",
        snapshot_path=snapshot_path,
    )

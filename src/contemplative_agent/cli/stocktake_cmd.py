"""skill-stocktake / rules-stocktake rendering and phase drivers.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.stocktake import MergeGroup, QualityIssue, StocktakeResult

from ..adapters.moltbook import config
from . import approval, memory_cmds, staging
from .registry import CommandSpec, Tier
from .staging import StageItem

logger = logging.getLogger(__name__)


def _render_merged_group(
    group_items: list[tuple[str, str]],
    merge_prompt: str,
    fallback_title: str,
    trace_sink: list[str] | None = None,
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
    trace_sink: list[str] | None = None,
    trace_labels: list[str] | None = None,
    snapshot_path: Path | None = None,
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
    snapshot_path: Path | None = None,
) -> set[str]:
    """Delete (or stage for deferred approval) files flagged as low quality.

    Returns the filenames actually removed from the store this run —
    deleted, or staged for drop approval. A candidate the operator KEEPS is
    not in the set, so downstream phases (description audit) still cover it
    (codex review 2026-07-24: a kept file stays in the selector catalog and
    its description still needs checking).
    """
    print(f"\n{'=' * 60}")
    print(f"Low-quality files: {len(quality_issues)}")

    dropped_names: set[str] = set()
    dropped = 0
    for issue in quality_issues:
        target_path = target_dir / issue.filename
        if not target_path.exists():
            continue
        body = items_dict.get(issue.filename, "")
        if not body:
            # Defensive: quality_issues and items both come from
            # read_markdown_documents, so they should agree. Skip rather than
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
            dropped_names.add(issue.filename)
            continue

        approved = approval._approve_delete(target_path)
        approval._log_approval(
            drop_command, target_path, approved, body, snapshot_path=snapshot_path
        )
        if approved:
            target_path.unlink()
            print(f"  Deleted {issue.filename}")
            dropped_names.add(issue.filename)
            dropped += 1
        else:
            print("  Kept.")

    if not stage:
        print(f"\n--- Drop summary: {dropped} deleted, {len(quality_issues) - dropped} kept ---")
    return dropped_names


def _clean_one_skill(
    name: str,
    body: str,
    target_path: Path,
    clean_prompt: str,
    trace_sink: list[str] | None = None,
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
    trace_sink: list[str] | None = None,
    trace_labels: list[str] | None = None,
    snapshot_path: Path | None = None,
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


def _stocktake_description_phase(
    items: Sequence[tuple[str, str]],
    *,
    target_dir: Path,
    desc_prompt: str,
    skip_names: set[str],
    usage_counts: dict[str, int] | None = None,
    trace_sink: list[str] | None = None,
    trace_labels: list[str] | None = None,
) -> None:
    """Audit description fidelity for surviving skills (ADR-0081, advisory).

    Under two-pass injection the frontmatter description is the selector's
    only evidence, so a description broader or narrower than the body's
    triggers distorts every selection. This phase prints mismatch reasons
    for the operator — it writes nothing and gates nothing. Files consumed
    by a merge or flagged for drop are excluded (their descriptions are
    about to change or disappear). ``usage_counts`` (skill name → window
    selection count) annotates each finding so near-always-selected skills
    — the over-broad suspects — are visible next to the verdict.
    """
    from ..core.stocktake import audit_skill_description
    from ..core.text_utils import skill_theme, split_frontmatter

    targets = [name for name, _ in items if name not in skip_names]
    if not targets:
        return

    print(f"\n{'=' * 60}")
    print(f"Auditing descriptions for {len(targets)} skill(s)...")

    findings = 0
    for name in targets:
        # Read description AND body from the file on disk, not result.items:
        # the clean phase may have just rewritten this skill's triggers, and
        # auditing the pre-clean body could report the opposite verdict from
        # the skill actually saved (codex review 2026-07-24). The raw read is
        # also the same seam the selector's catalog loader uses.
        try:
            raw = (target_dir / name).read_text(encoding="utf-8")
        except OSError:
            print(f"  Skipped (unreadable): {name}")
            continue
        _, body = split_frontmatter(raw)
        skill_name, description = skill_theme(raw, fallback_name=Path(name).stem)
        if not description:
            print(f"  {name} — no description in frontmatter (selector sees title only)")
            findings += 1
            continue

        n_before = len(trace_sink) if trace_sink is not None else 0
        reason = audit_skill_description((name, description, body), desc_prompt, trace_sink)
        if trace_sink is not None and trace_labels is not None and len(trace_sink) > n_before:
            trace_labels.append(name)
        if reason is None:
            continue
        findings += 1
        suffix = ""
        if usage_counts is not None:
            suffix = f" [selected {usage_counts.get(skill_name, 0)}x in window]"
        print(f"  {name}{suffix} — {reason}")

    print(f"--- Description audit: {findings} mismatch(es), advisory only ---")


def _labeled_sections(
    prefix: str, labels: list[str], traces: list[str]
) -> list[tuple[str, str | None]]:
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


@dataclass(frozen=True)
class StocktakeRun:
    """What differs between the skill and rules stocktakes, in one object.

    The two handlers diff only in these fields; everything else about a run is
    shared. Passing them as a unit keeps ``_handle_stocktake_result`` from
    growing another positional-argument column each time a phase needs one more
    piece of configuration.

    ``clean_prompt`` / ``desc_prompt`` are ``None`` for rules — their absence is
    what selects the phases that run, so they are configuration, not options.
    """

    args: argparse.Namespace
    target_dir: Path
    label: str
    merge_prompt: str
    command_prefix: str
    fallback_title: str
    clean_prompt: str | None = None
    desc_prompt: str | None = None
    snapshot_path: Path | None = None

    @property
    def stage(self) -> bool:
        return bool(getattr(self.args, "stage", False))

    @property
    def drop_command(self) -> str:
        """Drop items carry their own command for audit/meta consistency."""
        return f"{self.command_prefix}-drop"


@dataclass(frozen=True)
class _DropOutcome:
    """Which files the drop phase *proposed* versus which it actually removed.

    These two sets are not interchangeable and the later phases each need a
    different one — conflating them was a real bug (codex review 2026-07-24).
    Separate fields make picking the wrong one a visible choice rather than a
    silent reuse of whichever local variable was in scope.
    """

    flagged: frozenset[str]
    """Every file the quality audit flagged, whether or not it was removed."""

    removed: frozenset[str]
    """Files actually deleted or staged for drop this run."""


@dataclass(frozen=True)
class _TraceSink:
    """Per-phase reasoning traces plus the operation label each came from.

    Traces used to be numbered by list position, so a group skipped mid-run
    shifted every later trace onto the wrong group number (round-2 R2-L1).
    Keeping the label beside its trace is what ``_labeled_sections`` needs, so
    they travel together instead of as two lists a caller must keep aligned.

    Frozen like every dataclass here: the phase drivers append to the two
    lists, they never rebind them, so the sink itself stays a fixed pair.
    """

    traces: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    def sections(self, prefix: str) -> list[tuple[str, str | None]]:
        return _labeled_sections(prefix, self.labels, self.traces)


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
    desc_prompt: str | None = None,
    snapshot_path: Path | None = None,
) -> None:
    """Shared body for _handle_skill_stocktake and _handle_rules_stocktake."""
    _run_stocktake_phases(
        StocktakeRun(
            args=args,
            target_dir=target_dir,
            label=label,
            merge_prompt=merge_prompt,
            command_prefix=command_prefix,
            fallback_title=fallback_title,
            clean_prompt=clean_prompt,
            desc_prompt=desc_prompt,
            snapshot_path=snapshot_path,
        ),
        result,
    )


def _grouping_section(result: StocktakeResult) -> tuple[str, str | None]:
    """The reasoning.md section for the grouping call.

    A no-verdict run (``grouping_reason`` set) must be legible from the
    snapshot alone, not only from the terminal: without this line a skipped
    grouping call left ``reasoning.md`` byte-identical to a clean run and the
    offline replay (ADR-0075) could not say why the run merged nothing.
    """
    text = result.thinking
    if result.grouping_reason is not None:
        note = f"no verdict: {result.grouping_reason}"
        text = f"{text}\n\n{note}" if text else note
    return ("duplicate grouping", text)


def _run_stocktake_phases(run: StocktakeRun, result: StocktakeResult) -> None:
    """Report, then merge -> drop -> clean -> description audit -> persist.

    Single staging batch for the whole run: ``staging._stage_results`` wipes
    STAGED_DIR on every call, so flushing per phase would erase the earlier
    batches. Per-item ``command`` lets one batch mix "<prefix>",
    "<prefix>-drop", and "<prefix>-clean".
    """
    from ..core.stocktake import format_stocktake_report

    print(format_stocktake_report(result, run.label))

    # With a clean_prompt (skills), the clean phase may rewrite singleton
    # triggers even when there is nothing to merge or drop, so don't short-
    # circuit. Rules pass no clean_prompt and keep the original early return.
    if not result.merge_groups and not result.quality_issues and run.clean_prompt is None:
        # Nothing to merge/drop/clean, but the grouping call still reasoned
        # about the corpus — persist that trace (ADR-0069) before returning.
        memory_cmds._write_reasoning(run.snapshot_path, [_grouping_section(result)])
        return

    items_dict = dict(result.items)
    staged_batch: list[StageItem] = []
    # ADR-0069: per-phase reasoning traces (stocktake runs think-ON). The
    # grouping trace rides on result.thinking; the rest are gathered per
    # operation and aggregated into reasoning.md at the end.
    merge_trace = _TraceSink()
    clean_trace = _TraceSink()
    desc_trace = _TraceSink()

    consumed = _stocktake_merge(run, result, items_dict, staged_batch, merge_trace)
    dropped = _stocktake_drop(run, result, items_dict, staged_batch)
    _stocktake_clean(run, result, consumed, dropped, staged_batch, clean_trace)
    _stocktake_describe(run, result, consumed, dropped, desc_trace)

    if run.stage and staged_batch:
        staging._stage_results(staged_batch, command=run.command_prefix)

    # ADR-0069: persist the run's reasoning — grouping (the main judgment) plus
    # each merge / clean / description-audit operation — to reasoning.md.
    sections: list[tuple[str, str | None]] = [_grouping_section(result)]
    sections += merge_trace.sections("merge")
    sections += clean_trace.sections("clean")
    sections += desc_trace.sections("description")
    memory_cmds._write_reasoning(run.snapshot_path, sections)


def _stocktake_merge(
    run: StocktakeRun,
    result: StocktakeResult,
    items_dict: dict[str, str],
    staged_batch: list[StageItem],
    trace: _TraceSink,
) -> frozenset[str]:
    """Filenames consumed by a successful merge (originals deleted on adopt)."""
    if not result.merge_groups:
        return frozenset()
    return frozenset(
        _stocktake_merge_phase(
            result.merge_groups,
            items_dict,
            target_dir=run.target_dir,
            merge_prompt=run.merge_prompt,
            command_prefix=run.command_prefix,
            fallback_title=run.fallback_title,
            stage=run.stage,
            staged_batch=staged_batch,
            trace_sink=trace.traces,
            trace_labels=trace.labels,
            snapshot_path=run.snapshot_path,
        )
    )


def _stocktake_drop(
    run: StocktakeRun,
    result: StocktakeResult,
    items_dict: dict[str, str],
    staged_batch: list[StageItem],
) -> _DropOutcome:
    flagged = frozenset(issue.filename for issue in result.quality_issues)
    if not result.quality_issues:
        return _DropOutcome(flagged=flagged, removed=frozenset())
    removed = _stocktake_drop_phase(
        result.quality_issues,
        items_dict,
        target_dir=run.target_dir,
        drop_command=run.drop_command,
        stage=run.stage,
        staged_batch=staged_batch,
        snapshot_path=run.snapshot_path,
    )
    return _DropOutcome(flagged=flagged, removed=frozenset(removed))


def _stocktake_clean(
    run: StocktakeRun,
    result: StocktakeResult,
    consumed: frozenset[str],
    dropped: _DropOutcome,
    staged_batch: list[StageItem],
    trace: _TraceSink,
) -> None:
    """Rewrite surviving singletons. Skips *flagged* drops, not just removed
    ones: there is no point cleaning a file this run is proposing to delete."""
    if run.clean_prompt is None:
        return
    _stocktake_clean_phase(
        result.items,
        target_dir=run.target_dir,
        command_prefix=run.command_prefix,
        clean_prompt=run.clean_prompt,
        skip_names=set(consumed | dropped.flagged),
        stage=run.stage,
        staged_batch=staged_batch,
        trace_sink=trace.traces,
        trace_labels=trace.labels,
        snapshot_path=run.snapshot_path,
    )


def _stocktake_describe(
    run: StocktakeRun,
    result: StocktakeResult,
    consumed: frozenset[str],
    dropped: _DropOutcome,
    trace: _TraceSink,
) -> None:
    """Audit descriptions of files that survive the run.

    Skips only files *actually removed* — a quality-flagged file the operator
    KEEPS stays in the selector catalog, so its description still needs
    auditing (codex review 2026-07-24). This is the one place that wants
    ``removed`` rather than ``flagged``.
    """
    # Truthiness, not `is not None`: a missing template file loads as ""
    # (domain.py required=False), and an empty prompt would fabricate
    # mismatch findings for every skill instead of abstaining
    # (python-reviewer 2026-07-24 MEDIUM).
    if not run.desc_prompt:
        return
    usage_counts = (
        dict(result.selection_usage.per_skill) if result.selection_usage is not None else None
    )
    _stocktake_description_phase(
        result.items,
        target_dir=run.target_dir,
        desc_prompt=run.desc_prompt,
        skip_names=set(consumed | dropped.removed),
        usage_counts=usage_counts,
        trace_sink=trace.traces,
        trace_labels=trace.labels,
    )


# ADR-0081 usage window: matches the 2-week shadow-reading cadence the
# enforcement decision was made on (2026-07-24 first reading).
_USAGE_WINDOW_DAYS = 14


def _load_selection_reading():
    """Read the ADR-0081 usage dimension for the skill stocktake report.

    The instrument is optional (audit_dir unset disables it; the log dir may
    simply not exist), so any failure degrades to None — the stocktake runs
    exactly as before, just without the usage section. Never fatal.
    """
    from ..core.skill_selection import read_skill_selection_log

    try:
        reading = read_skill_selection_log(
            config.EPISODE_LOG_DIR,
            days=_USAGE_WINDOW_DAYS,
            skills_dir=config.SKILLS_DIR,
        )
    except Exception as exc:  # noqa: BLE001 — advisory reading, never fatal
        logger.warning("skill-selection usage reading unavailable: %s", exc)
        return None
    if reading.records == 0:
        # Fresh install or kill-switched instrument: an empty log window is
        # "no observation", not "every skill went unselected" — attaching it
        # would render a spurious all-never-selected section and annotate
        # findings as 0x (codex review 2026-07-24).
        return None
    return reading


def _handle_skill_stocktake(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Audit skills and merge duplicates / drop low-quality files."""
    from ..core import prompts
    from ..core.stocktake import run_skill_stocktake

    # ADR-0074 fast-fail (see staging._refuse_if_pending). Must precede
    # run_skill_stocktake: its whole-corpus grouping call is the most
    # expensive request in the run.
    if getattr(args, "stage", False) and staging._refuse_if_pending("skill-stocktake"):
        return

    snapshot_path = memory_cmds._take_snapshot(args, "skill-stocktake", think=True)
    result = run_skill_stocktake(
        skills_dir=config.SKILLS_DIR,
        selection_reading=_load_selection_reading(),
    )
    _handle_stocktake_result(
        args,
        result,
        target_dir=config.SKILLS_DIR,
        label="Skill",
        merge_prompt=prompts.STOCKTAKE_MERGE_PROMPT,
        command_prefix="skill-stocktake",
        fallback_title="merged-skill",
        clean_prompt=prompts.STOCKTAKE_CLEAN_PROMPT,
        desc_prompt=prompts.STOCKTAKE_DESC_PROMPT,
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

    # ADR-0074 fast-fail (see staging._refuse_if_pending). Shares
    # skill-stocktake's staging call site but has its own grouping call.
    if getattr(args, "stage", False) and staging._refuse_if_pending("rules-stocktake"):
        return

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


def _add_skill_stocktake_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stage",
        action="store_true",
        help="Write merged skills to staging dir instead of interactive approval",
    )


def _add_rules_stocktake_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stage",
        action="store_true",
        help="Write merged rules to staging dir instead of interactive approval",
    )


# Tier 1.5: telemetry without the skills/rules/axioms corpus. Stocktake passes
# its own explicit system prompts, so loading the corpus would pollute its
# prompt environment (review 2026-06-27 M1) — but running with no telemetry at
# all, as the old no-LLM slot did, hid its generation behaviour entirely.
COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="skill-stocktake",
        help="Audit skills for duplicates and quality issues",
        handler=_handle_skill_stocktake,
        tier=Tier.LLM_RUNTIME_ONLY,
        add_arguments=_add_skill_stocktake_arguments,
    ),
    CommandSpec(
        name="rules-stocktake",
        help="Audit rules for duplicates and quality issues",
        handler=_handle_rules_stocktake,
        tier=Tier.LLM_RUNTIME_ONLY,
        add_arguments=_add_rules_stocktake_arguments,
    ),
)

"""Stocktake: audit skills and rules for duplicates and quality issues.

Duplicate detection is a single LLM grouping call: all candidate bodies
go to one ``generate`` request that returns the subsets which genuinely
describe the same behavior (``{"groups": [{"files": [...], "reason": ...}]}``).
The LLM reads full bodies, so it discriminates on concrete behavior — two
skills that share vocabulary or an abstract framing but prescribe distinct
actions are left in separate groups (or ungrouped) rather than collapsed.

This replaces the embedding-cosine + union-find clustering that shipped in
316719f: that path was a transitive single-linkage closure whose cosine was
dominated by the shared boilerplate of auto-extracted skills, so distinct
patterns scored ~0.9 alike and the whole set chained into one over-merged
blob. The grouping LLM does not have that blind spot. The original perf
motivation for embedding-only (generate() hung at the hardcoded
num_predict=8192) is moot now that every caller passes an explicit
num_predict.

Each returned group is then handed to ``merge_group`` for the actual merge.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ._io import strip_code_fence
from .llm import generate_full
from .text_utils import read_markdown_bodies

logger = logging.getLogger(__name__)

MIN_FILES_FOR_DEDUP = 2

# Code-side defaults for the stocktake LLM system prompts. The canonical text
# lives in config/prompts/stocktake_*_system.md (ADR-0054) so it is observable
# in the prompt layer; these defaults preserve today's behavior if a template
# file is missing or empty.
_DEFAULT_GROUP_SYSTEM = "Return only valid JSON."
_DEFAULT_MERGE_SYSTEM = "Merge skills, preserving every distinct concrete pattern."
_DEFAULT_CLEAN_SYSTEM = "Rewrite only the trigger conditions; preserve all else."

# Token budget per input file for a pattern-preserving merge. The merged
# skill is the union of each input's distinct patterns, so the output scales
# with group size. Used as ``min(8192, max(3000, _PER_FILE_MERGE_TOKENS * n))``
# in ``merge_group`` — floor preserves prior small-group behavior, 8192
# ceiling stays within the 32768 num_ctx headroom (see core/llm.generate).
_PER_FILE_MERGE_TOKENS = 500

# Token budget per input file for the grouping call. Its output is a compact
# JSON of filenames + brief reasons, so it needs far less than the merge.
# The 3000 floor dominates for typical stores (n <= 20); per-file scaling
# only engages beyond that, with the 8192 ceiling matching merge for very
# large stores. A too-small budget would truncate the JSON and corrupt
# parsing, silently dropping detected groups.
_GROUPING_TOKENS_PER_FILE = 150

# Tolerate leading whitespace and minor punctuation drift
# (e.g. "CANNOT_MERGE :", "cannot_merge:") the LLM may emit.
_CANNOT_MERGE_RE = re.compile(r"^\s*CANNOT_MERGE\s*:", re.IGNORECASE)


@dataclass(frozen=True)
class MergeGroup:
    """A group of files identified as semantically redundant."""

    filenames: Tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class QualityIssue:
    """A file with structural quality problems."""

    filename: str
    reason: str


@dataclass(frozen=True)
class StocktakeResult:
    """Result of a stocktake audit."""

    merge_groups: Tuple[MergeGroup, ...]
    quality_issues: Tuple[QualityIssue, ...]
    total_files: int
    items: Tuple[Tuple[str, str], ...] = ()
    # ADR-0069: the duplicate-grouping reasoning trace (stocktake runs
    # think-ON). This is the run's main judgment — which skills/rules are
    # redundant. Per-merge / per-clean traces are collected separately via the
    # ``trace_sink`` parameter in the CLI phases. None when think was off.
    thinking: Optional[str] = None


def _read_files(directory: Path) -> List[Tuple[str, str]]:
    """Read all .md files from a directory, stripping frontmatter.

    Returns list of (filename, body_text) tuples, sorted by name.
    """
    return read_markdown_bodies(directory)


def _format_items(items: List[Tuple[str, str]]) -> str:
    """Format (filename, body) tuples as LLM input with === separators."""
    return "\n\n===\n\n".join(f"**{name}**\n\n{body}" for name, body in items)


def _generate_with_trace(
    prompt: str,
    *,
    system: str,
    num_predict: int,
    caller: str,
    trace_sink: Optional[List[str]],
) -> Optional[str]:
    """Run a think-ON generate, append the reasoning trace, return the text.

    Centralises the ADR-0069 trace-capture contract shared by the grouping /
    merge / clean calls: think=True, append ``out.thinking`` to *trace_sink*
    when present, and return ``out.text`` (None when the LLM produced no
    text). Callers own any failure-path logging and post-processing.
    """
    out = generate_full(
        prompt, system=system, num_predict=num_predict,
        caller=caller, think=True,
    )
    if out is None or out.text is None:
        return None
    if trace_sink is not None and out.thinking:
        trace_sink.append(out.thinking)
    return out.text


def _find_duplicate_groups(
    items: List[Tuple[str, str]],
    prompt_template: str,
    trace_sink: Optional[List[str]] = None,
) -> List[MergeGroup]:
    """Detect semantic duplicate groups via a single LLM grouping call.

    All bodies go to one ``generate`` request; the LLM returns the subsets
    that genuinely describe the same behavior. Because it reads full bodies,
    it discriminates on concrete behavior rather than shared vocabulary, so
    it produces several coherent groups (or none) instead of collapsing the
    whole set into one over-merged blob.

    Args:
        items: List of (filename, body_text) tuples.
        prompt_template: Grouping prompt with an ``{items}`` placeholder.
        trace_sink: Optional list. When provided, the call runs think-ON
            (ADR-0069) and the grouping reasoning trace is appended to it.
            None (the test/default path) keeps the return type a plain list.

    Returns:
        List of MergeGroup. Empty list on LLM failure (safe default).
    """
    if len(items) < MIN_FILES_FOR_DEDUP:
        return []

    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from .prompts import STOCKTAKE_GROUP_SYSTEM_PROMPT

    prompt = prompt_template.format(items=_format_items(items))
    num_predict = min(8192, max(3000, _GROUPING_TOKENS_PER_FILE * len(items)))
    system = STOCKTAKE_GROUP_SYSTEM_PROMPT or _DEFAULT_GROUP_SYSTEM
    text = _generate_with_trace(
        prompt, system=system, num_predict=num_predict,
        caller="stocktake.duplicates", trace_sink=trace_sink,
    )
    if text is None:
        logger.warning("LLM failed during stocktake duplicate detection")
        return []

    return _parse_groups(text)


def _parse_groups(raw: str) -> List[MergeGroup]:
    """Parse LLM grouping output into a MergeGroup list.

    Attempts JSON extraction (tolerating code fences and surrounding prose).
    Groups with fewer than two files are dropped. Returns an empty list on
    parse failure — a malformed response yields no merges rather than an error.
    """
    text = strip_code_fence(raw)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object embedded in surrounding text.
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                logger.warning("Could not parse stocktake LLM output as JSON")
                return []
        else:
            logger.warning("No JSON found in stocktake LLM output")
            return []

    groups = data.get("groups", [])
    if not isinstance(groups, list):
        return []

    result: List[MergeGroup] = []
    for g in groups:
        files = g.get("files", [])
        reason = g.get("reason", "")
        if isinstance(files, list) and len(files) >= 2 and reason:
            result.append(
                MergeGroup(
                    filenames=tuple(str(f) for f in files),
                    reason=str(reason),
                )
            )
    return result


def merge_group(
    items: List[Tuple[str, str]],
    prompt_template: str,
    trace_sink: Optional[List[str]] = None,
) -> Optional[str]:
    """Merge redundant files into a single unified skill via LLM.

    The prompt instructs the LLM to emit ``CANNOT_MERGE: <reason>`` when
    the candidates are not actually redundant — callers should inspect
    the return value for that sentinel and treat it as a rejection.

    Args:
        items: List of (filename, body_text) tuples for the group.
        prompt_template: Prompt with {candidates} placeholder.
        trace_sink: Optional list. When provided, the call runs think-ON
            (ADR-0069) and the merge reasoning trace is appended to it. None
            (the test/default path) keeps the return type a plain string.

    Returns:
        Merged skill text (or CANNOT_MERGE response), None on LLM failure.
    """
    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from .prompts import STOCKTAKE_MERGE_SYSTEM_PROMPT

    prompt = prompt_template.format(candidates=_format_items(items))
    # The merge prompt preserves the *union* of every distinct concrete
    # pattern rather than synthesizing a shared core, so output length grows
    # with the number of inputs. Scale the token budget with group size:
    # a fixed cap would truncate large groups, silently dropping the very
    # patterns this merge exists to preserve. Floor keeps small-group
    # behavior unchanged; ceiling stays within the model's num_ctx headroom.
    num_predict = min(8192, max(3000, _PER_FILE_MERGE_TOKENS * len(items)))
    system = STOCKTAKE_MERGE_SYSTEM_PROMPT or _DEFAULT_MERGE_SYSTEM
    return _generate_with_trace(
        prompt, system=system, num_predict=num_predict,
        caller="stocktake.merge", trace_sink=trace_sink,
    )


def is_merge_rejected(merged_text: str) -> bool:
    """Check whether the merge LLM rejected this group as not actually redundant."""
    return _CANNOT_MERGE_RE.match(merged_text) is not None


# Token budget for a single-skill trigger-clean rewrite. Output is one skill
# of roughly the input's size (only the ``## When to Use`` triggers change),
# so a flat budget suffices — distilled skills are short. The 3000 floor
# matches merge_group's small-group budget, generous enough that a long skill
# is never truncated mid-rewrite. Bump if truncation is ever observed.
_CLEAN_TOKENS = 3000

# CLEAN_NOOP sentinel: the cleaner emits this when a skill's triggers already
# carry no transient surface identifiers, so there is nothing to generalize.
# Callers skip re-staging the file, keeping stocktake idempotent across runs.
# Start-anchored (like _CANNOT_MERGE_RE) so any trailing model chatter after
# the sentinel still reads as a no-op.
_CLEAN_NOOP_RE = re.compile(r"^\s*CLEAN_NOOP", re.IGNORECASE)


def clean_skill_triggers(
    item: Tuple[str, str],
    prompt_template: str,
    trace_sink: Optional[List[str]] = None,
) -> Optional[str]:
    """Rewrite a single skill's triggers at structural altitude.

    The prompt generalizes transient surface identifiers (usernames, post
    IDs, timestamp windows, single relevance scores) in the ``## When to
    Use`` section while keeping genuine recurring thresholds and preserving
    every other section verbatim. When the triggers are already clean the
    prompt emits ``CLEAN_NOOP`` — callers should detect that via
    ``is_clean_noop`` and skip re-staging the file.

    This is the singleton counterpart to ``merge_group``: a merged skill is
    rewritten at altitude by the merge prompt, but a skill with no twin never
    goes through a merge, so this pass cleans it directly.

    Args:
        item: (filename, body_text) of the skill to clean.
        prompt_template: Prompt with a ``{skill}`` placeholder.
        trace_sink: Optional list. When provided, the call runs think-ON
            (ADR-0069) and the clean reasoning trace is appended to it. None
            (the test/default path) keeps the return type a plain string.

    Returns:
        Rewritten skill text (or the CLEAN_NOOP sentinel), None on LLM failure.
    """
    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from .prompts import STOCKTAKE_CLEAN_SYSTEM_PROMPT

    _, body = item
    prompt = prompt_template.format(skill=body)
    return _generate_with_trace(
        prompt,
        system=STOCKTAKE_CLEAN_SYSTEM_PROMPT or _DEFAULT_CLEAN_SYSTEM,
        num_predict=_CLEAN_TOKENS,
        caller="stocktake.clean_triggers",
        trace_sink=trace_sink,
    )


def is_clean_noop(text: str) -> bool:
    """Check whether the cleaner found no transient identifiers to generalize."""
    return _CLEAN_NOOP_RE.match(text) is not None


def _check_skill_quality(filename: str, body: str) -> Optional[QualityIssue]:
    """Check a skill file for structural quality issues."""
    if len(body) < 200:
        return QualityIssue(filename=filename, reason="body < 200 chars")
    if "## Problem" not in body:
        return QualityIssue(filename=filename, reason='missing "## Problem" section')
    if "## Solution" not in body:
        return QualityIssue(filename=filename, reason='missing "## Solution" section')
    return None


def _check_rule_quality(filename: str, body: str) -> Optional[QualityIssue]:
    """Check a rule file for structural quality issues.

    Rules use the B-layer Practice/Rationale format (standing methodology),
    distinct from skill's trigger-action Problem/Solution format and from
    constitution's axiomatic clauses. A rule must declare an imperative or
    declarative practice and its rationale.
    """
    if len(body) < 200:
        return QualityIssue(filename=filename, reason="body < 200 chars")
    if "**Practice:**" not in body:
        return QualityIssue(filename=filename, reason='missing "**Practice:**" section')
    if "**Rationale:**" not in body:
        return QualityIssue(filename=filename, reason='missing "**Rationale:**" section')
    return None


def _run_stocktake(
    directory: Optional[Path],
    group_prompt: str,
    quality_check: Callable[[str, str], Optional[QualityIssue]],
) -> StocktakeResult:
    """Audit a directory of ``*.md`` files for duplicates and quality issues.

    Shared body for the skill and rule passes: they differ only in the
    grouping prompt and the per-file quality check.
    """
    if directory is None or not directory.is_dir():
        return StocktakeResult(merge_groups=(), quality_issues=(), total_files=0)

    items = _read_files(directory)
    if not items:
        return StocktakeResult(merge_groups=(), quality_issues=(), total_files=0)

    grouping_traces: List[str] = []
    merge_groups = _find_duplicate_groups(items, group_prompt, grouping_traces)

    # Structural quality checks
    quality_issues: List[QualityIssue] = []
    for filename, body in items:
        issue = quality_check(filename, body)
        if issue is not None:
            quality_issues.append(issue)

    return StocktakeResult(
        merge_groups=tuple(merge_groups),
        quality_issues=tuple(quality_issues),
        total_files=len(items),
        items=tuple(items),
        thinking="\n\n".join(grouping_traces) or None,
    )


def run_skill_stocktake(
    skills_dir: Optional[Path] = None,
) -> StocktakeResult:
    """Audit skills/*.md for duplicates and quality issues.

    Args:
        skills_dir: Directory containing skill files.

    Returns:
        StocktakeResult with merge groups and quality issues.
    """
    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from . import prompts

    return _run_stocktake(
        skills_dir, prompts.STOCKTAKE_SKILLS_PROMPT, _check_skill_quality
    )


def run_rules_stocktake(
    rules_dir: Optional[Path] = None,
) -> StocktakeResult:
    """Audit rules/*.md for duplicates and quality issues.

    Args:
        rules_dir: Directory containing rule files.

    Returns:
        StocktakeResult with merge groups and quality issues.
    """
    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from . import prompts

    return _run_stocktake(
        rules_dir, prompts.STOCKTAKE_RULES_PROMPT, _check_rule_quality
    )


def format_stocktake_report(result: StocktakeResult, label: str) -> str:
    """Format a StocktakeResult as a human-readable report.

    Renamed from ``format_report`` in ADR-0035 PR2 to remove the same-name
    collision with ``core.metrics.format_report`` (which formats a
    SessionReport, not a StocktakeResult).
    """
    lines: List[str] = []
    lines.append(f"{label} Stocktake Report")
    lines.append("=" * len(lines[0]))
    lines.append(f"{result.total_files} files scanned")

    if result.merge_groups:
        lines.append("")
        lines.append("MERGE groups:")
        for i, group in enumerate(result.merge_groups, 1):
            files = ", ".join(group.filenames)
            lines.append(f"  Group {i}: {files}")
            lines.append(f"    -> {group.reason}")
    else:
        lines.append("")
        lines.append("No duplicates detected.")

    if result.quality_issues:
        lines.append("")
        lines.append("LOW QUALITY:")
        for issue in result.quality_issues:
            lines.append(f"  {issue.filename} — {issue.reason}")

    # Summary
    merge_file_count = sum(len(g.filenames) for g in result.merge_groups)
    healthy = result.total_files - merge_file_count - len(result.quality_issues)
    lines.append("")
    lines.append(
        f"Summary: {len(result.merge_groups)} merge group(s) "
        f"({merge_file_count} files), "
        f"{len(result.quality_issues)} low quality, "
        f"{max(0, healthy)} healthy"
    )
    return "\n".join(lines)

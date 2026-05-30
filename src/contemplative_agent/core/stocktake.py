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
from typing import List, Optional, Tuple

from ._io import strip_code_fence
from .llm import generate
from .text_utils import strip_frontmatter

logger = logging.getLogger(__name__)

MIN_FILES_FOR_DEDUP = 2

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


def _read_files(directory: Path) -> List[Tuple[str, str]]:
    """Read all .md files from a directory, stripping frontmatter.

    Returns list of (filename, body_text) tuples, sorted by name.
    """
    if not directory.is_dir():
        return []

    items: List[Tuple[str, str]] = []
    for p in sorted(directory.glob("*.md")):
        if p.name.startswith("."):
            continue
        try:
            body = strip_frontmatter(p.read_text(encoding="utf-8")).strip()
            if body:
                items.append((p.name, body))
        except OSError:
            logger.warning("Could not read file %s", p)
    return items


def _format_items(items: List[Tuple[str, str]]) -> str:
    """Format (filename, body) tuples as LLM input with === separators."""
    return "\n\n===\n\n".join(f"**{name}**\n\n{body}" for name, body in items)


def _find_duplicate_groups(
    items: List[Tuple[str, str]],
    prompt_template: str,
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

    Returns:
        List of MergeGroup. Empty list on LLM failure (safe default).
    """
    if len(items) < MIN_FILES_FOR_DEDUP:
        return []

    prompt = prompt_template.format(items=_format_items(items))
    num_predict = min(8192, max(3000, _GROUPING_TOKENS_PER_FILE * len(items)))
    raw = generate(prompt, system="Return only valid JSON.", num_predict=num_predict)
    if raw is None:
        logger.warning("LLM failed during stocktake duplicate detection")
        return []

    return _parse_groups(raw)


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
) -> Optional[str]:
    """Merge redundant files into a single unified skill via LLM.

    The prompt instructs the LLM to emit ``CANNOT_MERGE: <reason>`` when
    the candidates are not actually redundant — callers should inspect
    the return value for that sentinel and treat it as a rejection.

    Args:
        items: List of (filename, body_text) tuples for the group.
        prompt_template: Prompt with {candidates} placeholder.

    Returns:
        Merged skill text (or CANNOT_MERGE response), None on LLM failure.
    """
    prompt = prompt_template.format(candidates=_format_items(items))
    # The merge prompt preserves the *union* of every distinct concrete
    # pattern rather than synthesizing a shared core, so output length grows
    # with the number of inputs. Scale the token budget with group size:
    # a fixed cap would truncate large groups, silently dropping the very
    # patterns this merge exists to preserve. Floor keeps small-group
    # behavior unchanged; ceiling stays within the model's num_ctx headroom.
    num_predict = min(8192, max(3000, _PER_FILE_MERGE_TOKENS * len(items)))
    return generate(prompt, system="Merge skills, preserving every distinct concrete pattern.", num_predict=num_predict)


def is_merge_rejected(merged_text: str) -> bool:
    """Check whether the merge LLM rejected this group as not actually redundant."""
    return _CANNOT_MERGE_RE.match(merged_text) is not None


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


def run_skill_stocktake(
    skills_dir: Optional[Path] = None,
) -> StocktakeResult:
    """Audit skills/*.md for duplicates and quality issues.

    Args:
        skills_dir: Directory containing skill files.

    Returns:
        StocktakeResult with merge groups and quality issues.
    """
    if skills_dir is None or not skills_dir.is_dir():
        return StocktakeResult(merge_groups=(), quality_issues=(), total_files=0)

    items = _read_files(skills_dir)
    if not items:
        return StocktakeResult(merge_groups=(), quality_issues=(), total_files=0)

    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from . import prompts

    merge_groups = _find_duplicate_groups(items, prompts.STOCKTAKE_SKILLS_PROMPT)

    # Structural quality checks
    quality_issues: List[QualityIssue] = []
    for filename, body in items:
        issue = _check_skill_quality(filename, body)
        if issue is not None:
            quality_issues.append(issue)

    return StocktakeResult(
        merge_groups=tuple(merge_groups),
        quality_issues=tuple(quality_issues),
        total_files=len(items),
        items=tuple(items),
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
    if rules_dir is None or not rules_dir.is_dir():
        return StocktakeResult(merge_groups=(), quality_issues=(), total_files=0)

    items = _read_files(rules_dir)
    if not items:
        return StocktakeResult(merge_groups=(), quality_issues=(), total_files=0)

    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from . import prompts

    merge_groups = _find_duplicate_groups(items, prompts.STOCKTAKE_RULES_PROMPT)

    # Structural quality checks
    quality_issues: List[QualityIssue] = []
    for filename, body in items:
        issue = _check_rule_quality(filename, body)
        if issue is not None:
            quality_issues.append(issue)

    return StocktakeResult(
        merge_groups=tuple(merge_groups),
        quality_issues=tuple(quality_issues),
        total_files=len(items),
        items=tuple(items),
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

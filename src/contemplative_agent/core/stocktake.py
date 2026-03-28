"""Stocktake: audit skills and rules for duplicates and quality issues.

LLM-based semantic duplicate detection + mechanical structure checks.
Read-only — produces reports without modifying files.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .llm import generate
from .rules_distill import _strip_frontmatter

logger = logging.getLogger(__name__)

MIN_FILES_FOR_DEDUP = 2


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
            body = _strip_frontmatter(p.read_text(encoding="utf-8")).strip()
            if body:
                items.append((p.name, body))
        except OSError:
            logger.warning("Could not read file %s", p)
    return items


def _find_duplicate_groups(
    items: List[Tuple[str, str]],
    prompt_template: str,
) -> List[MergeGroup]:
    """Pass all files to LLM and detect semantic duplicate groups.

    Args:
        items: List of (filename, body_text) tuples.
        prompt_template: Prompt with {items} placeholder.

    Returns:
        List of MergeGroup. Empty list on LLM failure (safe default).
    """
    if len(items) < MIN_FILES_FOR_DEDUP:
        return []

    formatted = "\n\n===\n\n".join(
        f"**{name}**\n\n{body}" for name, body in items
    )
    prompt = prompt_template.format(items=formatted)

    raw = generate(prompt, system="Return only valid JSON.", max_length=4000)
    if raw is None:
        logger.warning("LLM failed during stocktake duplicate detection")
        return []

    return _parse_groups(raw)


def _parse_groups(raw: str) -> List[MergeGroup]:
    """Parse LLM output into MergeGroup list.

    Attempts JSON extraction. Returns empty list on parse failure.
    """
    # Try to extract JSON from the response
    text = raw.strip()

    # Handle code fences
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            if block.startswith("{"):
                text = block
                break

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
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
            result.append(MergeGroup(
                filenames=tuple(str(f) for f in files),
                reason=str(reason),
            ))
    return result


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
    """Check a rule file for structural quality issues."""
    if len(body) < 200:
        return QualityIssue(filename=filename, reason="body < 200 chars")
    if "**When:**" not in body:
        return QualityIssue(filename=filename, reason='missing "**When:**" section')
    if "**Do:**" not in body:
        return QualityIssue(filename=filename, reason='missing "**Do:**" section')
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

    # Duplicate detection via LLM
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

    # Duplicate detection via LLM
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
    )


def format_report(result: StocktakeResult, label: str) -> str:
    """Format a StocktakeResult as a human-readable report."""
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

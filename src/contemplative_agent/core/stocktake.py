"""Stocktake: audit skills and rules for duplicates and quality issues.

Embedding-only duplicate detection: cosine similarity matrix via
nomic-embed-text → single-threshold union-find clustering. False
positives are reconciled at merge time — the merge LLM sees full bodies
and can emit ``CANNOT_MERGE: <reason>`` to reject spurious groupings.

Pair-level LLM judging was removed: num_ctx=32768 made "keep prompts
short" meaningless (KV cache allocated regardless), and sequential
pair calls ran ~15-30 minutes on M1. The merge step already reads both
full bodies, so a separate judge layer was redundant.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

from .embeddings import cosine_similarity_matrix, embed_texts
from .llm import generate
from .text_utils import strip_frontmatter
from .thresholds import SIM_CLUSTER_THRESHOLD

logger = logging.getLogger(__name__)

MIN_FILES_FOR_DEDUP = 2

# Token budget per input file for a pattern-preserving merge. The merged
# skill is the union of each input's distinct patterns, so the output scales
# with group size. Used as ``min(8192, max(3000, _PER_FILE_MERGE_TOKENS * n))``
# in ``merge_group`` — floor preserves prior small-group behavior, 8192
# ceiling stays within the 32768 num_ctx headroom (see core/llm.generate).
_PER_FILE_MERGE_TOKENS = 500

# Embedding cosine threshold for clustering. Calibrated on real
# auto-extracted skill bodies: the same attractor expressed with
# different vocabulary (adaptive/fluid/dynamic) lands in the 0.86-0.94
# band; distinct skills typically score < 0.75. 0.80 is the midpoint
# and errs slightly toward over-grouping, relying on the merge LLM's
# CANNOT_MERGE path to reject genuine false positives.

_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_WS_RE = re.compile(r"\s+")

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


def _normalize_for_similarity(body: str) -> str:
    """Strip Markdown scaffolding and collapse whitespace for similarity scoring.

    Reduces the baseline ratio inflation caused by shared section headings
    (e.g. "## Problem", "## Solution") that all auto-extracted skills share.
    """
    no_headings = _HEADING_RE.sub("", body)
    return _WS_RE.sub(" ", no_headings).strip()


def _pairwise_similarity(items: List[Tuple[str, str]]) -> List[Tuple[int, int, float]]:
    """Compute embedding cosine similarity for every (i, j) pair with i < j.

    Returns list of (i, j, similarity) tuples. Bodies are normalized first.
    Returns an empty list if the embedding service is unavailable — caller
    will then produce zero MergeGroups (safe default).
    """
    normalized = [_normalize_for_similarity(body) for _, body in items]
    vectors = embed_texts(normalized)
    if vectors is None or vectors.shape[0] != len(items):
        logger.warning("Embedding unavailable — skipping similarity-based dedup")
        return []
    sim = cosine_similarity_matrix(vectors)
    out: List[Tuple[int, int, float]] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            out.append((i, j, float(sim[i][j])))
    return out


def _cluster_pairs(
    pairs: List[Tuple[int, int, float]],
    item_count: int,
) -> List[Set[int]]:
    """Union-find transitive closure over pairs that cleared the threshold.

    Singleton items (no qualifying pair) are not returned. Clusters of
    size >= 2 only.
    """
    if not pairs:
        return []

    parent = list(range(item_count))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, j, _ in pairs:
        union(i, j)

    groups: dict[int, Set[int]] = {}
    seen_in_pair: Set[int] = set()
    for i, j, _ in pairs:
        seen_in_pair.add(i)
        seen_in_pair.add(j)
    for x in seen_in_pair:
        root = find(x)
        groups.setdefault(root, set()).add(x)

    return [g for g in groups.values() if len(g) >= 2]


def _find_duplicate_groups(
    items: List[Tuple[str, str]],
) -> List[MergeGroup]:
    """Embedding-only duplicate detection.

    Pipeline:
      1. Compute cosine similarity for every pair (single nomic-embed batch).
      2. Keep pairs with similarity >= SIM_CLUSTER_THRESHOLD.
      3. Union-find clusters all qualifying pairs into MergeGroups.

    False positives (borderline 0.80-0.86 pairs that embedding flags but
    aren't actually redundant) are caught at merge time — merge_group()
    sees the full bodies and can respond CANNOT_MERGE.

    Returns empty list if embedding service unavailable (safe default).
    """
    if len(items) < MIN_FILES_FOR_DEDUP:
        return []

    pairs = _pairwise_similarity(items)
    if logger.isEnabledFor(logging.DEBUG):
        for i, j, ratio in sorted(pairs, key=lambda p: -p[2]):
            logger.debug("ratio %.2f: %s <> %s", ratio, items[i][0], items[j][0])

    qualifying = [(i, j, r) for i, j, r in pairs if r >= SIM_CLUSTER_THRESHOLD]
    clusters = _cluster_pairs(qualifying, len(items))

    groups: List[MergeGroup] = []
    for cluster in clusters:
        filenames = tuple(items[idx][0] for idx in sorted(cluster))
        cluster_pairs = [(i, j, r) for i, j, r in qualifying if i in cluster and j in cluster]
        max_ratio = max((r for _, _, r in cluster_pairs), default=0.0)
        reason = f"{len(cluster_pairs)} pair(s) >= {SIM_CLUSTER_THRESHOLD:.2f} (max={max_ratio:.2f})"
        groups.append(MergeGroup(filenames=filenames, reason=reason))
    return groups


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

    merge_groups = _find_duplicate_groups(items)

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

    merge_groups = _find_duplicate_groups(items)

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

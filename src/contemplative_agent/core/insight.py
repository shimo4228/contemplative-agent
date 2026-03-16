"""Insight extraction: synthesize learned patterns into behavioral skills.

Uses a two-pass LLM approach:
1. Extract a skill candidate from accumulated knowledge patterns.
2. Evaluate the candidate with a rubric (5 dimensions × 1-5 score).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from ._io import write_restricted
from .llm import generate, validate_identity_content
from .memory import KnowledgeStore
from .prompts import INSIGHT_EXTRACTION_PROMPT, INSIGHT_EVAL_PROMPT

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3
MAX_FIELD_LENGTH = 200
MAX_SLUG_LENGTH = 50

RUBRIC_DIMENSIONS = (
    "SPECIFICITY",
    "ACTIONABILITY",
    "SCOPE_FIT",
    "NON_REDUNDANCY",
    "COVERAGE",
)
MIN_SCORE = 1
MAX_SCORE = 5
PASS_THRESHOLD = 3  # Every dimension must be >= this to pass


@dataclass(frozen=True)
class SkillCandidate:
    """Parsed skill extracted from accumulated knowledge."""

    title: str
    context: str
    problem: str
    behavior: str
    evidence: str


@dataclass(frozen=True)
class RubricScore:
    """Rubric evaluation result (5 dimensions × 1-5)."""

    specificity: int
    actionability: int
    scope_fit: int
    non_redundancy: int
    coverage: int

    @property
    def total(self) -> int:
        return (
            self.specificity
            + self.actionability
            + self.scope_fit
            + self.non_redundancy
            + self.coverage
        )

    @property
    def passed(self) -> bool:
        """All dimensions must be >= PASS_THRESHOLD."""
        return all(
            s >= PASS_THRESHOLD
            for s in (
                self.specificity,
                self.actionability,
                self.scope_fit,
                self.non_redundancy,
                self.coverage,
            )
        )

    @property
    def confidence(self) -> float:
        """Normalize total to 0.0-1.0."""
        return self.total / (MAX_SCORE * len(RUBRIC_DIMENSIONS))


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _parse_skill_response(response: str) -> Optional[SkillCandidate]:
    """Parse LLM response into a SkillCandidate.

    Returns None if any required field is missing.
    """
    fields = {}
    for field in ("TITLE", "CONTEXT", "PROBLEM", "BEHAVIOR", "EVIDENCE"):
        match = re.search(
            rf"^{field}:\s*(.+?)$", response, re.MULTILINE | re.IGNORECASE
        )
        if not match:
            return None
        fields[field] = match.group(1).strip()[:MAX_FIELD_LENGTH]

    return SkillCandidate(
        title=fields["TITLE"],
        context=fields["CONTEXT"],
        problem=fields["PROBLEM"],
        behavior=fields["BEHAVIOR"],
        evidence=fields["EVIDENCE"],
    )


def _parse_rubric_response(response: str) -> RubricScore:
    """Parse rubric scores from LLM response.

    Handles multiple output formats from Qwen:
    - Standard: "SPECIFICITY: 3"
    - Markdown bold: "**SPECIFICITY**: 3"
    - Table: "| SPECIFICITY | 3 |"
    - Inline: "SPECIFICITY: 3 (because...)"

    Returns default score (3 for each dimension) on parse failure.
    """
    scores = {}
    for dim in RUBRIC_DIMENSIONS:
        # Try multiple patterns: standard, markdown bold, table format
        match = re.search(
            rf"(?:^|\|)\s*\**{dim}\**[:\s|]+(\d+)",
            response,
            re.MULTILINE | re.IGNORECASE,
        )
        if match:
            scores[dim] = _clamp(int(match.group(1)), MIN_SCORE, MAX_SCORE)
        else:
            logger.warning("Failed to parse rubric dimension %s, defaulting to %d (fail-safe)", dim, MIN_SCORE)
            scores[dim] = MIN_SCORE

    return RubricScore(
        specificity=scores["SPECIFICITY"],
        actionability=scores["ACTIONABILITY"],
        scope_fit=scores["SCOPE_FIT"],
        non_redundancy=scores["NON_REDUNDANCY"],
        coverage=scores["COVERAGE"],
    )


def _slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    normalized = unicodedata.normalize("NFKD", title)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH]


def _yaml_safe(text: str, max_len: int) -> str:
    """Sanitize text for YAML quoted values: strip newlines and double quotes."""
    return text.replace("\r", "").replace("\n", " ").replace('"', "'")[:max_len]


def _render_skill_file(
    candidate: SkillCandidate, score: RubricScore, source_patterns: int
) -> str:
    """Render a SkillCandidate + RubricScore as YAML frontmatter + Markdown."""
    safe_name = _slugify(candidate.title)
    safe_desc = _yaml_safe(candidate.context, 130)
    safe_title = candidate.title.replace("\r", "").replace("\n", " ")
    return (
        f"---\n"
        f'name: "{safe_name}"\n'
        f'description: "{safe_desc}"\n'
        f"origin: auto-extracted\n"
        f"confidence: {score.confidence:.2f}\n"
        f'extracted: "{date.today().isoformat()}"\n'
        f"source_patterns: {source_patterns}\n"
        f"---\n"
        f"# {safe_title}\n"
        f"\n"
        f"**Context:** {candidate.context}\n"
        f"\n"
        f"## Problem\n"
        f"{candidate.problem}\n"
        f"\n"
        f"## Behavior\n"
        f"{candidate.behavior}\n"
        f"\n"
        f"## Evidence\n"
        f"{candidate.evidence}\n"
    )


def _render_score_table(score: RubricScore) -> str:
    """Render rubric scores as a Markdown table."""
    rows = [
        f"| Specificity | {score.specificity}/5 |",
        f"| Actionability | {score.actionability}/5 |",
        f"| Scope Fit | {score.scope_fit}/5 |",
        f"| Non-redundancy | {score.non_redundancy}/5 |",
        f"| Coverage | {score.coverage}/5 |",
        f"| **Total** | **{score.total}/25** |",
    ]
    header = "| Dimension | Score |\n|-----------|-------|\n"
    return header + "\n".join(rows)


def _extract_skill(
    patterns: List[str], insights: List[str]
) -> Optional[SkillCandidate]:
    """LLM call 1: Extract a skill candidate from patterns and insights."""
    prompt = INSIGHT_EXTRACTION_PROMPT.format(
        patterns="\n".join(f"- {p}" for p in patterns),
        insights="\n".join(f"- {i}" for i in insights) if insights else "(none)",
    )

    result = generate(prompt, max_length=1500)
    if result is None:
        logger.warning("LLM failed to generate skill extraction.")
        return None

    candidate = _parse_skill_response(result)
    if candidate is None:
        logger.warning("Failed to parse skill extraction response.")
        logger.debug("Raw LLM output (first 200 chars): %.200s", result)
    return candidate


def _evaluate_skill(candidate: SkillCandidate) -> RubricScore:
    """LLM call 2: Evaluate a skill candidate with the rubric."""
    prompt = INSIGHT_EVAL_PROMPT.format(
        title=candidate.title,
        context=candidate.context,
        problem=candidate.problem,
        behavior=candidate.behavior,
        evidence=candidate.evidence,
    )

    result = generate(prompt, max_length=500)
    logger.debug("Eval raw output: %s", result)
    if result is None:
        logger.warning("LLM failed to evaluate skill — dropping candidate (fail-safe).")
        return RubricScore(
            specificity=MIN_SCORE,
            actionability=MIN_SCORE,
            scope_fit=MIN_SCORE,
            non_redundancy=MIN_SCORE,
            coverage=MIN_SCORE,
        )

    return _parse_rubric_response(result)


def extract_insight(
    knowledge_store: Optional[KnowledgeStore] = None,
    skills_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Extract a behavioral skill from accumulated knowledge.

    Two-pass LLM approach:
    1. Extract skill candidate from patterns + insights.
    2. Evaluate with rubric. Save if all dimensions >= 3, else drop.

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        skills_dir: Directory to write skill files. Created if needed.
        dry_run: If True, show result without writing.

    Returns:
        The rendered skill file content, score table, or an error message.
    """
    if knowledge_store is None:
        return "No knowledge store provided."

    knowledge_store.load()
    patterns: List[str] = list(knowledge_store.get_learned_patterns())
    insights: List[str] = list(knowledge_store.get_insights(limit=10))

    if len(patterns) < MIN_PATTERNS_REQUIRED:
        return (
            f"Insufficient patterns ({len(patterns)}/{MIN_PATTERNS_REQUIRED}). "
            f"Run more sessions and distill first."
        )

    # Pass 1: Extract
    candidate = _extract_skill(patterns, insights)
    if candidate is None:
        return "Failed to extract skill from knowledge."

    # Validate against forbidden patterns
    combined = (
        f"{candidate.title} {candidate.context} "
        f"{candidate.problem} {candidate.behavior} {candidate.evidence}"
    )
    if not validate_identity_content(combined):
        return "Generated skill contains forbidden patterns. Skipping."

    # Pass 2: Evaluate
    score = _evaluate_skill(candidate)
    score_table = _render_score_table(score)

    if not score.passed:
        return (
            f"Skill did not pass quality gate (need all dimensions >= {PASS_THRESHOLD}).\n\n"
            f"{score_table}\n\n"
            f"--- Candidate (not saved) ---\n"
            f"Title: {candidate.title}\n"
            f"Context: {candidate.context}\n"
            f"Problem: {candidate.problem}\n"
            f"Behavior: {candidate.behavior}\n"
            f"Evidence: {candidate.evidence}"
        )

    rendered = _render_skill_file(candidate, score, source_patterns=len(patterns))

    if dry_run:
        logger.info("Dry run — not writing skill file")
        return f"{rendered}\n{score_table}"

    if skills_dir is None:
        logger.info("No skills directory configured, returning result only")
        return f"{rendered}\n{score_table}"

    skills_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(candidate.title)
    if not slug:
        logger.warning("Skill title produced empty slug, dropping candidate")
        return "Generated skill title produced no valid slug. Skipping."
    today = date.today().isoformat()
    filename = f"{today}-{slug}.md"
    file_path = skills_dir / filename

    if not file_path.resolve().is_relative_to(skills_dir.resolve()):
        logger.error("Skill path escape attempt: %s", file_path)
        return "Internal error: invalid skill path."

    write_restricted(file_path, rendered)
    logger.info("Skill written: %s", file_path)
    return f"{rendered}\n{score_table}"

"""Insight extraction: synthesize learned patterns into behavioral skills."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

from ._io import write_restricted
from .llm import generate, validate_identity_content
from .memory import KnowledgeStore
from .prompts import INSIGHT_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3
MAX_FIELD_LENGTH = 200
MAX_SLUG_LENGTH = 50


@dataclass(frozen=True)
class SkillFile:
    """Parsed skill extracted from accumulated knowledge."""

    title: str
    context: str
    behavior: str
    evidence: str
    axiom: str
    confidence: float
    extracted: str
    source_patterns: int


def _parse_skill_content(response: str) -> Optional[Tuple[str, str, str, str]]:
    """Parse LLM response into (title, context, behavior, evidence).

    Returns None if any required field is missing.
    """
    fields = {}
    for field in ("TITLE", "CONTEXT", "BEHAVIOR", "EVIDENCE"):
        match = re.search(
            rf"^{field}:\s*(.+?)$", response, re.MULTILINE | re.IGNORECASE
        )
        if not match:
            return None
        fields[field] = match.group(1).strip()[:MAX_FIELD_LENGTH]

    return (fields["TITLE"], fields["CONTEXT"], fields["BEHAVIOR"], fields["EVIDENCE"])


def _match_axiom(content: str, clauses: str) -> str:
    """Find the most relevant constitutional clause by keyword overlap.

    Returns a truncated clause snippet, or "none" if no match.
    """
    if not clauses.strip():
        return "none"

    content_words = set(re.findall(r"[a-z]{4,}", content.lower()))
    if not content_words:
        return "none"

    best_clause = ""
    best_overlap = 0

    for line in clauses.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        clause_words = set(re.findall(r"[a-z]{4,}", line.lower()))
        overlap = len(content_words & clause_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_clause = line

    if best_overlap < 2:
        return "none"

    return best_clause[:80]


def _slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    # Normalize unicode, lowercase, replace non-alnum with hyphens
    normalized = unicodedata.normalize("NFKD", title)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH]


def _render_skill_file(skill: SkillFile) -> str:
    """Render a SkillFile as YAML frontmatter + Markdown body."""
    safe_axiom = skill.axiom.replace('"', "'")
    return (
        f"---\n"
        f'axiom: "{safe_axiom}"\n'
        f"confidence: {skill.confidence}\n"
        f'extracted: "{skill.extracted}"\n'
        f"source_patterns: {skill.source_patterns}\n"
        f"---\n"
        f"# {skill.title}\n"
        f"\n"
        f"## Context\n"
        f"{skill.context}\n"
        f"\n"
        f"## Behavior\n"
        f"{skill.behavior}\n"
        f"\n"
        f"## Evidence\n"
        f"{skill.evidence}\n"
    )


def extract_insight(
    knowledge_store: Optional[KnowledgeStore] = None,
    constitutional_clauses: str = "",
    skills_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Extract a behavioral skill from accumulated knowledge.

    Args:
        knowledge_store: KnowledgeStore with learned patterns and insights.
        constitutional_clauses: Current constitutional clauses text.
        skills_dir: Directory to write skill files. Created if needed.
        dry_run: If True, show result without writing.

    Returns:
        The rendered skill file content, or an error/status message.
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

    prompt = INSIGHT_EXTRACTION_PROMPT.format(
        patterns="\n".join(f"- {p}" for p in patterns),
        insights="\n".join(f"- {i}" for i in insights) if insights else "(none)",
        clauses=constitutional_clauses if constitutional_clauses else "(none)",
    )

    result = generate(prompt, max_length=1500)
    if result is None:
        msg = "LLM failed to generate insight."
        logger.warning(msg)
        return msg

    parsed = _parse_skill_content(result)
    if parsed is None:
        msg = "Failed to parse LLM output into skill format."
        logger.warning(msg)
        logger.debug("Raw LLM output: %s", result)
        return msg

    title, context, behavior, evidence = parsed

    # Validate against forbidden patterns
    combined = f"{title} {context} {behavior} {evidence}"
    if not validate_identity_content(combined):
        msg = "Generated insight contains forbidden patterns. Skipping."
        logger.warning(msg)
        return msg

    axiom = _match_axiom(combined, constitutional_clauses)
    today = date.today().isoformat()

    skill = SkillFile(
        title=title,
        context=context,
        behavior=behavior,
        evidence=evidence,
        axiom=axiom,
        confidence=0.5,
        extracted=today,
        source_patterns=len(patterns),
    )

    rendered = _render_skill_file(skill)

    if dry_run:
        logger.info("Dry run — not writing skill file")
        return rendered

    if skills_dir is None:
        logger.info("No skills directory configured, returning result only")
        return rendered

    skills_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(title)
    filename = f"{today}-{slug}.md"
    file_path = skills_dir / filename

    if not file_path.resolve().is_relative_to(skills_dir.resolve()):
        logger.error("Skill path escape attempt: %s", file_path)
        return "Internal error: invalid skill path."

    write_restricted(file_path, rendered)
    logger.info("Skill written: %s", file_path)
    return rendered

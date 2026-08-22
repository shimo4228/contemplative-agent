"""Stocktake: audit the skill store for structural quality and description fidelity.

ADR-0097 reduced this module to what survived the consolidator dissolution:

- a deterministic structural check per file (``_check_skill_quality``, run
  over the store by ``run_skill_stocktake``; and ``_check_rule_quality``,
  which this module no longer runs at all — see below);
- the ADR-0081 description-fidelity audit (``audit_skill_description``), the
  one LLM call left, advisory only;
- the ADR-0081 usage reading attached to the report (statistics computed by
  code; retirement is a human decision at the Saturday gate on the packet's
  never-selected section — never a numeric auto-threshold).

``_check_rule_quality`` has no caller here, and that is its role rather
than a gap. ADR-0097 slice 2 put the rules layer's maintenance reading in the
weekly packet, and the packet's producer (``scripts/value_layer_due_check``)
runs under the SYSTEM python3 — no ``contemplative_agent`` on its path — so it
re-derives the two-line check locally. What survives here is the **reference**
that re-derivation is pinned against: ``tests/test_value_layer_due_check``
imports this function and asserts the two agree verdict-for-verdict, so a
change to one and not the other fails Verify. That is a live consumer; it is
simply not the in-process one the reservation named. The wrapper that named
it (``run_rules_quality_check``) was deleted with the reservation.

The LLM grouping call, the union merge and the ADR-0048 clean stage were
retired by ADR-0097: grouping judged from frontmatter summaries with no recall
measurement, merge produced over-broad skills, and clean rewrote 14 of 47
files byte-identically while inserting generalization boilerplate into 3.
Duplicate structure is now read from the selection log (co-selection), and
consolidation happens at the gate as supersede-and-archive.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ._io import scrub_control
from .llm import generate_full
from .text_utils import read_markdown_documents

if TYPE_CHECKING:
    from .skill_selection import SkillSelectionReading

logger = logging.getLogger(__name__)

# Code-side default for the description-audit system prompt. The canonical text
# lives in config/prompts/stocktake_description_system.md (ADR-0054) so it is
# observable in the prompt layer; the default preserves behavior if the template
# file is missing or empty.
_DEFAULT_DESC_SYSTEM = "Judge description fidelity only; output DESC_OK or one reason line."


@dataclass(frozen=True)
class QualityIssue:
    """A file with structural quality problems."""

    filename: str
    reason: str


@dataclass(frozen=True)
class StocktakeResult:
    """Result of a stocktake audit."""

    quality_issues: tuple[QualityIssue, ...]
    total_files: int
    # (filename, raw text, frontmatter-stripped body) — the raw half rides
    # along so the description audit judges the same bytes the quality check
    # read, instead of re-reading each file under a second read policy.
    items: tuple[tuple[str, str, str], ...] = ()
    # ADR-0081 usage dimension: the selection-log reading (statistics computed
    # by code). Rendered as a report section only — retirement is a human
    # decision at the gate, never a numeric auto-threshold (ADR-0097 D5).
    selection_usage: SkillSelectionReading | None = None


# Token budget for a single-skill description audit. Output is DESC_OK or a
# one-line mismatch reason, so a small flat budget suffices (same shape as
# the selection call's name-list budget in core.skill_selection).
_DESC_AUDIT_TOKENS = 400

# Terminal-safety bound for the audit's reason line (it is untrusted LLM
# output printed to the operator's console). The scrub itself is
# ``_io.scrub_control`` — collapses whitespace to one line, drops control
# characters, caps length — shared with the selector's catalog and the
# episode renderer rather than re-derived here.
_DESC_REASON_MAX_CHARS = 300

# DESC_OK sentinel: the auditor emits this when the frontmatter description
# faithfully carries the body's trigger conditions. Start-anchored so trailing
# model chatter still reads as a pass.
_DESC_OK_RE = re.compile(r"^\s*DESC_OK", re.IGNORECASE)


def audit_skill_description(
    item: tuple[str, str, str],
    prompt_template: str,
) -> tuple[str | None, str | None]:
    """Judge whether a skill's description faithfully carries its triggers.

    ADR-0081: under two-pass injection the description is the selector's
    only evidence, so a description that is broader or narrower than the
    body's actual trigger conditions distorts every selection. This audit
    is advisory-only — it returns a one-line mismatch reason for the
    stocktake report (the human decides what to do), or ``None`` when the
    description is faithful (``DESC_OK``) or the LLM call fails (abstain,
    logged — never a fabricated verdict).

    Args:
        item: (filename, description, body_text) of the skill to audit.
        prompt_template: Prompt with ``{name}`` / ``{description}`` /
            ``{skill}`` placeholders.

    Returns:
        ``(reason, thinking)`` — the mismatch reason line, or None when the
        description is faithful or the call failed; and the ADR-0069
        reasoning trace (think-ON), or None when the model returned none.
        The result carries its own trace, like every other value-layer
        pipeline, so no caller has to keep a parallel list in step.
    """
    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from .llm import wrap_untrusted_content
    from .prompts import STOCKTAKE_DESC_SYSTEM_PROMPT

    name, description, body = item
    # Both fields are persistent LLM-distilled content and the exact target
    # of this judgment — a skill body saying "output DESC_OK" must not be
    # able to suppress its own mismatch. Wrap them in the untrusted-content
    # boundary before generation (codex review 2026-07-24): this call judges
    # content rather than transforming it, so the incentive to self-exonerate
    # is real.
    prompt = prompt_template.format(
        name=name,
        description=wrap_untrusted_content(description),
        skill=wrap_untrusted_content(body),
    )
    out = generate_full(
        prompt,
        system=STOCKTAKE_DESC_SYSTEM_PROMPT or _DEFAULT_DESC_SYSTEM,
        num_predict=_DESC_AUDIT_TOKENS,
        caller="stocktake.description_audit",
        think=True,
        drop_truncated=True,
    )
    thinking = out.thinking if out is not None else None
    if out is None or out.text is None:
        logger.warning("LLM failed during stocktake description audit: %s", name)
        return None, thinking
    if _DESC_OK_RE.match(out.text):
        return None, thinking
    # The reason reaches the terminal report: one line guaranteed (embedded
    # newlines could spoof extra report entries — security review
    # 2026-07-24), control characters dropped (ANSI injection guard), capped.
    return scrub_control(out.text, _DESC_REASON_MAX_CHARS), thinking


def _check_skill_quality(filename: str, body: str) -> QualityIssue | None:
    """Check a skill file for structural quality issues."""
    if len(body) < 200:
        return QualityIssue(filename=filename, reason="body < 200 chars")
    if "## Problem" not in body:
        return QualityIssue(filename=filename, reason='missing "## Problem" section')
    if "## Solution" not in body:
        return QualityIssue(filename=filename, reason='missing "## Solution" section')
    return None


def _check_rule_quality(filename: str, body: str) -> QualityIssue | None:
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
    skills_dir: Path | None = None,
    selection_reading: SkillSelectionReading | None = None,
) -> StocktakeResult:
    """Audit skills/*.md for structural quality issues (no LLM call).

    Args:
        skills_dir: Directory containing skill files.
        selection_reading: Optional ADR-0081 usage dimension — the selection
            log reading, attached to the result for the report's usage
            section. Statistics only; no gate or threshold consumes it.

    Returns:
        StocktakeResult with quality issues and the scanned items.
    """
    if skills_dir is None or not skills_dir.is_dir():
        return StocktakeResult(quality_issues=(), total_files=0)
    docs = read_markdown_documents(skills_dir)
    if not docs:
        return StocktakeResult(quality_issues=(), total_files=0)

    quality_issues = tuple(
        issue
        for issue in (_check_skill_quality(filename, body) for filename, _raw, body in docs)
        if issue is not None
    )
    result = StocktakeResult(
        quality_issues=quality_issues,
        total_files=len(docs),
        items=tuple(docs),
    )
    if selection_reading is None:
        return result
    return replace(result, selection_usage=selection_reading)


def format_stocktake_report(result: StocktakeResult, label: str) -> str:
    """Format a StocktakeResult as a human-readable report.

    Renamed from ``format_report`` in ADR-0035 PR2 to remove the same-name
    collision with ``core.metrics.format_report`` (which formats a
    SessionReport, not a StocktakeResult).
    """
    lines: list[str] = []
    lines.append(f"{label} Stocktake Report")
    lines.append("=" * len(lines[0]))
    lines.append(f"{result.total_files} files scanned")

    if result.quality_issues:
        lines.append("")
        lines.append("LOW QUALITY:")
        for issue in result.quality_issues:
            lines.append(f"  {issue.filename} — {issue.reason}")

    # ADR-0081 usage dimension: full selection distribution, ascending so the
    # quiet tail (retirement candidates for the human gate) reads first.
    # Never survivors-only; never a numeric auto-retire threshold.
    usage = result.selection_usage
    if usage is not None:
        lines.append("")
        lines.append(
            f"SKILL USAGE (selection window {usage.days}d, {usage.records} records, "
            f"{usage.judged_records} judged):"
        )
        for name, count in sorted(usage.per_skill, key=lambda kv: (kv[1], kv[0])):
            lines.append(f"  {name}: selected {count}x")
        if usage.never_selected_exposure:
            # Exposure, not a bare list: this is the surface the human
            # retirement gate reads, so "adopted yesterday" and "offered a
            # thousand times and refused" must not look the same here.
            # Imported here rather than at module level: the type-only
            # import above exists to keep this module free of a runtime
            # dependency on the instrument, and the phrasing is needed on
            # exactly one branch.
            from .skill_selection import format_never_selected_exposure

            lines.append("  Never selected in window:")
            for name, exposure in usage.never_selected_exposure:
                lines.append(f"    {name}: {format_never_selected_exposure(exposure, usage)}")

    healthy = result.total_files - len(result.quality_issues)
    lines.append("")
    lines.append(f"Summary: {len(result.quality_issues)} low quality, {max(0, healthy)} healthy")
    return "\n".join(lines)

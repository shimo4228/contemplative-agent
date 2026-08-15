"""Stocktake: audit skills and rules for duplicates and quality issues.

Duplicate detection is a single LLM grouping call: one ``generate`` request
returns the subsets which genuinely describe the same behavior
(``{"groups": [{"files": [...], "reason": ...}]}``). The skill pass sends
one summary per skill (frontmatter description + Context sentence — see
``_skill_grouping_evidence``); the rules pass sends the short rule bodies;
``merge_group`` always reads full bodies and can refuse a group. Shared
vocabulary or an abstract framing is not grounds for grouping — the prompt
says so and the merge stage re-checks on the concrete text.

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
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ._io import strip_code_fence
from .llm import generate_full
from .text_utils import context_summary, read_markdown_documents, skill_theme

if TYPE_CHECKING:
    from .skill_selection import SkillSelectionReading

logger = logging.getLogger(__name__)

MIN_FILES_FOR_DEDUP = 2

# Code-side defaults for the stocktake LLM system prompts. The canonical text
# lives in config/prompts/stocktake_*_system.md (ADR-0054) so it is observable
# in the prompt layer; these defaults preserve today's behavior if a template
# file is missing or empty.
_DEFAULT_GROUP_SYSTEM = "Return only valid JSON."
_DEFAULT_MERGE_SYSTEM = "Merge skills, preserving every distinct concrete pattern."
_DEFAULT_CLEAN_SYSTEM = "Rewrite only the trigger conditions; preserve all else."
_DEFAULT_DESC_SYSTEM = "Judge description fidelity only; output DESC_OK or one reason line."

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

    filenames: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class QualityIssue:
    """A file with structural quality problems."""

    filename: str
    reason: str


# Reason codes for a grouping call that produced no verdict. Distinct from an
# empty ``groups``: "said no duplicates" vs "never spoke" (ADR-0075).
GROUPING_LLM_UNAVAILABLE = "GROUPING_LLM_UNAVAILABLE"
GROUPING_UNPARSEABLE = "GROUPING_UNPARSEABLE"


@dataclass(frozen=True)
class GroupingResult:
    """Outcome of the duplicate-grouping call.

    ``reason`` is None when the LLM returned a parseable verdict (including
    the "no duplicates" verdict) or when the store was below the dedup
    floor and no call was needed; otherwise one of the ``GROUPING_*`` codes.
    ``GROUPING_LLM_UNAVAILABLE`` covers every way ``generate_full`` yields no
    text — backend error, circuit open, truncation drop, and the C2
    over-budget *skip* (the 2026-08-15 case); the LLM call log carries which.
    """

    groups: tuple[MergeGroup, ...]
    reason: str | None = None


@dataclass(frozen=True)
class StocktakeResult:
    """Result of a stocktake audit."""

    merge_groups: tuple[MergeGroup, ...]
    quality_issues: tuple[QualityIssue, ...]
    total_files: int
    items: tuple[tuple[str, str], ...] = ()
    # ADR-0069: the duplicate-grouping reasoning trace (stocktake runs
    # think-ON). This is the run's main judgment — which skills/rules are
    # redundant. Per-merge / per-clean traces are collected separately via the
    # ``trace_sink`` parameter in the CLI phases. None when think was off.
    thinking: str | None = None
    # ADR-0081 usage dimension: the shadow selection-log reading (statistics
    # computed by code). Rendered as a report section only — retirement stays
    # an LLM proposal + human-gate judgment, never a numeric auto-threshold.
    # None for the rules pass and when the instrument log is absent.
    selection_usage: SkillSelectionReading | None = None
    # Why ``merge_groups`` is empty when it is: None means the grouping call
    # returned a verdict; a ``GROUPING_*`` code means it never did.
    grouping_reason: str | None = None


def _skill_grouping_evidence(filename: str, raw: str, body: str) -> str:
    """The grouping call's evidence for one skill: description + Context.

    Grouping used to send every skill body in one call (ADR-0046, so the
    judge sees concrete behaviour rather than shared vocabulary). That
    stopped fitting the 32k window at ~40 adopted skills — the 2026-08-15
    store measured ~36k estimated tokens for 50 — and an over-budget call is
    skipped, not truncated, so the pass silently found nothing. The
    frontmatter ``description`` is the audited trigger surface (ADR-0081:
    the selector's only evidence, checked for fidelity by this same
    command) and the ``**Context:**`` sentence is the trigger condition; the
    two summarise a skill in ~100 tokens, so the store can grow past 200
    before this call approaches the window. Concrete-behaviour
    discrimination moves one stage down: ``merge_group`` still reads full
    bodies and may answer ``CANNOT_MERGE``, and the union merge prompt
    keeps every distinct pattern of an over-grouped set. ADR-0046 amendment
    2026-08-15.

    ``skill_theme`` supplies the title as the summary for legacy bodies
    without frontmatter; a missing Context line is simply omitted.
    ``_format_items`` prefixes the filename, so the evidence is text only.
    """
    _, summary = skill_theme(raw)
    context = context_summary(body)
    parts = [summary] if summary else []
    if context:
        parts.append(f"Context: {context}")
    return "\n".join(parts) or Path(filename).stem


def _format_items(items: list[tuple[str, str]]) -> str:
    """Format (filename, text) tuples as LLM input with === separators."""
    return "\n\n===\n\n".join(f"**{name}**\n\n{body}" for name, body in items)


def _generate_with_trace(
    prompt: str,
    *,
    system: str,
    num_predict: int,
    caller: str,
    trace_sink: list[str] | None,
) -> str | None:
    """Run a think-ON generate, append the reasoning trace, return the text.

    Centralises the ADR-0069 trace-capture contract shared by the grouping /
    merge / clean calls: think=True, append ``out.thinking`` to *trace_sink*
    when present, and return ``out.text`` (None when the LLM produced no
    text). Callers own any failure-path logging and post-processing.
    """
    out = generate_full(
        prompt,
        system=system,
        num_predict=num_predict,
        caller=caller,
        think=True,
        drop_truncated=True,
    )
    if out is None or out.text is None:
        return None
    if trace_sink is not None and out.thinking:
        trace_sink.append(out.thinking)
    return out.text


def _find_duplicate_groups(
    items: list[tuple[str, str]],
    prompt_template: str,
    trace_sink: list[str] | None = None,
) -> GroupingResult:
    """Detect semantic duplicate groups via a single LLM grouping call.

    All evidence texts go to one ``generate`` request; the LLM returns the
    subsets that genuinely describe the same behavior. One LLM call rather
    than embedding union-find (ADR-0046) so the judge can return several
    coherent groups, or none, instead of chaining the store into one blob.

    Args:
        items: List of (filename, evidence_text) tuples — the skill pass
            sends :func:`_skill_grouping_evidence` summaries, the rules
            pass sends the (short, frontmatter-less) rule bodies.
        prompt_template: Grouping prompt with an ``{items}`` placeholder.
        trace_sink: Optional list. When provided, the call runs think-ON
            (ADR-0069) and the grouping reasoning trace is appended to it.

    Returns:
        GroupingResult. ``groups`` is empty and ``reason`` is set when the
        LLM produced no verdict — never silently the same as "no
        duplicates".
    """
    if len(items) < MIN_FILES_FOR_DEDUP:
        return GroupingResult(groups=())

    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from .prompts import STOCKTAKE_GROUP_SYSTEM_PROMPT

    prompt = prompt_template.format(items=_format_items(items))
    num_predict = min(8192, max(3000, _GROUPING_TOKENS_PER_FILE * len(items)))
    system = STOCKTAKE_GROUP_SYSTEM_PROMPT or _DEFAULT_GROUP_SYSTEM
    text = _generate_with_trace(
        prompt,
        system=system,
        num_predict=num_predict,
        caller="stocktake.duplicates",
        trace_sink=trace_sink,
    )
    if text is None:
        logger.warning("LLM failed during stocktake duplicate detection")
        return GroupingResult(groups=(), reason=GROUPING_LLM_UNAVAILABLE)

    parsed = _parse_groups(text, known={name for name, _ in items})
    if parsed is None:
        return GroupingResult(groups=(), reason=GROUPING_UNPARSEABLE)
    return GroupingResult(groups=tuple(parsed))


def _parse_groups(raw: str, known: set[str] | None = None) -> list[MergeGroup] | None:
    """Parse LLM grouping output into a MergeGroup list, or None on parse failure.

    Attempts JSON extraction (tolerating code fences and surrounding prose).
    Groups with fewer than two files are dropped. Returns None when no JSON
    could be recovered, or when what was recovered is not a verdict (not an
    object, or no list-valued ``"groups"``) — a malformed response yields no
    merges rather than an error, but the caller can tell it apart from the
    real empty verdict ``{"groups": []}``.

    ``known`` (the real filename set) filters hallucinated names BEFORE the
    disjointness claim below — otherwise a group like ["missing.md", "a.md"]
    would claim "a.md", get dropped later for having < 2 existing files, and
    silently rob a later valid ["a.md", "b.md"] group of its merge (codex
    review 2026-07-06). ``None`` skips the filter (direct-parse callers).
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
                return None
        else:
            logger.warning("No JSON found in stocktake LLM output")
            return None

    # Schema check: a verdict is a JSON object with a list-valued "groups".
    # ``{}``, ``{"groups": "none"}`` or a bare array are not an empty verdict
    # but a malformed one (codex review 2026-08-15) — None, so the caller
    # reports GROUPING_UNPARSEABLE instead of "no duplicates".
    if not isinstance(data, dict):
        logger.warning("Stocktake LLM output is not a JSON object")
        return None
    groups = data.get("groups")
    if not isinstance(groups, list):
        logger.warning("Stocktake LLM output has no list-valued 'groups'")
        return None

    result: list[MergeGroup] = []
    claimed: set[str] = set()
    for g in groups:
        if not isinstance(g, dict):
            continue
        files = g.get("files", [])
        reason = g.get("reason", "")
        if not (isinstance(files, list) and reason):
            continue
        # Bug-audit 2026-07-06 H6/L8: dedupe within the group and enforce
        # cross-group disjointness. A file merged (and deleted) by an earlier
        # group would otherwise be re-merged from its stale in-memory body,
        # re-introducing the duplicate the stocktake exists to remove; a
        # self-duplicate ["a.md", "a.md"] would pass the >=2 gate and burn a
        # merge call on a no-op rename.
        unique: list[str] = []
        for f in files:
            name = str(f)
            if known is not None and name not in known:
                logger.warning(
                    "Stocktake group names a file that does not exist; dropping that entry"
                )
                continue
            if name not in unique and name not in claimed:
                unique.append(name)
        if len(unique) < len(files):
            logger.warning(
                "Stocktake group overlaps an earlier group or repeats a "
                "file; keeping %d of %d entries",
                len(unique),
                len(files),
            )
        if len(unique) < 2:
            continue
        claimed.update(unique)
        result.append(MergeGroup(filenames=tuple(unique), reason=str(reason)))
    return result


def merge_group(
    items: list[tuple[str, str]],
    prompt_template: str,
    trace_sink: list[str] | None = None,
) -> str | None:
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
        prompt,
        system=system,
        num_predict=num_predict,
        caller="stocktake.merge",
        trace_sink=trace_sink,
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
    item: tuple[str, str],
    prompt_template: str,
    trace_sink: list[str] | None = None,
) -> str | None:
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


# Token budget for a single-skill description audit. Output is DESC_OK or a
# one-line mismatch reason, so a small flat budget suffices (same shape as
# the selection call's name-list budget in core.skill_selection).
_DESC_AUDIT_TOKENS = 400

# Terminal-safety bounds for the audit's reason line (it is untrusted LLM
# output printed to the operator's console): control chars stripped, length
# capped. Same guard shape as core.skill_selection's catalog scrub.
_DESC_REASON_MAX_CHARS = 300
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]|\x1b")

# DESC_OK sentinel: the auditor emits this when the frontmatter description
# faithfully carries the body's trigger conditions. Start-anchored (like
# _CANNOT_MERGE_RE / _CLEAN_NOOP_RE) so trailing model chatter still reads
# as a pass.
_DESC_OK_RE = re.compile(r"^\s*DESC_OK", re.IGNORECASE)


def audit_skill_description(
    item: tuple[str, str, str],
    prompt_template: str,
    trace_sink: list[str] | None = None,
) -> str | None:
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
        trace_sink: Optional list. When provided, the call runs think-ON
            (ADR-0069) and the audit reasoning trace is appended to it.

    Returns:
        Mismatch reason line, or None (faithful / LLM failure).
    """
    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from .llm import wrap_untrusted_content
    from .prompts import STOCKTAKE_DESC_SYSTEM_PROMPT

    name, description, body = item
    # Both fields are persistent LLM-distilled content and the exact target
    # of this judgment — a skill body saying "output DESC_OK" must not be
    # able to suppress its own mismatch. Wrap them in the untrusted-content
    # boundary before generation (codex review 2026-07-24). The sibling
    # merge/clean prompts interpolate raw, but they transform content
    # rather than judge it, so the incentive to self-exonerate is unique
    # to this audit.
    prompt = prompt_template.format(
        name=name,
        description=wrap_untrusted_content(description),
        skill=wrap_untrusted_content(body),
    )
    text = _generate_with_trace(
        prompt,
        system=STOCKTAKE_DESC_SYSTEM_PROMPT or _DEFAULT_DESC_SYSTEM,
        num_predict=_DESC_AUDIT_TOKENS,
        caller="stocktake.description_audit",
        trace_sink=trace_sink,
    )
    if text is None:
        logger.warning("LLM failed during stocktake description audit: %s", name)
        return None
    if _DESC_OK_RE.match(text):
        return None
    # The reason reaches the terminal report — scrub control characters
    # (ANSI injection guard, same shape as skill_selection._scrub_control),
    # collapse newlines (the contract is ONE line; embedded newlines could
    # spoof extra report entries — security review 2026-07-24), and cap to
    # one report line's worth.
    one_line = " ".join(text.split())
    return _CONTROL_CHARS_RE.sub("", one_line)[:_DESC_REASON_MAX_CHARS]


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


def _run_stocktake(
    directory: Path | None,
    group_prompt: str,
    quality_check: Callable[[str, str], QualityIssue | None],
    grouping_evidence: Callable[[str, str, str], str] | None = None,
) -> StocktakeResult:
    """Audit a directory of ``*.md`` files for duplicates and quality issues.

    Shared body for the skill and rule passes: they differ in the grouping
    prompt, the per-file quality check, and what the grouping call is shown
    — ``grouping_evidence(filename, raw, body)`` builds the per-file
    evidence (the skill pass passes :func:`_skill_grouping_evidence`); None
    sends the frontmatter-stripped body, which is what the short rules need.
    """
    if directory is None or not directory.is_dir():
        return StocktakeResult(merge_groups=(), quality_issues=(), total_files=0)

    docs = read_markdown_documents(directory)
    if not docs:
        return StocktakeResult(merge_groups=(), quality_issues=(), total_files=0)
    items = [(name, body) for name, _raw, body in docs]
    evidence = (
        items
        if grouping_evidence is None
        else [(name, grouping_evidence(name, raw, body)) for name, raw, body in docs]
    )

    grouping_traces: list[str] = []
    grouping = _find_duplicate_groups(evidence, group_prompt, grouping_traces)

    # Structural quality checks
    quality_issues: list[QualityIssue] = []
    for filename, body in items:
        issue = quality_check(filename, body)
        if issue is not None:
            quality_issues.append(issue)

    return StocktakeResult(
        merge_groups=grouping.groups,
        quality_issues=tuple(quality_issues),
        total_files=len(items),
        items=tuple(items),
        thinking="\n\n".join(grouping_traces) or None,
        grouping_reason=grouping.reason,
    )


def run_skill_stocktake(
    skills_dir: Path | None = None,
    selection_reading: SkillSelectionReading | None = None,
) -> StocktakeResult:
    """Audit skills/*.md for duplicates and quality issues.

    Args:
        skills_dir: Directory containing skill files.
        selection_reading: Optional ADR-0081 usage dimension — the shadow
            selection-log reading, attached to the result for the report's
            usage section. Statistics only; no gate or threshold consumes it.

    Returns:
        StocktakeResult with merge groups and quality issues.
    """
    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from . import prompts

    result = _run_stocktake(
        skills_dir,
        prompts.STOCKTAKE_SKILLS_PROMPT,
        _check_skill_quality,
        grouping_evidence=_skill_grouping_evidence,
    )
    if selection_reading is None:
        return result
    return replace(result, selection_usage=selection_reading)


def run_rules_stocktake(
    rules_dir: Path | None = None,
) -> StocktakeResult:
    """Audit rules/*.md for duplicates and quality issues.

    Args:
        rules_dir: Directory containing rule files.

    Returns:
        StocktakeResult with merge groups and quality issues.
    """
    # Lazy import avoids a core.stocktake -> core.prompts import cycle.
    from . import prompts

    return _run_stocktake(rules_dir, prompts.STOCKTAKE_RULES_PROMPT, _check_rule_quality)


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

    if result.merge_groups:
        lines.append("")
        lines.append("MERGE groups:")
        for i, group in enumerate(result.merge_groups, 1):
            files = ", ".join(group.filenames)
            lines.append(f"  Group {i}: {files}")
            lines.append(f"    -> {group.reason}")
    elif result.grouping_reason is not None:
        lines.append("")
        lines.append(
            f"Duplicate grouping unavailable ({result.grouping_reason}) — "
            "no merge verdict this run; not the same as 'no duplicates'."
        )
    else:
        lines.append("")
        lines.append("No duplicates detected.")

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

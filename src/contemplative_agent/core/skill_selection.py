"""Skill-selection shadow instrument (ADR-0076).

Pass-1 LLM applicability selection over the learned-skill catalog, run in
shadow mode: the selection is recorded to an append-only audit log and has
zero effect on what the system prompt injects. The log feeds the
``report --skill-selection`` reading (ADR-0071 style) that will inform a
later enforcement decision.

Design constraints inherited from ADR-0036: applicability is a semantic
judgment, so it belongs to the LLM (mechanism-vs-value-split) — no cosine
similarity, no typed-metadata predicates. The selection call sees only
skill names + descriptions plus the situation, under the identity-only
system prompt (audit H5: the learned corpus must not feed its own
vocabulary back into the judge).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ._io import append_jsonl_restricted, now_iso, strip_to_printable
from .insight import skill_theme
from .llm import (
    _estimate_tokens,
    circuit_shield,
    generate,
    get_identity_system_prompt,
    validate_identity_content,
)
from .text_utils import strip_frontmatter

logger = logging.getLogger(__name__)


def _load_selection_template() -> str:
    """Lazy template access — importing from ``.prompts`` at module level
    would force the full prompt registry to load for any importer of this
    module (same eager-load hazard the framing imports in ``llm.py`` avoid,
    codex review 2026-07-06 P2)."""
    from .prompts import SKILL_SELECTION_PROMPT

    return SKILL_SELECTION_PROMPT


# Audit-record payload bound. Half of insight-novelty's 131072: selection
# records are written per publish action (dozens per session) rather than
# once per weekly insight run, and the situation excerpt (p90 ≈ 4.7K chars
# post body) dominates the prompt, so a tighter bound keeps daily files
# proportionate while still preserving the full prompt for typical actions.
_MAX_SKILL_SELECTION_AUDIT_BYTES = 65536

# Selection output is a handful of skill names (worst case: every catalog
# name, ~19 lines × ~15 tokens). 400 leaves headroom without letting a
# runaway response occupy the window.
_SELECTION_NUM_PREDICT = 400

# Sentinel the prompt instructs the model to emit when no skill applies.
_NONE_SENTINEL = "none"

# Length bounds for catalog fields and hallucinated names (security review
# 2026-07-10). Names are kebab-case ASCII by insight convention →
# strip_to_printable; descriptions and hallucinated names may legitimately
# carry CJK → control characters only are removed (ANSI escapes included),
# CJK preserved.
_NAME_MAX_CHARS = 80
_DESCRIPTION_MAX_CHARS = 300

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]|\x1b")


def _scrub_control(value: str, max_len: int) -> str:
    """Drop control characters (terminal/ANSI injection guard), cap length.

    CJK-preserving counterpart to ``strip_to_printable`` for fields where
    non-ASCII content is legitimate (descriptions, hallucinated names)."""
    return _CONTROL_CHARS_RE.sub("", value)[:max_len]


_skills_dir: Path | None = None
_audit_dir: Path | None = None


def configure_skill_selection(
    skills_dir: Path | None = None,
    audit_dir: Path | None = None,
) -> None:
    """Configure the shadow instrument (same module-global pattern as
    ``configure_llm``).

    ``audit_dir`` unset means shadow observation is disabled: the hook in
    the adapter becomes a no-op, so tests and one-shot CLI paths that never
    call this function stay clean — the kill switch is built into the
    configuration itself.
    """
    global _skills_dir, _audit_dir
    _skills_dir = skills_dir
    _audit_dir = audit_dir


def reset_skill_selection() -> None:
    """Reset module state (test isolation)."""
    global _skills_dir, _audit_dir
    _skills_dir = None
    _audit_dir = None


@dataclass(frozen=True)
class SkillCatalogEntry:
    """One skill as seen by the pass-1 selector."""

    name: str
    description: str
    body_tokens: int


def load_skill_catalog(skills_dir: Path | None) -> tuple[SkillCatalogEntry, ...]:
    """Read ``skills_dir/*.md`` into catalog entries.

    Same traversal contract as insight's ``_load_known_themes``: sorted
    glob, dotfiles skipped, unreadable files logged and skipped.
    ``body_tokens`` is the audit-C2 estimate of the full file text — the
    cost the skill contributes to the system prompt today, kept per entry
    so audit records can bake in the would-be reduction at record time.
    """
    if skills_dir is None or not skills_dir.is_dir():
        return ()
    entries: list[SkillCatalogEntry] = []
    for path in sorted(skills_dir.glob("*.md")):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("skill selection: unreadable skill file %s", path.name)
            continue
        name, description = skill_theme(text, fallback_name=path.stem)
        # Skill files are untrusted (LLM-distilled); the name reaches the
        # audit log and the terminal report, the description reaches the
        # selection prompt — scrub both at the single load seam.
        entries.append(
            SkillCatalogEntry(
                name=strip_to_printable(name, _NAME_MAX_CHARS),
                description=_scrub_control(description, _DESCRIPTION_MAX_CHARS),
                body_tokens=_estimate_tokens(text),
            )
        )
    return tuple(entries)


@dataclass(frozen=True)
class SkillSelectionResult:
    """Outcome of one pass-1 selection call.

    ``verdict`` reason codes (ADR-0075 — abstains carry a reason):
    ``judged`` (LLM answered and the answer parsed, even if every picked
    name was hallucinated — "parse failed" and "every pick was wrong" are
    different events), ``fail_open_llm`` (no response), ``fail_open_parse``
    (blank/unusable response).
    """

    verdict: str
    selected: tuple[str, ...]
    rejected_names: tuple[str, ...]
    prompt: str
    raw_output: str | None


def _render_catalog(catalog: tuple[SkillCatalogEntry, ...]) -> str:
    return "\n".join(f"{e.name} — {e.description}" for e in catalog)


def select_applicable_skills(
    situation: str,
    catalog: tuple[SkillCatalogEntry, ...],
) -> SkillSelectionResult:
    """Run one selection call and validate the answer against the catalog.

    ``situation`` must already be wrapped by the caller
    (``wrap_untrusted_content``) — this function does not re-wrap.
    Output names are matched case-insensitively against catalog names and
    reported in canonical catalog casing; names with no catalog match are
    recorded as ``rejected_names`` (hallucinations), never injected
    downstream. No numeric cap is applied to the selection size.
    """
    prompt = _load_selection_template().format(
        skill_catalog=_render_catalog(catalog), situation=situation
    )
    # circuit_shield: this is an observability-only call — its failures
    # must not open the breaker that guards the publish generation it
    # precedes (codex review 2026-07-10 P2).
    with circuit_shield():
        raw = generate(
            prompt,
            system=get_identity_system_prompt(),
            num_predict=_SELECTION_NUM_PREDICT,
            caller="core.skill_selection",
            think=False,
        )
    if raw is None:
        return SkillSelectionResult(
            verdict="fail_open_llm",
            selected=(),
            rejected_names=(),
            prompt=prompt,
            raw_output=None,
        )
    lines = [line.strip() for line in raw.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return SkillSelectionResult(
            verdict="fail_open_parse",
            selected=(),
            rejected_names=(),
            prompt=prompt,
            raw_output=raw,
        )
    by_lower = {e.name.lower(): e.name for e in catalog}
    selected: set[str] = set()
    rejected: list[str] = []
    for line in lines:
        if line.lower() == _NONE_SENTINEL:
            continue
        canonical = by_lower.get(line.lower())
        if canonical is not None:
            selected.add(canonical)
        else:
            # Hallucinated names are raw LLM output shaped by untrusted
            # input; scrub before they enter the plaintext audit field
            # (the unscrubbed original survives in output_b64 for replay).
            rejected.append(_scrub_control(line, _NAME_MAX_CHARS))
    return SkillSelectionResult(
        verdict="judged",
        selected=tuple(sorted(selected)),
        rejected_names=tuple(rejected),
        prompt=prompt,
        raw_output=raw,
    )


def _b64_fields(name: str, text: str | None) -> dict[str, Any]:
    """Untrusted-text storage bundle (same shape as insight-novelty audit):
    sha256 over the full text, base64 of the kept prefix, explicit
    truncation flag."""
    if text is None:
        return {f"{name}_b64": None}
    raw = text.encode("utf-8", "replace")
    kept = raw[:_MAX_SKILL_SELECTION_AUDIT_BYTES]
    return {
        f"{name}_sha256": hashlib.sha256(raw).hexdigest(),
        f"{name}_encoding": "base64:utf-8",
        f"{name}_b64": base64.b64encode(kept).decode("ascii"),
        f"{name}_bytes": len(raw),
        f"{name}_truncated": len(kept) < len(raw),
    }


def _append_selection_audit(record: dict[str, Any]) -> None:
    if _audit_dir is None:
        return
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    append_jsonl_restricted(_audit_dir / f"skill-selection-{date_str}.jsonl", record)


def enforcement_enabled() -> bool:
    """ADR-0081 rollout flag: ``MOLTBOOK_SKILL_SELECTION_ENFORCE=1`` opts in
    to two-pass injection. Read at call time so a launchd plist / shell can
    flip it without touching ``configure_skill_selection``."""
    import os

    return os.environ.get("MOLTBOOK_SKILL_SELECTION_ENFORCE") == "1"


def selected_skills_block(selected: tuple[str, ...]) -> str:
    """Concatenated bodies of the selected skills, for pass-2 injection.

    Same traversal, identity-matching (``skill_theme``), and body guards
    (frontmatter strip + forbidden-pattern validation) as the full-corpus
    loader in ``llm.prompting._load_md_files`` — the selector's catalog and
    this filter must agree on skill identity, so both derive the name via
    ``skill_theme``. A selected name with no matching file (adopt/stocktake
    raced the selection) is logged and skipped, never fatal. Empty
    selection returns "" (ADR-0081: a judged-empty selection injects no
    skill bodies).
    """
    if not selected or _skills_dir is None or not _skills_dir.is_dir():
        return ""
    wanted = {name.lower() for name in selected}
    found: set[str] = set()
    bodies: list[str] = []
    for path in sorted(_skills_dir.glob("*.md")):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("skill selection: unreadable skill file %s", path.name)
            continue
        name, _ = skill_theme(text, fallback_name=path.stem)
        key = strip_to_printable(name, _NAME_MAX_CHARS).lower()
        if key not in wanted:
            continue
        found.add(key)
        body = strip_frontmatter(text).strip()
        if body and validate_identity_content(body):
            bodies.append(body)
        elif body:
            logger.warning("skill selection: %s contains forbidden patterns, skipping", path.name)
    for missing in wanted - found:
        logger.warning("skill selection: selected skill %r has no file, skipping", missing)
    return "\n\n".join(bodies)


def shadow_observe_skill_selection(
    situation: str, *, generation_caller: str
) -> tuple[str, ...] | None:
    """Selection entry point: select, record, and (ADR-0081) optionally enforce.

    Returns ``None`` for full injection — shadow mode (flag off), any
    fail-open verdict, the kill switch (``audit_dir`` unset), or an internal
    failure. Returns the selected skill names (possibly an empty tuple =
    inject nothing) ONLY when ``MOLTBOOK_SKILL_SELECTION_ENFORCE=1`` and the
    verdict is ``judged``. The whole body degrades to a WARNING on any
    failure (degrade-never-abort): a broken instrument must never block the
    publish action it observes. Every audit record carries ``enforced``
    (whether this observation fed back into injection).
    """
    if _audit_dir is None:
        return None
    try:
        catalog = load_skill_catalog(_skills_dir)
        base: dict[str, Any] = {
            "ts": now_iso("seconds"),
            "generation_caller": generation_caller,
            "catalog_count": len(catalog),
            "catalog_names": sorted(e.name for e in catalog),
        }
        if not catalog:
            _append_selection_audit(
                {
                    **base,
                    "verdict": "empty_catalog",
                    "enforced": False,
                    "selected": [],
                    "selected_count": 0,
                    "rejected_names": [],
                    "full_skill_tokens": 0,
                    "would_be_skill_tokens": 0,
                    **_b64_fields("prompt", None),
                    **_b64_fields("output", None),
                }
            )
            return None
        if not _load_selection_template():
            _append_selection_audit(
                {
                    **base,
                    "verdict": "no_template",
                    "enforced": False,
                    "selected": [],
                    "selected_count": 0,
                    "rejected_names": [],
                    "full_skill_tokens": sum(e.body_tokens for e in catalog),
                    "would_be_skill_tokens": 0,
                    **_b64_fields("prompt", None),
                    **_b64_fields("output", None),
                }
            )
            return None
        result = select_applicable_skills(situation, catalog)
        # ADR-0081: only a judged verdict under the rollout flag feeds back
        # into injection; every fail-open path stays full injection.
        enforced = enforcement_enabled() and result.verdict == "judged"
        by_name = {e.name: e.body_tokens for e in catalog}
        _append_selection_audit(
            {
                **base,
                "verdict": result.verdict,
                "enforced": enforced,
                "selected": list(result.selected),
                "selected_count": len(result.selected),
                "rejected_names": list(result.rejected_names),
                # Baked in at record time: the catalog changes under
                # adopt/stocktake, so a report-time recomputation could not
                # replay what the reduction would have been for this action.
                "full_skill_tokens": sum(e.body_tokens for e in catalog),
                "would_be_skill_tokens": sum(by_name[name] for name in result.selected),
                **_b64_fields("prompt", result.prompt),
                **_b64_fields("output", result.raw_output),
            }
        )
        return result.selected if enforced else None
    except Exception as exc:
        logger.warning(
            "skill selection shadow observation failed (generation unaffected): %s",
            exc,
        )
        return None


@dataclass(frozen=True)
class SkillSelectionReading:
    """Read-only aggregate over the shadow log (ADR-0071 instrument).

    Feeds no gate, ranking, or retrieval — it informs the operator's
    enforcement decision and points ``skill-stocktake`` at never-selected
    skills. Percentiles are computed over ``judged`` records only.
    """

    days: int
    records: int
    verdicts: tuple[tuple[str, int], ...]
    per_skill: tuple[tuple[str, int], ...]
    never_selected: tuple[str, ...]
    # ADR-0081: judged records whose answer included at least one
    # hallucinated (non-catalog) name — one of ADR-0076's four
    # enforcement criteria, surfaced in the report as a rate over judged.
    hallucination_records: int
    selected_count_p50: float
    selected_count_p90: float
    token_reduction_p50: float
    token_reduction_p90: float


def read_skill_selection_log(
    log_dir: Path,
    *,
    days: int,
    skills_dir: Path | None,
) -> SkillSelectionReading:
    """Aggregate ``skill-selection-*.jsonl`` files within the window.

    Files are selected by the date embedded in the filename (same daily
    rotation as LLM telemetry); broken lines are skipped, never fatal.
    ``never_selected`` is computed against the *current* catalog, so a
    skill adopted yesterday with no selections yet will appear — read it
    alongside ``records`` before drawing conclusions.
    """
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    verdict_counts: dict[str, int] = {}
    skill_counts: dict[str, int] = {}
    selected_counts: list[int] = []
    reductions: list[int] = []
    records = 0
    hallucination_records = 0
    if log_dir.is_dir():
        for path in sorted(log_dir.glob("skill-selection-*.jsonl")):
            date_part = path.stem.removeprefix("skill-selection-")
            try:
                file_date = datetime.strptime(date_part, "%Y-%m-%d").date()
            except ValueError:
                continue
            if file_date < cutoff:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                logger.warning("skill selection reading: unreadable %s", path.name)
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records += 1
                verdict = str(rec.get("verdict", "unknown"))
                verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
                if verdict != "judged":
                    continue
                selected = rec.get("selected") or []
                for name in selected:
                    skill_counts[name] = skill_counts.get(name, 0) + 1
                selected_counts.append(len(selected))
                if rec.get("rejected_names"):
                    hallucination_records += 1
                full = rec.get("full_skill_tokens")
                would_be = rec.get("would_be_skill_tokens")
                if isinstance(full, int) and isinstance(would_be, int):
                    reductions.append(full - would_be)

    catalog_names = [e.name for e in load_skill_catalog(skills_dir)]
    never_selected = tuple(name for name in catalog_names if name not in skill_counts)

    def _pct(values: list[int], q: float) -> float:
        if not values:
            return 0.0
        return float(np.percentile(np.asarray(values, dtype=float), q))

    return SkillSelectionReading(
        days=days,
        records=records,
        verdicts=tuple(sorted(verdict_counts.items())),
        per_skill=tuple(sorted(skill_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        never_selected=never_selected,
        hallucination_records=hallucination_records,
        selected_count_p50=_pct(selected_counts, 50),
        selected_count_p90=_pct(selected_counts, 90),
        token_reduction_p50=_pct(reductions, 50),
        token_reduction_p90=_pct(reductions, 90),
    )


def format_skill_selection_report(reading: SkillSelectionReading) -> str:
    """Render the reading for the ``report --skill-selection`` flag."""
    lines = [
        "## Skill-selection shadow reading (ADR-0076)",
        "",
        f"Window: last {reading.days} days — {reading.records} records",
    ]
    if reading.verdicts:
        verdict_text = ", ".join(f"{v}: {n}" for v, n in reading.verdicts)
        lines.append(f"Verdicts: {verdict_text}")
    judged = dict(reading.verdicts).get("judged", 0)
    if judged:
        rate = reading.hallucination_records / judged
        lines.append(
            f"Hallucination: {reading.hallucination_records}/{judged} judged "
            f"({rate:.1%} with rejected names)"
        )
    lines.append(
        "Selected per action: p50 "
        f"{reading.selected_count_p50:.1f} / p90 {reading.selected_count_p90:.1f}"
    )
    lines.append(
        "Would-be token reduction: p50 "
        f"≈{reading.token_reduction_p50:,.0f} tok / p90 "
        f"≈{reading.token_reduction_p90:,.0f} tok (audit C2 scale)"
    )
    if reading.per_skill:
        lines.append("")
        lines.append("Selection frequency:")
        for name, count in reading.per_skill:
            lines.append(f"- {name}: {count}")
    if reading.never_selected:
        lines.append("")
        lines.append("Never selected in window (stocktake candidates, check records count first):")
        for name in reading.never_selected:
            lines.append(f"- {name}")
    return "\n".join(lines)

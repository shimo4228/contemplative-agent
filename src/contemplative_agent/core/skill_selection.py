"""Skill-selection instrument and pass-1 selector (ADR-0076, ADR-0081).

Pass-1 LLM applicability selection over the learned-skill catalog. Every
selection is recorded to an append-only audit log, and a judged selection
feeds back into injection — see ``configured_injection_regime()``, the
single place that names what may reach ``<learned_skills>``. It shipped
shadow-only (ADR-0076, recorded but inert), gained flag-gated two-pass
enforcement in ``0723726`` (ADR-0081), and the flag retired on 2026-08-08
once the second reading closed the rollout: 15 consecutive days at
1,316/1,316 enforced, fail-open zero for 26 days, hallucinated names
rejected without propagation. Prose that still describes this module as
shadow-only, or as flag-gated, is stale — a 2026-08-08 eval defect traced
back to exactly that kind of staleness (ADR-0089 amendment).

Design constraints inherited from ADR-0036: applicability is a semantic
judgment, so it belongs to the LLM (mechanism-vs-value-split) — no cosine
similarity, no typed-metadata predicates. The selection call sees only
skill names + descriptions plus the situation, under the identity-only
system prompt (audit H5: the learned corpus must not feed its own
vocabulary back into the judge).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, TypeAlias

import numpy as np

from ._io import append_jsonl_restricted, b64_audit_fields, now_iso, strip_to_printable
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
    """Configure the selector (same module-global pattern as
    ``configure_llm``).

    ``audit_dir`` unset disables it: the hook in the adapter becomes a
    no-op, so tests and one-shot CLI paths that never call this function
    stay clean — the kill switch is built into the configuration itself.
    Since the ADR-0081 flag retired this is the only switch left, and it is
    a code-level one: no environment variable or CLI flag reaches it.
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
    """Untrusted-text storage bundle at this log's byte cap.

    Thin binding of the shared encoder to ``_MAX_SKILL_SELECTION_AUDIT_BYTES``;
    the replay format itself lives in ``_io.b64_audit_fields`` so the three
    audit writers cannot drift apart.
    """
    return b64_audit_fields(name, text, max_bytes=_MAX_SKILL_SELECTION_AUDIT_BYTES)


def _append_selection_audit(record: dict[str, Any]) -> None:
    if _audit_dir is None:
        return
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    append_jsonl_restricted(_audit_dir / f"skill-selection-{date_str}.jsonl", record)


# The states of "what reaches <learned_skills>". Named because the
# distinction that matters downstream is *what was injected*, not whether
# the selector ran: shadow observation records a selection and still injects
# the whole corpus, so it is a full-corpus regime with a log, not a third
# injection behaviour. Consumed by the eval manifest (ADR-0089 amendment) —
# a run that cannot say which of these it measured is not comparable to one
# that can.
#
# ``full_corpus_shadow_observed`` is no longer reachable: it named the
# ADR-0081 rollout flag being off, and the flag retired on 2026-08-08 when
# the second reading closed the rollout. The literal stays because eval
# manifests recorded before that date carry it, and a comparison layer that
# cannot name a historical run's regime cannot tell "incomparable" from
# "unrecognised".
InjectionRegime: TypeAlias = Literal[
    "full_corpus", "full_corpus_shadow_observed", "two_pass_selected"
]

REGIME_FULL_CORPUS: InjectionRegime = "full_corpus"
REGIME_FULL_CORPUS_SHADOW: InjectionRegime = "full_corpus_shadow_observed"
REGIME_TWO_PASS_SELECTED: InjectionRegime = "two_pass_selected"


def configured_injection_regime() -> InjectionRegime:
    """The regime this module's *configuration* permits — not the regime any
    particular call ends up taking.

    Derived from the one condition ``shadow_observe_skill_selection``
    short-circuits on before it does any work: the kill switch (``audit_dir``
    unset). Until 2026-08-08 an environment flag was read here too; retiring
    it means no out-of-tree artefact can move the regime, which is why the
    eval's plist-versus-pin comparison retired with it.

    **This is a ceiling, not an outcome.** ``two_pass_selected`` here means
    "two-pass injection is reachable", and four further conditions can still
    send an individual call back to full-corpus injection: an empty catalog,
    an unloadable selection template, and the two fail-open verdicts
    (``fail_open_llm`` / ``fail_open_parse``), none of which are visible to
    a configuration reading. Callers that need the regime a call *actually
    took* must read the per-call ``enforced`` field in the selection audit
    log; ``observed_injection_outcomes()`` aggregates that for a run. Naming
    this function for the outcome would repeat, one layer down, the defect
    ADR-0089's amendment exists to fix.
    """
    if _audit_dir is None:
        return REGIME_FULL_CORPUS
    return REGIME_TWO_PASS_SELECTED


def selection_preconditions_unmet() -> str | None:
    """Why two-pass injection could not be reached on this configuration,
    or ``None`` when the deterministic preconditions hold.

    Covers the two short-circuits that are knowable *before* any LLM call —
    an empty catalog and an unloadable selection template. The two fail-open
    verdicts are per-call and inherently not preflightable; they are visible
    only after the fact, in the audit log. Returned as a reason string
    rather than a bool so a caller can put the cause in its own diagnostic
    (silent-fallback prohibition, ADR-0075).
    """
    if not load_skill_catalog(_skills_dir):
        return f"empty skill catalog at {_skills_dir}"
    try:
        if not _load_selection_template().strip():
            return "selection prompt template is empty"
    except Exception as exc:  # template registry failure is a precondition failure
        return f"selection prompt template unloadable: {type(exc).__name__}: {exc}"
    return None


def observed_injection_outcomes(audit_dir: Path) -> dict[str, Any]:
    """Counts of what injection each recorded observation *actually* took.

    The configured regime is an intent; this is the outcome. Every record
    carries ``enforced`` (whether the selection fed back into injection), so
    a run can report how many of its generations really ran two-pass and how
    many fell back to the full corpus — the difference
    ``configured_injection_regime()`` structurally cannot see.

    Counts and verdict names only. The records embed the selection situation
    (untrusted post bodies, base64) and must never be rendered by an
    aggregate, the same boundary ``format_skill_selection_report`` observes
    (ADR-0083). An unreadable or absent directory yields zeroes with a
    reason rather than an exception — this is an instrument, and a broken
    instrument must not break its subject.
    """
    out: dict[str, Any] = {"records": 0, "enforced": 0, "fell_back": 0, "verdicts": {}}
    if not audit_dir.is_dir():
        out["unavailable"] = f"no selection audit directory at {audit_dir}"
        return out
    for path in sorted(audit_dir.glob("skill-selection-*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            out["unavailable"] = f"unreadable {path.name}: {exc}"
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                out["verdicts"]["UNPARSEABLE_RECORD"] = (
                    out["verdicts"].get("UNPARSEABLE_RECORD", 0) + 1
                )
                continue
            out["records"] += 1
            verdict = str(record.get("verdict", "MISSING_VERDICT"))
            out["verdicts"][verdict] = out["verdicts"].get(verdict, 0) + 1
            if record.get("enforced"):
                out["enforced"] += 1
            else:
                out["fell_back"] += 1
    return out


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
    """Selection entry point: select, record, and (ADR-0081) enforce.

    Returns the selected skill names (possibly an empty tuple = inject
    nothing) whenever the verdict is ``judged``. Returns ``None`` for full
    injection — either fail-open verdict, an empty catalog, an unloadable
    template, the kill switch (``audit_dir`` unset), or an internal failure.
    Unconditional since 2026-08-08; the ``MOLTBOOK_SKILL_SELECTION_ENFORCE``
    flag that used to co-gate the judged branch retired with the rollout.

    The whole body degrades to a WARNING on any failure
    (degrade-never-abort): a broken instrument must never block the publish
    action it observes. Every audit record carries ``enforced`` (whether
    this observation fed back into injection).
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
        # ADR-0081: only a judged verdict feeds back into injection; every
        # fail-open path stays full injection. The rollout flag that used to
        # co-gate this retired on 2026-08-08.
        enforced = result.verdict == "judged"
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
class SkillSelectionDay:
    """One UTC day of the window, so a reader can see regime changes instead
    of their average.

    Window-wide aggregates hid a rollout and a corpus tripling from two
    consecutive readings: the 2026-07-24 one reported 83.6% fail-open that
    was a single incident, and the 2026-08-08 one reported 51.5% enforced
    across a window whose second half was 100% and a 2.2% hallucination rate
    spanning a catalog that went 19 → 45. Both had to be re-derived by hand.
    A window only gets longer as the corpus grows, so the day is the unit
    the log is actually informative at.
    """

    date: str
    records: int
    judged: int
    enforced: int
    judged_empty: int
    hallucination_records: int
    distinct_selected: int

    @property
    def fell_back(self) -> int:
        """Records that did not reach a judgment, so injection stayed
        full-corpus: every ``fail_open_*`` plus ``empty_catalog`` and
        ``no_template``. Derived rather than counted so ``records`` has no
        silent residual — a column that named only the fail-open family
        would read as calm on a day the whole catalog went missing. Which
        fallback verdicts fired is in the window's ``verdicts`` tally."""
        return self.records - self.judged


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
    # The denominator every rate below is taken over. Held explicitly rather
    # than re-derived from ``verdicts`` at each call site, so a numerator and
    # its denominator cannot drift apart.
    judged_records: int
    # Records whose selection actually fed back into injection. The verdict
    # counts say the selector succeeded; only this says the success was
    # used. Reading the rollout off the verdicts alone is what produced the
    # "38% enforced" misreading that outlived a whole ledger entry.
    enforced_records: int
    # Judged records that selected nothing. A judgment, not a failure
    # (ADR-0081 Decision 3) — but it injects no skill bodies at all, and
    # ADR-0081 closed its rollout partly on this being zero, so it needs to
    # be visible rather than inferable from a selected_count buried in the
    # log.
    judged_empty_records: int
    per_day: tuple[SkillSelectionDay, ...]
    # ``never_selected`` names paired with how many *judged* records carried
    # them in the catalog. Without it the report can only tell the operator
    # to "check the records count first" while holding the only copy of it —
    # and a skill adopted yesterday is indistinguishable from one that has
    # been offered a thousand times and refused. Counted over judged records
    # only: a name offered to a selector that never answered was not refused.
    #
    # Matched on exact name, so a skill renamed mid-window reports the
    # exposure of its new name — near zero, i.e. it reads as newly adopted.
    # The pending frontmatter-name backfill will do exactly that; read the
    # first window after it with that in mind.
    never_selected_exposure: tuple[tuple[str, int], ...]


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
    judged_records = 0
    hallucination_records = 0
    enforced_records = 0
    judged_empty_records = 0
    # Exposure is counted for every catalogued name, not just the ones that
    # end up never-selected: which names those are is only known after the
    # whole window has been read, and the current catalog is resolved later
    # still.
    exposure_counts: dict[str, int] = {}
    days_seen: list[SkillSelectionDay] = []
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
            # The day is taken from the filename rather than each record's
            # ``ts``: the writer derives both from the same UTC clock, and
            # the filename is the field the window is already cut on, so a
            # record with a damaged timestamp still lands on the right day.
            day_records = 0
            day_judged = 0
            day_enforced = 0
            day_judged_empty = 0
            day_hallucinations = 0
            day_selected: set[str] = set()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records += 1
                day_records += 1
                verdict = str(rec.get("verdict", "unknown"))
                verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
                if verdict != "judged":
                    continue
                # Everything below is judged-only, deliberately. Every rate
                # this instrument reports is a rate over judged records, so a
                # numerator counted on the other side of this line would be
                # measured against a population it is not drawn from — which
                # is exactly how "in catalog for 100 of 105 records" came to
                # describe a skill that had never once been judged.
                judged_records += 1
                day_judged += 1
                if rec.get("enforced"):
                    enforced_records += 1
                    day_enforced += 1
                names = rec.get("catalog_names")
                if isinstance(names, list):
                    for name in names:
                        if isinstance(name, str):
                            exposure_counts[name] = exposure_counts.get(name, 0) + 1
                selected = rec.get("selected") or []
                for name in selected:
                    skill_counts[name] = skill_counts.get(name, 0) + 1
                    day_selected.add(name)
                selected_counts.append(len(selected))
                if not selected:
                    judged_empty_records += 1
                    day_judged_empty += 1
                if rec.get("rejected_names"):
                    hallucination_records += 1
                    day_hallucinations += 1
                full = rec.get("full_skill_tokens")
                would_be = rec.get("would_be_skill_tokens")
                if isinstance(full, int) and isinstance(would_be, int):
                    reductions.append(full - would_be)
            if day_records:
                days_seen.append(
                    SkillSelectionDay(
                        date=date_part,
                        records=day_records,
                        judged=day_judged,
                        enforced=day_enforced,
                        judged_empty=day_judged_empty,
                        hallucination_records=day_hallucinations,
                        distinct_selected=len(day_selected),
                    )
                )

    catalog_names = [e.name for e in load_skill_catalog(skills_dir)]
    never_selected = tuple(name for name in catalog_names if name not in skill_counts)
    never_selected_exposure = tuple((name, exposure_counts.get(name, 0)) for name in never_selected)

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
        judged_records=judged_records,
        enforced_records=enforced_records,
        judged_empty_records=judged_empty_records,
        per_day=tuple(sorted(days_seen, key=lambda d: d.date)),
        never_selected_exposure=never_selected_exposure,
    )


def format_skill_selection_report(reading: SkillSelectionReading) -> str:
    """Render the reading for the ``report --skill-selection`` flag."""
    lines = [
        "## Skill-selection reading (ADR-0076 instrument, ADR-0081 enforcement)",
        "",
        f"Window: last {reading.days} days — {reading.records} records",
    ]
    if reading.verdicts:
        verdict_text = ", ".join(f"{v}: {n}" for v, n in reading.verdicts)
        lines.append(f"Verdicts: {verdict_text}")
    judged = reading.judged_records
    if judged:
        lines.append(
            f"Enforced: {reading.enforced_records}/{judged} judged "
            f"({reading.enforced_records / judged:.1%} fed back into injection)"
        )
        lines.append(
            f"Hallucination: {reading.hallucination_records}/{judged} judged "
            f"({reading.hallucination_records / judged:.1%} with rejected names)"
        )
        lines.append(
            f"Judged-empty: {reading.judged_empty_records}/{judged} judged "
            f"({reading.judged_empty_records / judged:.1%} injected no skill bodies)"
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
    if reading.per_day:
        lines.append("")
        lines.append("Per day (a window-wide average hides the day a regime changed):")
        lines.append(
            f"{'date':<12}{'records':>9}{'judged':>8}{'fell-back':>11}"
            f"{'enforced':>10}{'jd-empty':>10}{'halluc':>8}{'distinct':>10}"
        )
        for day in reading.per_day:
            lines.append(
                f"{day.date:<12}{day.records:>9}{day.judged:>8}{day.fell_back:>11}"
                f"{day.enforced:>10}{day.judged_empty:>10}"
                f"{day.hallucination_records:>8}{day.distinct_selected:>10}"
            )
        lines.append(
            "  records = judged + fell-back; all other columns count judged "
            "records only. Which fallback verdicts fired is in `Verdicts` above."
        )
    if reading.per_skill:
        lines.append("")
        lines.append("Selection frequency:")
        for name, count in reading.per_skill:
            lines.append(f"- {name}: {count}")
    if reading.never_selected_exposure:
        lines.append("")
        lines.append("Never selected in window (stocktake candidates):")
        for name, exposure in reading.never_selected_exposure:
            lines.append(f"- {name}: {format_never_selected_exposure(exposure, reading)}")
    return "\n".join(lines)


def format_never_selected_exposure(exposure: int, reading: SkillSelectionReading) -> str:
    """How often a never-selected skill was actually offered, in words.

    Shared by the two renderers of this reading (`report --skill-selection`
    and the stocktake usage section) so the surface where retirement is
    actually decided cannot keep the older, less informative phrasing.
    """
    if not reading.judged_records:
        return "no judged records in window — nothing was offered"
    if not exposure:
        return (
            f"never in catalog for any of {reading.judged_records} judged records "
            "(adopted after the window, or renamed since)"
        )
    return f"offered in {exposure} of {reading.judged_records} judged records, chosen 0"

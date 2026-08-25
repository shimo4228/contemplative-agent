"""Pass-1 skill selection: the LLM call and the injection regime (ADR-0076, ADR-0081).

Pass-1 LLM applicability selection over the learned-skill catalog. Every
selection is recorded to an append-only audit log, and a judged selection
feeds back into injection -- see ``configured_injection_regime()``, the
single place that names what may reach ``<learned_skills>``. It shipped
shadow-only (ADR-0076, recorded but inert), gained flag-gated two-pass
enforcement in ``0723726`` (ADR-0081), and the flag retired on 2026-08-08
once the second reading closed the rollout: 15 consecutive days at
1,316/1,316 enforced, fail-open zero for 26 days, hallucinated names
rejected without propagation. Prose that still describes this module as
shadow-only, or as flag-gated, is stale -- a 2026-08-08 eval defect traced
back to exactly that kind of staleness (ADR-0089 amendment).

Design constraints inherited from ADR-0036: applicability is a semantic
judgment, so it belongs to the LLM (mechanism-vs-value-split) -- no cosine
similarity, no typed-metadata predicates. The selection call sees only
skill names + descriptions plus the situation, under the identity-only
system prompt (audit H5: the learned corpus must not feed its own
vocabulary back into the judge).

**This module is the write side only.** It calls the LLM, decides the
regime, and appends to ``skill-selection-*.jsonl``. Reading that log back
is an instrument (ADR-0071) and lives in siblings that import *from* here,
never the other way: :mod:`.selection_metrics` (per-window selection
reading) and :mod:`.never_selected_metrics` (the ADR-0097 D5 exit reading),
over the shared day/window base :mod:`.selection_window`. The split is what
keeps ``numpy`` and ``difflib`` -- pure reading-side dependencies -- off the
agent's import path.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypeAlias

from ._io import (
    append_jsonl_restricted,
    b64_audit_fields,
    now_iso,
    scrub_control,
    strip_to_printable,
)
from .llm import (
    _estimate_tokens,
    circuit_shield,
    generate,
    get_identity_system_prompt,
    validate_identity_content,
)
from .text_utils import skill_theme, strip_frontmatter

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
        # ValueError, which subsumes UnicodeDecodeError — that is NOT an
        # OSError, so a skill file with one bad byte used to raise out of
        # every caller of this loader. It now has one more (the ADR-0097
        # exit reading, whose host catches broadly and would have dropped a
        # whole packet section with no reason code).
        except (OSError, ValueError):
            logger.warning("skill selection: unreadable skill file %s", path.name)
            continue
        name, description = skill_theme(text, fallback_name=path.stem)
        # Skill files are untrusted (LLM-distilled); the name reaches the
        # audit log and the terminal report, the description reaches the
        # selection prompt — scrub both at the single load seam.
        entries.append(
            SkillCatalogEntry(
                name=strip_to_printable(name, _NAME_MAX_CHARS),
                description=scrub_control(description, _DESCRIPTION_MAX_CHARS),
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
            rejected.append(scrub_control(line, _NAME_MAX_CHARS))
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

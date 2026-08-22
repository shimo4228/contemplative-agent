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

import difflib
import json
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, TypeAlias, TypeGuard

import numpy as np

from ._io import (
    append_jsonl_restricted,
    b64_audit_fields,
    now_iso,
    scrub_control,
    strip_to_printable,
)
from .llm import (
    NUM_CTX,
    _estimate_tokens,
    circuit_shield,
    generate,
    get_identity_system_prompt,
    validate_identity_content,
)
from .text_utils import read_markdown_documents, skill_theme, strip_frontmatter

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
# Rows of the rejected-name tally the report renders before summarising the
# rest. Bounds the *output*, never the reading — see the renderer.
_REJECTED_NAME_RENDER_LIMIT = 50

# Hallucination-mechanism split (T-SKILLSEL-REPORT-WINDOW, 2026-08-22). The
# rule is stated once, here, so a reader can re-derive every row:
#   1. whitespace or ``/`` in the name → prose, not a slug → ``value_layer``
#   2. a token outside the catalog vocabulary (frontmatter name +
#      description — the two scalars the pass-1 prompt is built from) that
#      does occur in the value layer (constitution / identity) → ``value_layer``
#   3. surface similarity to the nearest catalog name ≥ the floor → ``wordform``
#   4. otherwise → ``semantic`` (a different real word swapped in)
# Rule 2 abstains (``unclassified`` / ``value_layer_unavailable``) when no
# value-layer text was readable, and every rule but 1 abstains
# (``catalog_unavailable``) when there is no catalog to measure against.
# The floor is the third reading's (2026-08-22 §4.2); it is a reporting
# boundary, never a gate.
WORDFORM_SIMILARITY_FLOOR = 0.90
# Value-layer tokens shorter than this are function words and would match
# almost any slug fragment; the reference classifier used the same cut.
_VALUE_LAYER_TOKEN_MIN_CHARS = 4
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")

HallucinationMechanism: TypeAlias = Literal["wordform", "semantic", "value_layer", "unclassified"]

# Non-judged verdicts that still injected the whole corpus, named apart from
# the ``fail_open_*`` prefix family. ``shadow_observe_skill_selection``
# returns ``None`` for these and ``None`` means "keep the full prompt";
# ``empty_catalog`` is deliberately absent, because an empty catalog has
# nothing to inject.
_FULL_CORPUS_VERDICTS = frozenset({"no_template"})


def _tokens(text: str, *, min_chars: int = 1) -> set[str]:
    """The one tokenizer behind every vocabulary the split compares:
    lower-cased, split on anything outside ``[a-z0-9]``."""
    return {t for t in _TOKEN_SPLIT_RE.split(text.lower()) if len(t) >= min_chars}


def _is_prose(name: str) -> bool:
    """Rule 1: whitespace or a slash means a clause, not a slug."""
    return " " in name or "/" in name


def _is_int(value: Any) -> TypeGuard[int]:
    """``bool`` excluded on purpose: ``isinstance(True, int)`` is True, so a
    JSON ``true`` would otherwise be read as the number 1.

    A ``TypeGuard`` rather than a plain ``bool`` so the narrowing survives
    into the caller. The readers used to take their records straight from
    ``json.loads`` (``Any``, which type-checks against anything); once the
    shared walk started handing back ``dict[str, Any]``, every
    ``rec.get(...)`` became ``Any | None`` and five call sites of this
    predicate stopped type-checking — the annotation, not the calls, was
    what was wrong.
    """
    return isinstance(value, int) and not isinstance(value, bool)


# ADR-0097 D5. Judged exposures a skill must have accumulated over the WHOLE
# selection history before "never selected" is worth listing as an archive
# candidate. 600 is the smallest round number above the observed maximum
# first-selection latency: among skills that were eventually selected, the
# judged exposures before the first selection were p50 7 / p90 99 / p95 302 /
# max 569 (measured 2026-08-22 over `logs/skill-selection-*.jsonl`).
#
# It is NOT a retirement threshold and nothing downstream may treat it as one
# (`core/stocktake.py`: "never a numeric auto-retire threshold"). It selects
# what gets LISTED for a human to decide; the decision, the reason and the
# archive move stay at the Saturday gate. Its own expiry is pre-registered in
# ADR-0097 Review-when: a skill archived as strict never-selected being
# restored more than once means the floor is too low and must be re-read from
# the first-selection latency distribution.
NEVER_SELECTED_EXPOSURE_FLOOR = 600

# ADR-0097 D5's dormant cut: "zero selections in the trailing 14 days". A
# property of the decision, not of whatever window a caller happened to ask
# the surrounding report for — `report --days 7` would otherwise silently
# halve it and call a week's silence dormancy.
NEVER_SELECTED_DORMANT_WINDOW_DAYS = 14


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
class RejectedNameTally:
    """One hallucinated name, how often it was emitted, and how far it sits
    from the nearest name actually in the catalog.

    The rate alone (``hallucination_records``) cannot separate the three
    mechanisms the 2026-08-08 reading found behind it — wordform variance
    on a name that *is* in the catalog (``identify-`` for ``identifying-``),
    substitution of a different word (``translate-`` for ``trace-``), and
    text bled in from elsewhere in the prompt (constitution clauses
    arriving as skill names). Distance to the nearest catalog entry
    separates them at a glance: near-1.0 is wordform, mid-range is
    substitution, low is bleed.

    Classified since 2026-08-22 (``mechanism``), after two consecutive
    readings re-derived the same split by hand: the rule is fixed and
    stated once at ``WORDFORM_SIMILARITY_FLOOR``, so the assignment is a
    reproducible reading, not a judgment. It still feeds nothing — the
    instrument reports, the human decides (ADR-0071 /
    ``read-only-instruments``) — and whenever an input the rule needs is
    missing the row abstains with a reason code instead of guessing.

    ``similarity`` is surface (orthographic) distance from ``difflib``, not
    embedding cosine — on purpose. The embedding layer exists to resolve
    "structural similarity hidden by vocabulary variation"
    (``embeddings.py``); here vocabulary variation *is* the signal, and a
    semantic measure would collapse the wordform and substitution cases
    into each other.
    """

    name: str
    # Emissions, not records: one judged record that emitted the same
    # bogus name twice counts twice, so this does not sum to
    # ``hallucination_records``.
    count: int
    # Nearest catalog name, or ``""`` both when the catalog could not be
    # read (``skills_dir=None``) and when nothing in it resembles the name
    # at all. The renderer tells those two apart; neither fabricates a
    # match.
    nearest: str
    # 0.0 when ``nearest`` is empty. Only ``WORDFORM_SIMILARITY_FLOOR``
    # reads it as a boundary, and that is a reporting bucket, not a gate.
    similarity: float
    # One of ``HallucinationMechanism``; ``unclassified`` carries a reason
    # code in ``mechanism_reason`` (``catalog_unavailable`` /
    # ``value_layer_unavailable``). ``mechanism_note`` is the evidence for
    # a value-layer / semantic call (the foreign tokens) — it contains
    # fragments of the name, so it renders only where the name does.
    mechanism: HallucinationMechanism = "unclassified"
    mechanism_reason: str = ""
    mechanism_note: str = ""


@dataclass(frozen=True)
class MechanismTally:
    """Emissions and distinct names per hallucination mechanism."""

    mechanism: HallucinationMechanism
    emissions: int
    distinct: int


@dataclass(frozen=True)
class CatalogRegime:
    """Judged records conditioned on the catalog size they were offered.

    The catalog moves under adopt / stocktake inside one window, and the
    third reading (2026-08-22 §4.1) found the hallucination rate tracks
    the regime, not the window: 0.6% at 19 entries, 20% at 45. The corpus
    token axis sits beside the entry count because those two moved in
    opposite directions exactly once (45 → 48 entries, 35,992 → 33,745
    tokens) and the next window has to say whether that pair reproduces.
    """

    catalog_count: int
    judged: int
    hallucination_records: int
    # Median of ``full_skill_tokens`` over the judged records that carried
    # an integer value; ``None`` when none did (``tokens_missing`` says how
    # many were dropped). Never imputed.
    full_skill_tokens_median: float | None
    tokens_missing: int
    first_date: str
    last_date: str


@dataclass
class _RegimeAccumulator:
    """Mutable per-``catalog_count`` counters while the window is read;
    frozen into ``CatalogRegime`` once it has been. Same shape as the
    ``day_*`` counters that become ``SkillSelectionDay``."""

    first_date: str
    last_date: str
    judged: int = 0
    hallucination_records: int = 0
    tokens: list[int] = field(default_factory=list)
    tokens_missing: int = 0


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
    # Any bulk rename would do exactly that; read the first window after
    # one with that in mind. (The frontmatter-name backfill that used to be
    # named here as pending was dropped on 2026-08-08 — it moved every
    # renamed name *away* from what the selector emits.)
    never_selected_exposure: tuple[tuple[str, int], ...]
    # Hallucinated names themselves, not just how many records had one.
    # Added 2026-08-08 after a third ad-hoc script was needed to answer a
    # question the instrument already held the data for.
    rejected_name_tally: tuple[RejectedNameTally, ...]
    # Whether a catalog was readable at all. Without it the reading cannot
    # tell "measured, and nothing resembled it" from "there was no ruler":
    # both leave ``RejectedNameTally.similarity`` at 0.0, and the first
    # render of this tally claimed the former in both cases — so an
    # unreadable ``skills_dir`` would have read as the value-layer-bleed
    # signature, which is the single worst misreading this tally can
    # produce (cross-model review, 2026-08-08).
    catalog_available: bool
    # Explicit UTC calendar bounds when the caller windowed by
    # ``since`` / ``until``; both ``None`` in ``days`` mode. ``days`` is then
    # the calendar length of the bounded window.
    window_since: str | None = None
    window_until: str | None = None
    # Judged records bucketed by ``catalog_count``, ascending.
    catalog_regimes: tuple[CatalogRegime, ...] = ()
    # Judged records with no integer ``catalog_count`` — left out of the
    # regime table and reported, not folded into a bucket.
    catalog_count_missing: int = 0
    mechanism_tally: tuple[MechanismTally, ...] = ()
    # ``None`` when value-layer text was read; otherwise the reason code the
    # abstaining rows carry (``value_layer_not_configured`` when the caller
    # passed no paths, ``value_layer_unreadable`` when none could be read).
    value_layer_reason: str | None = "value_layer_not_configured"
    value_layer_files: int = 0
    # Configured value-layer paths that yielded no text (basenames only —
    # a home directory is not this instrument's to print). Non-empty with
    # ``value_layer_reason is None`` is the partial case: the split ran
    # against an incomplete vocabulary and says so.
    value_layer_missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SelectionDayFile:
    """One daily selection log as the two readings see it.

    ``readable=False`` means the file exists and was skipped — a state a
    reading must be able to *count*, not merely survive, which is why this
    is a value rather than a ``continue``.
    """

    date_part: str
    file_date: date
    records: tuple[dict[str, Any], ...]
    # Lines that were neither blank, valid-JSON-object rows: unparseable
    # text and valid JSON that is not an object.
    malformed_rows: int
    readable: bool


def _iter_selection_days(
    log_dir: Path, keep: Callable[[date], bool] | None = None
) -> Iterator[_SelectionDayFile]:
    """Yield one :class:`_SelectionDayFile` per daily selection log.

    The one place the log's *file* grammar lives — which files are logs,
    how their day is spelled, and what makes a line a record — shared by
    the windowed reading and the ADR-0097 exit reading. It was two copies
    that had already drifted, and the drift ran toward a crash: a line
    decoding to a JSON array reached ``rec.get`` in the windowed reader and
    raised ``AttributeError`` out of an instrument whose whole contract is
    degrade-never-abort. Non-object lines are now skipped by both readers,
    like unparseable ones, and **counted** by both.

    Decode faults are ``ValueError`` as well as ``OSError``: a log file
    with one bad byte raises ``UnicodeDecodeError``, which is not an
    ``OSError``, and the callers that broke on exactly that gap are named
    in ``scripts/value_layer_due_check.py`` and
    ``scripts/build_decision_packet.py``. Here it would have taken out a
    packet section with no reason code at all.

    ``keep`` is the caller's window predicate, applied to the filename date
    **before the file is opened** so a seven-day reading does not pay to
    decode a year of history; each caller still owns its predicate and its
    tallies. ``None`` reads every day — what the whole-history reading needs.

    Day is taken from the filename, not from each record's ``ts``: the
    writer derives both from the same UTC clock, and the filename is the
    field the window is cut on, so a record with a damaged timestamp still
    lands on the right day.
    """
    if not log_dir.is_dir():
        return
    for path in sorted(log_dir.glob("skill-selection-*.jsonl")):
        date_part = path.stem.removeprefix("skill-selection-")
        try:
            file_date = datetime.strptime(date_part, "%Y-%m-%d").date()
        except ValueError:
            continue
        if keep is not None and not keep(file_date):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError):
            logger.warning("skill selection reading: unreadable %s", path.name)
            yield _SelectionDayFile(date_part, file_date, (), 0, readable=False)
            continue
        records: list[dict[str, Any]] = []
        malformed = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(rec, dict):
                records.append(rec)
            else:
                malformed += 1
        yield _SelectionDayFile(date_part, file_date, tuple(records), malformed, readable=True)


def resolve_selection_window(
    days: int | None, since: date | None, until: date | None
) -> tuple[date, date | None, int]:
    """Return ``(cutoff, upper, calendar_days)``; ``upper`` is ``None`` in
    ``days`` mode. The one place the window rules live — the CLI calls it
    to turn a bad flag combination into a usage error.

    ``days`` mode keeps its historical meaning — every file dated on or
    after ``today - days`` — which is ``days + 1`` calendar days including
    today; that is the trap the explicit window exists to avoid, and the
    two modes are exclusive so a caller cannot get both by accident.
    """
    if since is None:
        if until is not None:
            raise ValueError("until requires since")
        if days is None:
            raise ValueError("one of days or since is required")
        return datetime.now(timezone.utc).date() - timedelta(days=days), None, days
    if days is not None:
        raise ValueError("days and since/until are exclusive")
    upper = until if until is not None else datetime.now(timezone.utc).date()
    if since > upper:
        raise ValueError("since must not be after until")
    return since, upper, (upper - since).days + 1


def _read_value_layer_vocabulary(
    paths: tuple[Path, ...],
) -> tuple[frozenset[str] | None, int, tuple[str, ...]]:
    """Tokens (≥ ``_VALUE_LAYER_TOKEN_MIN_CHARS``) of every readable ``*.md``
    under ``paths`` — a directory through ``read_markdown_documents`` (the
    file rules of every other value-layer reader in core), a file as
    itself. Read-only.

    Returns ``(vocabulary, files read, paths that yielded nothing)``.
    ``vocabulary`` is ``None`` when no file could be read at all, so the
    caller can tell "configured but unreadable" from "nothing configured";
    the third element names the *partial* case — a root that yielded
    nothing, or a directory that yielded fewer documents than it holds
    ``*.md`` files. That case is the one that silently produces wrong
    readings: half a value layer still classifies, and a token living only
    in the missing half reads as ``semantic``.
    """
    tokens: set[str] = set()
    files = 0
    missing: list[str] = []
    for root in paths:
        before = files
        expected = 0
        try:
            if root.is_dir():
                texts = [raw for _, raw, _ in read_markdown_documents(root)]
                # ``read_markdown_documents`` skips unreadable files and
                # drops empty-bodied ones, so "some text came back" is not
                # "the directory was read": a clause file lost to
                # permissions leaves its vocabulary out while the count
                # still looks healthy.
                expected = len([f for f in root.glob("*.md") if not f.name.startswith(".")])
            elif root.is_file():
                # Decoding failures are a ValueError, not an OSError: an
                # identity file with one bad byte must abstain here, not
                # take the whole reading down through the caller's
                # degrade path.
                texts = [root.read_text(encoding="utf-8")]
            else:
                texts = []
        except (OSError, UnicodeDecodeError):
            logger.warning("skill selection reading: unreadable value-layer path %s", root.name)
            texts = []
        for text in texts:
            files += 1
            tokens |= _tokens(text, min_chars=_VALUE_LAYER_TOKEN_MIN_CHARS)
        if files == before:
            logger.warning("skill selection reading: value-layer path %s read nothing", root.name)
            missing.append(root.name)
        elif files - before < expected:
            logger.warning(
                "skill selection reading: value-layer path %s read %d of %d file(s)",
                root.name,
                files - before,
                expected,
            )
            missing.append(root.name)
    if not files:
        return None, 0, tuple(missing)
    return frozenset(tokens), files, tuple(missing)


def classify_hallucination(
    name: str,
    similarity: float,
    *,
    catalog_vocabulary: frozenset[str] | None,
    value_layer_vocabulary: frozenset[str] | None,
) -> tuple[HallucinationMechanism, str, str]:
    """Apply the four-rule split documented at ``WORDFORM_SIMILARITY_FLOOR``.

    Returns ``(mechanism, reason, note)``. ``catalog_vocabulary=None``
    means there was no catalog (no ruler) and ``value_layer_vocabulary=None``
    means no value-layer text was readable; each abstains exactly the rules
    that need it, nothing more.
    """
    if _is_prose(name):
        return "value_layer", "", "prose, not a slug"
    if catalog_vocabulary is None:
        return "unclassified", "catalog_unavailable", ""
    # Only tokens long enough to exist in the value-layer vocabulary are
    # tested against it — otherwise a 3-char foreign token would be reported
    # as "not in value layer" without ever having been looked up.
    foreign = sorted(
        t for t in _tokens(name) - catalog_vocabulary if len(t) >= _VALUE_LAYER_TOKEN_MIN_CHARS
    )
    if foreign:
        if value_layer_vocabulary is None:
            # Rule 3 needs no value layer, so check it before abstaining: a
            # misspelling *is* a token outside the catalog vocabulary, and
            # abstaining first made the weekly packet (which passes no
            # value-layer paths) call `unclassified` what the terminal
            # report called `wordform` — the same log line, two answers.
            # Only names far from every catalog entry, where the choice is
            # genuinely value_layer vs semantic, still abstain. On the
            # 2026-08-09..22 window no value-layer name sits at or above the
            # floor, so this costs no accuracy there; a name that did would
            # read as wordform without the value layer and value_layer with
            # it, which the reason code makes visible.
            if similarity >= WORDFORM_SIMILARITY_FLOOR:
                return "wordform", "", ""
            return "unclassified", "value_layer_unavailable", ""
        bled = [t for t in foreign if t in value_layer_vocabulary]
        if bled:
            return "value_layer", "", "foreign token(s) present in value layer: " + ",".join(bled)
    if similarity >= WORDFORM_SIMILARITY_FLOOR:
        return "wordform", "", ""
    note = ("foreign token(s) not in value layer: " + ",".join(foreign)) if foreign else ""
    return "semantic", "", note


def read_skill_selection_log(
    log_dir: Path,
    *,
    days: int | None = None,
    since: date | None = None,
    until: date | None = None,
    skills_dir: Path | None,
    value_layer_paths: tuple[Path, ...] = (),
) -> SkillSelectionReading:
    """Aggregate ``skill-selection-*.jsonl`` files within the window.

    The window is either ``days`` (files dated on or after ``today - days``,
    unchanged since the instrument shipped) or an explicit, inclusive UTC
    calendar range ``since`` .. ``until`` (``until`` defaults to today); the
    two are exclusive. Files are selected by the date embedded in the
    filename (same daily rotation as LLM telemetry); broken lines are
    skipped, never fatal. ``never_selected`` is computed against the
    *current* catalog, so a skill adopted yesterday with no selections yet
    will appear — read it alongside ``records`` before drawing conclusions.
    ``value_layer_paths`` (constitution dir, identity file) are read, never
    written, and only feed the mechanism split of rejected names.
    """
    cutoff, upper, window_days = resolve_selection_window(days, since, until)
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
    # Names the selector emitted that matched nothing. Scrubbed here as
    # well as at the write seam: the writer sanitises what *it* appends,
    # but this reader parses a file on disk, and the global rule treats the
    # agent's own store as untrusted regardless of who wrote it.
    rejected_counts: dict[str, int] = {}
    days_seen: list[SkillSelectionDay] = []
    regimes: dict[int, _RegimeAccumulator] = {}
    catalog_count_missing = 0
    for day_file in _iter_selection_days(
        log_dir, lambda d: d >= cutoff and (upper is None or d <= upper)
    ):
        if day_file.readable:
            date_part = day_file.date_part
            day_records = 0
            day_judged = 0
            day_enforced = 0
            day_judged_empty = 0
            day_hallucinations = 0
            day_selected: set[str] = set()
            for rec in day_file.records:
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
                rejected = rec.get("rejected_names")
                if rejected:
                    hallucination_records += 1
                    day_hallucinations += 1
                # Counted separately from the record tally above: a record
                # whose ``rejected_names`` is truthy but unusable (wrong
                # type, non-string entries) still *is* a hallucination
                # record. Folding the two would let a malformed field
                # quietly lower the rate.
                if isinstance(rejected, list):
                    for name in rejected:
                        if not isinstance(name, str):
                            continue
                        clean = scrub_control(name, _NAME_MAX_CHARS)
                        if not clean:
                            continue
                        rejected_counts[clean] = rejected_counts.get(clean, 0) + 1
                full = rec.get("full_skill_tokens")
                would_be = rec.get("would_be_skill_tokens")
                if _is_int(full) and _is_int(would_be):
                    reductions.append(full - would_be)
                count = rec.get("catalog_count")
                if _is_int(count):
                    regime = regimes.setdefault(count, _RegimeAccumulator(date_part, date_part))
                    regime.judged += 1
                    regime.hallucination_records += 1 if rejected else 0
                    if _is_int(full):
                        regime.tokens.append(full)
                    else:
                        regime.tokens_missing += 1
                    regime.last_date = date_part
                else:
                    catalog_count_missing += 1
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

    catalog = load_skill_catalog(skills_dir)
    catalog_names = [e.name for e in catalog]
    never_selected = tuple(name for name in catalog_names if name not in skill_counts)
    never_selected_exposure = tuple((name, exposure_counts.get(name, 0)) for name in never_selected)
    # Catalog vocabulary = what the pass-1 prompt actually shows (name +
    # description), plus every name the window's records carried, so a
    # name renamed away mid-window is still catalog-derived rather than
    # foreign. Names only for the ruler below — it stays the current
    # catalog so the tally's nearest and the split's similarity agree.
    catalog_vocabulary: frozenset[str] | None = None
    if catalog_names:
        vocabulary: set[str] = set()
        for entry in catalog:
            vocabulary |= _tokens(f"{entry.name} {entry.description}")
        for name in exposure_counts:
            vocabulary |= _tokens(name)
        catalog_vocabulary = frozenset(vocabulary)
    value_layer_vocabulary, value_layer_files, value_layer_missing = (
        _read_value_layer_vocabulary(value_layer_paths) if value_layer_paths else (None, 0, ())
    )
    value_layer_reason = (
        None
        if value_layer_vocabulary is not None
        else ("value_layer_unreadable" if value_layer_paths else "value_layer_not_configured")
    )

    def _nearest(name: str) -> tuple[str, float]:
        """Closest catalog name by surface similarity, with its ratio.

        No cutoff: a name with no close match is exactly the interesting
        case (value-layer bleed), so its distance is worth reporting.

        Scored in one explicit pass rather than ``get_close_matches`` plus
        a second ``ratio()``. ``SequenceMatcher.ratio()`` is **not
        symmetric**, and the two calls take their operands in opposite
        orders — so on roughly 1% of realistic kebab-case names the
        printed similarity would not be the score that picked the winner,
        and a reader comparing rows would see an inconsistency with no
        way to explain it. That lands precisely on the wordform-versus-
        substitution boundary this tally exists to discriminate.

        Ties break toward the alphabetically first name; a name that
        matches nothing at all reports no nearest rather than the
        alphabetical accident ``get_close_matches`` would hand back.
        """
        if not catalog_names:
            return "", 0.0
        matcher = difflib.SequenceMatcher(autojunk=False)
        matcher.set_seq2(name)
        best_name, best_ratio = "", 0.0
        for candidate in sorted(catalog_names):
            matcher.set_seq1(candidate)
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_name, best_ratio = candidate, ratio
        return best_name, best_ratio

    def _tally(name: str, count: int) -> RejectedNameTally:
        nearest, similarity = _nearest(name)
        mechanism, reason, note = classify_hallucination(
            name,
            similarity,
            catalog_vocabulary=catalog_vocabulary,
            value_layer_vocabulary=value_layer_vocabulary,
        )
        return RejectedNameTally(
            name=name,
            count=count,
            nearest=nearest,
            similarity=similarity,
            mechanism=mechanism,
            mechanism_reason=reason,
            mechanism_note=note,
        )

    rejected_name_tally = tuple(
        _tally(name, count)
        for name, count in sorted(rejected_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    mechanism_rows: dict[HallucinationMechanism, list[int]] = {}
    for entry in rejected_name_tally:
        mechanism_rows.setdefault(entry.mechanism, []).append(entry.count)
    mechanism_tally = tuple(
        MechanismTally(mechanism=m, emissions=sum(counts), distinct=len(counts))
        for m, counts in sorted(mechanism_rows.items(), key=lambda kv: (-sum(kv[1]), kv[0]))
    )

    def _pct(values: list[int], q: float) -> float:
        if not values:
            return 0.0
        return float(np.percentile(np.asarray(values, dtype=float), q))

    catalog_regimes = tuple(
        CatalogRegime(
            catalog_count=count,
            judged=acc.judged,
            hallucination_records=acc.hallucination_records,
            full_skill_tokens_median=_pct(acc.tokens, 50) if acc.tokens else None,
            tokens_missing=acc.tokens_missing,
            first_date=acc.first_date,
            last_date=acc.last_date,
        )
        for count, acc in sorted(regimes.items())
    )

    return SkillSelectionReading(
        days=window_days,
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
        rejected_name_tally=rejected_name_tally,
        catalog_available=bool(catalog_names),
        window_since=cutoff.isoformat() if upper is not None else None,
        window_until=upper.isoformat() if upper is not None else None,
        catalog_regimes=catalog_regimes,
        catalog_count_missing=catalog_count_missing,
        mechanism_tally=mechanism_tally,
        value_layer_reason=value_layer_reason,
        value_layer_files=value_layer_files,
        value_layer_missing=value_layer_missing,
    )


def format_skill_selection_report(
    reading: SkillSelectionReading, *, include_rejected_names: bool = False
) -> str:
    """Render the reading. ``include_rejected_names`` is a trust decision.

    This renderer has two consumers with different trust requirements, and
    the difference is not phrasing — it is who reads the output:

    - ``report --skill-selection`` prints to a terminal for a human, who
      is the only reader that needs the hallucinated strings themselves
      (comparing their spelling against real names is the whole point of
      the tally). It passes ``include_rejected_names=True``.
    - ``scripts/weekly-analysis.sh`` pastes the same report into the
      weekly prompt, which an unattended chain reads before writing code
      patches (ADR-0085). It takes the default.

    A rejected name is, by definition, a string that matched nothing in
    the catalog: free text from a model whose prompt embeds untrusted post
    bodies. The 2026-08-08 reading measured this happening — 12% of
    rejected names were fragments bled from elsewhere in the prompt. Every
    other string this renderer emits comes from a closed, self-written
    vocabulary (catalog names via ``strip_to_printable``, fixed verdict
    tokens), so the tally would be the first arbitrary model output to
    reach that prompt. ADR-0083's precedent for the same tension — the
    cross-day duplicate scan — sends digests rather than content.

    The default is the restrictive one so a new caller is safe by
    omission, and the weekly script needs no knowledge of the boundary it
    is on the wrong side of.

    Withholding the names costs the weekly reader little: the *shape* of
    the tally — how many distinct names, how many emissions, and how far
    each sits from which real skill — is rendered either way, because the
    nearest name is a catalog name and the distance is a float.
    """
    if reading.window_since is not None:
        window_text = (
            f"{reading.window_since} .. {reading.window_until} UTC ({reading.days} calendar days)"
        )
    else:
        window_text = f"last {reading.days} days"
    lines = [
        "## Skill-selection reading (ADR-0076 instrument, ADR-0081 enforcement)",
        "",
        f"Window: {window_text} — {reading.records} records",
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
    if reading.catalog_regimes or reading.catalog_count_missing:
        lines.append("")
        lines.append("By catalog size (the rate tracks the regime, not the window):")
        lines.append(f"{'catalog':>8}{'judged':>8}{'halluc':>8}{'rate':>9}{'tok p50':>10}  days")
        for regime in reading.catalog_regimes:
            rate = regime.hallucination_records / regime.judged if regime.judged else 0.0
            if regime.full_skill_tokens_median is None:
                tokens_text = "—"
            else:
                tokens_text = f"{regime.full_skill_tokens_median:,.0f}"
            span = (
                regime.first_date
                if regime.first_date == regime.last_date
                else f"{regime.first_date}..{regime.last_date}"
            )
            missing = (
                f" (full_skill_tokens_missing={regime.tokens_missing})"
                if regime.tokens_missing
                else ""
            )
            lines.append(
                f"{regime.catalog_count:>8}{regime.judged:>8}{regime.hallucination_records:>8}"
                f"{rate:>9.1%}{tokens_text:>10}  {span}{missing}"
            )
        if reading.catalog_count_missing:
            lines.append(
                f"  catalog_count_missing={reading.catalog_count_missing} judged records carried "
                "no integer catalog_count and are excluded from this table"
            )
        lines.append(
            "  halluc = judged records with ≥1 rejected name; tok p50 = median "
            "full_skill_tokens the record baked in (corpus size as offered)."
        )
    if reading.per_skill:
        lines.append("")
        lines.append("Selection frequency:")
        for name, count in reading.per_skill:
            lines.append(f"- {name}: {count}")
    if reading.mechanism_tally:
        lines.append("")
        lines.append("Hallucination by mechanism (emissions over distinct rejected names):")
        total_emissions = sum(m.emissions for m in reading.mechanism_tally)
        for tally in reading.mechanism_tally:
            share = tally.emissions / total_emissions if total_emissions else 0.0
            lines.append(
                f"- {tally.mechanism}: {tally.emissions} emissions ({share:.1%}), "
                f"{tally.distinct} distinct"
            )
        if not reading.catalog_available:
            lines.append(
                "  no catalog to measure against: every non-prose name is "
                "`unclassified` (catalog_unavailable), not classified."
            )
        if reading.value_layer_reason is not None:
            lines.append(
                f"  value-layer rule abstained: {reading.value_layer_reason} — names with "
                "tokens outside the catalog vocabulary are `unclassified`, not `semantic`."
            )
        else:
            missing = (
                f"; read nothing from {', '.join(reading.value_layer_missing)}"
                if reading.value_layer_missing
                else ""
            )
            lines.append(
                f"  value layer read from {reading.value_layer_files} file(s) "
                f"(constitution / identity, read-only){missing}."
            )
        lines.append(
            "  Both rulers are the catalog and value layer as they stand *now*, not "
            "as each record saw them: a window spanning a rename, a rewritten "
            "description or a constitution amendment classifies older emissions "
            "against today's text. The audit records carry `catalog_names` (folded "
            "in above) but no description or value-layer snapshot, so this reading "
            "is not replayable across such a change — read a regime boundary in the "
            "table above as a boundary here too (cross-model review, 2026-08-22)."
        )
    if reading.rejected_name_tally:
        lines.append("")
        lines.append("Rejected names (emitted, matched no catalog entry):")
        if not include_rejected_names:
            lines.append(
                "  (names withheld — this renderer's default. They are model "
                "output shaped by untrusted input; `report --skill-selection` "
                "shows them. Shape below is catalog names and distances only.)"
            )
        shown = reading.rejected_name_tally[:_REJECTED_NAME_RENDER_LIMIT]
        for entry in shown:
            if entry.nearest:
                nearest_text = (
                    f"nearest catalog name `{entry.nearest}` (similarity {entry.similarity:.2f})"
                )
            elif reading.catalog_available:
                # Measured against a real catalog and nothing came close:
                # the value-layer-bleed signature. Rendering this as
                # `nearest \`x\` (similarity 0.00)` read as a match claim.
                nearest_text = "no catalog name resembles it"
            else:
                # No ruler. Must not be reported as the line above — a
                # broken skills_dir would then read as bleed.
                nearest_text = "no catalog to compare against"
            # The name is the only untrusted half of the row; dropping it
            # still leaves the distance and which real skill it is near,
            # which is what "did wordform slips concentrate on three
            # skills, or is text bleeding in?" actually needs.
            head = f"{entry.name}: " if include_rejected_names else ""
            mechanism_text = entry.mechanism
            if entry.mechanism_reason:
                mechanism_text += f" ({entry.mechanism_reason})"
            # The note quotes tokens of the name: same trust boundary as
            # the name itself.
            if include_rejected_names and entry.mechanism_note:
                mechanism_text += f"; {entry.mechanism_note}"
            lines.append(f"- {head}{entry.count} emissions — {nearest_text} — {mechanism_text}")
        hidden = reading.rejected_name_tally[_REJECTED_NAME_RENDER_LIMIT:]
        if hidden:
            # Bounding the *rendering*, not the reading: the dataclass
            # still carries every row. Prose bleed — the degenerate mode
            # this tally exists to detect — is exactly the mode that emits
            # thousands of unique names, so an uncapped section would
            # explode the one artifact it is meant to inform. Silently
            # truncating would read as "that was all of it".
            lines.append(
                f"- … and {len(hidden)} more distinct names "
                f"({sum(e.count for e in hidden)} emissions), not shown"
            )
        lines.append(
            "  Counts are emissions, not records — one record can emit the same "
            "name twice, so these do not sum to the Hallucination line above. "
            "Similarity is surface (orthographic), not semantic: near 1.00 is a "
            "wordform slip on a name that IS in the catalog, mid-range is a "
            "different word, low means the text came from somewhere other than "
            "the catalog. The trailing bucket is the fixed four-rule split "
            f"(wordform floor {WORDFORM_SIMILARITY_FLOOR:.2f}); `unclassified` rows "
            "name the input the rule was missing."
        )
    if reading.never_selected_exposure:
        lines.append("")
        # Deliberately not "candidates": this list is window-scoped, so most
        # of it is skills that were selected before the window opened
        # (dormant, ADR-0097 D5) and archiving one of those WOULD change
        # judged behaviour. Archive candidacy is decided by the whole-history
        # strict reading below, never by this line.
        lines.append("Never selected in window (window reading — not archive candidates):")
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


@dataclass(frozen=True)
class NeverSelectedSkill:
    """One catalogued skill the selector did not choose, with the evidence a
    human needs to decide whether that means anything.

    Exposure — how often the name was actually *offered* — is the whole
    point. Without it a skill adopted yesterday is indistinguishable from one
    that has been offered two thousand times and refused, and the first is
    not evidence of anything (ADR-0097 D5).
    """

    name: str
    # Judged records over the WHOLE history that carried this name in
    # ``catalog_names``. The floor is applied to this number.
    judged_exposure: int
    # Same, restricted to the trailing window — the number that makes a
    # dormant row readable ("offered 606 times this fortnight, chosen 0").
    # Read only for dormant rows; carried on all three populations so one row
    # shape crosses the process boundary into the packet's JSON.
    window_exposure: int
    # Filename day of the last judged record that selected this name, or ""
    # when it never was. **`""` is not data**: it is `""` by construction for
    # every strict and every below-floor row (that is what those populations
    # mean), so only a dormant row's value carries information — there it is
    # the last-circulation date CREW library weeding treats as a filter the
    # librarian must still review. The field stays on all three for the same
    # uniform-shape reason as `window_exposure`.
    last_selected: str


@dataclass(frozen=True)
class NeverSelectedReading:
    """Whole-history exit reading over the selection log (ADR-0097 D5).

    Read-only. It lists; it never archives, ranks, gates or thresholds — the
    floor selects what gets listed and the Saturday gate decides
    (``read-only-instruments``: the instrument reports, the human decides).

    Two populations, kept apart because conflating them is the error this
    reading exists to avoid:

    - ``strict`` — zero selections across the whole selection history, at or
      above ``exposure_floor`` judged exposures. Only these are archive
      candidates: a skill never selected under two-pass injection was never
      injected, so removing it cannot change judged behaviour.
    - ``dormant`` — zero selections in the trailing window but selected at
      some point before. A reading only. Archiving one of these WOULD change
      judged behaviour, which is exactly why it is a separate field and not a
      longer version of the first list.

    ``below_floor`` is the third state and is not a population to act on:
    never selected, but not yet offered often enough for that to mean
    anything (ADR-0097 D8 — "a newly adopted skill becomes a never-selected
    candidate only after 600 judged exposures"). It is carried so a name
    missing from ``strict`` reads as "not yet measured" rather than "was
    selected".

    The neutrality caveat travels in the same object as the populations,
    because behaviour-neutrality holds for *judged* actions only: the
    fail-open path injects the full corpus. ``window_fail_open`` and
    ``history_full_skill_tokens`` against ``num_ctx`` are what let a reader check
    that instead of taking it on faith (the Codex challenge recorded in
    ADR-0097's Context).
    """

    strict: tuple[NeverSelectedSkill, ...]
    dormant: tuple[NeverSelectedSkill, ...]
    below_floor: tuple[NeverSelectedSkill, ...]
    exposure_floor: int
    # History span actually read, so "zero selections in the whole history"
    # can be weighed against how much history there was. ``history_files``
    # counts only the days this reading could open — the ones it could not
    # are ``unreadable_files`` below, and the difference is the whole point:
    # a reading that silently narrowed its own evidence is how a skill the
    # selector chose last month becomes an archive candidate.
    history_files: int
    history_records: int
    history_judged: int
    # Same population as ``window_fail_open`` over the whole history, kept
    # beside it because the two skill populations have two scopes and this
    # one belongs to ``strict``: a candidate never *judged*-selected may
    # still have been injected by every full-corpus action in the log's
    # life, and that count is not recoverable by subtraction from a
    # windowed one.
    history_fail_open: int
    history_first_day: str
    history_last_day: str
    # Evidence this reading could not see. A whole day that would not open
    # (``unreadable_files``) withholds the strict list outright; individual
    # lines that would not decode, or decoded to something other than an
    # object (``malformed_rows``), are bounded loss and are reported beside
    # the populations instead. Both raise ``NEVER_SELECTED_LOG_PARTIAL``.
    unreadable_files: int
    malformed_rows: int
    # Trailing window — the dormant cut and the neutrality caveat. Cut by
    # ``resolve_selection_window``, the same seam ``read_skill_selection_log``
    # uses, so the two readings of one log agree about where the window is;
    # ``window_since`` / ``window_until`` mirror that reading's fields and are
    # ``None`` in ``days`` mode.
    window_days: int
    window_since: str | None
    window_until: str | None
    window_records: int
    window_judged: int
    # Window records that injected the FULL corpus instead of a selection:
    # every ``fail_open_*`` **and** ``no_template``. The producer settles
    # what belongs here — ``shadow_observe_skill_selection`` returns ``None``
    # for both, and ``None`` means "keep the full prompt"
    # (``adapters/moltbook/llm_functions``). ``empty_catalog`` is the one
    # non-judged verdict left out, because there was no corpus to inject.
    #
    # This is the same population ``SkillSelectionDay.fell_back`` describes,
    # minus ``empty_catalog``; an earlier version of this field excluded
    # ``no_template`` too and so would have printed "fail-open: 0 of 700"
    # for a week in which a missing selection template sent the whole corpus
    # into all 700 actions — the exact claim this caveat exists to let a
    # reader check. Still not ``records - judged``, so the residual stays
    # visible rather than being absorbed silently.
    window_fail_open: int
    # Latest ``full_skill_tokens`` in the WHOLE history (baked in at record
    # time by the writer, so it is the corpus as the selector saw it), and
    # the context window it is compared against. 0 when no record carried a
    # usable value — see ``NEVER_SELECTED_FULL_TOKENS_UNKNOWN``.
    #
    # Whole-history on purpose, and named so: it is evidence for the
    # ``strict`` population, which is itself whole-history, and it is
    # rendered only beside that list. ``since``/``until`` move the dormant
    # cut and the window figures; they do not narrow the strict population,
    # so clamping this to the window would pair a whole-history list with
    # window-scoped evidence — the mismatch this rename exists to end.
    # ``dormant`` makes no neutrality claim and gets no corpus figure.
    history_full_skill_tokens: int
    num_ctx: int
    # Size of the catalog the populations were computed against — the
    # denominator a reader needs for "N of M skills". ``catalog_available``
    # is ``bool(catalog_size)`` and is carried anyway: it is the field the
    # renderers branch on, named as the sibling ``SkillSelectionReading``
    # names it, so the two readings of one log read alike. The third
    # encoding, ``NEVER_SELECTED_NO_CATALOG``, is the no-silent-fallback
    # contract and is what a consumer that cannot see this object gets.
    catalog_size: int
    catalog_available: bool
    # ADR-0075: anything not computable abstains with a code rather than
    # guessing. Closed vocabulary in ``NEVER_SELECTED_REASONS``.
    reasons: tuple[str, ...]


# Closed reason vocabulary for ``NeverSelectedReading.reasons``. The weekly
# packet re-renders these into its header, so they are named once here rather
# than spelled at each emit site.
#
# ``NEVER_SELECTED_BELOW_FLOOR`` is the one that means a guard WORKED: skills
# were never selected but none had been offered often enough to be worth
# listing, so nothing is proposed. It recurs by design in any week following
# an adoption, and the packet's recurrence trigger must treat it as designed.
NEVER_SELECTED_REASONS = (
    "NEVER_SELECTED_NO_CATALOG",
    "NEVER_SELECTED_NO_HISTORY",
    # The reading is degraded: something it should have read, it did not.
    # Raised for a lost day and for a lost row alike, so one code answers
    # "is this week's exit reading complete?".
    "NEVER_SELECTED_LOG_PARTIAL",
    # ...and the sharper one, raised only for a lost DAY. The two are kept
    # apart because the withholding decision turns on exactly this
    # difference: a dropped row is bounded evidence loss (one action out of
    # thousands), a dropped day is not — the single record that ever
    # selected a name may be the whole of it. Folding them would let two
    # corrupt lines in a 3,700-record log withhold the list every week,
    # which is how a safety guard becomes the reason the guard is removed.
    "NEVER_SELECTED_LOG_UNREADABLE",
    "NEVER_SELECTED_EMPTY_WINDOW",
    "NEVER_SELECTED_BELOW_FLOOR",
    "NEVER_SELECTED_FULL_TOKENS_UNKNOWN",
)

# Reasons under which a population is not a reading but the absence of one.
# A renderer must say "withheld" for these, never "none": the difference
# between "nothing to archive" and "this reading cannot tell you" is the
# entire safety margin of the exit.
NEVER_SELECTED_STRICT_WITHHELD = frozenset(
    {
        "NEVER_SELECTED_NO_CATALOG",
        "NEVER_SELECTED_NO_HISTORY",
        "NEVER_SELECTED_LOG_UNREADABLE",
    }
)
NEVER_SELECTED_DORMANT_WITHHELD = frozenset(
    {"NEVER_SELECTED_NO_CATALOG", "NEVER_SELECTED_EMPTY_WINDOW"}
)


def read_never_selected(
    log_dir: Path,
    *,
    days: int | None = None,
    since: date | None = None,
    until: date | None = None,
    skills_dir: Path | None,
    exposure_floor: int = NEVER_SELECTED_EXPOSURE_FLOOR,
) -> NeverSelectedReading:
    """Walk the whole selection history for the ADR-0097 D5 exit reading.

    **Two scopes in one pass, on purpose.** The strict population is defined
    over the *whole* selection history — a window cannot express it, because
    a skill selected once in March and never since is dormant rather than an
    archive candidate, and only a full walk tells those apart. The dormant
    population and the neutrality caveat are defined over a *trailing
    window*. Which scope each field is measured under is in its comment on
    :class:`NeverSelectedReading`: everything named ``history_*`` and the
    ``judged_exposure`` the floor tests are whole-history; everything named
    ``window_*``, plus ``dormant`` and ``NeverSelectedSkill.window_exposure``,
    are windowed.

    There is still only **one** windowing implementation in this module:
    ``days`` / ``since`` / ``until`` mean exactly what they mean on
    :func:`read_skill_selection_log` and are resolved by the same
    :func:`resolve_selection_window`, so the two readings of one log cannot
    disagree about where the window is. Passing ``since`` / ``until`` is also
    how a caller gets a reading that replays identically offline (ADR-0091's
    shape); ``days`` mode reads the UTC clock, as it does for the sibling.

    This is a separate function rather than another mode of
    :func:`read_skill_selection_log` because a single call would have to
    answer both scopes at once: ``dormant`` needs the windowed and the
    whole-history view of the same name simultaneously.

    One pass over every ``skill-selection-*.jsonl``, four fields per record
    and no per-name similarity scan (no ``difflib``, no mechanism split), so
    the weekly cost is a JSON decode of the log — ~3.7k records over ~44
    files at the 2026-08 volume.
    """
    cutoff, upper, window_days = resolve_selection_window(days, since, until)

    # Tallied for every catalogued name seen in the log, not just the ones
    # that turn out never-selected: which names those are is only known after
    # the whole history has been read, and the current catalog is resolved
    # later still.
    exposure_history: dict[str, int] = {}
    exposure_window: dict[str, int] = {}
    selected_history: dict[str, int] = {}
    selected_window: dict[str, int] = {}
    last_selected: dict[str, str] = {}
    history_files = 0
    history_records = 0
    history_judged = 0
    history_fail_open = 0
    unreadable_files = 0
    malformed_rows = 0
    window_records = 0
    window_judged = 0
    window_fail_open = 0
    full_skill_tokens = 0
    days_read: list[str] = []

    for day_file in _iter_selection_days(log_dir):
        date_part = day_file.date_part
        if not day_file.readable:
            # Counted, not merely survived. A day this reading could not open
            # is a day whose selections it cannot see, and the strict list is
            # a list of skills a human is about to remove — so the evidence
            # loss is named here and withholds that list below.
            unreadable_files += 1
            continue
        history_files += 1
        malformed_rows += day_file.malformed_rows
        days_read.append(date_part)
        in_window = day_file.file_date >= cutoff and (upper is None or day_file.file_date <= upper)
        for rec in day_file.records:
            history_records += 1
            if in_window:
                window_records += 1
            verdict = str(rec.get("verdict", "unknown"))
            if verdict != "judged":
                if verdict in _FULL_CORPUS_VERDICTS or verdict.startswith("fail_open"):
                    # Two scopes, because the two skill populations have two
                    # scopes: the whole-history count is the one that belongs
                    # beside the strict list, and it is NOT recoverable by
                    # subtraction from the window's.
                    history_fail_open += 1
                    if in_window:
                        window_fail_open += 1
                continue
            # Judged-only below, for the reason the windowed reader's cut
            # records: every number here is a count over judged records,
            # and a name offered to a selector that never answered was
            # not refused.
            history_judged += 1
            if in_window:
                window_judged += 1
            names = rec.get("catalog_names")
            if isinstance(names, list):
                for name in names:
                    if isinstance(name, str):
                        exposure_history[name] = exposure_history.get(name, 0) + 1
                        if in_window:
                            exposure_window[name] = exposure_window.get(name, 0) + 1
            selected = rec.get("selected")
            if isinstance(selected, list):
                for name in selected:
                    if not isinstance(name, str):
                        continue
                    selected_history[name] = selected_history.get(name, 0) + 1
                    if in_window:
                        selected_window[name] = selected_window.get(name, 0) + 1
                    # Filename day, like the window cut: the writer
                    # derives both from the same UTC clock, so a record
                    # with a damaged ``ts`` still lands on the right day.
                    if date_part > last_selected.get(name, ""):
                        last_selected[name] = date_part
            full = rec.get("full_skill_tokens")
            # ``_is_int``, not ``isinstance(full, int)``: ``True`` is an
            # int in Python, so a record carrying ``"full_skill_tokens":
            # true`` would read as a 1-token corpus and print "fits
            # within NUM_CTX" — the exact claim the abstain code exists
            # to withhold. The sibling reader takes the same field
            # through the same helper.
            if _is_int(full) and full > 0:
                # Last writer wins: files are walked in date order, so
                # this ends as the corpus the most recent judged action
                # saw. Recomputing it from today's catalog would answer a
                # different question than the caveat asks.
                full_skill_tokens = full

    catalog_names = [e.name for e in load_skill_catalog(skills_dir)]
    flagged: set[str] = set()

    def _entry(name: str) -> NeverSelectedSkill:
        return NeverSelectedSkill(
            name=name,
            judged_exposure=exposure_history.get(name, 0),
            window_exposure=exposure_window.get(name, 0),
            last_selected=last_selected.get(name, ""),
        )

    strict: list[NeverSelectedSkill] = []
    below_floor: list[NeverSelectedSkill] = []
    dormant: list[NeverSelectedSkill] = []
    for name in catalog_names:
        if name in selected_history:
            # Selected at some point. Dormant only if the trailing window
            # also offered it and it went unchosen there — a name absent from
            # the window's catalog entirely was not refused, it was not on
            # the table (the 2026-07-12 breaker-open misreading, in the
            # windowed reader's own words).
            if name not in selected_window and exposure_window.get(name, 0) > 0:
                dormant.append(_entry(name))
            continue
        entry = _entry(name)
        if entry.judged_exposure >= exposure_floor:
            strict.append(entry)
        else:
            below_floor.append(entry)

    if not catalog_names:
        # No ruler: "never selected" cannot be said of names that could not be
        # enumerated. Every population stays empty rather than reading as
        # "nothing to archive".
        flagged.add("NEVER_SELECTED_NO_CATALOG")
    if not history_judged:
        flagged.add("NEVER_SELECTED_NO_HISTORY")
    if unreadable_files or malformed_rows:
        flagged.add("NEVER_SELECTED_LOG_PARTIAL")
    if unreadable_files:
        flagged.add("NEVER_SELECTED_LOG_UNREADABLE")
    if not window_records:
        # The window is empty while the history is not: every window-scoped
        # figure below reads 0, including the fail-open count a reader would
        # otherwise take as "no fail-open ever happened". An agent that was
        # down for the requested fortnight produces exactly this.
        flagged.add("NEVER_SELECTED_EMPTY_WINDOW")
    if below_floor and not strict:
        flagged.add("NEVER_SELECTED_BELOW_FLOOR")
    if not full_skill_tokens:
        # Without it the neutrality caveat is half a sentence: the reader
        # cannot check whether a fail-open would re-inject the corpus or
        # abstain for exceeding the context window.
        flagged.add("NEVER_SELECTED_FULL_TOKENS_UNKNOWN")

    # Declared order, not emit order: the weekly packet renders this list and
    # a stable order is what makes week-over-week diffs readable. Filtering
    # through the vocabulary also means an undeclared code cannot leave this
    # function.
    reasons = tuple(c for c in NEVER_SELECTED_REASONS if c in flagged)
    if NEVER_SELECTED_STRICT_WITHHELD & flagged:
        # A day that would not open is unbounded evidence loss: the one
        # record that ever selected this name may be in it. Withholding the
        # list is the only honest answer, and it is the same move
        # ``NEVER_SELECTED_NO_CATALOG`` already makes — the renderers say
        # "withheld", never "none" (``NEVER_SELECTED_STRICT_WITHHELD``).
        strict = []
    if NEVER_SELECTED_DORMANT_WITHHELD & flagged:
        dormant = []

    # Exposure descending: the most-offered, least-chosen skill is the one the
    # human has the most evidence about. A reading order, not a rank — nothing
    # downstream may treat position as priority (ADR-0071 invariant 1).
    # Each population is ordered by the exposure its own renderers print, so
    # the column a reader scans is monotonic; the packet preserves the order
    # it receives rather than re-sorting, so the two surfaces agree.
    def _by_exposure(entries: list[NeverSelectedSkill]) -> tuple[NeverSelectedSkill, ...]:
        return tuple(sorted(entries, key=lambda e: (-e.judged_exposure, e.name)))

    def _by_window_exposure(entries: list[NeverSelectedSkill]) -> tuple[NeverSelectedSkill, ...]:
        return tuple(sorted(entries, key=lambda e: (-e.window_exposure, e.name)))

    return NeverSelectedReading(
        strict=_by_exposure(strict),
        dormant=_by_window_exposure(dormant),
        below_floor=_by_exposure(below_floor),
        exposure_floor=exposure_floor,
        history_files=history_files,
        history_records=history_records,
        history_judged=history_judged,
        history_fail_open=history_fail_open,
        history_first_day=min(days_read) if days_read else "",
        history_last_day=max(days_read) if days_read else "",
        unreadable_files=unreadable_files,
        malformed_rows=malformed_rows,
        window_days=window_days,
        window_since=since.isoformat() if since is not None else None,
        window_until=upper.isoformat() if upper is not None else None,
        window_records=window_records,
        window_judged=window_judged,
        window_fail_open=window_fail_open,
        history_full_skill_tokens=full_skill_tokens,
        num_ctx=NUM_CTX,
        catalog_size=len(catalog_names),
        catalog_available=bool(catalog_names),
        reasons=reasons,
    )


def never_selected_reading_json(reading: NeverSelectedReading) -> dict[str, Any]:
    """Serialize the reading for the weekly packet (`build_decision_packet.py`).

    Rows, not counts. The packet builder computes every number it prints from
    these rows and re-applies the floor itself — a count asserted in a field
    is a count nobody checked, and the strict list is the one list a human
    acts on.
    """

    def _rows(entries: tuple[NeverSelectedSkill, ...]) -> list[dict[str, Any]]:
        return [
            {
                "name": e.name,
                "judged_exposure": e.judged_exposure,
                "window_exposure": e.window_exposure,
                "last_selected": e.last_selected,
            }
            for e in entries
        ]

    return {
        "exposure_floor": reading.exposure_floor,
        "strict": _rows(reading.strict),
        "dormant": _rows(reading.dormant),
        "below_floor": _rows(reading.below_floor),
        "history": {
            "files": reading.history_files,
            "records": reading.history_records,
            "judged": reading.history_judged,
            "fail_open": reading.history_fail_open,
            "first_day": reading.history_first_day,
            "last_day": reading.history_last_day,
            "unreadable_files": reading.unreadable_files,
            "malformed_rows": reading.malformed_rows,
        },
        "window": {
            "days": reading.window_days,
            "since": reading.window_since,
            "until": reading.window_until,
            "records": reading.window_records,
            "judged": reading.window_judged,
            "fail_open": reading.window_fail_open,
        },
        "corpus": {
            # Named for its scope: the latest the WHOLE history carries, and
            # the packet renders it beside the whole-history strict list only.
            "history_full_skill_tokens": reading.history_full_skill_tokens,
            "num_ctx": reading.num_ctx,
        },
        "catalog": {
            "size": reading.catalog_size,
            "available": reading.catalog_available,
        },
        "reasons": list(reading.reasons),
    }


def _withholding(reading: NeverSelectedReading, codes: frozenset[str]) -> tuple[str, ...]:
    """The reasons, if any, under which a population must read as withheld
    rather than empty. Shared by both renderers of this reading so the
    packet — the surface a human archives from — cannot keep the weaker
    phrasing (the failure this helper exists to prevent was exactly that
    asymmetry)."""
    return tuple(c for c in reading.reasons if c in codes)


def format_never_selected_report(reading: NeverSelectedReading) -> str:
    """Render the exit reading for a terminal (`report --skill-selection`).

    The weekly packet renders the same reading from JSON; this one exists so
    the human at the gate can ask the question outside the weekly chain — and
    so the reading has a live consumer, which is the condition this repo puts
    on an instrument existing at all (signal-first).
    """
    lines = [
        "## Never-selected reading (ADR-0097 D5 exit — listing only)",
        "",
        f"History: {reading.history_files} daily logs "
        f"({reading.history_first_day or '—'} … {reading.history_last_day or '—'}), "
        f"{reading.history_judged} judged of {reading.history_records} records",
        f"Catalog: {reading.catalog_size} skills"
        + (
            ""
            if reading.catalog_available
            else " (unreadable OR empty — `load_skill_catalog` returns () for both; "
            "populations withheld either way)"
        ),
        f"Exposure floor: {reading.exposure_floor} judged exposures",
    ]
    if reading.unreadable_files or reading.malformed_rows:
        lines.append(
            f"Evidence lost: {reading.unreadable_files} unreadable day(s), "
            f"{reading.malformed_rows} unusable row(s)"
        )
    if reading.reasons:
        lines.append(f"Reasons: {', '.join(reading.reasons)}")
    span = (
        f"{reading.window_since} … {reading.window_until}"
        if reading.window_since
        else f"the last {reading.window_days} days"
    )
    lines.append("")
    lines.append(
        "Behaviour-neutrality holds for JUDGED actions only — the fail-open "
        "path injects the full corpus:"
    )
    # Whole-history, beside the whole-history population. A window figure
    # here would answer a question nobody asked of a strict candidate, and
    # would read as 0 for an agent that was down for the window.
    lines.append(
        f"- fail-open across the whole history: {reading.history_fail_open} "
        f"of {reading.history_records} records"
    )
    if reading.history_full_skill_tokens:
        relation = (
            "exceeds" if reading.history_full_skill_tokens >= reading.num_ctx else "fits within"
        )
        lines.append(
            f"- full corpus {reading.history_full_skill_tokens:,} tok {relation} "
            f"NUM_CTX {reading.num_ctx:,}"
        )
    else:
        lines.append(
            "- full corpus size unknown (NEVER_SELECTED_FULL_TOKENS_UNKNOWN) — "
            f"NUM_CTX is {reading.num_ctx:,}"
        )
    lines.append(
        "  One number, the latest the WHOLE history carries: the corpus as "
        "the most recent judged action saw it. Its distribution — median size "
        "per catalog size, and where the regime boundaries fall — is the "
        "`By catalog size` table of the windowed reading above; this line "
        "adds only the comparison against NUM_CTX, which that table does "
        "not make."
    )
    lines.append("")
    lines.append(
        f"Strict (0 selections in the whole history, >= {reading.exposure_floor} "
        "judged exposures) — archive candidates for the human gate:"
    )
    withheld = _withholding(reading, NEVER_SELECTED_STRICT_WITHHELD)
    if withheld:
        lines.append(f"- WITHHELD ({', '.join(withheld)}) — this reading cannot answer")
    elif reading.strict:
        for entry in reading.strict:
            lines.append(f"- {entry.name}: offered in {entry.judged_exposure} judged records")
    else:
        lines.append("- (none)")
    if reading.below_floor:
        highest = max(e.judged_exposure for e in reading.below_floor)
        lines.append("")
        lines.append(
            f"Below the floor: {len(reading.below_floor)} never-selected skills "
            f"under {reading.exposure_floor} exposures (highest {highest}) — "
            "not yet candidates, not listed"
        )
    lines.append("")
    lines.append(
        f"Dormant (0 selections in {span} but selected before) — "
        "reading only, NOT archive candidates:"
    )
    lines.append(
        f"  fail-open in {span}: {reading.window_fail_open} of {reading.window_records} records"
    )
    dormant_withheld = _withholding(reading, NEVER_SELECTED_DORMANT_WITHHELD)
    if dormant_withheld:
        lines.append(f"- WITHHELD ({', '.join(dormant_withheld)}) — this reading cannot answer")
    elif reading.dormant:
        for entry in reading.dormant:
            lines.append(
                f"- {entry.name}: offered in {entry.window_exposure} judged records "
                f"this window, last selected {entry.last_selected or '—'} "
                "(whole history — may post-date the window)"
            )
    else:
        lines.append("- (none)")
    return "\n".join(lines)

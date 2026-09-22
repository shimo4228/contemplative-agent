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

import logging
import uuid
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
    REASON_ANSWERED,
    NoulQuestion,
    _estimate_tokens,
    circuit_shield,
    decide,
    decision_backend_name,
    generate,
    get_identity_system_prompt,
    validate_identity_content,
)
from .selection_window import _NAME_MAX_CHARS, PUBLISH_RECORD_KIND, SELECTION_RECORD_KIND
from .text_utils import iter_markdown_documents, skill_theme, strip_frontmatter

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


# Sampling temperature of the selection call (RFC-0044). The selector ran at
# ``generate``'s default of 1.0 until 2026-09-20, when an offline replay of 150
# logged situations (``docs/evidence/rfc-0043/``, "第 2 ラウンド" §3) found
# hallucinated names on 28.7% and 20.7% of rows across two repetitions at 1.0,
# against 7.3% at 0 — while agreement with the frontier ceiling did not move
# (paired difference −0.008, 95% CI [−0.023, +0.007]) and the selection size
# stayed at ~6 names. A hallucinated name is rejected rather than injected, so
# what the sampling noise was costing is a skill that should have been picked.
# Same move RFC-0042 made for the novelty judge
# (``insight_novelty._NOVELTY_TEMPERATURE``).
_SELECTION_TEMPERATURE = 0.0


# Sentinel the prompt instructs the model to emit when no skill applies.
_NONE_SENTINEL = "none"


# Length bound for catalog descriptions (security review 2026-07-10).
# Names are kebab-case ASCII by insight convention → strip_to_printable
# under ``selection_window._NAME_MAX_CHARS``, the cap the log's own reader
# shares; descriptions and hallucinated names may legitimately carry CJK →
# control characters only are removed (ANSI escapes included), CJK preserved.
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


# One log label and one identity expression for every reader of the skill
# directory: the catalog (pass 1) and the body loader (pass 2) must key the
# same file the same way, or a judged selection injects an empty block.
_UNREADABLE_SKILL_LOG = "skill selection: unreadable skill file"


def _catalog_key(name: str) -> str:
    """Lowercased catalog identity for a skill file's ``skill_theme`` name."""
    return strip_to_printable(name, _NAME_MAX_CHARS).lower()


def load_skill_catalog(skills_dir: Path | None) -> tuple[SkillCatalogEntry, ...]:
    """Read ``skills_dir/*.md`` into catalog entries.

    Traversal (sorted glob, dotfiles skipped, unreadable files logged and
    skipped) is ``text_utils.iter_markdown_documents``, shared with the
    novelty gate's inventory and the pass-2 body loader so the three cannot
    drift on the same directory. ``body_tokens`` is the audit-C2 estimate of
    the full file text — the cost the skill contributes to the system prompt
    today, kept per entry so audit records can bake in the would-be reduction
    at record time.
    """
    entries: list[SkillCatalogEntry] = []
    for path, text in iter_markdown_documents(skills_dir, label=_UNREADABLE_SKILL_LOG):
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
            temperature=_SELECTION_TEMPERATURE,
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


# --------------------------------------------------------------------------
# ADR-0112: the decision shadow. A second judge, observe-only, in the same row.
# --------------------------------------------------------------------------

# Written on EVERY record, null where there is nothing to say, so the log has
# one shape: a reader counting keys must not have to tell "this row predates
# the judge" from "this row's judge abstained".
_DECISION_FIELDS = (
    "decision_backend",
    "decision_model",
    "decision_latency_ms",
    "decision_reason",
    "decision_answered_count",
    "decision_p",
    "decision_topk",
)

_DECISION_CALLER = "core.skill_selection.decision"

# One yes/no per catalog entry rather than one choice over the catalog: the
# decomposed shape is the one that covers the whole catalog (RFC-0043: AUC
# 0.728 at 100% coverage, against 0.642 at 37% for the one-pass readout). The
# backend appends its own "answer yes or no" instruction.
_DECISION_QUESTION = "Does the skill `{name} — {description}` apply to the situation above?"


def _null_decision_fields(reason: str | None = None) -> dict[str, Any]:
    """The seven fields with nothing in them. *reason* names why, when known."""
    fields: dict[str, Any] = {name: None for name in _DECISION_FIELDS}
    fields["decision_reason"] = reason
    return fields


def _shadow_decision(
    situation: str,
    catalog: tuple[SkillCatalogEntry, ...],
    live: SkillSelectionResult,
) -> dict[str, Any]:
    """Ask the decision backend about this selection; return the record fields.

    Runs AFTER the live selection and returns nothing the caller can inject —
    the whole point of the shadow (ADR-0076). ``decision_topk`` is sized to
    what the live path selected and baked in here rather than at report time,
    because the catalog changes under adopt/stocktake and a later
    recomputation could not replay this row's comparison.
    """
    questions = tuple(
        NoulQuestion(
            id=entry.name,
            instructions=_DECISION_QUESTION.format(name=entry.name, description=entry.description),
        )
        for entry in catalog
    )
    try:
        result = decide(
            situation,
            questions,
            caller=_DECISION_CALLER,
            # The judge runs under the system prompt the live selection ran
            # under (audit H5: identity only, so the learned corpus does not
            # feed its own vocabulary back into the judge).
            system=get_identity_system_prompt(),
        )
    except Exception as exc:
        # Its own handler, not the caller's: an escape from here would reach
        # ``observe_skill_selection_recorded``'s outer except, which discards
        # the judged selection (reverting the generation to full injection)
        # and writes no audit row — the shadow taking the thing it observes
        # with it, which is the one thing it may never do.
        logger.warning("decision shadow failed (selection unaffected): %s", exc)
        return _null_decision_fields("backend_exception")
    if result is None:
        # The kill switch: no backend configured, nothing sent, nothing timed.
        return _null_decision_fields("unconfigured")
    probabilities: dict[str, float] = {}
    answered = 0
    for answer in result.answers:
        if answer.reason != REASON_ANSWERED:
            continue
        answered += 1
        probability = answer.as_dict().get("yes")
        if probability is not None:
            probabilities[answer.id] = probability
    ranked = sorted(probabilities.items(), key=lambda item: (-item[1], item[0]))
    return {
        # The class, not the model: two backends can serve the same model id
        # through different interfaces and are not the same judge.
        "decision_backend": decision_backend_name(),
        "decision_model": result.model,
        "decision_latency_ms": result.latency_ms,
        "decision_reason": result.reason,
        "decision_answered_count": answered,
        "decision_p": probabilities,
        "decision_topk": [name for name, _p in ranked[: len(live.selected)]],
    }


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


# ``publish_status`` reason codes. A publish that produced no usable comment
# id says WHY rather than going missing — the reading counts each of these
# separately, so "the selector was never published" and "the platform
# answered without an id" cannot collapse into one silence (ADR-0075).
PUBLISH_PUBLISHED = "published"


PUBLISH_ID_UNKNOWN = "published_id_unknown"


PUBLISH_UNVERIFIED = "unverified"


PUBLISH_FAILED = "publish_failed"


# ``failure_reason`` vocabulary (RFC-0029): WHY a ``publish_failed`` row
# failed, in terms a reading can count. Closed and code-owned on purpose —
# the cause arrives as a platform-authored message, and the only readable log
# that ever held it in full is one the harness forbids reading
# (``agent-launchd.log``). A code maps that message to one of these members
# and nothing else crosses (ADR-0083: untrusted text reaches a readable log
# as a digest at most).
#
# Set ONLY on a PUBLISH_FAILED row: every other status already names its own
# cause (``unverified`` is the handshake, ``declined`` the operator,
# ``published_id_unknown`` the envelope), and a second column repeating it is
# a column a later reading can disagree with.
PUBLISH_FAILURE_RATE_LIMITED = "rate_limited"


PUBLISH_FAILURE_PARENT_REJECTED = "parent_rejected"


PUBLISH_FAILURE_TRANSPORT = "transport"


PUBLISH_FAILURE_UNKNOWN = "unknown"


PUBLISH_FAILURE_REASONS = frozenset(
    {
        PUBLISH_FAILURE_RATE_LIMITED,
        PUBLISH_FAILURE_PARENT_REJECTED,
        PUBLISH_FAILURE_TRANSPORT,
        PUBLISH_FAILURE_UNKNOWN,
    }
)


# The approval gate said no. Distinct from PUBLISH_FAILED on purpose: a
# declined action is an operator decision, not a fault, and an approval-gated
# run would otherwise leave the same silence as an internal failure.
PUBLISH_DECLINED = "declined"


@dataclass(frozen=True)
class SelectionObservation:
    """One recorded selection: what was injected, and the id that names it.

    ``selection_id`` is minted *before* the record is written, which is what
    makes the publish link possible without rewriting anything: the comment
    id does not exist until after the generation is published, and an
    append-only log cannot go back and add it to the selection record
    (RFC-0028 Unresolved 1). The publish side appends its own record
    carrying this id instead.

    ``selected`` keeps the meaning ``shadow_observe_skill_selection`` has
    always had: names to inject, or ``None`` for full injection.
    """

    selected: tuple[str, ...] | None
    selection_id: str | None


def _recorded_http_status(value: object) -> int | None:
    """The status to record, or ``None`` when there is no usable one.

    A status arrives from an adapter that read it off a response, so the type
    is not assumed: only a real int inside the HTTP range is written. Anything
    else would put adapter- or platform-shaped text into a column the reading
    groups by. ``bool`` is excluded because it is an ``int`` that means
    nothing here.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 100 <= value <= 599 else None


def _recorded_failure_reason(value: object) -> str | None:
    """The reason to record: a member of the closed vocabulary, or ``None``.

    An unrecognised reason is recorded as ``unknown`` rather than verbatim —
    this function is the vocabulary's gate, so a caller cannot widen the
    column into free text (RFC-0029). The rejected value is named in the
    warning, never in the record.
    """
    if value is None:
        return None
    # ``isinstance`` first, like the status gate above: ``x in frozenset``
    # raises TypeError for an unhashable value, and this function runs inside
    # the publish path — an instrument may not fail the action it observes
    # (security review 2026-09-12).
    if isinstance(value, str) and value in PUBLISH_FAILURE_REASONS:
        return value
    logger.warning(
        "skill selection: unknown publish failure reason (%s chars) recorded as %r",
        len(str(value)),
        PUBLISH_FAILURE_UNKNOWN,
    )
    return PUBLISH_FAILURE_UNKNOWN


def record_publish_outcome(
    selection_id: str | None,
    *,
    comment_id: str | None,
    publish_status: str,
    http_status: int | None = None,
    failure_reason: str | None = None,
) -> None:
    """Append the ``publish`` record that links a selection to its comment.

    ``comment_id`` is ``None`` whenever the publish produced no usable id —
    the reason is in ``publish_status``. A missing ``selection_id`` (the
    selector was disabled, or the generation never ran under one) writes
    nothing: a publish record with no selection to join to is a row the
    reading would have to discard anyway.

    ``http_status`` / ``failure_reason`` say why a ``publish_failed`` row
    failed (RFC-0029); both are written as explicit nulls on every other exit,
    so "no reason because it worked" and "written before RFC-0029" stay
    distinguishable. Both are sanitised here rather than trusted from the
    caller — the values are derived from an untrusted error.

    Never raises: this runs inside the publish path, and an instrument must
    not be able to fail an action it only observes.
    """
    if _audit_dir is None or not selection_id:
        return
    try:
        _append_selection_audit(
            {
                "kind": PUBLISH_RECORD_KIND,
                "ts": now_iso("seconds"),
                "selection_id": selection_id,
                "comment_id": comment_id or None,
                "publish_status": publish_status,
                "http_status": _recorded_http_status(http_status),
                "failure_reason": _recorded_failure_reason(failure_reason),
            }
        )
    except OSError as exc:
        logger.warning("skill selection: publish outcome not recorded (%s)", exc)


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
    log; ``selection_metrics.observed_injection_outcomes()`` aggregates that
    for a run. Naming
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


def selected_skills_block(selected: tuple[str, ...]) -> str:
    """Concatenated bodies of the selected skills, for pass-2 injection.

    Shares the traversal (``text_utils.iter_markdown_documents``) and the
    identity derivation (``skill_theme`` + the same name scrub) with
    :func:`load_skill_catalog` — the selector's catalog and this filter must
    agree on skill identity, so the key is derived by one expression, below.
    Body guards (frontmatter strip + forbidden-pattern validation) mirror the
    full-corpus loader in ``llm.prompting._load_md_files``. A selected name
    with no matching file (adopt/stocktake raced the selection) is logged and
    skipped, never fatal. Empty selection returns "" (ADR-0081: a judged-empty
    selection injects no skill bodies).
    """
    if not selected:
        return ""
    wanted = {name.lower() for name in selected}
    found: set[str] = set()
    bodies: list[str] = []
    for path, text in iter_markdown_documents(_skills_dir, label=_UNREADABLE_SKILL_LOG):
        name, _ = skill_theme(text, fallback_name=path.stem)
        key = _catalog_key(name)
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
    """Selection entry point for callers that do not publish.

    Thin wrapper over :func:`observe_skill_selection_recorded` keeping the
    pre-RFC-0028 return: the selection alone. Callers that go on to publish
    use the recorded form instead, because they need the id that links the
    selection record to the comment it became.
    """
    return observe_skill_selection_recorded(situation, generation_caller=generation_caller).selected


def observe_skill_selection_recorded(
    situation: str, *, generation_caller: str
) -> SelectionObservation:
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

    Returns a :class:`SelectionObservation`: the selection plus the
    ``selection_id`` under which it was recorded (``None`` when nothing was
    recorded — kill switch or internal failure), which the publish path
    hands back to :func:`record_publish_outcome`.
    """
    if _audit_dir is None:
        return SelectionObservation(selected=None, selection_id=None)
    selection_id = uuid.uuid4().hex
    try:
        catalog = load_skill_catalog(_skills_dir)
        base: dict[str, Any] = {
            "kind": SELECTION_RECORD_KIND,
            "selection_id": selection_id,
            "ts": now_iso("seconds"),
            "generation_caller": generation_caller,
            "catalog_count": len(catalog),
            "catalog_names": sorted(e.name for e in catalog),
            # Placeholders, always null here: the comment this generation
            # becomes does not exist yet. The values live in the matching
            # ``publish`` record (RFC-0028) — this pair is here so a reader
            # of one record can see that the fields exist and where they get
            # filled, rather than discovering the second family by accident.
            "comment_id": None,
            "publish_status": None,
        }

        def _abstain(verdict: str, full_skill_tokens: int) -> SelectionObservation:
            """Record a pre-judgment abstain: nothing selected, nothing enforced.

            The two abstains differ only in the verdict and in whether a
            catalog existed to price, so the record's zero-valued shape is
            written once.

            ``temperature`` is null here because these abstains return
            before the call site is reached, so there is no configured call
            to report — the same rule the novelty judge's
            ``fail_open_budget`` follows (RFC-0042).
            """
            _append_selection_audit(
                {
                    **base,
                    "verdict": verdict,
                    "enforced": False,
                    "temperature": None,
                    "selected": [],
                    "selected_count": 0,
                    "rejected_names": [],
                    "full_skill_tokens": full_skill_tokens,
                    "would_be_skill_tokens": 0,
                    # Null, not absent: these abstains return before the
                    # selection call, so no judge was asked either (ADR-0112).
                    **_null_decision_fields(),
                    **_b64_fields("prompt", None),
                    **_b64_fields("output", None),
                }
            )
            return SelectionObservation(selected=None, selection_id=selection_id)

        if not catalog:
            return _abstain("empty_catalog", 0)
        if not _load_selection_template():
            return _abstain("no_template", sum(e.body_tokens for e in catalog))
        result = select_applicable_skills(situation, catalog)
        # ADR-0081: only a judged verdict feeds back into injection; every
        # fail-open path stays full injection. The rollout flag that used to
        # co-gate this retired on 2026-08-08.
        enforced = result.verdict == "judged"
        # ADR-0112: the second judge runs here, after the live selection has
        # been decided and before the row is written. It returns record fields
        # only — nothing it says can reach ``selected``.
        decision_fields = _shadow_decision(situation, catalog, result)
        by_name = {e.name: e.body_tokens for e in catalog}
        _append_selection_audit(
            {
                **base,
                "verdict": result.verdict,
                "enforced": enforced,
                # The temperature this selection was configured to run at
                # (RFC-0044) — not proof that a request was sent. Both
                # fail-open verdicts land here, and ``generate`` can return
                # None without sending anything (open breaker, audit-C2
                # context budget), which this module can only see as
                # ``fail_open_llm``; ``llm-calls-*.jsonl`` holds one row per
                # actual attempt. Written per record because this log spans
                # both regimes and a reading must separate them by the row,
                # not by the date; absence means the pre-2026-09-20 default
                # of 1.0.
                "temperature": _SELECTION_TEMPERATURE,
                "selected": list(result.selected),
                "selected_count": len(result.selected),
                "rejected_names": list(result.rejected_names),
                # Baked in at record time: the catalog changes under
                # adopt/stocktake, so a report-time recomputation could not
                # replay what the reduction would have been for this action.
                "full_skill_tokens": sum(e.body_tokens for e in catalog),
                "would_be_skill_tokens": sum(by_name[name] for name in result.selected),
                **decision_fields,
                **_b64_fields("prompt", result.prompt),
                **_b64_fields("output", result.raw_output),
            }
        )
        return SelectionObservation(
            selected=result.selected if enforced else None, selection_id=selection_id
        )
    except Exception as exc:
        logger.warning(
            "skill selection shadow observation failed (generation unaffected): %s",
            exc,
        )
        # No id either: the failure may have preceded the record, and a
        # publish record pointing at a selection that was never logged is
        # worse than no link at all.
        return SelectionObservation(selected=None, selection_id=None)

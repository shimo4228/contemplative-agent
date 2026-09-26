"""The relevance gate's record, with a 4-level Score read beside it (RFC-0046 / ADR-0113).

One row per live relevance judgment in ``logs/relevance-{date}.jsonl``: what
the live gate scored and decided, and — when the decision backend is
configured for the ``relevance`` face — what the same model says when asked
the 4-level Score (``core.relevance_state``) and read through first-token
logprobs instead of writing a number. Observe-only (ADR-0076's shape): the
function returns nothing, the live score, threshold and gate are passed in
already decided, and every failure degrades to a named reason in the row.

The row is written whether or not the backend is configured (decision fields
null, ``decision_reason: "unconfigured"``): the live half is the replayable
relevance record ADR-0075 asked for and the gate never had. Leaving
``audit_dir`` unset — the default — disables the recorder outright, which is
its kill switch; the backend's is ``DECISION_MODEL`` + ``DECISION_FACES``.

The state's ``domain`` is identity + axioms
(``core.relevance_state.production_domain_text``, RFC-0046) and every row
names it in ``domain_source``.

The post body is stored only as ``content_b64`` + digest (``b64_audit_fields``),
the same form ``submolt-scope`` uses: a Claude Code session reading this log
meets no plaintext from another agent.

**Enforce-first (RFC-0046 / RFC-0047 Tier L).** When ``DECISION_ENFORCE``
names ``relevance`` and ``domain.relevance_threshold_score4`` is set, the
answered read decides the gate: ``P(directly on-topic) >= threshold``.
:func:`enforce_and_record` returns that outcome to the feed; the free-generated
live score is still asked and lands in the same row (paired), so every row
says which gate acted (``gate_source``) and, whenever it was the live one while
enforce was asked for, why (``enforce_reason`` — no silent fallback, ADR-0075).
Only the gate comparison moves: the engage bar, upvote-only and the note stay
on the live score's scale. The enforce kill switch is ``DECISION_ENFORCE``
absent; it is independent of the recorder's (``audit_dir``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...core._io import append_jsonl_restricted, b64_audit_fields, now_iso, strip_to_printable
from ...core.llm import (
    DECISION_FACE_RELEVANCE,
    REASON_ANSWERED,
    decide,
    decision_backend_name,
    decision_enforce_enabled,
    decision_face_enabled,
)
from ...core.relevance_state import (
    DOMAIN_SOURCE_PRODUCTION,
    TOP_LEVEL,
    build_state,
    production_domain_text,
    score4_question,
    state_text,
)
from .llm_functions import RelevanceScore

logger = logging.getLogger(__name__)

LOG_PREFIX = "relevance-"
# Telemetry caller tag: the shadow's calls stay separable from the live
# ``moltbook.score_relevance`` rows in llm-calls.
DECISION_CALLER = "moltbook.relevance_shadow"
# The same byte cap submolt-scope gives the same kind of text.
_MAX_POST_AUDIT_BYTES = 8192
_POST_ID_MAX_CHARS = 64

_DECISION_FIELDS: tuple[str, ...] = (
    "decision_backend",
    "decision_model",
    "decision_reason",
    "decision_p",
    "decision_p_top",
    "decision_expected_level",
    "decision_latency_ms",
)

# Why the gate that acted is the one it is. Closed: ``enforced`` is the only
# value with ``gate_source == "score4"``; each other names one missing piece
# and means the live gate acted.
ENFORCE_ENFORCED = "enforced"
ENFORCE_UNCONFIGURED = "enforce_unconfigured"  # DECISION_ENFORCE lacks relevance
ENFORCE_NO_THRESHOLD = "enforce_no_threshold"  # domain has no relevance_score4
# The decision was not answered; the row's ``decision_reason`` says how.
ENFORCE_BACKEND_NULL = "enforce_backend_null"
ENFORCE_EXCEPTION = "enforce_exception"  # resolving the outcome raised
ENFORCE_REASONS: tuple[str, ...] = (
    ENFORCE_ENFORCED,
    ENFORCE_UNCONFIGURED,
    ENFORCE_NO_THRESHOLD,
    ENFORCE_BACKEND_NULL,
    ENFORCE_EXCEPTION,
)
GATE_SOURCE_LIVE = "live"
GATE_SOURCE_SCORE4 = "score4"


@dataclass(frozen=True)
class EnforceOutcome:
    """Which gate acted on one post, and why. ``enforce_gate`` is None unless enforced."""

    gate_source: str
    enforce_gate: bool | None
    enforce_reason: str
    enforce_threshold: float | None

    def fields(self) -> dict[str, Any]:
        return {
            "gate_source": self.gate_source,
            "enforce_gate": self.enforce_gate,
            "enforce_reason": self.enforce_reason,
            "enforce_threshold": self.enforce_threshold,
        }


LIVE_UNCONFIGURED = EnforceOutcome(GATE_SOURCE_LIVE, None, ENFORCE_UNCONFIGURED, None)

_audit_dir: Path | None = None


def configure_relevance_shadow(audit_dir: Path | None = None) -> None:
    """Point the recorder at a log directory. ``None`` leaves it off."""
    global _audit_dir
    _audit_dir = audit_dir


def reset_relevance_shadow() -> None:
    global _audit_dir
    _audit_dir = None


def _null_decision(reason: str) -> dict[str, Any]:
    fields: dict[str, Any] = {name: None for name in _DECISION_FIELDS}
    fields["decision_reason"] = reason
    return fields


def _shadow_decision(content: str) -> dict[str, Any]:
    """Ask the 4-level Score once; the decision half of the row.

    Its own handler: anything raised while building the question or the state
    (an unparseable home override of the prompt, say) or while reading the
    answer (a distribution shorter than the levels) is this instrument's
    failure, recorded as ``backend_exception`` — never the live gate's, and it
    leaves an enforce request on the live gate (``enforce_backend_null``).
    """
    if not decision_face_enabled(DECISION_FACE_RELEVANCE):
        return _null_decision("unconfigured")
    try:
        return _read_decision(content)
    except Exception as exc:
        logger.warning("relevance shadow failed (gate unaffected): %s", exc)
        return _null_decision("backend_exception")


def _read_decision(content: str) -> dict[str, Any]:
    question = score4_question()
    state = state_text(build_state(production_domain_text(), content))
    result = decide(state, (question,), caller=DECISION_CALLER, system="")
    if result is None:
        # No backend: nothing was sent and nothing was timed.
        return _null_decision("unconfigured")
    fields = _null_decision(result.reason)
    fields["decision_backend"] = decision_backend_name()
    fields["decision_model"] = result.model
    fields["decision_latency_ms"] = result.latency_ms
    answer = result.answers[0] if result.answers else None
    if answer is not None and answer.reason == REASON_ANSWERED:
        probabilities = [round(p, 6) for _level, p in answer.probabilities]
        expected = answer.expected_level()
        fields["decision_p"] = probabilities
        fields["decision_p_top"] = probabilities[TOP_LEVEL]
        fields["decision_expected_level"] = round(expected, 6) if expected is not None else None
    return fields


def _resolve(decision: dict[str, Any], threshold: float | None) -> EnforceOutcome:
    if not decision_enforce_enabled(DECISION_FACE_RELEVANCE):
        return LIVE_UNCONFIGURED
    if threshold is None:
        return EnforceOutcome(GATE_SOURCE_LIVE, None, ENFORCE_NO_THRESHOLD, None)
    p_top = decision.get("decision_p_top")
    if (
        decision.get("decision_reason") != REASON_ANSWERED
        or isinstance(p_top, bool)
        or not isinstance(p_top, (int, float))
    ):
        return EnforceOutcome(GATE_SOURCE_LIVE, None, ENFORCE_BACKEND_NULL, threshold)
    return EnforceOutcome(GATE_SOURCE_SCORE4, p_top >= threshold, ENFORCE_ENFORCED, threshold)


def resolve_enforce(decision: dict[str, Any], threshold: float | None) -> EnforceOutcome:
    """The enforce outcome for one decision half of a row. Never raises.

    Anything raised here degrades to the live gate with ``enforce_exception``:
    an enforce failure must not stop the post being judged at all.
    """
    try:
        return _resolve(decision, threshold)
    except Exception as exc:
        logger.warning("relevance enforce failed (live gate acts): %s", exc)
        kept = threshold if isinstance(threshold, (int, float)) else None
        return EnforceOutcome(GATE_SOURCE_LIVE, None, ENFORCE_EXCEPTION, kept)


def enforce_and_record(
    post_id: str,
    content: str,
    *,
    live: RelevanceScore,
    threshold: float,
    author_known: bool,
    threshold_score4: float | None,
) -> EnforceOutcome:
    """Decide which gate acts on this post, and write its row. Never raises.

    The 4-level question is asked when the row will be written (the recorder
    is on) or when enforce is asked for — otherwise nothing is sent, the same
    as before enforce existed. The row's ``live_gate`` is always the live
    comparison, whichever gate acted.
    """
    recording = _audit_dir is not None
    if not recording and not decision_enforce_enabled(DECISION_FACE_RELEVANCE):
        return LIVE_UNCONFIGURED
    decision = _shadow_decision(content)
    outcome = resolve_enforce(decision, threshold_score4)
    if recording:
        _write_row(
            post_id,
            content,
            live=live,
            threshold=threshold,
            gate=live.score >= threshold,
            author_known=author_known,
            decision=decision,
            outcome=outcome,
        )
    return outcome


def observe_relevance_recorded(
    post_id: str,
    content: str,
    *,
    live: RelevanceScore,
    threshold: float,
    gate: bool,
    author_known: bool,
) -> None:
    """Record one live relevance judgment, and the shadow read beside it.

    Observe-only: called after the live gate decided, with its result; returns
    nothing the caller could act on. The enforce fields say the live gate acted
    (the resolution a caller would have got, with no threshold to cut at).
    Never raises.
    """
    if _audit_dir is None:
        return
    decision = _shadow_decision(content)
    _write_row(
        post_id,
        content,
        live=live,
        threshold=threshold,
        gate=gate,
        author_known=author_known,
        decision=decision,
        outcome=resolve_enforce(decision, None),
    )


def _write_row(
    post_id: str,
    content: str,
    *,
    live: RelevanceScore,
    threshold: float,
    gate: bool,
    author_known: bool,
    decision: dict[str, Any],
    outcome: EnforceOutcome,
) -> None:
    """``run_id`` / ``session_id`` are stamped by the shared writer. Never raises."""
    if _audit_dir is None:
        return
    try:
        record: dict[str, Any] = {
            "ts": now_iso("seconds"),
            "post_id": strip_to_printable(post_id, _POST_ID_MAX_CHARS),
            "author_known": author_known,
            "live_score": live.score,
            "live_reason": live.reason,
            "threshold_applied": threshold,
            "live_gate": gate,
            # The definition the question is asked under (RFC-0046); rows
            # written before the field existed were identity alone.
            "domain_source": DOMAIN_SOURCE_PRODUCTION,
            **decision,
            **outcome.fields(),
            **b64_audit_fields("content", content, max_bytes=_MAX_POST_AUDIT_BYTES),
        }
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        append_jsonl_restricted(_audit_dir / f"{LOG_PREFIX}{date_str}.jsonl", record)
    except Exception as exc:
        logger.warning("relevance record not written (gate unaffected): %s", exc)

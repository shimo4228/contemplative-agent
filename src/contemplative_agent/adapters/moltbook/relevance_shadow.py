"""The relevance gate: a 4-level Score read and its record (RFC-0046 / ADR-0113).

One row per relevance reading in ``logs/relevance-{date}.jsonl``: what the
decision backend says when asked, for the ``relevance`` face, the 4-level
Score (``core.relevance_state``) read through first-token logprobs, and the
gate outcome that gives. Every failure degrades to a named reason in the row.

**One judge, fail-closed (RFC-0046 cleanup 2, owner decision 2026-10-07).**
The gate is ``P(directly on-topic) >= domain.relevance_threshold_score4`` and
it is the only relevance judgment the feed acts on: the comment, the upvote,
the pre-action note and the full-body fetch all follow it. The feed no longer
asks the free-generated 0-1 score (``score_relevance_detailed``), so a row
carries no ``live_*`` / ``threshold_applied`` / ``author_known`` field (rows
written before 2026-10-07 do). When the gate cannot answer —
``DECISION_ENFORCE`` lacks ``relevance``, the domain has no
``relevance_score4``, the decision was not ``answered``, or resolving raised —
the outcome is ``gate_source: "fail_closed"`` with ``enforce_gate`` null and
the cause in ``enforce_reason`` (no silent fallback, ADR-0075): the feed
engages with nothing that cycle and asks again on the next.

The row is written whether or not the backend is configured (decision fields
null, ``decision_reason: "unconfigured"``). Leaving ``audit_dir`` unset — the
default — disables the recorder, which is its kill switch; it is independent
of the gate.

The state's ``domain`` is identity + axioms
(``core.relevance_state.production_domain_text``, RFC-0046) and every row
names it in ``domain_source``.

The post body is stored only as ``content_b64`` + digest (``b64_audit_fields``),
the same form ``submolt-scope`` uses: a Claude Code session reading this log
meets no plaintext from another agent.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
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

logger = logging.getLogger(__name__)

LOG_PREFIX = "relevance-"
# Telemetry caller tag: the gate's calls stay separable from the
# ``moltbook.score_relevance`` rows (seed selection, submolt-scope) in llm-calls.
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

# Why the gate's outcome is what it is. Closed: ``enforced`` is the only value
# with ``gate_source == "score4"``; each other names one missing piece and
# means the gate failed closed.
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
# The reasons no answer can fix within a session: the configuration lacks a
# piece, so every post this session fails closed for the same cause.
CONFIGURATION_REASONS = frozenset({ENFORCE_UNCONFIGURED, ENFORCE_NO_THRESHOLD})
# Decision reasons that come from the post's own text, not from the backend,
# the batch or the configuration: the next post may well be answered, so the
# feed skips this one instead of ending the cycle. Every other reason
# (``circuit_open``, ``http_error``, ``budget_exceeded``, ``backend_exception``
# — which an outage also raises — ...) ends it.
POST_LEVEL_DECISION_REASONS = frozenset({"no_option_observed"})
GATE_SOURCE_SCORE4 = "score4"
# No answer to cut, so no verdict. Rows written before 2026-10-07 carry
# ``"live"`` here instead: the free-generated gate that acted then.
GATE_SOURCE_FAIL_CLOSED = "fail_closed"


@dataclass(frozen=True)
class EnforceOutcome:
    """The gate's outcome for one post, and why. ``enforce_gate`` is None unless enforced.

    None is "no verdict", never "judged and closed": the caller engages with
    nothing and does not memoize it, so the next cycle asks again.
    """

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


CLOSED_UNCONFIGURED = EnforceOutcome(GATE_SOURCE_FAIL_CLOSED, None, ENFORCE_UNCONFIGURED, None)


@dataclass(frozen=True)
class RecordedReading:
    """What :func:`enforce_and_record` decided, and the decision half it read.

    ``decision`` is the row's decision fields (``decision_reason``,
    ``decision_p_top`` ...), or None when the question was not asked
    (recorder and gate both off). The cross-session relevance cache
    (``relevance_cache``) remembers it, and re-derives ``outcome`` from it with
    :func:`resolve_enforce` at today's threshold.
    """

    outcome: EnforceOutcome
    decision: Mapping[str, Any] | None

    @property
    def post_level_failure(self) -> bool:
        """The gate failed closed for a reason tied to this post's text alone."""
        reason = self.decision.get("decision_reason") if self.decision is not None else None
        return (
            self.outcome.enforce_reason == ENFORCE_BACKEND_NULL
            and reason in POST_LEVEL_DECISION_REASONS
        )

    @property
    def p_top(self) -> float | None:
        """P(directly on-topic) when the decision answered, else None."""
        value = self.decision.get("decision_p_top") if self.decision is not None else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)


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
    answer (a distribution shorter than the levels) is recorded as
    ``backend_exception``, and the gate then fails closed
    (``enforce_backend_null``).
    """
    if not decision_face_enabled(DECISION_FACE_RELEVANCE):
        return _null_decision("unconfigured")
    try:
        return _read_decision(content)
    except Exception as exc:
        logger.warning("relevance read failed (the gate fails closed): %s", exc)
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


def _resolve(decision: Mapping[str, Any], threshold: float | None) -> EnforceOutcome:
    if not decision_enforce_enabled(DECISION_FACE_RELEVANCE):
        return CLOSED_UNCONFIGURED
    if threshold is None:
        return EnforceOutcome(GATE_SOURCE_FAIL_CLOSED, None, ENFORCE_NO_THRESHOLD, None)
    p_top = decision.get("decision_p_top")
    if (
        decision.get("decision_reason") != REASON_ANSWERED
        or isinstance(p_top, bool)
        or not isinstance(p_top, (int, float))
    ):
        return EnforceOutcome(GATE_SOURCE_FAIL_CLOSED, None, ENFORCE_BACKEND_NULL, threshold)
    return EnforceOutcome(GATE_SOURCE_SCORE4, p_top >= threshold, ENFORCE_ENFORCED, threshold)


def resolve_enforce(decision: Mapping[str, Any], threshold: float | None) -> EnforceOutcome:
    """The gate outcome for one decision half of a row. Never raises.

    Anything raised here fails closed with ``enforce_exception``: the post is
    not engaged this cycle, and the session goes on.
    """
    try:
        return _resolve(decision, threshold)
    except Exception as exc:
        logger.warning("relevance gate failed (fails closed): %s", exc)
        kept = threshold if isinstance(threshold, (int, float)) else None
        return EnforceOutcome(GATE_SOURCE_FAIL_CLOSED, None, ENFORCE_EXCEPTION, kept)


def enforce_and_record(
    post_id: str,
    content: str,
    *,
    threshold_score4: float | None,
) -> RecordedReading:
    """The gate outcome for this post, and its row. Never raises.

    The 4-level question is asked when the row will be written (the recorder
    is on) or when the gate is on (``DECISION_ENFORCE`` names ``relevance``).
    With both off nothing is sent and the outcome fails closed
    (``enforce_unconfigured``).
    """
    recording = _audit_dir is not None
    if not recording and not decision_enforce_enabled(DECISION_FACE_RELEVANCE):
        return RecordedReading(CLOSED_UNCONFIGURED, None)
    decision = _shadow_decision(content)
    outcome = resolve_enforce(decision, threshold_score4)
    if recording:
        _write_row(post_id, content, decision=decision, outcome=outcome)
    return RecordedReading(outcome, decision)


def _write_row(
    post_id: str,
    content: str,
    *,
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

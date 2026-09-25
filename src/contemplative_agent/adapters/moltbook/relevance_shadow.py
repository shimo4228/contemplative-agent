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

The post body is stored only as ``content_b64`` + digest (``b64_audit_fields``),
the same form ``submolt-scope`` uses: a Claude Code session reading this log
meets no plaintext from another agent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...core._io import append_jsonl_restricted, b64_audit_fields, now_iso, strip_to_printable
from ...core.llm import (
    DECISION_FACE_RELEVANCE,
    REASON_ANSWERED,
    decide,
    decision_backend_name,
    decision_face_enabled,
    get_identity_text,
)
from ...core.relevance_state import TOP_LEVEL, build_state, score4_question, state_text
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
    (an unparseable home override of the prompt, say) is this instrument's
    failure, recorded as ``backend_exception`` — never the live gate's.
    """
    if not decision_face_enabled(DECISION_FACE_RELEVANCE):
        return _null_decision("unconfigured")
    try:
        question = score4_question()
        state = state_text(build_state(get_identity_text(), content))
        result = decide(state, (question,), caller=DECISION_CALLER, system="")
    except Exception as exc:
        logger.warning("relevance shadow failed (gate unaffected): %s", exc)
        return _null_decision("backend_exception")
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

    Called after the live gate decided, with its result; returns nothing the
    caller could act on. ``run_id`` / ``session_id`` are stamped by the shared
    writer. Never raises.
    """
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
            **_shadow_decision(content),
            **b64_audit_fields("content", content, max_bytes=_MAX_POST_AUDIT_BYTES),
        }
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        append_jsonl_restricted(_audit_dir / f"{LOG_PREFIX}{date_str}.jsonl", record)
    except Exception as exc:
        logger.warning("relevance record not written (gate unaffected): %s", exc)

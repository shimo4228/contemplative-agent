"""What the Maintainer and the Proposer loops share (RFC-0017 S2/S3).

Both are the same machine with different inputs: one generation per turn under
a per-turn JSON Schema, a JSON answer that either names an action or costs the
turn, and an audit row per turn carrying the prompt and the raw output as
base64 + sha256. Extracted when the Proposer arrived rather than guessed at in
S2, so what lives here is what two callers actually needed.

What deliberately did NOT move: the schemas (their enums are each loop's own
state), the turn dispatch (the actions differ), and the run records (the two
runs answer different questions). A shared driver over two different action
sets would be a switch on the caller, which is the shape this split exists to
avoid.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, TypeAlias

from . import llm
from ._io import append_jsonl_restricted, b64_audit_fields, now_iso

logger = logging.getLogger(__name__)


# Same cap and encoding as ``insight-novelty.jsonl``: one replay format across
# the audit writers, so a harness that reads one reads all of them.
MAX_AUDIT_BYTES = 131072

# Room for the model's answer. A turn can carry a whole skill body, so this is
# the order of the insight extraction call (``num_predict=3000``) rather than
# the few hundred tokens a classification answer needs.
OUTPUT_RESERVE = 3000

FailClosed: TypeAlias = Literal[
    "fail_closed_llm",
    "fail_closed_parse",
    "fail_closed_truncated",
]


class TurnFault(Exception):
    """A turn the code refuses. Carries the outcome the run ends with."""

    def __init__(self, outcome: FailClosed) -> None:
        super().__init__(outcome)
        self.outcome: FailClosed = outcome


def looks_cut_off(text: str) -> bool:
    """Did this unparseable answer stop mid-object rather than start wrong?

    Under ``format=`` the answer is a JSON object, so a complete one ends with
    ``}``; an answer that opens one and never closes it hit the output budget.

    A shape check, not a signal: ``done_reason == "length"`` is the real
    evidence and the ``generate_full`` seam does not surface it. This
    distinguishes the two common cases correctly and, when it is wrong, is
    wrong between two fail-closed codes — the run aborts either way, only the
    label differs.
    """
    stripped = text.strip()
    return stripped.startswith("{") and not stripped.endswith("}")


def parse_turn(raw: str) -> dict[str, Any]:
    """Parse one turn's answer, or raise the fail-closed outcome it earns.

    Valid JSON of the wrong shape is ``fail_closed_parse``, not a silently
    ignored turn: a top-level array or string means the constrained decoder
    did not apply, which is a different world from the one every enum in the
    schema assumes.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.startswith("```")).strip()
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TurnFault(
            "fail_closed_truncated" if looks_cut_off(text) else "fail_closed_parse"
        ) from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("action"), str):
        raise TurnFault("fail_closed_parse")
    return parsed


def call_turn(prompt: str, system: str, schema: dict[str, Any], reserve: int, caller: str) -> str:
    """One generation, or the fail-closed outcome it earns.

    ``drop_truncated=False`` on purpose: ``True`` collapses a cut answer into
    the same ``None`` a dead backend returns, and a run that hit its output
    budget needs a different reason code from one whose backend died — the
    first is a budget to raise, the second is a service to restart. The
    truncated text is never *used*, only classified, and the run then ends
    without applying anything.
    """
    out = llm.generate_full(
        prompt,
        system=system,
        num_predict=reserve,
        format=schema,
        caller=caller,
        think=True,
        drop_truncated=False,
    )
    if out is None or out.text is None:
        raise TurnFault("fail_closed_llm")
    return out.text


def audit_b64(name: str, text: str | None) -> dict[str, Any]:
    """Bind the shared replay encoder to this family's byte cap."""
    return b64_audit_fields(name, text, max_bytes=MAX_AUDIT_BYTES)


def append_audit(path: Path, record: dict[str, Any]) -> None:
    """Best-effort audit append. A lost row must not change what ran."""
    try:
        append_jsonl_restricted(path, record)
    except OSError:
        logger.warning("wiki loop: failed to append an audit row (kind=%s)", record.get("kind"))


def append_turn_audit(
    path: Path, *, step: int, prompt: str, raw: str | None, action: str | None
) -> None:
    """One turn's replay row: what was asked, what came back, what it meant."""
    record: dict[str, Any] = {
        "kind": "turn",
        "ts": now_iso(timespec="seconds"),
        "step": step,
        "action": action,
    }
    record.update(audit_b64("prompt", prompt))
    record.update(audit_b64("output", raw))
    append_audit(path, record)

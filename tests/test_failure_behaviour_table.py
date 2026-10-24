"""The failure-behaviour table in docs/CONFIGURATION.md (P1-07.1).

Every reason code it names must exist in a vocabulary the code owns: a
``<field>=<value>`` code names a field some registered census log reads as an
enum, and its value is drawn from the code-side closed set when there is one.
A bare code is an api-audit row key the client writes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _census_registry as reg  # type: ignore[import-not-found]  # noqa: E402

from contemplative_agent.adapters.moltbook.relevance_gate import ENFORCE_REASONS  # noqa: E402
from contemplative_agent.core.llm import DECISION_REASONS  # noqa: E402

DOC = ROOT / "docs" / "CONFIGURATION.md"

# llm-calls ``outcome`` values the generation / embedding paths stamp.
OUTCOMES = {"ok", "error", "empty", "circuit_open", "budget_exceeded",
            "truncated_dropped", "truncated_kept"}
VALUES = {
    "decision_reason": set(DECISION_REASONS),
    "enforce_reason": set(ENFORCE_REASONS),
    "outcome": OUTCOMES,
}
# Keys client.py writes into an api-audit row (checked against its source).
ROW_KEYS = {"transport_error", "soft_fail"}


def _section() -> str:
    text = DOC.read_text(encoding="utf-8")
    start = text.index("## Failure Behaviour")
    return text[start : text.index("\n## ", start + 5)]


def _codes() -> list[str]:
    rows = [ln for ln in _section().splitlines() if ln.startswith("| ")][2:]
    assert len(rows) >= 12
    out: list[str] = []
    for row in rows:
        cell = row.split("|")[4]
        out += re.findall(r"`([^`]+)`", cell)
    return out


def test_table_covers_the_five_surfaces_and_the_three_edge_rows():
    sec = _section()
    for surface in ("decision", "generation", "embedding", "Moltbook read", "Moltbook write"):
        assert f"| {surface}" in sec
    for edge in ("3xx", "non-JSON", "success:false"):
        assert edge in sec


def test_every_reason_code_exists_in_a_code_side_vocabulary():
    enum_fields = {f for e in reg.REGISTRY for f in e.enum_fields}
    client_src = (ROOT / "src/contemplative_agent/adapters/moltbook/client.py").read_text()
    codes = _codes()
    assert codes
    for code in codes:
        if "=" in code:
            field, value = code.split("=", 1)
            assert field in enum_fields, code
            if field in VALUES:
                assert value in VALUES[field], code
        elif code in ROW_KEYS:
            assert f'"{code}"' in client_src, code
        else:
            assert code in enum_fields, code

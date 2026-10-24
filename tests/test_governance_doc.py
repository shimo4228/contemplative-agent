"""docs/GOVERNANCE.md is the page the rest of the repository points at (P1-12.7).

It is read by code (the approver registry in ``value_layer_approval_join.py``)
and cited by other documents, so its load-bearing facts are pinned: the
Accountable-operator line, a filled cell in every class row, the record
locations, and that the retired private ``human-gate.md`` is no longer the
reference.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "GOVERNANCE.md"

sys.path.insert(0, str(REPO / "scripts"))
import value_layer_approval_join as vlaj  # noqa: E402  # pyright: ignore[reportMissingImports]

CLASS_ROWS = (
    "Value layer",
    "`config/prompts`",
    "`.claude`",
    "`scripts/weekly-*`",
    "`src`",
    "`tests`",
    "`docs/adr`",
    "`rfcs`",
    "Data repo",
)


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_the_accountable_operator_line_is_the_registry():
    names = vlaj.load_registered(DOC, [])
    assert names == frozenset({"tatsuya shimomoto"})
    assert re.search(r"^Accountable operator: .+since 2026-03-07\.$", _text(), re.MULTILINE)


def test_every_artifact_class_row_has_every_cell_filled():
    rows = [ln for ln in _text().splitlines() if ln.startswith("| **")]
    for cls in CLASS_ROWS:
        (row,) = [r for r in rows if cls in r.split("|")[1]]
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        assert len(cells) == 8, row
        assert all(cells), row
    # A row that is not public says why (here: only parts of the value layer stay home).
    value_layer = next(r for r in rows if "Value layer" in r)
    assert "stay home" in value_layer


def test_the_aap_column_and_the_dated_mapping_reference_exist():
    text = _text()
    assert "| AAP ADR |" in text
    assert "docs/policy-mapping/eu-ai-act.md` (read 2026-08-04" in text


def test_the_records_table_names_api_audit_and_the_chain():
    text = _text()
    assert "logs/api-audit.jsonl" in text
    assert "never rotated" in text
    assert "`prev` chain" in text


def test_the_three_gate_rules_are_transcribed():
    text = _text()
    for phrase in (
        "One job, one gate",
        "An inspector is not an approver",
        "Escalation is available",
    ):
        assert phrase in text


def test_cycles_points_here_and_carries_the_three_columns():
    cycles = (REPO / "docs" / "CYCLES.md").read_text(encoding="utf-8")
    assert "[GOVERNANCE.md](GOVERNANCE.md)" in cycles
    header = next(ln for ln in cycles.splitlines() if ln.startswith("| # | Cycle |"))
    assert header.rstrip().endswith("| Approver | Record | Public? |")


def test_no_adr_or_skill_cites_the_retired_private_gate_page():
    offenders = []
    for base in (REPO / "docs" / "adr", REPO / ".claude"):
        for path in base.rglob("*.md"):
            if "human-gate.md" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(REPO)))
    assert offenders == []

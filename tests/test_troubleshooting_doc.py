"""docs/TROUBLESHOOTING.md quotes every non-ok line `doctor` can print (P1-09.17).

The check reads `cli/doctor.py` as source: each ``Finding(WARN|FAIL, "<check>",
<detail>)`` call must have a table line starting ``[ WARN ] <check>:`` (or
``[ FAIL ]``) that contains every literal fragment of ``<detail>`` that is at
least four characters long. A new or reworded finding without a row fails here.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCTOR = ROOT / "src" / "contemplative_agent" / "cli" / "doctor.py"
DOC = ROOT / "docs" / "TROUBLESHOOTING.md"

# Findings that cannot reach the operator: `canary_finding` configures the
# backend one line before it asks, so `decide()` returning None is a guard.
UNREACHABLE = {("Decision canary", ": no backend")}

_TAGS = {"WARN": "[ WARN ]", "FAIL": "[ FAIL ]"}


def _fragments(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        parts = [node.value]
    elif isinstance(node, ast.JoinedStr):
        parts = [
            v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
        ]
    else:
        raise AssertionError(f"unexpected detail node at line {node.lineno}")
    return [p for p in parts if len(p.strip()) >= 4]


def _non_ok_findings() -> list[tuple[str, str, list[str]]]:
    tree = ast.parse(DOCTOR.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Finding"
            and len(node.args) >= 3
        ):
            continue
        level = node.args[0]
        if not (isinstance(level, ast.Name) and level.id in _TAGS):
            continue
        check = node.args[1]
        assert isinstance(check, ast.Constant) and isinstance(check.value, str)
        found.append((level.id, check.value, _fragments(node.args[2])))
    return found


def test_doctor_has_non_ok_findings() -> None:
    # Guard against the parser silently finding nothing.
    assert len(_non_ok_findings()) >= 8


def test_every_non_ok_doctor_line_has_a_row() -> None:
    lines = DOC.read_text(encoding="utf-8").splitlines()
    missing = []
    for level, check, fragments in _non_ok_findings():
        prefix = f"{_TAGS[level]} {check}:"
        rows = [line for line in lines if line.startswith("|") and prefix in line]
        if not rows:
            missing.append(prefix)
            continue
        for fragment in fragments:
            if (check, fragment) in UNREACHABLE:
                continue
            if not any(fragment in row for row in rows):
                missing.append(f"{prefix} ...{fragment!r}")
    assert not missing, f"TROUBLESHOOTING.md lacks doctor lines: {missing}"

"""scripts/revise_table.py — the one-shot ADR-0111 revise table (P0-01.6)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "revise_table", Path(__file__).resolve().parent.parent / "scripts" / "revise_table.py"
)
assert _SPEC and _SPEC.loader
rt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rt)


def _row(kind="insight_naming", verdict="revise", **extra):
    return {"kind": kind, "verdict": verdict, "ts": "2026-10-03T08:01:02+00:00", **extra}


def test_only_revise_naming_rows_are_listed(tmp_path, capsys):
    log = tmp_path / "insight-stages.jsonl"
    rows = [
        _row(target_skill="skill-a", change_reason="narrow it\x1b[31m | now"),
        _row(verdict="new"),
        _row(kind="insight_duplicate", verdict="duplicate"),
        _row(target_skill=None, change_reason="x", prompt_b64="SECRET"),
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\nbroken\n")
    assert rt.main(["--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "2 revise row(s)" in out
    assert "| 2026-10-03 | skill-a | narrow it [31m / now |" in out
    assert "\x1b" not in out
    assert "SECRET" not in out
    assert "(none)" in out


def test_absent_log_prints_an_empty_table(tmp_path, capsys):
    assert rt.main(["--log", str(tmp_path / "nope.jsonl")]) == 0
    assert "0 revise row(s)" in capsys.readouterr().out

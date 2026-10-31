"""Guard on the roadmap step of the weekly-gate skill (roadmap P2-01.10).

Step 1c reads `docs/plans/roadmap-2026-10/decisions.md` and records each
decision as a `gate_item category=roadmap` row. Two things can drift without
anyone noticing: the date lookup (the skill is run with `{end-date}`, a Friday,
while the table is keyed by the Saturday gate) and the field set of the
template, which the census reader (P2-01.1) will parse. Step 0 (d) decides
whether the quarterly T4 inventory is due; its one-line rule is checked here
against a synthetic metrics log.

The snippets are executed out of SKILL.md itself, so editing the skill and
forgetting the table (or the reverse) fails here.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / ".claude" / "skills" / "weekly-gate" / "SKILL.md"
DECISIONS = REPO_ROOT / "docs" / "plans" / "roadmap-2026-10" / "decisions.md"


def _snippet(marker: str) -> str:
    """The heredoc body that follows the line containing *marker*."""
    text = SKILL.read_text(encoding="utf-8")
    match = re.search(re.escape(marker) + r".*?<<'EOF'\n(.*?)\n\s*EOF", text, re.S)
    assert match, f"no heredoc after {marker!r} in SKILL.md"
    lines = match.group(1).splitlines()
    indent = min(len(line) - len(line.lstrip()) for line in lines if line.strip())
    return "\n".join(line[indent:] for line in lines)


def _run(code: str, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code, *args], check=True, capture_output=True, text=True
    )
    return result.stdout


def test_friday_end_date_finds_the_saturday_rows() -> None:
    out = _run(
        _snippet("python3 - docs/plans/roadmap-2026-10/decisions.md"), str(DECISIONS), "2026-10-16"
    )
    decided = re.findall(r"^decided \(do not re-ask\): ((?:D-|ROADMAP-)[\w-]+) = ", out, re.M)
    assert decided == [
        "ROADMAP-2026-10",
        "D-P0-01-2",
        "D-P0-02-1",
        "D-P0-02-2",
        "D-P1-04-1",
        "D-P3-04-2",
    ]
    assert out.splitlines()[0] == "gate 2026-10-17: 0 open roadmap decision(s), 6 already decided"


def test_a_2027_gate_is_keyed_with_its_year() -> None:
    out = _run(
        _snippet("python3 - docs/plans/roadmap-2026-10/decisions.md"), str(DECISIONS), "2027-01-08"
    )
    assert out.splitlines()[0] == "gate 2027-01-09: 0 open roadmap decision(s), 4 already decided"


def test_an_undecided_row_is_still_presented(tmp_path: Path) -> None:
    text = DECISIONS.read_text(encoding="utf-8")
    edited = tmp_path / "decisions.md"
    edited.write_text(
        text.replace("| D-P0-05-1 | A | 2026-10-24 |", "| D-P0-05-1 | 未決 | |"), encoding="utf-8"
    )
    out = _run(
        _snippet("python3 - docs/plans/roadmap-2026-10/decisions.md"), str(edited), "2026-11-06"
    )
    assert out.splitlines()[0] == "gate 2026-11-07: 1 open roadmap decision(s), 4 already decided"
    assert re.search(r"^\| 11-07 の土曜ゲート \| D-P0-05-1 \|", out, re.M)


def test_every_decision_has_a_record_row() -> None:
    text = DECISIONS.read_text(encoding="utf-8")
    asked = set(
        re.findall(r"^\| [^|]*(?:の土曜ゲート|2027-Q2) \| ((?:D-|ROADMAP-)[\w-]+) \|", text, re.M)
    )
    record = text[text.index("## 決定の記録") : text.index("## 遅れたとき")]
    rows = dict(re.findall(r"^\| ((?:D-|ROADMAP-)[\w-]+) \| ([^|]+?) \|", record, re.M))
    assert asked == set(rows)
    assert [i for i, d in rows.items() if d == "未決"] == ["D-P4-02-2"]


def test_every_decision_row_names_its_material() -> None:
    rows = [
        line
        for line in DECISIONS.read_text(encoding="utf-8").splitlines()
        if re.match(r"^\| [^|]+の土曜ゲート \| (D-|ROADMAP-)", line)
    ]
    assert len(rows) >= 99
    for row in rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        assert len(cells) == 6 and cells[5], row[:80]


def test_the_roadmap_gate_item_template_carries_the_field_set() -> None:
    text = SKILL.read_text(encoding="utf-8")
    step = text[text.index("### Step 1c.") : text.index("### Step 4.")]
    fields = set(re.findall(r"--field (\w+)=", step))
    assert {
        "category",
        "item",
        "recommendation",
        "decision",
        "recommender",
        "reason",
        "decided_at",
    } <= fields
    assert "--event roadmap_start" in step and "--event roadmap_end" in step


def _t4(tmp_path: Path, rows: list[dict], end_date: str) -> str:
    log = tmp_path / "pipeline-metrics.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return _run(_snippet("#### (d) 四半期の T4"), str(log), end_date).strip()


def test_t4_is_due_at_the_first_gate_of_a_quarter(tmp_path: Path) -> None:
    earlier = {"ts": "2026-09-26T05:00:00+00:00", "event": "gate_record", "t4_run": "1"}
    assert _t4(tmp_path, [earlier], "2026-10-16").startswith("T4: DUE")


def test_t4_is_not_due_twice_in_a_quarter(tmp_path: Path) -> None:
    rows = [
        {"ts": "2026-10-17T05:00:00+00:00", "event": "gate_record", "t4_run": "2"},
        {"ts": "2026-10-17T05:00:00+00:00", "event": "gate_item", "category": "roadmap"},
    ]
    assert _t4(tmp_path, rows, "2026-10-23") == "T4: done this quarter"

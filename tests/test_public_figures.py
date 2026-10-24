"""P3-05.11: figures from the public data only; the comment-report parser drops Context."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "public_figures", ROOT / "analysis" / "public_figures.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REPORT = """# Moltbook Activity Report — 2026-10-20

## Comments (1 total)

### 1. [2026-10-20 03:03:26] COMMENT · with Somebody · post 6c1846e4… · relevance P(top) 0.92

**Context:**
QUOTED THIRD-PARTY TEXT

**Internal note:**
note

**Output:**
reply

---
"""

LEGACY = """# Moltbook Activity Report — 2026-03-10

### 1. [2026-03-10 02:11:02] Post ID: a01f20f3-aba... (relevance: 1.00)

**Context:**
old quote
"""


def _mk(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


def _data(tmp_path: Path) -> Path:
    (tmp_path / "knowledge.json").write_text(
        json.dumps(
            [
                {"pattern": "a", "distilled": "2026-04-01T00:00+00:00"},
                {"pattern": "b", "distilled": "2026-04-02T00:00+00:00"},
                {"pattern": "c", "distilled": "2026-05-02T00:00+00:00"},
            ]
        ),
        encoding="utf-8",
    )
    reports = tmp_path / "reports" / "comment-reports"
    reports.mkdir(parents=True)
    (reports / "comment-report-2026-10-20.md").write_text(REPORT, encoding="utf-8")
    (reports / "comment-report-2026-03-10.md").write_text(LEGACY, encoding="utf-8")
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "x-20260725.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    return tmp_path


def test_parser_keeps_own_text_and_drops_context_and_counterparty() -> None:
    entries = _mod().parse_comment_report(REPORT)
    assert entries == [
        {
            "ts": "2026-10-20 03:03:26",
            "kind": "COMMENT",
            "post": "6c1846e4",
            "internal_note": "note",
            "output": "reply",
        }
    ]
    assert "QUOTED" not in json.dumps(entries) and "Somebody" not in json.dumps(entries)


def test_legacy_headers_are_counted_not_dropped() -> None:
    entries = _mod().parse_comment_report(LEGACY)
    assert [e["kind"] for e in entries] == ["LEGACY"]
    assert "old quote" not in json.dumps(entries)


def test_build_writes_three_svgs_with_the_plotted_numbers(tmp_path: Path) -> None:
    mod = _mod()
    data = _data(_mk(tmp_path))
    series = mod.build(data, tmp_path / "out")
    assert series["patterns-per-month"] == {"2026-04": 2, "2026-05": 1}
    assert series["comments-per-month"] == {"2026-03": 1, "2026-10": 1}
    assert series["skills-per-month"] == {"2026-07": 1}
    for name in series:
        svg = (tmp_path / "out" / f"{name}.svg").read_text(encoding="utf-8")
        assert svg.startswith("<svg") and "</svg>" in svg


def test_cli_exit_codes(tmp_path: Path) -> None:
    mod = _mod()
    data = _data(_mk(tmp_path))
    assert mod.main(["x", str(data), str(tmp_path / "o")]) == 0
    assert mod.main(["x", str(tmp_path / "nowhere"), str(tmp_path / "o")]) == 2
    assert mod.main(["x"]) == 2

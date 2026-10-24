"""P3-05.11: the DATACARD draft's runnable examples really run.

The data repo's DATACARD.md is hand-kept there (an rsync mirror would delete
anything else), so the text lives in ``docs/evidence/p3-05/data-repo/`` until
the owner applies it. These tests execute its "Loading" and id-formula code
blocks against a small fixture laid out like the data repo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "docs" / "evidence" / "p3-05" / "data-repo" / "DATACARD.md.draft"

REPORT = """# Moltbook Activity Report — 2026-10-20

## Comments (2 total)

### 1. [2026-10-20 03:03:26] COMMENT · with someone · post 6c1846e4… · relevance P(top) 0.92

**Context:**
THIRD-PARTY-QUOTE must never reach the parsed rows.

**Internal note:**
my note line one
my note line two

**Output:**
my reply

---

### 2. [2026-10-20 04:00:00] REPLY · with other · post aaaaaaaa… · relevance —

**Context:**
ANOTHER-QUOTE

**Output:**
second reply

---
"""


def _blocks(section_heading: str) -> list[str]:
    text = CARD.read_text(encoding="utf-8")
    start = text.index(section_heading)
    nxt = re.search(r"^#{2,3} ", text[start + len(section_heading) :], re.MULTILINE)
    body = text[start : start + len(section_heading) + (nxt.start() if nxt else len(text))]
    return re.findall(r"```python\n(.*?)```", body, re.DOTALL)


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    rows = [
        {"pattern": "a", "distilled": "2026-04-01T10:00+00:00", "valid_until": None},
        {
            "pattern": "b",
            "distilled": "2026-05-01T10:00+00:00",
            "valid_until": "2026-06-01T00:00+00:00",
        },
    ]
    (tmp_path / "knowledge.json").write_text(json.dumps(rows), encoding="utf-8")
    reports = tmp_path / "reports" / "comment-reports"
    reports.mkdir(parents=True)
    (reports / "comment-report-2026-10-20.md").write_text(REPORT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_card_has_the_seven_datasheet_sections() -> None:
    text = CARD.read_text(encoding="utf-8")
    headings = re.findall(r"^## (\d)\. (.+)$", text, re.MULTILINE)
    assert [h[1] for h in headings] == [
        "Motivation",
        "Composition",
        "Collection process",
        "Preprocessing, cleaning, labeling",
        "Uses",
        "Distribution",
        "Maintenance",
    ]


def test_pandas_example_runs(data_dir: Path, capsys) -> None:
    pytest.importorskip("pandas")
    block = _blocks("### Loading")[0]
    exec(block, {})
    assert capsys.readouterr().out.split() == ["2", "1"]


def test_polars_example_runs(data_dir: Path, capsys) -> None:
    pytest.importorskip("polars")
    block = _blocks("### Loading")[1]
    exec(block, {})
    assert capsys.readouterr().out.split() == ["2", "1"]


def test_comment_report_parser_drops_context(data_dir: Path, capsys) -> None:
    block = _blocks("### Loading")[2]
    ns: dict = {}
    exec(block, ns)
    out = capsys.readouterr().out.split()
    assert out == ["2", "REPLY"]
    parsed = ns["parse"](data_dir / "reports" / "comment-reports" / "comment-report-2026-10-20.md")
    flat = json.dumps(parsed)
    assert "THIRD-PARTY-QUOTE" not in flat and "ANOTHER-QUOTE" not in flat
    assert parsed[0]["internal_note"] == "my note line one\nmy note line two"
    assert parsed[0]["output"] == "my reply"


def test_id_formula_block_runs(data_dir: Path) -> None:
    block = next(b for b in _blocks("**Identity.**") if "sha256" in b)
    exec(block, {})

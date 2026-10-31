"""The incident runbook's reach table is a copy of the data repo NOTICE's (P4-03.3).

Until the data repository's NOTICE carries its "Third-party content & takedown"
section, the source is the drafted NOTICE hunk in
``docs/evidence/p3-05/data-repo/hand-kept-files.patch``. Rows and the first four
columns must agree; *Checked* is filled by the owner in both places.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNBOOK = REPO / "docs" / "runbooks" / "incident-response.md"
PATCH = REPO / "docs" / "evidence" / "p3-05" / "data-repo" / "hand-kept-files.patch"
HEADER = "| Surface | Remove or replace | Withdrawal request | Traces that remain | Checked |"


def _rows(lines: list[str]) -> list[tuple[str, ...]]:
    start = lines.index(HEADER)
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        cells = tuple(c.strip() for c in line.strip().strip("|").split("|"))
        rows.append(cells[:4])
    return rows


def _notice_rows() -> list[tuple[str, ...]]:
    text = PATCH.read_text(encoding="utf-8")
    notice = text.split("diff --git a/NOTICE b/NOTICE", 1)[1].split("\ndiff --git", 1)[0]
    lines = [ln[1:] for ln in notice.splitlines() if ln.startswith("+")]
    rows = _rows(lines)
    # In the NOTICE "this repository" is the data repository.
    return [(r[0].replace("this repository", "the data repository"), *r[1:]) for r in rows]


def test_reach_table_matches_the_notice_draft():
    runbook = _rows(RUNBOOK.read_text(encoding="utf-8").splitlines())
    assert runbook == _notice_rows()
    assert len(runbook) == 5


def test_reach_table_says_its_cells_are_unverified():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "external knowledge, unverified" in text

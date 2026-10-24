"""The ADR index tables are generated from the ADR bodies (P1-03.5, PR-A and the Last revised half of PR-C).

The index in ``docs/adr/README.md`` / ``README.ja.md`` was hand-written: 113 rows
x 2 faces that drifted from the bodies. ``scripts/adr_index.py`` now derives the
table from them, and this module is the single gate: the committed table must be
byte-for-byte what the script generates. Fixing a stale row therefore means
fixing the ADR body (or running the script), never editing the row.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import adr_index  # noqa: E402  # pyright: ignore[reportMissingImports]


@pytest.mark.unit
@pytest.mark.parametrize("readme,ja", [("README.md", False), ("README.ja.md", True)])
def test_committed_index_equals_generated(readme: str, ja: bool) -> None:
    path = REPO / "docs" / "adr" / readme
    assert path.read_text(encoding="utf-8") == adr_index.generated(path, ja), (
        f"docs/adr/{readme} differs from what scripts/adr_index.py generates — "
        f"run `python3 scripts/adr_index.py` and commit the result"
    )


@pytest.mark.unit
def test_check_mode_exits_zero_when_current_and_revised_since_prints_a_count() -> None:
    assert adr_index.main(["--check"]) == 0
    out = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "adr_index.py"), "--revised-since", "30"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0
    assert "ADR(s) revised in the last 30 days" in out.stdout


@pytest.mark.unit
def test_revised_since_counts_by_the_latest_dated_event() -> None:
    today = date(2026, 10, 24)
    inside = adr_index.revised_since(30, today)
    # ADR-0113's last Amendment is 2026-10-17; ADR-0001 was never revised.
    assert "0113" in inside
    assert "0001" not in inside
    assert adr_index.revised_since(3650, today) == sorted(adr_index._adr_files(".md"))


@pytest.mark.unit
def test_every_adr_has_a_row_with_the_same_date_as_its_body() -> None:
    rows = adr_index._rows(False)
    assert [r["adr"] for r in rows] == sorted(adr_index._adr_files(".md"))
    assert all(r["date"] and r["revised"] >= r["date"] for r in rows)


def _body(status: str, extra: str = "", date_line: str = "2026-01-01") -> str:
    return f"# ADR-0200: Title (withdrawn 2026-02-02)\n\n## Status\n\n{status}\n\n## Date\n\n{date_line}\n\n{extra}"


@pytest.mark.unit
@pytest.mark.parametrize(
    "status,extra,expected",
    [
        ("accepted", "", "accepted"),
        ("accepted (note) — narrow", "", "accepted (note)"),
        ("**withdrawn (2026-04-27)** — same day", "", "withdrawn (2026-04-27)"),
        (
            "accepted — supersedes ADR-0064 (MLX) and ADR-0006 (Docker); partially-supersedes [ADR-0065](./x.md) (a), partially-supersedes ADR-0067 (b)",
            "",
            "accepted — supersedes 0006, 0064; partially-supersedes 0065, 0067",
        ),
        (
            "partially-superseded-by ADR-0104 (x)",
            "## Amendment (2026-07-18): a\n\n## Amendment 2 (2026-09-19): b\n",
            "partially-superseded-by 0104 (amended 2026-07-18, 2026-09-19)",
        ),
        ("partially-superseded-by ADR-0067 (a); partially-superseded-by ADR-0070 (b)", "", "partially-superseded-by 0067, 0070"),
        ("accepted (amended 2026-08-29)", "", "accepted (amended 2026-08-29)"),
        ("accepted — extends [ADR-0066](./0066.md)", "**D3 amendment (2026-09-12, RFC-0029)** x\n", "accepted (amended 2026-09-12) — extends 0066"),
    ],
)
def test_status_cell_is_the_spine_of_the_body_status(status: str, extra: str, expected: str) -> None:
    assert adr_index.status_cell("0200", _body(status, extra)) == expected


@pytest.mark.unit
def test_last_revised_takes_the_latest_of_date_amendment_and_note() -> None:
    body = _body(
        "accepted",
        "> **Note (2026-03-05, ADR-0101 T4)**: x\n## Amendment (2026-02-01): y\n> **Note added 2026-04-09 (ADR-0111)**: z\n",
    )
    assert adr_index.last_revised(body) == "2026-04-09"
    assert adr_index.last_revised(_body("accepted")) == "2026-01-01"


@pytest.mark.unit
def test_title_drops_the_prefix_and_a_trailing_withdrawal_note() -> None:
    assert adr_index._title(_body("accepted")) == "Title"


@pytest.mark.unit
def test_akc_tags_are_kept_on_their_rows() -> None:
    by_adr = {r["adr"]: r["title"] for r in adr_index._rows(False)}
    assert by_adr["0004"].endswith("`[AKC: Extract/Curate/Promote]`")
    assert "[AKC" not in by_adr["0001"]

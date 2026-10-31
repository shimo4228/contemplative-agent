"""Tests for scripts/self_regulation_reading.py (P2-01.5 / .13).

The table is a reading, not a verdict: these pin the column definitions (what
counts as a ruling, what is separated as the roadmap's own execution), the
candidate and metabolism-floor lines, and that a week with no gate is never
read as a zero-load week.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _census_series as census_series  # type: ignore[import-not-found]  # noqa: E402
import self_regulation_reading as srr  # type: ignore[import-not-found]  # noqa: E402

END = date(2026, 10, 24)  # a Saturday, ISO week 2026-W43


def _w(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _ts(day: str, hhmm: str = "04:00") -> str:
    return f"{day}T{hhmm}:00+00:00"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "logs").mkdir()
    return tmp_path


def _by_label(table):
    return {w.label: w for w in table}


def _quiet_repo(tmp_path: Path) -> Path:
    """A checkout whose only commit is long before any window: drafts / outside read as 0."""
    repo = tmp_path / "quiet-repo"
    (repo / "rfcs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "rfcs" / "README.md").write_text("x")
    _git(repo, "add", "-A", when="2020-01-01T12:00:00+00:00")
    _git(repo, "commit", "-q", "-m", "chore: init", when="2020-01-01T12:00:00+00:00")
    return repo


def test_decision_fields_match_the_census_definition():
    assert srr.GATE_DECISION_FIELDS == census_series.GATE_DECISION_FIELDS


def test_rulings_minutes_and_the_roadmap_part_are_separated(home):
    _w(
        home / "logs" / "pipeline-metrics.jsonl",
        [
            {"ts": _ts("2026-10-17", "03:00"), "event": "gate_start"},
            {"ts": _ts("2026-10-17", "03:10"), "event": "roadmap_start"},
            {"ts": _ts("2026-10-17", "03:40"), "event": "roadmap_end"},
            {
                "ts": _ts("2026-10-17"),
                "event": "gate_item",
                "category": "roadmap",
                "recommendation": "A",
                "decision": "A",
            },
            {
                "ts": _ts("2026-10-17"),
                "event": "gate_item",
                "category": "roadmap",
                "item": "P2-01",
                "recommendation": "closed",
                "decision": "closed",
            },
            {
                "ts": _ts("2026-10-17", "05:00"),
                "event": "gate_record",
                "insight_adopted": "2",
                "insight_rejected": "1",
                "skills_archived": "0",
                "insight_held": "5",
            },
        ],
    )
    table, _ = srr.build(home, None, END, 8)
    w = _by_label(table)["2026-W42"]
    assert (w.rulings, w.rm_dec, w.rm_min, w.gate_min) == (3, 1, 30, 90)  # 120 - 30 roadmap


def test_a_week_without_a_gate_is_not_a_zero_load_week(home, tmp_path):
    _w(home / "logs" / "pipeline-metrics.jsonl", [])
    table, _ = srr.build(home, _quiet_repo(tmp_path), END, 8)
    line = srr.candidate(table, 8)
    assert "0 week(s)" in line and "not a candidate" in line
    assert "weeks with no gate_record: 7" in line  # the last week's gate is pending


def test_eight_zero_load_gates_declare_a_candidate(home, tmp_path):
    rows = [
        {"ts": _ts(d.isoformat()), "event": "gate_record", "insight_adopted": "0"}
        for d in (
            date(2026, 9, 5),
            date(2026, 9, 12),
            date(2026, 9, 19),
            date(2026, 9, 26),
            date(2026, 10, 3),
            date(2026, 10, 10),
            date(2026, 10, 17),
            date(2026, 10, 24),
        )
    ]
    _w(home / "logs" / "pipeline-metrics.jsonl", rows)
    table, _ = srr.build(home, _quiet_repo(tmp_path), END, 8)
    assert "self-regulating candidate" in srr.candidate(table, 8)


def test_the_candidate_abstains_when_a_load_source_was_not_read(home):
    rows = [
        {"ts": _ts((date(2026, 9, 5) + timedelta(days=7 * i)).isoformat()), "event": "gate_record"}
        for i in range(8)
    ]
    _w(home / "logs" / "pipeline-metrics.jsonl", rows)
    table, _ = srr.build(home, None, END, 8)  # no --repo: drafts / outside unread
    line = srr.candidate(table, 8)
    assert "reason=SELFREG_LOAD_UNREAD drafts, outside" in line
    assert "candidate verdict" in line and "self-regulating candidate" not in line


def test_friday_end_treats_the_unrun_saturday_gate_as_pending(home, tmp_path):
    friday = date(2026, 10, 23)
    sats = [date(2026, 8, 29) + timedelta(days=7 * i) for i in range(8)]
    assert sats[-1] == date(2026, 10, 17)
    rows = [
        {"ts": _ts(d.isoformat()), "event": "gate_record", "insight_adopted": "0"} for d in sats
    ]
    _w(home / "logs" / "pipeline-metrics.jsonl", rows)
    repo = _quiet_repo(tmp_path)
    table, _ = srr.build(home, repo, friday, 9)
    assert table[-1].pending
    table2, footer = srr.build(home, repo, friday, 9)
    assert "(gate pending)" in srr.render(table2, footer, 8)
    line = srr.candidate(table, 8)
    assert "self-regulating candidate" in line and "no gate_record: 0" in line
    assert "metabolism floor reached" in srr.floor(table)


def test_metabolism_floor_needs_eight_quiet_weeks_and_names_the_p4_event(home):
    table, _ = srr.build(home, None, END, 9)  # the gate-less last week is pending
    assert "metabolism floor reached" in srr.floor(table)
    _w(
        home / "logs" / "audit.jsonl",
        [
            {
                "ts": _ts("2026-10-17"),
                "command": "insight",
                "decision": "approved",
                "source": "stage-adopted-names",
            }
        ],
    )
    table, _ = srr.build(home, None, END, 9)  # the gate-less last week is pending
    assert "floor not reached" in srr.floor(table)


def test_empty_selection_has_an_interval_and_a_rejected_only_count(home):
    rows = [{"ts": _ts("2026-10-20"), "verdict": "judged", "selected": ["a"]} for _ in range(8)]
    rows += [{"ts": _ts("2026-10-20"), "verdict": "judged", "selected": []} for _ in range(4)]
    rows += [
        {"ts": _ts("2026-10-20"), "verdict": "judged", "selected": [], "rejected_names": ["x"]}
    ]
    rows += [{"ts": _ts("2026-10-20"), "kind": "publish", "verdict": "judged"}]  # not a selection
    _w(home / "logs" / "skill-selection-2026-10-20.jsonl", rows)
    table, footer = srr.build(home, None, END, 8)
    w = _by_label(table)["2026-W43"]
    assert (w.judged, w.empty, w.rejected_only) == (13, 4, 1)
    out = srr.render(table, footer, 8)
    assert "4/13 = 30.8% [" in out and "+1 rejected-only" in out


def test_intake_line_counts_four_weeks_and_pending(home):
    _w(
        home / "logs" / "insight-staged.jsonl",
        [{"ts": _ts("2026-10-20")}, {"ts": _ts("2026-08-01")}],
    )
    (home / ".staged").mkdir()
    (home / ".staged" / "a.meta.json").write_text("{}")
    _w(
        home / "logs" / "audit.jsonl",
        [{"ts": _ts("2026-10-17"), "command": "insight", "decision": "approved", "source": "x"}],
    )
    _, footer = srr.build(home, None, END, 8)
    assert (
        srr.intake_line(footer["intake"]) == "- ➖ intake — staged 4w: 1, pending: 1, adopted 4w: 1"
    )


def test_unread_git_columns_print_a_dash_not_a_zero(home):
    table, footer = srr.build(home, None, END, 1)  # no --repo
    assert table[0].drafts is None
    row = next(
        ln for ln in srr.render(table, footer, 8).splitlines() if ln.startswith("| 2026-W43")
    )
    # week | rulings | agree | gate_min | drafts | outside | repairs
    assert row.split(" | ")[4:7] == ["-", "-", "-"]


def test_a_git_failure_leaves_the_git_cells_dashed_not_zero(home, tmp_path):
    not_a_repo = tmp_path / "plain"
    (not_a_repo / "rfcs").mkdir(parents=True)
    table, footer = srr.build(home, not_a_repo, END, 2)
    assert all(
        (w.drafts, w.outside, w.repairs, w.rm_files) == (None, None, None, None) for w in table
    )
    assert any("git/rfcs columns unavailable" in n for n in footer["notes"])
    row = next(
        ln for ln in srr.render(table, footer, 8).splitlines() if ln.startswith("| 2026-W43")
    )
    cells = row.split(" | ")
    assert cells[4:7] == ["-", "-", "-"] and cells[10] == "-"  # drafts outside repairs rm_files


def test_missing_pipeline_metrics_prints_dashes_and_a_reason(home):
    table, footer = srr.build(home, None, END, 2)
    assert any("reason=SELFREG_NO_METRICS" in n for n in footer["notes"])
    out = srr.render(table, footer, 8)
    row = next(ln for ln in out.splitlines() if ln.startswith("| 2026-W43"))
    cells = row.split(" | ")
    # week | rulings | agree | gate_min ... rm_dec | rm_agree
    assert "(metrics not read)" in cells[0]
    assert cells[1:4] == ["-", "-", "-"] and cells[7:9] == ["-", "-"]
    assert "recommender: not read." in out
    assert "reason=SELFREG_LOAD_UNREAD rulings" in srr.candidate(table, 8)


def test_missing_logs_dir_abstains_with_a_reason(tmp_path, capsys):
    rc = srr.main(["--home", str(tmp_path / "nowhere"), "--end", "2026-10-24"])
    assert rc == 2 and "reason=SELFREG_NO_LOG_DIR" in capsys.readouterr().err


def _git(repo: Path, *args: str, when: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def test_git_columns_separate_roadmap_commits_and_exclude_the_readme(home, tmp_path):
    repo = tmp_path / "repo"
    (repo / "rfcs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    sat = "2026-10-24T12:00:00+09:00"
    (repo / "rfcs" / "README.md").write_text("x")
    (repo / "rfcs" / "0001-a.md").write_text("---\nstate: draft\norigin: gate\n---\n")
    (repo / "other.txt").write_text("x")
    _git(repo, "add", "-A", when=sat)
    _git(repo, "commit", "-q", "-m", "docs(rfcs): file a draft", when=sat)
    (repo / "scripts.txt").write_text("x")
    _git(repo, "add", "-A", when=sat)
    _git(repo, "commit", "-q", "-m", "feat: roadmap work\n\nRoadmap: P2-01.5", when=sat)
    table, footer = srr.build(home, repo, END, 8)
    w = _by_label(table)["2026-W43"]
    assert w.drafts == 1
    assert w.outside == 2  # 0001-a.md and other.txt; README.md excluded
    assert w.rm_files == 1  # scripts.txt, from the Roadmap-trailer commit
    assert footer["open_ledger"] == 1


# --- Reading volume: load series (ii) (P2-01.3 / P2-06.1) ----------------------


def _report(home: Path, stamp: str, exceptions_body: list[str], findings: int | None = 5) -> None:
    lines = [
        f"# Weekly Observation — x → {stamp}",
        "",
        "## Inventory",
        "",
        "decisions-pending 0 · exceptions 3 · new-observations 1 · continuing 4 · discarded 2",
        "",
        "## Ledger",
        "- O-001 continuing",
        "",
        "## Deviations",
        "",
        "## Exceptions",
        *exceptions_body,
        "",
        "## Sample",
        "**Context (counterparty, untrusted):** BODY-SENTINEL-must-not-print",
        "",
        "## Discarded",
        "- none",
    ]
    d = home / "reports" / "analysis"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"weekly-{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if findings is not None:
        (d / f"weekly-{stamp}-findings.md").write_text("x\n" * findings, encoding="utf-8")


def test_read_volume_counts_sections_inventory_and_the_carried_fold(home):
    _report(
        home,
        "2026-10-23",
        [
            "- **1. New thing.** fact",
            "  (materials:1-2). No filing.",
            "- Carried: census NO_ROWS `a` (since 2026-10-16), census UNKNOWN",
            "  `b` (since 2026-10-09 or earlier), `GET /home 503` (since",
            "  2026-10-16)",
        ],
    )
    rv = srr.read_volume(home / "reports" / "analysis" / "weekly-2026-10-23.md")
    assert rv is not None
    assert rv.inventory == (0, 3, 1, 4, 2)
    # Inventory 4, Ledger 3, Deviations 2, Exceptions 7 (header + 5 + blank), Discarded 2
    assert rv.sections == (4, 3, 2, 7, 2)
    assert (rv.carried_items, rv.carried_lines) == (3, 1)
    assert rv.doc_lines == 23 and rv.findings_lines == 5


def test_each_week_reads_its_friday_report_and_a_rerun_goes_to_the_next_week(home):
    _report(home, "2026-10-16", ["- a"])
    _report(home, "2026-10-17", ["- b", "- c"], findings=None)  # a Saturday re-run
    _report(home, "2026-10-23", ["- d"])
    table, footer = srr.build(home, None, date(2026, 10, 30), 3)
    w = _by_label(table)
    assert w["2026-W42"].read.stamp == "2026-10-16"
    assert w["2026-W43"].read.stamp == "2026-10-23"  # supersedes the 10-17 re-run
    assert w["2026-W44"].read is None and w["2026-W44"].read_pending
    out = srr.render(table, footer, 8)
    assert "| 2026-W44 | (report pending) |" in out
    assert "| 2026-W43 | 2026-10-23 | 0/3/1/4/2 |" in out


def test_read_volume_prints_counts_never_report_text(home):
    _report(home, "2026-10-23", ["- a"])
    table, footer = srr.build(home, None, END, 8)
    out = srr.render(table, footer, 8)
    assert "BODY-SENTINEL" not in out and "untrusted" not in out


def test_exceptions_trend_needs_three_reports_and_reads_two_falls(home):
    for stamp, n in (("2026-10-09", 6), ("2026-10-16", 4), ("2026-10-23", 2)):
        _report(home, stamp, [f"- e{i}" for i in range(n)])
    table, _ = srr.build(home, None, END, 8)
    line = srr.exceptions_trend(table)
    assert "8 (weekly-2026-10-09) → 6 (weekly-2026-10-16) → 4 (weekly-2026-10-23)" in line
    assert line.endswith("fell in both of the last two reports: yes.")
    table, _ = srr.build(home, None, date(2026, 10, 16), 8)
    assert "2 report(s) in the window; three are needed" in srr.exceptions_trend(table)


def test_the_trend_names_the_unwritten_report_and_the_gate_rerun(home):
    for stamp, n in (("2026-10-09", 6), ("2026-10-16", 4), ("2026-10-23", 2)):
        _report(home, stamp, [f"- e{i}" for i in range(n)])
    # materials of Friday 10-30, built before weekly-2026-10-30.md
    table, _ = srr.build(home, None, date(2026, 10, 30), 8)
    line = srr.exceptions_trend(table)
    assert "→ 4 (weekly-2026-10-23);" in line
    assert line.endswith(
        "weekly-2026-10-30 is not written yet (these materials precede it); "
        "the gate reads it with `--end 2026-10-31`."
    )
    _report(home, "2026-10-30", ["- e"])
    table, _ = srr.build(home, None, date(2026, 10, 31), 8)
    line = srr.exceptions_trend(table)
    assert "6 (weekly-2026-10-16) → 4 (weekly-2026-10-23) → 3 (weekly-2026-10-30)" in line
    assert "not written yet" not in line


def test_carried_label_variants_and_fenced_headers(home):
    _report(
        home,
        "2026-10-23",
        [
            "**Carried:** `a` (since 2026-10-16)",
            "```",
            "## Not-a-section",
            "```",
            "- Carried (2): `b` (since 2026-10-09), `c` (since 2026-10-16)",
        ],
    )
    rv = srr.read_volume(home / "reports" / "analysis" / "weekly-2026-10-23.md")
    assert rv is not None
    assert (rv.carried_items, rv.carried_lines) == (3, 2)
    assert rv.sections[srr.READ_SECTIONS.index("Exceptions")] == 7  # header + 5 + blank


# --- Agreement and the (vi) reconciliation (P2-01.5) ---------------------------


def _item(day: str, cat: str, rec: str | None, dec: str | None, **extra) -> dict:
    row = {"ts": _ts(day), "event": "gate_item", "category": cat, **extra}
    if rec is not None:
        row["recommendation"] = rec
    if dec is not None:
        row["decision"] = dec
    return row


def test_agreement_columns_split_the_roadmap_and_skip_closures(home):
    rows = [_item("2026-10-17", "insight", "adopt", "adopt") for _ in range(9)]
    rows += [_item("2026-10-17", "insight", "adopt", "reject")]
    rows += [_item("2026-10-17", "docs", "keep", None)]  # one side missing: not counted
    rows += [_item("2026-10-17", "roadmap", "A", "A", recommender="MODEL-ID-SENTINEL")]
    rows += [_item("2026-10-17", "roadmap", "B", "A", recommender="MODEL-ID-SENTINEL")]
    rows += [_item("2026-10-17", "roadmap", "closed", "closed", item="P2-01")]
    _w(home / "logs" / "pipeline-metrics.jsonl", rows)
    table, footer = srr.build(home, None, END, 8)
    w = _by_label(table)["2026-W42"]
    assert (w.agree, w.agree_n, w.rm_agree, w.rm_agree_n, w.rm_dec) == (9, 10, 1, 2, 2)
    out = srr.render(table, footer, 8)
    assert "| 9/10 = 90.0% [" in out  # ten rows: the interval prints (P2-01.9)
    assert "| 1/2 |" in out  # under ten: counts only
    assert "gate 0/10, roadmap 2/2" in out
    assert "MODEL-ID-SENTINEL" not in out  # recommender values are never printed


def test_agreement_matches_the_census_definition_on_the_same_rows(home):
    pd = pytest.importorskip("pandas")
    rows = [
        _item("2026-10-17", "insight", "adopt", "adopt"),
        _item("2026-10-17", "insight", "adopt", "hold"),
        _item("2026-10-17", "retire", "archive", "archive"),
        _item("2026-10-17", "roadmap", "A", "A"),
        _item("2026-10-17", "roadmap", "closed", "closed"),
    ]
    _w(home / "logs" / "pipeline-metrics.jsonl", rows)
    table, _ = srr.build(home, None, END, 8)
    w = _by_label(table)["2026-W42"]
    frame = pd.DataFrame(rows)
    census = {r["category"]: r for r in census_series.gate_agreement(frame)}
    assert census["(all)"]["agree"] == w.agree + w.rm_agree
    assert census["(all)"]["n"] == w.agree_n + w.rm_agree_n


def _changes(path: Path, rows: list[dict], last: str = "2026-10-23T18:30:00Z") -> Path:
    payload = {"coverage": {"last_ts": last}, "changes": rows}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_vi_reconciliation_names_only_the_weeks_that_differ(home, tmp_path):
    _w(
        home / "logs" / "audit.jsonl",
        [
            {"ts": _ts("2026-10-17"), "command": "insight", "decision": "approved"},
            {"ts": _ts("2026-10-10"), "command": "insight", "decision": "approved"},
            {"ts": _ts("2026-10-10"), "source": "stage-archived-names"},
        ],
    )
    changes = _changes(
        tmp_path / "changes.json",
        [
            {"kind": "skills", "ts_to": "2026-10-17T18:30:00Z", "files_added": ["a.md"]},
            {"kind": "skills", "ts_to": "2026-10-10T18:30:00Z", "files_added": ["b.md", "c.md"]},
            {"kind": "identity", "ts_to": "2026-10-03T18:30:00Z"},
        ],
    )
    table, footer = srr.build(home, None, END, 8, changes)
    line = footer["reconcile"]
    assert line.startswith("(vi) against changes.json (P2-05.7, last snapshot 2026-10-23)")
    # W43's Sunday (10-25) is after the last snapshot (10-23): W36..W42 are covered
    assert "5 of 7 covered week(s) agree" in line
    assert "2026-W41: adopted/skills added 1 vs 2, archived/skills removed 1 vs 0" in line
    assert "2026-W40: identity approved/changed no vs yes" in line
    assert "2026-W42" not in line
    assert line in srr.render(table, footer, 8)


def test_vi_reconciliation_leaves_weeks_after_the_last_snapshot_uncovered(home, tmp_path):
    changes = _changes(tmp_path / "changes.json", [], last="2026-10-11T18:30:00Z")
    _, footer = srr.build(home, None, END, 8, changes)
    assert "6 of 6 covered week(s) agree." in footer["reconcile"]  # W36..W41 (Sunday 10-11)


def test_vi_a_partly_covered_week_is_not_a_mismatch(home, tmp_path):
    _w(home / "logs" / "audit.jsonl", [{"ts": _ts("2026-10-21"), "source": "stage-archived-names"}])
    # last snapshot Thursday 10-22: W43 is only partly covered, its archive has no snapshot yet
    changes = _changes(tmp_path / "changes.json", [], last="2026-10-22T18:30:00Z")
    _, footer = srr.build(home, None, END, 8, changes)
    assert "7 of 7 covered week(s) agree." in footer["reconcile"]


def test_vi_identity_compares_any_approval_with_any_change(home, tmp_path):
    _w(
        home / "logs" / "audit.jsonl",
        [
            {"ts": _ts("2026-10-13"), "command": "distill-identity", "decision": "approved"},
            {"ts": _ts("2026-10-14"), "command": "distill-identity", "decision": "approved"},
        ],
    )
    changes = _changes(
        tmp_path / "changes.json",
        [{"kind": "identity", "ts_to": "2026-10-14T18:30:00Z"}],  # one snapshot diff
    )
    _, footer = srr.build(home, None, END, 8, changes)
    assert "2026-W42" not in footer["reconcile"]


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"coverage": {"last_ts": "not-a-time"}, "changes": []}, "CHANGES_NO_LAST_TS"),
        ({"coverage": {}, "changes": []}, "CHANGES_UNREADABLE"),
        ({"coverage": {"last_ts": "2026-10-23T18:30:00Z"}, "changes": {}}, "CHANGES_NOT_LIST"),
        (
            {"coverage": {"last_ts": "2026-01-01T00:00:00Z"}, "changes": []},
            "CHANGES_NO_COVERED_WEEK",
        ),
    ],
)
def test_vi_an_unusable_series_abstains_with_a_reason_code(home, tmp_path, payload, reason):
    path = tmp_path / "changes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    _, footer = srr.build(home, None, END, 8, path)
    assert footer["reconcile"].startswith(f"(vi) not reconciled: reason={reason} ")
    assert "agree" not in footer["reconcile"]


def test_vi_reconciliation_abstains_on_an_unreadable_file(home, tmp_path):
    bad = tmp_path / "changes.json"
    bad.write_text("{not json", encoding="utf-8")
    _, footer = srr.build(home, None, END, 8, bad)
    assert footer["reconcile"] == (
        "(vi) not reconciled: reason=CHANGES_UNREADABLE changes.json (JSONDecodeError)."
    )
    _, footer = srr.build(home, None, END, 8)
    assert "reconcile" not in footer

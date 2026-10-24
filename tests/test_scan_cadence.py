"""scripts/scan_cadence.py — weekly scans slow to monthly after N empty runs (P1-04.6)."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import scan_cadence as sc  # type: ignore[import-not-found]  # noqa: E402

END = date(2026, 10, 24)


def _hist(tmp: Path, counts: list, key: str = "candidates", prefix: str = "dead-code") -> None:
    """counts[0] is the most recent earlier run (7 days before END), then weekly back."""
    for i, c in enumerate(counts):
        d = END - timedelta(days=7 * (i + 1))
        (tmp / f"{prefix}-{d.isoformat()}.json").write_text(json.dumps({key: c}), encoding="utf-8")


def test_short_history_is_due(tmp_path):
    _hist(tmp_path, [[], [], []])
    assert sc.decide(tmp_path, "dead-code", "candidates", END)[0] is True
    assert sc.decide(tmp_path / "missing", "dead-code", "candidates", END)[0] is True


def test_four_empty_runs_skip_until_month_passes(tmp_path):
    _hist(tmp_path, [[], [], [], []])
    due, why = sc.decide(tmp_path, "dead-code", "candidates", END)
    assert due is False and "CADENCE_MONTHLY" in why
    # three weeks on with no new file the last run is 28 days old: monthly run is due
    later = END + timedelta(days=21)
    assert sc.decide(tmp_path, "dead-code", "candidates", later)[0] is True
    assert sc.decide(tmp_path, "dead-code", "candidates", END + timedelta(days=14))[0] is False


def test_one_positive_in_window_resumes_weekly(tmp_path):
    _hist(tmp_path, [[], [], ["x"], []])
    assert sc.decide(tmp_path, "dead-code", "candidates", END)[0] is True
    # a positive older than the window no longer counts
    _hist(tmp_path, [[], [], [], [], ["old"]])
    assert sc.decide(tmp_path, "dead-code", "candidates", END)[0] is False


def test_numeric_count_unreadable_and_countless_are_positive(tmp_path):
    _hist(tmp_path, [0, 0, 0, 3], key="count", prefix="docs-consistency")
    assert sc.decide(tmp_path, "docs-consistency", "count", END)[0] is True
    p = tmp_path / f"docs-consistency-{(END - timedelta(days=7)).isoformat()}.json"
    p.write_text("not json")
    assert sc._positive(p, "count") is True
    p.write_text(json.dumps({"other": 1}))
    assert sc._positive(p, "count") is True


def test_current_and_foreign_files_are_ignored(tmp_path):
    _hist(tmp_path, [[], [], [], []])
    (tmp_path / f"dead-code-{END.isoformat()}.json").write_text(json.dumps({"candidates": ["now"]}))
    (tmp_path / "dead-code-notadate.json").write_text("x")
    (tmp_path / "other-2026-10-17.json").write_text(json.dumps({"candidates": ["x"]}))
    assert sc.decide(tmp_path, "dead-code", "candidates", END)[0] is False


def test_main_exit_codes_and_error_is_due(tmp_path, capsys):
    _hist(tmp_path, [[], [], [], []])
    base = ["--dir", str(tmp_path), "--prefix", "dead-code", "--count-key", "candidates"]
    assert sc.main(base + ["--end-date", END.isoformat()]) == 1
    assert capsys.readouterr().out.startswith("skip ")
    assert sc.main(base + ["--end-date", "not-a-date"]) == 0
    assert "CADENCE_ERROR" in capsys.readouterr().out


def test_partial_scans_are_not_empty_runs(tmp_path):
    # four "empty" runs, but one carried errors / unparsed / stderr lines: stay weekly.
    for extra in ({"errors": ["boom"]}, {"unparsed_lines": 2}, {"stderr_lines": 1}):
        d = tmp_path / str(len(extra) + len(next(iter(extra))))
        d.mkdir()
        _hist(d, [[], [], [], []])
        newest = d / f"dead-code-{(END - timedelta(days=7)).isoformat()}.json"
        newest.write_text(json.dumps({"candidates": [], **extra}), encoding="utf-8")
        assert sc.decide(d, "dead-code", "candidates", END)[0] is True
    docs = tmp_path / "docs"
    docs.mkdir()
    _hist(docs, [0, 0, 0, 0], key="count", prefix="docs-consistency")
    p = docs / f"docs-consistency-{(END - timedelta(days=7)).isoformat()}.json"
    p.write_text(json.dumps({"count": 0, "errors": ["x"]}), encoding="utf-8")
    assert sc.decide(docs, "docs-consistency", "count", END)[0] is True


def test_only_exit_1_means_skip(tmp_path):
    import subprocess

    script = Path(__file__).resolve().parent.parent / "scripts" / "scan_cadence.py"
    bad = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=False)
    assert bad.returncode == 2  # argparse error: not the skip code

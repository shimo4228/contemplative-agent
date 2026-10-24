"""scripts/audit_correction.py: a hand repair becomes a chained `correction` row (P1-12.4)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from ._audit_schema import validate_row

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "audit_correction.py"
TEXT = "# Axioms\n"
DIGEST = hashlib.sha256(TEXT.rstrip("\n").encode()).hexdigest()[:16]
TS = "2026-08-09T04:02:11+00:00"


def _home(tmp_path: Path, *, live_text=TEXT) -> Path:
    home = tmp_path / "moltbook"
    (home / "logs").mkdir(parents=True)
    (home / "constitution").mkdir()
    (home / "constitution" / "axioms.md").write_text(live_text, encoding="utf-8")
    row = {
        "ts": TS,
        "command": "amend-constitution",
        "path": "/Users/x/.config/moltbook/constitution/axioms-2.md",
        "decision": "approved",
        "source": "stage-adopted-auto",
        "content_hash": DIGEST,
    }
    (home / "logs" / "audit.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return home


def _run(home: Path, *extra: str):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--home",
            str(home),
            "--corrects-ts",
            TS,
            "--mv-from",
            "constitution/axioms-2.md",
            "--mv-to",
            "constitution/axioms.md",
            "--approver",
            "Test Human",
            "--reason",
            "moved by hand",
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_dry_run_checks_but_writes_nothing(tmp_path):
    home = _home(tmp_path)
    out = _run(home)
    assert out.returncode == 0, out.stderr
    assert "dry run" in out.stdout
    assert len((home / "logs" / "audit.jsonl").read_text().splitlines()) == 1


def test_write_appends_one_chained_row_that_validates(tmp_path):
    home = _home(tmp_path)
    out = _run(home, "--write")
    assert out.returncode == 0, out.stderr
    lines = (home / "logs" / "audit.jsonl").read_text().splitlines()
    assert len(lines) == 2
    row = json.loads(lines[1])
    assert row["command"] == "correction" and row["decision"] == "corrected"
    assert row["content_hash"] == DIGEST and row["sha_checked"] == DIGEST
    assert (row["mv_from"], row["mv_to"]) == ("constitution/axioms-2.md", "constitution/axioms.md")
    assert row["approver"] == "Test Human"
    assert row["prev"] == hashlib.sha256(lines[0].encode()).hexdigest()[:16]
    assert validate_row(row) == []


def test_a_file_that_does_not_match_is_refused(tmp_path):
    home = _home(tmp_path, live_text="# something else\n")
    out = _run(home, "--write")
    assert out.returncode == 1
    assert "refusing to claim a repair" in out.stderr
    assert len((home / "logs" / "audit.jsonl").read_text().splitlines()) == 1


def test_an_unknown_ts_is_refused(tmp_path):
    home = _home(tmp_path)
    (home / "logs" / "audit.jsonl").write_text("", encoding="utf-8")
    assert _run(home, "--write").returncode == 1

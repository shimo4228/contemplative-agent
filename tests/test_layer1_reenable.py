"""scripts/layer1_reenable.py: the re-enable row goes through the real writer (ADR-0122 D5)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ._audit_schema import validate_row

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "layer1_reenable.py"
sys.path.insert(0, str(REPO / "scripts"))
import layer1_exit_guard as guard  # noqa: E402  # pyright: ignore[reportMissingImports]


def _row(ts: datetime, source: str, path: str) -> dict:
    return {
        "ts": ts.isoformat(timespec="seconds"),
        "command": "skill-archive",
        "path": path,
        "decision": "approved",
        "source": source,
        "content_hash": "0" * 16,
    }


def _halted_home(tmp_path: Path) -> Path:
    """Two layer-1 archives, each restored within days: the guard halts."""
    home = tmp_path / "moltbook"
    (home / "logs").mkdir(parents=True)
    t = datetime.now(timezone.utc) - timedelta(days=10)
    rows = [
        _row(t, "archive-l1-unattended", "skills/a.md"),
        _row(t, "archive-l1-unattended", "skills/b.md"),
        _row(t + timedelta(days=2), "direct-restore", "skills/a.md"),
        _row(t + timedelta(days=3), "direct-restore", "skills/b.md"),
    ]
    (home / "logs" / "audit.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return home


def _run(home: Path, *extra: str):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--home",
            str(home),
            "--approver",
            "Test Human",
            "--reason",
            "both restores were a naming collision",
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def _records(home: Path) -> list[dict]:
    return [json.loads(x) for x in (home / "logs" / "audit.jsonl").read_text().splitlines()]


def test_dry_run_reports_the_halt_and_writes_nothing(tmp_path):
    home = _halted_home(tmp_path)
    out = _run(home)
    assert out.returncode == 0, out.stderr
    assert "halted=True" in out.stdout and "dry run" in out.stdout
    assert len(_records(home)) == 4


def test_write_appends_a_chained_row_that_validates_and_lifts_the_halt(tmp_path):
    home = _halted_home(tmp_path)
    now = datetime.now(timezone.utc)
    assert guard.build_reading(_records(home), now)["halted"] is True
    out = _run(home, "--write")
    assert out.returncode == 0, out.stderr
    lines = (home / "logs" / "audit.jsonl").read_text().splitlines()
    row = json.loads(lines[-1])
    assert (row["command"], row["source"], row["decision"]) == (
        "layer1-reenable",
        "layer1-reenable",
        "approved",
    )
    assert row["approver"] == "Test Human"
    assert row["reason"] == "both restores were a naming collision"
    assert row["prev"] == hashlib.sha256(lines[-2].encode()).hexdigest()[:16]
    assert validate_row(row) == []
    reading = guard.build_reading(_records(home), datetime.now(timezone.utc))
    assert reading["halted"] is False and reading["reenabled_at"] is not None


def test_an_empty_reason_is_refused(tmp_path):
    home = _halted_home(tmp_path)
    out = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--home",
            str(home),
            "--approver",
            "X",
            "--reason",
            " ",
            "--write",
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert out.returncode == 1
    assert len(_records(home)) == 4

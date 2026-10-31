"""P2-05.2: the decisions projection keeps the audit columns and drops every body."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import decisions_projection as dp  # noqa: E402  # pyright: ignore[reportMissingImports]

HOME = "/Users/someone/.config/moltbook"


def _rows() -> list[dict]:
    return [
        {
            "timestamp": "2026-03-20T00:00:00Z",
            "command": "insight",
            "path": f"{HOME}/skills/old.md",
            "decision": "approved",
            "content_hash": "h0",
        },
        {
            "ts": "2026-07-01T00:00:00Z",
            "command": "insight",
            "path": f"{HOME}/skills/alpha-20260701.md",
            "decision": "approved",
            "source": "stage-adopted-names",
            "content_hash": "h1",
            "snapshot_path": f"{HOME}/snapshots/insight_20260701T000000",
            "reason": "PRIVATE REASON",
            "source_ids": ["p1", "p2"],
            "epistemic_counts": {"secret": 1},
            "run_id": "r1",
        },
        {
            "ts": "2026-08-01T00:00:00Z",
            "command": "distill",
            "path": "/elsewhere/custom/patterns.md",
            "decision": "rejected",
            "content_hash": "h2",
            "source_ids": ["p3"],
            "approver": "owner",
            "channel": "tty",
        },
    ]


def _run(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    audit = tmp_path / "audit.jsonl"
    audit.write_text("".join(json.dumps(r) + "\n" for r in _rows()) + "not json\n")
    out = tmp_path / "pipeline" / "decisions" / "decisions.jsonl"
    res = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPTS / "decisions_projection.py"),
            "--audit",
            str(audit),
            "--home",
            HOME,
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    rows = [json.loads(ln) for ln in out.read_text().splitlines()] if out.exists() else []
    return res, rows


def test_one_row_per_audit_row_and_no_body(tmp_path: Path) -> None:
    res, rows = _run(tmp_path)
    assert res.returncode == 0, res.stderr
    assert "decisions-projection: rows=3" in res.stdout
    assert len(rows) == 3
    blob = (tmp_path / "pipeline" / "decisions" / "decisions.jsonl").read_text()
    assert "PRIVATE REASON" not in blob and "secret" not in blob
    assert "/Users/" not in blob and "/elsewhere/" not in blob
    assert all("reason" not in r and "epistemic_counts" not in r and "prev" not in r for r in rows)


def test_columns(tmp_path: Path) -> None:
    _res, (old, alpha, outside) = _run(tmp_path)
    assert old["ts"] == "2026-03-20T00:00:00Z"  # the legacy key is read as ts
    assert alpha["path"] == "skills/alpha-20260701.md"
    assert alpha["name"] == "alpha-20260701"
    assert alpha["source_ids"] == ["p1", "p2"] and alpha["n_source_ids"] == 2
    assert alpha["snapshot"] == "insight_20260701T000000"
    assert alpha["run_id"] == "r1"
    # outside the home: the path is dropped, the name stays; ids are counted only
    assert outside["path"] is None and outside["name"] == "patterns"
    assert outside["source_ids"] is None and outside["n_source_ids"] == 1
    assert outside["approver"] == "owner" and outside["channel"] == "tty"


def test_no_audit_file_is_a_skip(tmp_path: Path) -> None:
    assert (
        dp.main(["--audit", str(tmp_path / "none"), "--home", HOME, "--out", str(tmp_path / "o")])
        == 0
    )
    assert not (tmp_path / "o").exists()

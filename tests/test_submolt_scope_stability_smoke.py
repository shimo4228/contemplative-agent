"""Smoke for the quarterly manual instruments kept by D-P1-04-1 = A (P1-04.7).

``scripts/submolt_scope_stability.py`` and ``scripts/ipd-two-arm.sh`` had no
test reference; both stay (ADR-0086 / ADR-0090 Consumption plans), so each gets
one check that it still starts and refuses what it should.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _old_scale_sweep(path: Path) -> None:
    rows = [
        {
            "ts": "2026-08-19T18:00:00+00:00",
            "event": "scan_start",
            "sample_size": 1,
            "subscribed": ["x"],
            "discovered": 1,
        },
        {
            "ts": "2026-08-19T18:00:01+00:00",
            "event": "score",
            "submolt": "x",
            "post_id": "p",
            "score": 0.9,
            "reason": "scored",
        },
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_stability_needs_two_logs():
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "submolt_scope_stability.py"), "only-one.jsonl"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "at least two" in proc.stderr


def test_stability_skips_and_counts_older_scale_sweeps(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _old_scale_sweep(a)
    _old_scale_sweep(b)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "submolt_scope_stability.py"), str(a), str(b)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "2 older-scale skipped" in proc.stderr


def test_ipd_two_arm_script_parses():
    proc = subprocess.run(
        ["bash", "-n", str(SCRIPTS / "ipd-two-arm.sh")], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr

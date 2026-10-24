"""Instruments-only mode of weekly-pipeline.sh (P2-02.2).

With the report stage not requested and no canonical report for the week, the
deterministic stages still complete: `claude` is not required, the chain ends
`ok`, and `REPORT_ABSENT` says why there is no report. Promote / ledger /
spawn stages (which only exist around a report) do not fire. A run that DID
ask for the session keeps the hard requirement (covered by the sibling suites).

macOS-only marker matches the other weekly-pipeline shell suites (BSD date).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_weekly_pipeline_valuelayer_shell as vl  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="weekly-pipeline.sh uses BSD stat/date"
)


def _env_without_claude(tmp_path: Path, stages: str) -> dict:
    env = vl._make_env(tmp_path, approval_audit_lines=[vl._identity_line(3)])
    home = Path(env["MOLTBOOK_HOME"])
    (home / "reports" / "analysis" / f"weekly-{vl.LIVE_END_DATE}.md").unlink()
    (tmp_path / "bin" / "claude").unlink()
    # Drop every PATH entry that provides a real `claude`: the point is that
    # the chain does not need one.
    kept = [d for d in env["PATH"].split(os.pathsep) if d and not (Path(d) / "claude").exists()]
    env["PATH"] = os.pathsep.join(kept)
    env["MOLTBOOK_PIPELINE_STAGES"] = stages
    return env


def _stage_rows(env: dict) -> list[tuple[str, str, str | None]]:
    return [
        (e["stage"], e["result"], e.get("reason"))
        for e in vl._audit_events(env)
        if e.get("event") == "stage_result"
    ]


def test_i1_no_report_stage_and_no_claude_still_ends_ok(tmp_path: Path):
    env = _env_without_claude(tmp_path, "valuelayer,deadcode,docsscan")
    proc = subprocess.run(
        ["bash", str(vl.SCRIPT), "--end-date", vl.LIVE_END_DATE],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    ends = [e for e in vl._audit_events(env) if e.get("event") == "chain_end"]
    assert ends and ends[-1]["result"] == "ok" and ends[-1]["report"] == "none"
    assert "REPORT_ABSENT" in vl._chain_reasons(env)
    rows = _stage_rows(env)
    assert ("report", "skipped", "REPORT_ABSENT") in rows
    assert not [r for r in rows if r[2] in ("REPORT_MISSING", "PREFLIGHT_MISSING_BIN")]
    # Nothing that exists only around a report ran.
    assert not [r for r in rows if r[0] in ("promote", "ledger", "sample_splice", "diagnosis")]
    assert not (
        Path(env["MOLTBOOK_HOME"]) / "reports" / "analysis" / f"weekly-{vl.LIVE_END_DATE}.md"
    ).exists()


def test_i2_skip_report_with_no_existing_report_is_the_same_shape(tmp_path: Path):
    env = _env_without_claude(tmp_path, "valuelayer")
    proc = vl._run(env, vl.LIVE_END_DATE)  # passes --skip-report
    assert proc.returncode == 0, proc.stderr
    assert "REPORT_ABSENT" in vl._chain_reasons(env)
    assert ("report", "skipped", "REPORT_ABSENT") in _stage_rows(env)


def test_i3_an_existing_report_is_an_ordinary_skip_not_absent(tmp_path: Path):
    env = _env_without_claude(tmp_path, "valuelayer")
    report = Path(env["MOLTBOOK_HOME"]) / "reports" / "analysis" / f"weekly-{vl.LIVE_END_DATE}.md"
    report.write_text("# report\n\nbody\n", encoding="utf-8")
    proc = vl._run(env, vl.LIVE_END_DATE)
    assert proc.returncode == 0, proc.stderr
    assert "REPORT_ABSENT" not in vl._chain_reasons(env)
    assert ("report", "skipped", None) in _stage_rows(env)

"""Fault column for the weekly-pipeline.sh timing and single-instance guards.

P2-04.8  second chain while one holds the lock     -> CHAIN_ALREADY_RUNNING, exit 0
P2-04.9  start >= 60 min after the plist slot      -> late_minutes= + CHAIN_LATE_START
P2-04.9  next agent session closer than the distill -> IDENTITY_WINDOW_TOO_SHORT
P2-04.10 run-log generations                       -> pruned to PIPELINE_KEEP_RUNS
P2-04.17 stale / missing watchdog status           -> watchdog_age_h= + WATCHDOG_STALE
P2-04.18 timeout resolution                        -> timeout_bin= (none -> NO_TIMEOUT_BIN)

macOS-only like the other weekly-pipeline shell tests (the script calls BSD
`date -v`); verified on the Mac, skipped on ubuntu. They reuse the value-layer
test's environment builder (stubbed `claude` / `uv`, instruments only).
"""

from __future__ import annotations

import fcntl
import os
import plistlib
import stat
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_weekly_pipeline_valuelayer_shell as vl  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="weekly-pipeline.sh uses BSD stat/date"
)


def _env(tmp_path: Path, **kw) -> dict:
    env = vl._make_env(tmp_path, approval_audit_lines=[vl._identity_line(3)], **kw)
    env["PIPELINE_LAUNCH_AGENTS_DIR"] = str(tmp_path / "LaunchAgents")
    (tmp_path / "LaunchAgents").mkdir()
    return env


def _chain_start(env: dict) -> dict:
    return [e for e in vl._audit_events(env) if e["event"] == "chain_start"][-1]


def _launchd_weekday(dt: datetime) -> int:
    return (dt.weekday() + 1) % 7


def test_g1_a_second_chain_exits_clean_while_the_lock_is_held(tmp_path: Path):
    env = _env(tmp_path)
    lock = Path(env["MOLTBOOK_HOME"]) / "logs" / ".weekly.lock"
    with lock.open("w") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proc = vl._run(env, vl.LIVE_END_DATE)
    assert proc.returncode == 0, proc.stderr
    events = vl._stage_events(env, "preflight")
    assert [(e["result"], e.get("reason")) for e in events] == [
        ("skipped", "CHAIN_ALREADY_RUNNING")
    ]
    assert not [e for e in vl._audit_events(env) if e["event"] == "chain_start"]


def test_g2_a_late_start_is_recorded_and_warned(tmp_path: Path):
    env = _env(tmp_path)
    slot = datetime.now() - timedelta(minutes=125)
    (tmp_path / "LaunchAgents" / "com.moltbook.weekly-pipeline.plist").write_bytes(
        plistlib.dumps(
            {
                "StartCalendarInterval": {
                    "Weekday": _launchd_weekday(slot),
                    "Hour": slot.hour,
                    "Minute": slot.minute,
                }
            }
        )
    )
    # No --end-date: only a default-dated run has a slot to be late for.
    proc = subprocess.run(
        ["bash", str(vl.SCRIPT), "--skip-report"],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    assert int(_chain_start(env)["late_minutes"]) >= 120
    assert "CHAIN_LATE_START" in vl._chain_reasons(env)


def test_g3_identity_defers_when_an_agent_session_starts_inside_its_window(tmp_path: Path):
    env = _env(tmp_path)
    # Rewrite the cadence so identity is due: last approval 40 days ago.
    audit = Path(env["MOLTBOOK_HOME"]) / "logs" / "audit.jsonl"
    audit.write_text(vl._identity_line(40) + "\n", encoding="utf-8")
    soon = datetime.now() + timedelta(minutes=8)
    (tmp_path / "LaunchAgents" / "com.moltbook.agent.plist").write_bytes(
        plistlib.dumps({"StartCalendarInterval": [{"Hour": soon.hour, "Minute": soon.minute}]})
    )
    proc = vl._run(env, vl.LIVE_END_DATE)
    assert proc.returncode == 0, proc.stderr
    events = vl._stage_events(env, "identity")
    assert [(e["result"], e.get("reason")) for e in events] == [
        ("skipped", "IDENTITY_WINDOW_TOO_SHORT")
    ]
    assert not (Path(env["STUB_STATE"]) / "identity_calls").exists()
    assert "IDENTITY_WINDOW_TOO_SHORT" in vl._chain_reasons(env)
    # The gate reads the JSON directly: the reason is written beside `due`.
    import json

    identity = json.loads(vl._vl_json_path(env, vl.LIVE_END_DATE).read_text(encoding="utf-8"))[
        "identity"
    ]
    assert identity["due"] is True and identity["deferred_reason"] == "IDENTITY_WINDOW_TOO_SHORT"
    # The due state persists: nothing was recorded as approved or rejected.
    assert audit.read_text(encoding="utf-8").count("\n") == 1


def test_g4_run_log_generations_are_pruned(tmp_path: Path):
    env = _env(tmp_path)
    runs = Path(env["MOLTBOOK_HOME"]) / "logs" / "weekly-pipeline"
    for day in range(1, 16):
        (runs / f"weekly-2026-01-{day:02d}-000000").mkdir(parents=True)
    (runs / "notes").mkdir()  # not a run directory: never touched
    proc = vl._run(env, vl.LIVE_END_DATE)
    assert proc.returncode == 0, proc.stderr
    kept = sorted(p.name for p in runs.iterdir() if p.name.startswith("weekly-"))
    assert len(kept) == 12
    assert "weekly-2026-01-01-000000" not in kept and (runs / "notes").is_dir()
    assert any(p.name.startswith(f"weekly-{vl.LIVE_END_DATE}-") for p in runs.iterdir())


def test_g5_a_stale_or_missing_watchdog_status_is_warned(tmp_path: Path):
    env = _env(tmp_path)
    proc = vl._run(env, vl.LIVE_END_DATE)  # no status file at all
    assert proc.returncode == 0, proc.stderr
    assert _chain_start(env)["watchdog_age_h"] == "none"
    assert "WATCHDOG_STALE" in vl._chain_reasons(env)


def test_g6_a_fresh_watchdog_status_is_quiet_and_an_old_one_is_not(tmp_path: Path):
    env = _env(tmp_path)
    status = Path(env["MOLTBOOK_HOME"]) / "reports" / "PIPELINE-STATUS.md"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text("# Pipeline Status\n", encoding="utf-8")
    assert vl._run(env, vl.LIVE_END_DATE).returncode == 0
    assert "WATCHDOG_STALE" not in vl._chain_reasons(env)

    old = (datetime.now() - timedelta(hours=100)).timestamp()
    os.utime(status, (old, old))
    assert vl._run(env, vl.LIVE_END_DATE).returncode == 0
    assert int(_chain_start(env)["watchdog_age_h"]) >= 100
    assert "WATCHDOG_STALE" in vl._chain_reasons(env)


def _path_without_timeout(tmp_path: Path, env: dict, *, gtimeout: bool) -> None:
    """A PATH of symlinks to every system tool except timeout/gtimeout."""
    bin_dir = Path(env["PATH"].split(":")[0])
    for src_dir in ("/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin"):
        d = Path(src_dir)
        if not d.is_dir():
            continue
        for tool in d.iterdir():
            if tool.name in ("timeout", "gtimeout"):
                continue
            link = bin_dir / tool.name
            if not link.exists():
                link.symlink_to(tool)
    if gtimeout:
        stub = bin_dir / "gtimeout"
        stub.write_text(
            '#!/bin/bash\necho "$1" >> "$STUB_STATE/gtimeout_calls"\nshift\nexec "$@"\n'
        )
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env["PATH"] = str(bin_dir)


def test_g7_no_timeout_binary_is_recorded_and_warned(tmp_path: Path):
    env = _env(tmp_path)
    _path_without_timeout(tmp_path, env, gtimeout=False)
    proc = vl._run(env, vl.LIVE_END_DATE)
    assert proc.returncode == 0, proc.stderr
    assert _chain_start(env)["timeout_bin"] == "none"
    assert "NO_TIMEOUT_BIN" in vl._chain_reasons(env)


def test_g8_gtimeout_alone_is_used(tmp_path: Path):
    env = _env(tmp_path)
    _path_without_timeout(tmp_path, env, gtimeout=True)
    proc = vl._run(env, vl.LIVE_END_DATE)
    assert proc.returncode == 0, proc.stderr
    assert _chain_start(env)["timeout_bin"].endswith("gtimeout")
    assert "NO_TIMEOUT_BIN" not in vl._chain_reasons(env)
    assert (Path(env["STUB_STATE"]) / "gtimeout_calls").exists()

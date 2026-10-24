"""scripts/chain_schedule_probe.py: late-start and next-agent-session readings (P2-04.9)."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROBE = Path(__file__).resolve().parent.parent / "scripts" / "chain_schedule_probe.py"

# Saturday 2026-10-24 (launchd weekday 6), local clock.
SAT = datetime(2026, 10, 24, 9, 0, 0)


def _probe(reading: str, plist: Path, now: datetime) -> str:
    out = subprocess.run(
        [sys.executable, str(PROBE), reading, "--plist", str(plist), "--now", str(int(now.timestamp()))],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _weekly(tmp_path: Path, weekday: int = 6, hour: int = 9) -> Path:
    p = tmp_path / "weekly.plist"
    p.write_bytes(plistlib.dumps({"StartCalendarInterval": {"Weekday": weekday, "Hour": hour, "Minute": 0}}))
    return p


def _agent(tmp_path: Path, hours: list[int]) -> Path:
    p = tmp_path / "agent.plist"
    p.write_bytes(plistlib.dumps({"StartCalendarInterval": [{"Hour": h, "Minute": 0} for h in hours]}))
    return p


def test_on_time_start_reads_zero(tmp_path):
    assert _probe("late-minutes", _weekly(tmp_path), SAT) == "0"


def test_an_overslept_start_reads_its_lateness(tmp_path):
    assert _probe("late-minutes", _weekly(tmp_path), SAT.replace(hour=10, minute=45)) == "105"


def test_a_start_a_day_later_is_a_hand_run_not_a_late_one(tmp_path):
    assert _probe("late-minutes", _weekly(tmp_path), datetime(2026, 10, 26, 9, 0)) == "unknown"


def test_unreadable_plist_reads_unknown(tmp_path):
    assert _probe("late-minutes", tmp_path / "missing.plist", SAT) == "unknown"
    junk = tmp_path / "junk.plist"
    junk.write_text("not a plist")
    assert _probe("agent-gap-minutes", junk, SAT) == "unknown"


def test_gap_to_the_next_agent_session(tmp_path):
    agent = _agent(tmp_path, [0, 6, 12, 18])
    assert _probe("agent-gap-minutes", agent, SAT.replace(hour=11, minute=50)) == "10"
    assert _probe("agent-gap-minutes", agent, SAT.replace(hour=19)) == "300"  # wraps to 00:00

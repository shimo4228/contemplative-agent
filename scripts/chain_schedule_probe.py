#!/usr/bin/env python3
"""Read the installed launchd plists for the weekly chain's timing guards (stdlib only).

Two readings, each printing ONE token on stdout and exiting 0 (an unreadable
plist prints ``unknown``; the chain records that rather than guessing):

``late-minutes``
    Minutes since the chain's own StartCalendarInterval slot (Weekday / Hour /
    Minute of ``com.moltbook.weekly-pipeline``). A launchd job that was asleep
    at its slot starts late (P2-04.9). More than 24 h after the slot means a
    hand-started run, not a late launchd one, and reads ``unknown``.

``agent-gap-minutes``
    Minutes from now to the next scheduled agent session start in
    ``com.moltbook.agent`` (its list of ``Hour`` slots), used by the identity
    stage's window guard: a distill that overruns into a session start would
    collide with the session's use of the same local model.

Both take ``--now EPOCH`` so the chain and the tests agree on the clock; local
time is used because launchd's calendar is local (docs/CONFIGURATION.md).

    python3 scripts/chain_schedule_probe.py late-minutes --plist P --now 1790000000
"""

from __future__ import annotations

import argparse
import plistlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.parsers.expat import ExpatError

UNKNOWN = "unknown"
_HAND_RUN_AFTER_MINUTES = 24 * 60


def _slots(plist_path: Path) -> list[dict[str, Any]]:
    with plist_path.open("rb") as fh:
        data = plistlib.load(fh)
    sci = data.get("StartCalendarInterval")
    if isinstance(sci, dict):
        return [sci]
    if isinstance(sci, list):
        return [s for s in sci if isinstance(s, dict)]
    return []


def late_minutes(plist_path: Path, now: datetime) -> str:
    slots = _slots(plist_path)
    if not slots or "Weekday" not in slots[0] or "Hour" not in slots[0]:
        return UNKNOWN
    slot = slots[0]
    weekday = int(slot["Weekday"]) % 7  # launchd: 0 and 7 are Sunday
    py_weekday = (weekday - 1) % 7  # datetime: Monday = 0
    back = (now.weekday() - py_weekday) % 7
    scheduled = (now - timedelta(days=back)).replace(
        hour=int(slot["Hour"]), minute=int(slot.get("Minute", 0)), second=0, microsecond=0
    )
    if scheduled > now:
        scheduled -= timedelta(days=7)
    minutes = int((now - scheduled).total_seconds() // 60)
    return str(minutes) if minutes <= _HAND_RUN_AFTER_MINUTES else UNKNOWN


def agent_gap_minutes(plist_path: Path, now: datetime) -> str:
    starts: list[datetime] = []
    for slot in _slots(plist_path):
        if "Hour" not in slot:
            continue
        for day in (0, 1):
            at = (now + timedelta(days=day)).replace(
                hour=int(slot["Hour"]), minute=int(slot.get("Minute", 0)), second=0, microsecond=0
            )
            if at > now:
                starts.append(at)
    if not starts:
        return UNKNOWN
    return str(int((min(starts) - now).total_seconds() // 60))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("reading", choices=["late-minutes", "agent-gap-minutes"])
    ap.add_argument("--plist", required=True, type=Path)
    ap.add_argument("--now", required=True, type=int, help="epoch seconds")
    args = ap.parse_args()
    now = datetime.fromtimestamp(args.now)
    try:
        fn = late_minutes if args.reading == "late-minutes" else agent_gap_minutes
        print(fn(args.plist, now))
    except (OSError, ValueError, KeyError, TypeError, ExpatError, plistlib.InvalidFileException):
        print(UNKNOWN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

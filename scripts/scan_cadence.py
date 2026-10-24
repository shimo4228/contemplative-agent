"""Cadence decision for the low-yield weekly scans (ADR-0085 dead-code, ADR-0093 docs-consistency).

stdlib only (bare ``python3``). Read-only: it lists the scan's own output files.

Rule (P1-04.6): after N consecutive empty runs the scan drops to monthly;
the first positive resumes the weekly cadence. State is the scan's own
history, ``<dir>/<prefix>-YYYY-MM-DD.json``; there is no counter file.

    due  iff  fewer than N earlier outputs exist (nothing to slow down on yet)
              OR any of the N most recent earlier outputs is positive or unreadable
              OR the most recent earlier output is >= MONTHLY_DAYS old

"Positive" = the count key is a non-empty list, or a number > 0. An unreadable
or count-less file counts as positive (fail toward running, never toward silence).
A skipped week writes no file, so the gap since the last output is what counts
the month out.

Exit 0 = run the scan, 1 = skip it. Always prints one ``due ...`` / ``skip ...``
line; any internal error prints ``due reason=CADENCE_ERROR`` and exits 0 so a
broken cadence check can never silence a scan.

Usage:
    python3 scripts/scan_cadence.py --dir DIR --prefix dead-code --count-key candidates \\
        --end-date 2026-10-24 [--n 4]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

DEFAULT_N = 4
MONTHLY_DAYS = 28


def _positive(path: Path, count_key: str) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))[count_key]
    except (OSError, ValueError, KeyError, TypeError):
        return True
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    return value > 0


def decide(
    directory: Path, prefix: str, count_key: str, end: date, n: int = DEFAULT_N
) -> tuple[bool, str]:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{4}}-\d{{2}}-\d{{2}})\.json$")
    history: list[tuple[date, Path]] = []
    if directory.is_dir():
        for p in directory.iterdir():
            m = pattern.match(p.name)
            if not m:
                continue
            try:
                d = date.fromisoformat(m.group(1))
            except ValueError:
                continue
            if d < end:
                history.append((d, p))
    history.sort(reverse=True)
    if len(history) < n:
        return True, f"history={len(history)}<N={n}"
    recent = history[:n]
    for d, p in recent:
        if _positive(p, count_key):
            return True, f"positive_in_last_{n}={d.isoformat()}"
    gap = (end - recent[0][0]).days
    if gap >= MONTHLY_DAYS:
        return True, f"monthly_due gap_days={gap}"
    return (
        False,
        f"CADENCE_MONTHLY last_run={recent[0][0].isoformat()} gap_days={gap} empty_runs>={n}",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--count-key", required=True)
    ap.add_argument("--end-date", required=True)
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    args = ap.parse_args(argv)
    try:
        is_due, why = decide(
            args.dir, args.prefix, args.count_key, date.fromisoformat(args.end_date), args.n
        )
    except Exception as exc:  # noqa: BLE001 - a broken cadence check must never silence a scan
        print(f"due reason=CADENCE_ERROR {type(exc).__name__}")
        return 0
    print(("due " if is_due else "skip ") + why)
    return 0 if is_due else 1


if __name__ == "__main__":
    sys.exit(main())

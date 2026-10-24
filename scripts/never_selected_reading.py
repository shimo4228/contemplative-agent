"""Weekly stage 7b: the never-selected reading (ADR-0097 D5), printed as JSON.

Moved out of ``scripts/weekly-pipeline.sh`` (RFC P2-04.13 PR-A) with the
behaviour unchanged: the chain redirects stdout into
``pipeline/never-selected/never-selected-<END_DATE>.json`` and reads only the
exit status.

since/until rather than days=: the dormant cut is anchored to ``--end-date``,
not the wall clock, so a backfill run reads the window it claims to. Both ends
are inclusive, so since = END_DATE - (N - 1).

Usage:
    uv run --no-sync python scripts/never_selected_reading.py \\
        --home ~/.config/moltbook --end-date 2026-09-05 > OUT.json
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from contemplative_agent.core.never_selected_metrics import (
    NEVER_SELECTED_DORMANT_WINDOW_DAYS,
    never_selected_reading_json,
    read_never_selected,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--home", required=True, type=Path)
    ap.add_argument("--end-date", required=True, type=date.fromisoformat)
    args = ap.parse_args()

    reading = read_never_selected(
        args.home / "logs",
        since=args.end_date - timedelta(days=NEVER_SELECTED_DORMANT_WINDOW_DAYS - 1),
        until=args.end_date,
        skills_dir=args.home / "skills",
    )
    print(json.dumps(never_selected_reading_json(reading)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

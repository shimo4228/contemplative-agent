"""Weekly stage 7d: the comment-outcome reading (RFC-0028 / ADR-0106), as JSON.

Moved out of ``scripts/weekly-pipeline.sh`` (RFC P2-04.13 PR-A) with the
behaviour unchanged: the chain redirects stdout into
``pipeline/comment-outcomes/comment-outcomes-<END_DATE>.json`` and reads only
the exit status. Read-only and unjoined to any gate.

Anchored to ``--end-date``, not the wall clock, so a backfill reads the week it
names (same rule as stage 7b). ``--days`` is the window length (default 7:
since = END_DATE - 6). min-age 2 days: replies land hours to days after a
comment, so the tail of the window would otherwise be counted as silence.

Usage:
    uv run --no-sync python scripts/comment_outcomes_reading.py \\
        --home ~/.config/moltbook --end-date 2026-09-05 > OUT.json
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from contemplative_agent.core.comment_outcomes import read_comment_outcomes


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--home", required=True, type=Path)
    ap.add_argument("--end-date", required=True, type=date.fromisoformat)
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    print(
        json.dumps(
            read_comment_outcomes(
                args.home / "logs",
                since=args.end_date - timedelta(days=args.days - 1),
                until=args.end_date,
                min_age_days=2,
            ),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

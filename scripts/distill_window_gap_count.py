#!/usr/bin/env python3
"""One-shot count of the distill window gap (P0-04.2). Stdlib only; read-only.

The old distill read today's UTC day-file at 18:30Z, so every episode appended
after 18:30Z (the 21Z / 06:00 JST session) was outside every window. This
prints the size of that loss from the two PUBLIC sources, never from the
episode logs (CLAUDE.md: Claude Code sessions do not read them):

1. ``knowledge.json`` ``provenance.source_episode_ids`` — the UTC hour of every
   episode that WAS distilled. A band with zero entries is a band that was
   never read.
2. ``reports/comment-reports/comment-report-*.md`` — ONLY the entry heading
   lines (``### N. [YYYY-MM-DD HH:MM:SS] [KIND] ...``, UTC). Context bodies, which
   quote other agents, are never touched: the file is filtered line by line on
   the heading pattern and everything else is dropped unseen.

Output is counts only (no episode text, no ids).

Usage:
    python3 scripts/distill_window_gap_count.py --data DIR [--cutoff 18:30]

``--data`` is a checkout of the public data repo.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

# Newer reports carry a KIND after the timestamp; the March-May format has none.
_HEADING = re.compile(r"^### \d+\. \[(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):\d{2}\](?: ([A-Z_]+)\b)?")


def _hour_month(ts: str) -> tuple[str, int, int] | None:
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt.strftime("%Y-%m"), dt.hour, dt.minute


def distilled_by_hour(knowledge: Path) -> tuple[Counter[int], Counter[tuple[str, int]], int]:
    """Hour histogram of distinct distilled episode ids (and by month x hour)."""
    rows = json.loads(knowledge.read_text(encoding="utf-8"))
    seen: set[str] = set()
    by_hour: Counter[int] = Counter()
    by_month_hour: Counter[tuple[str, int]] = Counter()
    for row in rows:
        prov = row.get("provenance") if isinstance(row, dict) else None
        ids = prov.get("source_episode_ids") if isinstance(prov, dict) else None
        for eid in ids or ():
            if not isinstance(eid, str) or eid in seen:
                continue
            seen.add(eid)
            parsed = _hour_month(eid)
            if parsed is None:
                continue
            month, hour, _ = parsed
            by_hour[hour] += 1
            by_month_hour[(month, hour)] += 1
    return by_hour, by_month_hour, len(seen)


def headings(reports_dir: Path) -> list[tuple[str, int, int, str]]:
    """(month, hour, minute, kind) per entry heading; nothing else is kept."""
    out: list[tuple[str, int, int, str]] = []
    for path in sorted(reports_dir.glob("comment-report-*.md")):
        with path.open(encoding="utf-8") as f:
            for line in f:
                m = _HEADING.match(line)
                if m:
                    out.append(
                        (
                            m.group(1)[:7],
                            int(m.group(2)),
                            int(m.group(3)),
                            m.group(4) or "unlabelled",
                        )
                    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True, help="public data repo checkout")
    ap.add_argument("--cutoff", default="18:30", help="distill start, UTC HH:MM")
    args = ap.parse_args()
    ch, cm = (int(x) for x in args.cutoff.split(":"))
    cutoff = ch * 60 + cm

    by_hour, by_month_hour, n_ids = distilled_by_hour(args.data / "knowledge.json")
    print(f"distilled episode ids (distinct): {n_ids}")
    print("distilled by UTC hour:", {h: by_hour[h] for h in range(24)})
    late = sum(v for (m, h), v in by_month_hour.items() if h * 60 >= cutoff)
    print(f"distilled with ts at/after {args.cutoff}Z: {late}")

    hs = headings(args.data / "reports" / "comment-reports")
    after = [h for h in hs if h[1] * 60 + h[2] >= cutoff]
    print(f"\ncomment-report headings: {len(hs)}; at/after {args.cutoff}Z: {len(after)}")
    print("headings by UTC hour:", dict(sorted(Counter(h[1] for h in hs).items())))
    print("headings at/after cutoff, by kind:", dict(Counter(h[3] for h in after)))
    by_month = Counter(h[0] for h in after)
    print("headings at/after cutoff, by month:", dict(sorted(by_month.items())))
    firsts = sorted({(h[0]) for h in hs})
    print(f"months covered: {firsts[0]} .. {firsts[-1]}" if firsts else "no headings found")


if __name__ == "__main__":
    main()

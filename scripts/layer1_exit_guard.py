#!/usr/bin/env python3
"""Layer-1 exit reading: archives by layer, restores, and the stop guard (ADR-0122).

Stdlib-only (bare ``python3`` in the weekly chain). Read-only over
``logs/audit.jsonl``. Three numbers and one verdict:

- ``skills_archived_l1``: approved rows with source ``archive-l1-unattended``
  (the unattended deterministic exit).
- ``skills_archived_l2``: approved rows whose source is a human-worded archive
  (``stage-archived-names``, ``direct-archive``, ``direct-archive-auto``).
- ``restored``: approved ``direct-restore`` rows (``restore-skill``).
- ``halted``: the pre-registered falsifier (RFC-0048): two layer-1 archives each
  restored within 28 days of the archive -> layer 1 stops, every candidate goes
  back to layer 2. A restore is matched to an archive by file name; the
  collision suffix ``-N`` the archive may add is stripped on both sides.

The counts feed the ``gate_record`` columns ``skills_archived_l1`` /
``skills_archived_l2`` and the restore column of the P2-01.5 table.

### Consumption plan (ADR-0101)
(a) The Saturday gate reads ``halted`` next to Step 6c (never-selected); the
    unattended stage reads it before each archive call (``--require-live``
    exits 3 when halted, so the stage skips and says why).
(b) One reading per week decides one thing: halted or not. Two restores in a
    4-week window stop layer 1; the owner re-enables by a dated note.
(c) Removal: when layer 1 is retired (D-P2-07-1 revisited) or has run 26 weeks
    with zero restores, fold the count into the census and delete this script.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

L1_SOURCE = "archive-l1-unattended"
L2_SOURCES = frozenset({"stage-archived-names", "direct-archive", "direct-archive-auto"})
RESTORE_SOURCE = "direct-restore"
RESTORE_WINDOW_DAYS = 28
HALT_AT = 2

_SUFFIX_RE = re.compile(r"-\d+(?=\.md$)")


def _ts(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def _name(record: dict[str, Any]) -> str:
    return _SUFFIX_RE.sub("", Path(str(record.get("path", ""))).name)


def _approved(record: dict[str, Any], source: str | frozenset[str]) -> bool:
    sources = frozenset({source}) if isinstance(source, str) else source
    return record.get("decision") == "approved" and record.get("source") in sources


def read_layers(
    records: list[dict[str, Any]], *, start: datetime | None = None, end: datetime | None = None
) -> dict[str, int]:
    """Counts inside [start, end); an open bound is unbounded."""
    counts = {"skills_archived_l1": 0, "skills_archived_l2": 0, "restored": 0}
    for rec in records:
        when = _ts(rec.get("ts"))
        if when is None or (start and when < start) or (end and when >= end):
            continue
        if _approved(rec, L1_SOURCE):
            counts["skills_archived_l1"] += 1
        elif _approved(rec, L2_SOURCES):
            counts["skills_archived_l2"] += 1
        elif _approved(rec, RESTORE_SOURCE):
            counts["restored"] += 1
    return counts


def layer1_restores(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Layer-1 archives that were restored within the window (each archive once)."""
    archives = [(r, t) for r in records if _approved(r, L1_SOURCE) and (t := _ts(r.get("ts")))]
    restores = [(r, t) for r in records if _approved(r, RESTORE_SOURCE) and (t := _ts(r.get("ts")))]
    hits: list[dict[str, str]] = []
    used: set[int] = set()
    for arec, at in sorted(archives, key=lambda x: x[1]):
        for i, (rrec, rt) in enumerate(sorted(restores, key=lambda x: x[1])):
            if i in used or _name(rrec) != _name(arec):
                continue
            if timedelta(0) <= rt - at <= timedelta(days=RESTORE_WINDOW_DAYS):
                used.add(i)
                hits.append(
                    {"name": _name(arec), "archived": at.isoformat(), "restored": rt.isoformat()}
                )
                break
    return hits


def build_reading(records: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
    hits = layer1_restores(records)
    week = read_layers(records, start=as_of - timedelta(days=7), end=as_of + timedelta(days=1))
    return {
        "as_of": as_of.date().isoformat(),
        "week": week,
        "total": read_layers(records),
        "layer1_restores_in_window": hits,
        "halted": len(hits) >= HALT_AT,
        "halt_at": HALT_AT,
        "restore_window_days": RESTORE_WINDOW_DAYS,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--require-live", action="store_true", help="exit 3 when layer 1 is halted")
    args = parser.parse_args(argv)
    try:
        text = args.audit.read_text(encoding="utf-8") if args.audit.exists() else ""
    except (OSError, UnicodeDecodeError) as exc:
        print(f"layer1_exit_guard: reason=AUDIT_UNREADABLE {exc}", file=sys.stderr)
        return 2
    records = []
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    as_of = datetime.fromisoformat(args.as_of).replace(tzinfo=timezone.utc)
    reading = build_reading(records, as_of)
    print(json.dumps(reading, indent=2))
    return 3 if args.require_live and reading["halted"] else 0


if __name__ == "__main__":
    sys.exit(main())

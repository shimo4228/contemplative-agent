#!/usr/bin/env python3
"""Append one event to the weekly-pipeline audit log (ADR-0075 / ADR-0085).

The bash orchestrator shells out here instead of hand-printing JSON: shell
quoting cannot be trusted to produce valid JSON for arbitrary reason strings,
and a corrupt audit line would silently break the packet builder that replays
this log. A write failure exits non-zero so the orchestrator can surface it —
never a silent fallback.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="extra event field (repeatable)",
    )
    args = parser.parse_args()

    record: dict[str, str] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id,
        "event": args.event,
    }
    for field in args.field:
        key, sep, value = field.partition("=")
        if not sep or not key:
            print(f"ERROR: --field expects KEY=VALUE, got: {field!r}", file=sys.stderr)
            return 1
        if key in ("ts", "run_id", "event"):
            print(f"ERROR: --field must not overwrite reserved key {key!r}", file=sys.stderr)
            return 1
        record[key] = value

    try:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        with args.log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"ERROR: audit append failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Append the `layer1-reenable` row that lifts a layer-1 halt (ADR-0122 D5). Owner-run.

`scripts/layer1_exit_guard.py` halts the unattended layer-1 exit when two of its
archives are each restored within 28 days. Re-enabling is a record, not a
reset: this appends one approved row with source `layer1-reenable`, and the
guard counts only layer-1 archives stamped after the latest such row.

The row goes through `cli/approval.py::log_layer1_reenable`, so it carries the
schema's required keys, the `approver` and the `prev` chain link. Hand-appending
the row (the procedure before 2026-10-24) left the source outside the schema
enum and broke the chain. Uses the package, so run it with
`uv run --no-sync python`, not bare `python3`.

Default is a dry run that prints the current guard reading; `--write` appends.
Not an instrument (ADR-0101 covers readings): a one-shot writer, retired with
the guard.

    uv run --no-sync python scripts/layer1_reenable.py --home ~/.config/moltbook \
        --approver "Tatsuya Shimomoto" --reason "the two restores were ..." [--write]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layer1_exit_guard as guard  # noqa: E402  # pyright: ignore[reportMissingImports]


def _records(audit: Path) -> list[dict]:
    out = []
    for line in audit.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--home", type=Path, required=True, help="MOLTBOOK_HOME")
    parser.add_argument("--approver", required=True, help="the human who re-enables")
    parser.add_argument("--reason", required=True, help="why layer 1 may run again")
    parser.add_argument("--write", action="store_true", help="append (default: dry run)")
    args = parser.parse_args(argv)
    if not args.reason.strip() or not args.approver.strip():
        print("ERROR: --approver and --reason must not be empty", file=sys.stderr)
        return 1

    audit = args.home / "logs" / "audit.jsonl"
    if not audit.is_file():
        print(f"ERROR: {audit} not found", file=sys.stderr)
        return 1
    reading = guard.build_reading(_records(audit), datetime.now(timezone.utc))
    print(f"guard now: halted={reading['halted']}")
    if not reading["halted"]:
        print("note: layer 1 is not halted; a re-enable row only moves the counting start")
    if not args.write:
        print("dry run - pass --write to append the layer1-reenable row")
        return 0

    from contemplative_agent.cli import approval

    approval.AUDIT_LOG_PATH = audit
    if not approval.log_layer1_reenable(approver=args.approver, reason=args.reason):
        print("ERROR: the layer1-reenable row did not reach disk", file=sys.stderr)
        return 1
    print("appended 1 layer1-reenable row")
    return 0


if __name__ == "__main__":
    sys.exit(main())

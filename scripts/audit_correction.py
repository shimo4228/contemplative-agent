#!/usr/bin/env python3
"""Append a `command: correction` row to audit.jsonl (P1-12.4). Owner-run, once per repair.

Two approved rows in the live log name a path that never held the approved
bytes (constitution 2026-08-09 `contemplative-axioms-2.md`, identity
2026-08-15): the H5 collision guard wrote an inert twin and the file was moved
into place by hand (ADR-0090 "Remediated by hand"; `cli/adopt.py`
`_replaces_canonical_target`). The log is append-only, so the repair is a new
row, not an edit.

This script checks the claim before it writes it: the live file's
`sha256[:16]` (and the same minus its trailing newline, the way an adopt row
hashes) must equal the corrected row's `content_hash`, and the corrected row
must exist in the log. Default is a dry run that prints the row; `--write`
appends it through `cli/approval.py::log_correction`, so the row carries the
`prev` chain link like any other. Never rewrites an existing line.

Uses the package (`uv run --no-sync python scripts/audit_correction.py ...`),
not bare `python3`: the chain link is computed by the writer, and a second
copy of that rule would be the thing that drifts.

Not an instrument and not part of the weekly chain, so no consumption plan
(ADR-0101 covers readings; this is a one-shot writer). Retire it after the
two known rows are appended.

Example (dry run, then write):

    uv run --no-sync python scripts/audit_correction.py \
        --home ~/.config/moltbook --corrects-ts 2026-08-09T04:02:11+00:00 \
        --mv-from constitution/contemplative-axioms-2.md \
        --mv-to constitution/contemplative-axioms.md \
        --approver "Tatsuya Shimomoto" \
        --reason "H5 guard twin moved into place by hand within minutes (ADR-0090)"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _digests(data: bytes) -> set[str]:
    out = {hashlib.sha256(data).hexdigest()[:16]}
    if data.endswith(b"\n"):
        out.add(hashlib.sha256(data[:-1]).hexdigest()[:16])
    return out


def _find_row(audit: Path, ts: str) -> dict | None:
    for line in audit.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("ts") == ts and row.get("decision") == "approved":
            return row
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--home", type=Path, required=True, help="MOLTBOOK_HOME")
    parser.add_argument("--corrects-ts", required=True, help="ts of the approved row to correct")
    parser.add_argument("--mv-from", required=True, help="home-relative path the row recorded")
    parser.add_argument("--mv-to", required=True, help="home-relative path the file lives at")
    parser.add_argument("--approver", required=True, help="who made the hand repair")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--write", action="store_true", help="append (default: dry run)")
    args = parser.parse_args(argv)

    audit = args.home / "logs" / "audit.jsonl"
    if not audit.is_file():
        print(f"ERROR: {audit} not found", file=sys.stderr)
        return 1
    corrected = _find_row(audit, args.corrects_ts)
    if corrected is None:
        print(f"ERROR: no approved row with ts={args.corrects_ts!r}", file=sys.stderr)
        return 1
    live = args.home / args.mv_to
    if not live.is_file():
        print(f"ERROR: {live} is not a file", file=sys.stderr)
        return 1
    digests = _digests(live.read_bytes())
    if corrected["content_hash"] not in digests:
        print(
            f"ERROR: live {args.mv_to} hashes to {sorted(digests)} but the row says "
            f"{corrected['content_hash']}; refusing to claim a repair that did not happen",
            file=sys.stderr,
        )
        return 1
    checked = corrected["content_hash"]
    print(
        f"ok: {args.mv_to} carries content_hash {checked}; row @{args.corrects_ts} "
        f"recorded path {corrected.get('path')!r}"
    )
    if not args.write:
        print("dry run - pass --write to append the correction row")
        return 0

    from contemplative_agent.cli import approval

    approval.AUDIT_LOG_PATH = audit
    wrote = approval.log_correction(
        corrects_ts=args.corrects_ts,
        content_hash_of_corrected=checked,
        mv_from=args.mv_from,
        mv_to=args.mv_to,
        sha_checked=checked,
        approver=args.approver,
        reason=args.reason,
    )
    if not wrote:
        print("ERROR: the correction row did not reach disk", file=sys.stderr)
        return 1
    print("appended 1 correction row")
    return 0


if __name__ == "__main__":
    sys.exit(main())

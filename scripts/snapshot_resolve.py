#!/usr/bin/env python3
"""Resolve gate decisions to the snapshot of the run that generated them, from public files only.

P1-12.9. A value-layer change is explainable only if its decision can be tied
back to the run (prompts, constitution, skills, identity as that run saw them)
that produced the candidate. In the private home that chain is
`audit.jsonl` row -> stage row -> `snapshot_path` -> `snapshots/<dir>/`. The
public data repo has no `audit.jsonl`; it has a decisions projection (selected
columns of those rows) and `snapshots/*/manifest.json`. This script walks the
same three-step rule over the public files and says, per decision, how far it
got:

1. decision row -> stage row: the stage row of the same `command` with the same
   `content_hash` (the carrier). No stage row (a `direct` approval, or an adopt
   whose canonicalized text hashes differently) makes the decision row its own
   carrier.
2. carrier -> snapshot, tried in order: `exact-path` (`snapshot_path` names a
   directory that exists), `exact-run_id` (the carrier's `run_id` equals a
   manifest's), `inferred-ts` (a manifest of the same `command` whose `ts` is
   within `--neighbour-seconds` of the carrier; marked inferred, never exact -
   18 manifests predate `run_id` and 2026-10-24 predates `snapshot_path`).
3. nothing matched: `rotated` - the snapshot was pruned (retention is capped,
   P3-04.1) or never taken. Printed in the table, not hidden.

Inputs: `--decisions FILE` (JSONL; any file whose rows carry the audit columns
`ts command decision content_hash` and optionally `snapshot_path run_id source`)
and `--snapshots DIR` (the public `snapshots/`). Reads nothing else.

Read-only; stdlib only (bare `python3`). Exit 0 after printing the table; with
`--require-resolved`, exit 1 if any decision is `rotated` (the release-gate
mode); exit 2 when an input cannot be read.

### Consumption plan (ADR-0101)
(a) Read by the foreign-reproduction guide and the RCA (`P4-03.3`) when they
    must name the version a decision applied to; the Saturday gate reads it
    through the decisions projection's `snapshot` column (`P2-05.2`).
(b) One reading: a human confirms the `inferred-ts` rows, and the count of
    `rotated` versions decides whether the snapshot retention (`P3-04.1`,
    per-kind prune) must change.
(c) Remove the script from the weekly path once every public `history/` version
    resolves and eight weeks pass with no new `rotated`; keep it only as a
    release gate (`--require-resolved`).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_DECIDED = ("approved", "rejected")


def _ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def load_manifests(snapshots: Path) -> list[tuple[str, dict[str, Any]]] | None:
    """``[(dir name, manifest)]`` for every snapshot dir with a readable manifest."""
    if not snapshots.is_dir():
        return None
    out = []
    for manifest in sorted(snapshots.glob("*/manifest.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            out.append((manifest.parent.name, data))
    return out


def _carrier(row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The stage row this decision came from, else the decision row itself."""
    for other in rows:
        if (
            other.get("decision") == "staged"
            and other.get("command") == row.get("command")
            and other.get("content_hash") == row.get("content_hash")
        ):
            return other
    return row


def _nearest_by_ts(
    carrier: dict[str, Any], manifests: list[tuple[str, dict[str, Any]]], neighbour: timedelta
) -> str | None:
    """The same-command snapshot whose ``ts`` is nearest the carrier's, within ``neighbour``."""
    when = _ts(carrier.get("ts"))
    if when is None:
        return None
    best: tuple[timedelta, str] | None = None
    for name, manifest in manifests:
        taken = _ts(manifest.get("ts"))
        if taken is None or manifest.get("command") != carrier.get("command"):
            continue
        gap = abs(when - taken)
        if gap <= neighbour and (best is None or gap < best[0]):
            best = (gap, name)
    return best[1] if best else None


def resolve_one(
    carrier: dict[str, Any],
    manifests: list[tuple[str, dict[str, Any]]],
    neighbour: timedelta,
) -> tuple[str, str | None]:
    """``(how, snapshot dir name)``; how is exact-path / exact-run_id / inferred-ts / rotated."""
    names = {name for name, _ in manifests}
    path = carrier.get("snapshot_path")
    if isinstance(path, str) and path:
        leaf = Path(path).name
        if leaf in names:
            return "exact-path", leaf
    run_id = carrier.get("run_id")
    if isinstance(run_id, str) and run_id:
        for name, manifest in manifests:
            if manifest.get("run_id") == run_id:
                return "exact-run_id", name
    name = _nearest_by_ts(carrier, manifests, neighbour)
    if name is not None:
        return "inferred-ts", name
    return "rotated", None


def resolve_all(
    rows: list[dict[str, Any]],
    manifests: list[tuple[str, dict[str, Any]]],
    *,
    neighbour: timedelta,
    since: datetime | None = None,
) -> list[tuple[dict[str, Any], str, str | None]]:
    out = []
    for row in rows:
        if row.get("decision") not in _DECIDED:
            continue
        when = _ts(row.get("ts"))
        if since is not None and (when is None or when < since):
            continue
        how, name = resolve_one(_carrier(row, rows), manifests, neighbour)
        out.append((row, how, name))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--snapshots", type=Path, required=True)
    parser.add_argument("--since", help="ISO-8601; only decisions at or after it")
    parser.add_argument("--neighbour-seconds", type=int, default=60)
    parser.add_argument("--require-resolved", action="store_true")
    args = parser.parse_args(argv)

    rows = _read_jsonl(args.decisions)
    manifests = load_manifests(args.snapshots)
    if rows is None or manifests is None:
        print("unavailable (reason=input-unreadable)", file=sys.stderr)
        return 2
    since = _ts(args.since) if args.since else None
    results = resolve_all(
        rows, manifests, neighbour=timedelta(seconds=args.neighbour_seconds), since=since
    )
    print("| ts | command | decision | content_hash | resolution | snapshot |")
    print("|---|---|---|---|---|---|")
    for row, how, name in results:
        shown = name or "snapshot rotated (pruned or never taken)"
        print(
            f"| {row.get('ts')} | {row.get('command')} | {row.get('decision')} | "
            f"{row.get('content_hash')} | {how} | {shown} |"
        )
    tally: dict[str, int] = {}
    for _, how, _ in results:
        tally[how] = tally.get(how, 0) + 1
    print(
        f"\n{len(results)} decision(s): " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items()))
    )
    return 1 if args.require_resolved and tally.get("rotated") else 0


if __name__ == "__main__":
    sys.exit(main())

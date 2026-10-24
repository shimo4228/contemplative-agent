#!/usr/bin/env python3
"""Resolve one gate session's `gate_item` rows to their `audit.jsonl` rows (read-only).

P1-12.1 PR-B. The Saturday gate records each decision twice: `adopt-staged`
writes an `audit.jsonl` row (the act), and weekly-gate Step 7 writes a
`gate_item` event to `pipeline-metrics.jsonl` (the lens: recommendation vs
decision). Until now nothing tied the two together, so "did the decision the
gate recorded match what the CLI recorded" was unanswerable. Step 7 now copies
the audit row's `content_hash` into the `gate_item` (and the signer's
`approver`); this script is the one read that resolves a week's `gate_item`
rows against the log and says which do not.

Per `gate_item` of the run (`--run-id gate-YYYY-MM-DD`):

- category `insight` / `identity` must carry a `content_hash` that equals an
  approved / rejected audit row's `content_hash`. Missing hash, no such row,
  or a verdict that disagrees (`decision=adopt` vs a `rejected` row) is
  UNRESOLVED. `decision=hold` has no audit row by design and passes.
- other categories (deadcode / retire / docs / roadmap) have no audit
  counterpart; they are counted, and their `approver` is reported.
- an `approver` on the gate_item that differs from the audit row's is flagged
  (the two should be the same human's signature).

Exit 0 when every row that needs a counterpart resolves, 1 otherwise, 2 when an
input cannot be read (an unreadable log is "cannot tell", never "all resolved").

Reads only `pipeline-metrics.jsonl` and `audit.jsonl`, both self-written logs
(never the episode logs). Prints hashes, names and counts only.

Stdlib only: invoked with bare `python3` from the gate session.

### Consumption plan (ADR-0101)
(a) The Saturday gate session runs it once, after Step 7, for that week's
    `gate-{end-date}` run. (b) After four consecutive weeks with exit 0 the
    check is known to hold and the gate stops running it by hand: the
    `gate_item` -> audit join then lives only in `tests/test_gate_item_audit_join.py`
    plus the weekly `value_layer_approval_join.py` approver line. One UNRESOLVED
    week resets the count. (c) Retire the script when `gate_item` stops carrying
    `content_hash` (a different recording shape), or at the 2027-Q2 mechanism
    freeze if the four clean weeks have happened by then.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_NEEDS_AUDIT = frozenset({"insight", "identity"})
_DECISION_TO_AUDIT = {"adopt": "approved", "reject": "rejected"}


def _read_jsonl(path: Path) -> list[dict[str, Any]] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _audit_index(audit: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in audit:
        digest = row.get("content_hash")
        if isinstance(digest, str) and row.get("decision") in ("approved", "rejected"):
            index.setdefault(digest.strip().lower(), []).append(row)
    return index


def resolve(
    items: list[dict[str, Any]], index: dict[str, list[dict[str, Any]]]
) -> tuple[list[tuple[str, str]], list[str]]:
    """``([(item, outcome)], notes)``; an outcome starting UNRESOLVED fails the run."""
    results: list[tuple[str, str]] = []
    notes: list[str] = []
    for item in items:
        name = str(item.get("item", "?"))
        category = str(item.get("category", ""))
        decision = str(item.get("decision", ""))
        if category not in _NEEDS_AUDIT:
            results.append((name, f"n/a (category={category or '?'}, no audit counterpart)"))
            continue
        if decision == "hold":
            results.append((name, "n/a (hold is not an audit event)"))
            continue
        digest = item.get("content_hash")
        if not isinstance(digest, str) or not digest.strip():
            results.append((name, "UNRESOLVED: gate_item has no content_hash"))
            continue
        rows = index.get(digest.strip().lower())
        if not rows:
            results.append((name, f"UNRESOLVED: no approved/rejected audit row for {digest}"))
            continue
        row = rows[-1]
        wanted = _DECISION_TO_AUDIT.get(decision)
        if wanted is not None and row.get("decision") != wanted:
            results.append(
                (
                    name,
                    f"UNRESOLVED: gate_item says {decision}, audit row says {row.get('decision')}",
                )
            )
            continue
        results.append((name, f"ok ({row.get('source')} @{row.get('ts')})"))
        mine, theirs = item.get("approver"), row.get("approver")
        if mine and theirs and str(mine).strip().casefold() != str(theirs).strip().casefold():
            notes.append(f"{name}: approver differs (gate_item {mine!r} vs audit {theirs!r})")
    return results, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--metrics", type=Path, required=True, help="pipeline-metrics.jsonl")
    parser.add_argument("--audit", type=Path, required=True, help="audit.jsonl")
    parser.add_argument("--run-id", required=True, help="the gate run, e.g. gate-2026-10-31")
    args = parser.parse_args(argv)

    metrics = _read_jsonl(args.metrics)
    audit = _read_jsonl(args.audit)
    if metrics is None or audit is None:
        which = args.metrics if metrics is None else args.audit
        print(f"unavailable (reason=log-unreadable): {which}", file=sys.stderr)
        return 2
    items = [r for r in metrics if r.get("event") == "gate_item" and r.get("run_id") == args.run_id]
    if not items:
        print(f"unavailable (reason=no-gate-items): no gate_item rows for run {args.run_id}")
        return 2
    results, notes = resolve(items, _audit_index(audit))
    bad = [r for r in results if r[1].startswith("UNRESOLVED")]
    print(f"{args.run_id}: {len(items)} gate_item row(s), {len(bad)} unresolved")
    for name, outcome in results:
        print(f"  {name}: {outcome}")
    for note in notes:
        print(f"  note: {note}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

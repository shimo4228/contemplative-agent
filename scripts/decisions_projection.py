#!/usr/bin/env python3
"""``pipeline/decisions/decisions.jsonl``: the approval log without its bodies (P2-05.2).

stdlib only; run as ``python3 -I scripts/decisions_projection.py`` from the sync
export stage (``sync-research-data.sh``), after the rsync. ``logs/`` is never
published (ADR-0010), so ``logs/audit.jsonl`` reaches the public data repo only
through this projection (decision D-P2-05-2 = A: no bodies).

One output row per audit row, in file order. Columns kept, and only these:
``ts`` (the older ``timestamp`` key is read as ``ts``), ``command``,
``decision``, ``source``, ``content_hash``, ``path`` (relative to the home;
an absolute path outside it becomes null and only ``name`` remains), ``name``
(the file stem), ``reason_code``, ``n_source_ids``, ``source_ids`` (ids only,
for value-layer paths: identity, constitution, rules, skills), ``approver``,
``channel``, ``session``, ``run_id``, ``snapshot_path`` (home-relative, same
rule as ``path``), ``snapshot`` (the snapshot dir name, which
``scripts/snapshot_resolve.py`` reads) and, on a correction row, ``corrects_ts``.
The free-text ``reason``, ``epistemic_counts``, ``prev`` and every key not listed
here are never copied. A key the row lacks is null.

Self-check: output rows = parseable input rows; a mismatch prints ERROR and
exits 1. The line printed on success is the export stage's one-line log.

Consumption plan (ADR-0101): (a) the public reader recomputing the README's
adoption counts, and ``snapshot_resolve.py`` (the Saturday gate and the RCA,
P4-03.3); (b) one judgement — can a value-layer change be tied to its decision
and run from public files alone; (c) retire at the final sync of P4-02.

Usage:
    decisions_projection.py --audit audit.jsonl --home DIR --out decisions.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_COPIED = (
    "command",
    "decision",
    "source",
    "content_hash",
    "reason_code",
    "approver",
    "channel",
    "session",
    "run_id",
    "corrects_ts",
)
_VALUE_LAYER_TOPS = ("identity.md", "identity", "constitution", "rules", "skills")


def _relative(raw: object, home: str) -> str | None:
    """Home-relative POSIX path; null for anything absolute outside the home."""
    if not isinstance(raw, str) or not raw:
        return None
    path = raw.replace("\\", "/")
    if not path.startswith("/"):
        return path
    prefix = home.rstrip("/") + "/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    marker = "/.config/moltbook/"  # the default home, as older rows recorded it
    if marker in path:
        return path.split(marker, 1)[1]
    return None


def project(rec: dict[str, Any], home: str) -> dict[str, Any]:
    raw_path = rec.get("path")
    rel = _relative(raw_path, home)
    base = str(raw_path).replace("\\", "/").rsplit("/", 1)[-1] if raw_path else ""
    ids = rec.get("source_ids")
    ids = [str(i) for i in ids] if isinstance(ids, list) else None
    top = rel.split("/", 1)[0] if rel else ""
    snap = _relative(rec.get("snapshot_path"), home)
    row: dict[str, Any] = {"ts": rec.get("ts") or rec.get("timestamp")}
    for key in _COPIED:
        row[key] = rec.get(key)
    row.update(
        {
            "path": rel,
            "name": base[:-3] if base.endswith(".md") else (base or None),
            "n_source_ids": len(ids) if ids is not None else None,
            "source_ids": ids if ids is not None and top in _VALUE_LAYER_TOPS else None,
            "snapshot_path": snap,
            "snapshot": snap.rstrip("/").rsplit("/", 1)[-1] if snap else None,
        }
    )
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--audit", type=Path, required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if not args.audit.is_file():
        print(f"decisions-projection: skipped (no {args.audit.name})")
        return 0
    n_in = 0
    out: list[str] = []
    for line in args.audit.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        n_in += 1
        out.append(json.dumps(project(rec, args.home), ensure_ascii=False, sort_keys=True))
    if len(out) != n_in:
        print(f"ERROR: decisions rows {len(out)} != audit rows {n_in}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text("".join(r + "\n" for r in out), encoding="utf-8")
    tmp.replace(args.out)
    print(f"decisions-projection: rows={len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

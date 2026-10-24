#!/usr/bin/env python3
"""Manifest key generations of the public snapshots (P3-02.7 (1)).

stdlib only; run as ``python3 -I scripts/manifest_key_generations.py SNAPSHOTS_DIR``.
Read-only. The public ``snapshots/*/manifest.json`` files fall into a few
generations by key set (today 14 keys x1, 15 keys x44, 19 keys x55). The table
says, per generation: how many manifests, the first and last ``ts``, the keys
it added over the previous generation and where the addition came from. A
reader of the longitudinal record needs it because the same field being absent
in an old manifest is a different fact from the field being null in a new one
(``ollama_version`` is absent before 2026-09-06, not unknown-by-accident).

Two manifests with equal key sets are one generation; generations are ordered by
their first ``ts``. The origin column comes from ``ORIGINS`` below (a key added
in code that is not listed shows ``-``); this is where the owner adds a line
when a new key lands with its ADR.

Consumption plan (ADR-0101): (a) the owner pastes the table into DATACARD
(Mac-side, hand-kept file) and P3-05.10's reproducer reads it to know which
fields a given snapshot can carry; (b) one tabulation now, then once when the
next key lands (a new generation shows up as a diff of the output against the
DATACARD copy); (c) retire when the table is in DATACARD and P4-02's final sync
has frozen the snapshots; the script then stays as a one-shot.

Usage:
    manifest_key_generations.py SNAPSHOTS_DIR [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# key -> where it came from (first generation: the ADR-0020 manifest + later additions
# that were already present at the oldest public snapshot).
ORIGINS: dict[str, str] = {
    "run_id": "T-MANIFEST-RUNID fix, 2026-08-02 (a snapshot finds its own telemetry)",
    "ollama_version": "ADR-0069 addendum, 2026-09-06",
    "generation_model_digest": "ADR-0069 addendum, 2026-09-06",
    "embedding_model_digest": "ADR-0069 addendum, 2026-09-06",
    "serving_environment_reason": "ADR-0069 addendum, 2026-09-06",
}


def generations(snapshots: Path) -> list[dict]:
    by_keys: dict[frozenset[str], list[tuple[str, str]]] = {}
    for f in sorted(snapshots.glob("*/manifest.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        by_keys.setdefault(frozenset(m), []).append((str(m.get("ts", "")), f.parent.name))
    gens = []
    for keys, items in by_keys.items():
        items.sort()
        gens.append({"keys": keys, "count": len(items), "first": items[0], "last": items[-1]})
    gens.sort(key=lambda g: g["first"])
    prev: frozenset[str] = frozenset()
    out = []
    for g in gens:
        added = sorted(g["keys"] - prev)
        removed = sorted(prev - g["keys"])
        out.append(
            {
                "n_keys": len(g["keys"]),
                "manifests": g["count"],
                "first_ts": g["first"][0],
                "first_snapshot": g["first"][1],
                "last_ts": g["last"][0],
                "last_snapshot": g["last"][1],
                "keys_added": added,
                "keys_removed": removed,
            }
        )
        prev = g["keys"]
    return out


def render(gens: list[dict]) -> str:
    lines = [
        "| keys | manifests | first snapshot (ts) | last (ts) | keys added over the previous generation | origin |",
        "|---|---|---|---|---|---|",
    ]
    for i, g in enumerate(gens):
        added = ", ".join(f"`{k}`" for k in g["keys_added"])
        if i == 0:
            added = "(base set) " + added
        if g["keys_removed"]:
            added += "; removed: " + ", ".join(f"`{k}`" for k in g["keys_removed"])
        origins = sorted({ORIGINS[k] for k in g["keys_added"] if k in ORIGINS})
        lines.append(
            f"| {g['n_keys']} | {g['manifests']} | `{g['first_snapshot']}` ({g['first_ts']}) | "
            f"`{g['last_snapshot']}` ({g['last_ts']}) | {added} | {'; '.join(origins) or '-'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("snapshots", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.snapshots.is_dir():
        print(f"manifest-key-generations: not a directory: {args.snapshots}", file=sys.stderr)
        return 2
    gens = generations(args.snapshots)
    if args.json:
        json.dump(gens, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        sys.stdout.write(render(gens))
    return 0


if __name__ == "__main__":
    sys.exit(main())

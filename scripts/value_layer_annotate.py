#!/usr/bin/env python3
"""Write the identity stage's deferral reason into the week's value-layer JSON (stdlib only).

``value_layer_due_check.py`` writes ``identity.due`` before the chain decides
whether it may stage the monthly identity distill. The decision (backfill run,
insight still pending, window too short, staging busy or lost) used to live
only in the chain's audit log, so the Saturday gate reading the JSON saw
``due: true`` with nothing staged and no reason (P2-04.13 PR-C). This adds
``identity.deferred_reason`` beside it. Atomic (temp + rename); fails without
touching the file when the JSON is unreadable or has no ``identity`` object.

    python3 scripts/value_layer_annotate.py --json F --identity-deferred REASON
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def annotate(path: Path, reason: str) -> None:
    if not _REASON_RE.match(reason):
        raise ValueError(f"reason must be an UPPER_SNAKE code, got {reason!r}")
    data = json.loads(path.read_text(encoding="utf-8"))
    identity = data.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("value-layer JSON has no identity object")
    identity["deferred_reason"] = reason
    # Named *.tmp: the public data sync excludes *.tmp, so an orphan left by a
    # crash between write and rename is never published (pipeline/ is synced).
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", required=True, type=Path)
    ap.add_argument("--identity-deferred", required=True, metavar="REASON")
    args = ap.parse_args()
    try:
        annotate(args.json, args.identity_deferred)
    except (OSError, ValueError) as exc:
        print(f"value_layer_annotate: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

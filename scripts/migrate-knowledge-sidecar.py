#!/usr/bin/env python3
"""Load and save the knowledge store once, reporting both halves (ADR-0108).

The inline-to-sidecar migration this script was written for is finished: the
production store moved on 2026-09-12, and since P1-06.13 ``KnowledgeStore.load()``
refuses rows that still carry an inline ``embedding`` or are bare strings
(``reason=legacy_row_shape``). To convert such a file (an old backup, say), run
this script from the v2.13.0 release tag, the last one with the inline read.

What it still does on a current store: one load, one save, the before/after
numbers and the reason codes, and ``--prune`` deletes sidecar vectors no row
claims (the broom ``scripts/state_invariant_check.py`` names for orphans).

Read-modify-write on the live store. It is therefore the one thing the runbook
tells you to take a backup before. Refuses to write when the load failed
(tainted, unparseable or legacy-shaped file), for the same reason ``save()`` does.

Usage:
    uv run python scripts/migrate-knowledge-sidecar.py [--home DIR] [--dry-run] [--prune]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from contemplative_agent.core.knowledge_store import KnowledgeStore
from contemplative_agent.core.pattern_embeddings import sidecar_path_for


def _mib(path: Path) -> str:
    return f"{path.stat().st_size / (1024 * 1024):.1f} MiB" if path.exists() else "absent"


def migrate(knowledge_path: Path, *, dry_run: bool = False, prune: bool = False) -> int:
    """Rewrite the store into its two-file form. Returns the rows carrying a vector."""
    sidecar = sidecar_path_for(knowledge_path)
    print(f"before: {knowledge_path.name} {_mib(knowledge_path)}, sidecar {_mib(sidecar)}")

    store = KnowledgeStore(path=knowledge_path)
    store.load()
    if store.load_failed:
        raise SystemExit(
            f"Error: {knowledge_path} could not be loaded (unreadable, tainted or not a "
            "JSON array) — nothing written."
        )

    if store.dropped_rows:
        raise SystemExit(
            f"Error: {knowledge_path} has {store.dropped_rows} element(s) that are not "
            "pattern rows. Saving would delete them, so nothing was written. Fix or "
            "remove them first."
        )
    rows = store.get_raw_patterns()
    report = store.sidecar_consistency()
    embedded = sum(1 for p in rows if p.get("embedding"))
    print(
        f"loaded: {len(rows)} rows, {embedded} with a vector "
        f"({report.describe()}; codes={report.reason_codes() or ['none']})"
    )
    if report.missing_ids:
        print(
            f"note: {len(report.missing_ids)} row(s) have no vector on either side — "
            "run scripts/restore-embed-knowledge.py to re-derive them."
        )

    if dry_run:
        print("dry-run: nothing written.")
        return embedded

    store.save()
    if prune:
        removed = store.prune_orphan_vectors()
        print(f"pruned {removed} orphan vector(s).")
    print(f"after:  {knowledge_path.name} {_mib(knowledge_path)}, sidecar {_mib(sidecar)}")
    return embedded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook")),
        help="MOLTBOOK_HOME (default: $MOLTBOOK_HOME or ~/.config/moltbook)",
    )
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="also delete sidecar vectors no pattern claims (orphans)",
    )
    args = parser.parse_args(argv)

    knowledge_path = args.home / "knowledge.json"
    if not knowledge_path.is_file():
        raise SystemExit(f"Error: {knowledge_path} not found")
    migrate(knowledge_path, dry_run=args.dry_run, prune=args.prune)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

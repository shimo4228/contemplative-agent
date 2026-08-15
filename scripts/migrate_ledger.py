#!/usr/bin/env python3
"""One-shot migration: the single-table ledger → one file per task (2026-08-15).

Reads `.notes/TASKS.md` (112 rows, ~102k chars) and writes `.notes/tasks/T-*.md`,
after which `tasks.py render` regenerates the table and `TASKS.md` becomes an
artifact. Delete this script once the migration has landed and been verified —
it is scaffolding, not a maintained tool.

**Aborts rather than guessing.** `split_row` raises on any row that does not
yield exactly five cells, and this script does not catch it per-row: a partial
migration is worse than none, because the missing tasks would be
indistinguishable from completed ones. Two rows needed a hand fix before this
ran (an unescaped `|` in a code span, and `|Δ効果|` used as absolute-value
notation) — both were bugs in the table that no consumer had ever surfaced.

**What is deliberately not inferred:**

- `origin` is left empty. The lineage vocabulary (review / gate / instrument /
  idea / incident) exists only in prose, and a regex over prose falls to
  whichever pattern matches first. A guessed origin would poison the very
  measurement the field was added for — the 4-week intake reading that decides
  the candidate→ready promotion rule.
- `state_since` is the migration date for every task, not a parsed filing date.
  Consequence, accepted on purpose: the ready rows all age out on the same day,
  which surfaces them together as one stocktake trigger.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from tasks import MalformedRow, Task, load_tasks_from_ledger, render_ledger, store_dir, write_store


def migrate(root: Path, today: str) -> list[Task]:
    ledger = root / ".notes" / "TASKS.md"
    # `legacy=True`: this script's input is the pre-migration table, the one
    # dialect where a bare `|` inside a code span is body text. A ledger this
    # repo has already rendered reads with the default dialect instead — that
    # direction is disaster recovery, not migration, and belongs to tasks.py.
    raw = load_tasks_from_ledger(ledger, legacy=True)
    return [
        Task(
            id=t.id,
            state=t.state,
            summary=t.summary,
            condition=t.condition,
            detail=t.detail,
            # `origin` is omitted, not written empty: an absent key reads as
            # "never recorded", an empty one as "recorded as nothing".
            meta={**t.meta, "state_since": today},
        )
        for t in raw
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args(argv)

    try:
        tasks = migrate(args.root, args.today)
    except MalformedRow as exc:
        print(f"MIGRATE_FAIL {exc}", file=sys.stderr)
        print("  この行を手で直してから再実行する（部分移行はしない）", file=sys.stderr)
        return 1

    states = Counter(t.state_word for t in tasks)
    store = store_dir(args.root)
    print(f"tasks: {len(tasks)}  →  {store}")
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(states.items())))

    rendered = render_ledger(tasks)
    original = (args.root / ".notes" / "TASKS.md").read_text(encoding="utf-8")

    # Compare by ID, not by position: render_ledger moves terminal tasks into
    # the Done section, so a positional zip lines up different tasks from the
    # first relocated row onward and reports a near-total change count with a
    # false explanation. That number is the operator's only evidence for
    # approving an unrecoverable migration (2026-08-15 code review MEDIUM).
    def by_id(text: str) -> dict[str, str]:
        return {ln.split("|")[1].strip(): ln for ln in text.split("\n") if ln.startswith("| T-")}

    before, after = by_id(original), by_id(rendered)
    print(f"rows: {len(before)} → {len(after)}")
    changed = sum(1 for tid in before.keys() & after.keys() if before[tid] != after[tid])
    print(f"  行内容が変わる行: {changed}（パイプのエスケープと空白の正規化）")
    for label, ids in (
        ("台帳のみ", before.keys() - after.keys()),
        ("store のみ", after.keys() - before.keys()),
    ):
        if ids:
            print(f"  **{label}: {sorted(ids)}**")

    if args.dry_run:
        print("\n--dry-run: 何も書いていない")
        return 0

    write_store(store, tasks)
    print(f"\n書いた: {len(tasks)} ファイル")
    print("次: python3 scripts/tasks.py render --output .notes/TASKS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

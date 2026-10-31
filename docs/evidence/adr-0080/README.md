# ADR-0080 evidence

- `core-commit-tags.md` — the `core/` commit tagging (P1-01.2).
- First frozen self-regulation table (P2-01.5): **not yet taken.** It needs the live
  `pipeline-metrics.jsonl`, `audit.jsonl` and `insight-staged.jsonl`, which are on the
  owner's Mac only. To freeze it (the earliest gate after the 11-28 reading is fine;
  six to eight weeks of history are already in the logs):

  ```bash
  python3 scripts/self_regulation_reading.py --home ~/.config/moltbook --repo . \
    --end <gate-saturday> > docs/evidence/adr-0080/self-regulation-<gate-saturday>.md
  ```

  Commit it with the gate's `gate_record` that carries `self_regulation_verdict=`.
  The `(vi)` columns are the script's own count until `pipeline/value-layer/changes.json`
  (P2-05.7) exists to reconcile against.

## Consumption plans of the columns added after the first version (ADR-0101)

The table's own plan is in ADR-0080 (amendment "How load and metabolism not stopped
are read") and in the script's docstring. These are the plans of the columns added
to it later; each retires with the weekly table at the latest.

- **Reading volume** (load series (ii), P2-01.3 / P2-06.1): the second table of
  `## Self-Regulation Reading` — per week, the report the Saturday gate reads
  (`reports/analysis/weekly-{stamp}.md`), its Inventory five numbers, the lines of
  Inventory / Ledger / Deviations / Exceptions / Discarded, the carried fold
  (`(since W)` items / `Carried:` lines), and the report and findings line counts.
  (a) The owner reads it at weekly-gate Step 1 every week. (b) The 2026-11-14 gate
  reads the "Exceptions lines" line once for P2-06.1's done-criterion (two production
  weeks after the fold, 11-06 and 11-13); the 2026-11-28 gate (D-P2-01-1 = B) reads
  the eight rows once to keep series (ii) as these columns or drop it. (c) Remove at
  11-28 if that gate drops series (ii), otherwise with the weekly table.

# ADR-0080 evidence

- `core-commit-tags.md` — the `core/` commit tagging (P1-01.2).
- `self-regulation-2026-10-31.md` — the first frozen self-regulation table (P2-01.5):
  eight weeks W37–W44, taken read-only on the owner's Mac after the 2026-10-31 gate.
  Initial values: rulings 0–75 per gate (0 in W40 / W42 / W43), `outside` 0–309 files,
  repairs 3–81, agreement 6/7 to 20/20 (roadmap 89/91 in W44), reading volume 245–350
  report lines and 82–198 findings lines, adopted 0 and archived 0 since W39, the
  zero-load run 0 weeks (not a candidate), the metabolism floor 3 of 8 weeks, and (vi)
  agreeing with the change series in all 8 weeks. The re-read of the load instrument
  (ADR-0080 Re-read trigger) and `self_regulation_verdict=` are the owner's, in the
  `gate_record` of the first gate that reads it. A later table is frozen the same way:

  ```bash
  python3 scripts/self_regulation_reading.py --home ~/.config/moltbook --repo . \
    --end <gate-saturday> \
    --changes ~/MyAI_Lab/contemplative-agent-data/pipeline/value-layer/changes.json \
    > docs/evidence/adr-0080/self-regulation-<gate-saturday>.md
  ```

  The `(vi)` columns are the script's own count; `--changes` (P2-05.7) adds the line
  that names each week where they differ from the value-layer change series.

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
- **Agreement** (`agree` / `rm_agree`, and the `recommender` coverage line, P2-01.5):
  per week, ruled `gate_item` rows whose `decision` equals the `recommendation`, the
  roadmap's own rows apart; `k/n` with the Wilson interval from ten rows (P2-01.9's
  rule). Same population as the census "Gate record" section, which splits it per
  category. (a) The owner reads it at Step 1 every week. (b) The 2026-12-12 gate
  reads the eight rows once to fix the n of the D-P2-01-2 audit (A: blind re-ruling of
  saved `gate_item` rows) and to see that `recommender` covers that population; after
  the audit, ADR-0099's Review-when (~100% sustained) is read from these cells at the
  quarterly T4. (c) Remove with the weekly table.
- **(vi) reconciliation line** (P2-01.5 against P2-05.7): names each week where adopted
  / archived / identity approvals differ from the change series' skills files added /
  removed and identity changes (placed by the snapshot `ts_to`). (a) The owner reads it
  at Step 1 every week. (b) A week it names is checked once at that gate against
  `audit.jsonl` and the snapshots, and the explanation goes in that gate's
  `gate_record` (known causes: a retired writer such as rules-distill adds and removes
  files no gate row names; an archive whose file removal fell outside the snapshots).
  (c) Remove with the weekly table.

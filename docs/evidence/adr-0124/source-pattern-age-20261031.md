# Q2 axis: age of the source patterns of selected skills — first reading (2026-10-31)

The fourth axis of the [ADR-0124](../../adr/0124-research-questions-operational-definitions.md)
Q2 table, which `scripts/compounding_axes_reading.py` declares `not_computed`
because its inputs are private (`reanalysis: private-rows`). Taken once on the
production machine with a throwaway script (not kept: ADR-0101, one reading per
quarter). Counts and dates only; no pattern or skill text.

## Inputs and join

- `logs/skill-selection-*.jsonl`, `kind: "selection"`, `verdict: "judged"`,
  `enforced: true`: 4,374 selections, 2026-09-09T15:00Z .. 2026-10-31T03:59Z
  (the first enforced row in the logs is 09-09).
- selected name → skill file in `skills/` (frontmatter `name`) → the
  `insight` / `approved` row of `logs/audit.jsonl` for that file → its
  `source_ids` → the pattern in `knowledge.json` whose computed id
  (`core/knowledge_store.pattern_id`) matches → its `distilled` time.
- Age = selection time minus the source pattern's `distilled` time, one value
  per (selection, selected skill, source pattern).

| join | count |
|---|---|
| selected-skill mentions | 29,083 over 52 distinct skills |
| mapped to `source_ids` | 28,830 (99.1%) |
| unmapped (4 skills adopted without insight lineage) | 253 |
| source-pattern mentions | 125,277 over 180 distinct patterns |
| `source_ids` not found in `knowledge.json` | 0 |

## Reading

| | median age (days) | quartiles |
|---|---|---|
| selections in 2026-09 (46,935 mentions) | 47 | 38 .. 62 |
| selections in 2026-10 (78,342 mentions) | 76 | 67 .. 90 |
| whole corpus at 2026-10-31 (all `knowledge.json` rows, 13,509) | 69 | 31 .. 104 |

Creation month of the source patterns behind the selections: 2026-07 55,698
and 2026-08 69,579 mentions; none older or newer. The corpus by creation month:
03 216, 04 239, 05 271, 06 707, 07 3,441, 08 2,678, 09 2,668, 10 3,289.

## What this first reading says (descriptive only)

Every selected skill draws on July–August patterns, because no skill has been
adopted since the last staged batch (2026-09-19). The selected material
therefore ages at calendar speed (47 → 76 days median between September and
October) while the corpus keeps adding new patterns, so the selected material
is now about as old as the corpus median and older than its newest half. This is
the store being frozen, not a choice by the selector between old and new
material: the selector can only choose among skills whose sources are all from
the same two months. The axis's judgement sentence waits for the second reading
(next quarter), as the ADR says; the noise floor is set from the two readings.

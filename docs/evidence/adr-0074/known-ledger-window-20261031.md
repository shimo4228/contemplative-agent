# Known-ledger window: age histogram re-read (2026-10-31)

One-shot reading for P0-01.7 (the `KNOWN_LEDGER_WEEKS` value of the
[ADR-0074](../../adr/0074-weekly-staged-insight.md) Amendment 2026-10-24). Read
on the production machine from `logs/insight-staged.jsonl` (`ts` field only)
and the `--- Summary:` lines of `logs/insight-launchd.log`. Not refreshed; the
Saturday gate reads it once to confirm or change N.

## Ledger age histogram

Unchanged since the 2026-10-24 reading: 587 rows, nothing staged after
2026-09-19 (the file was last written 2026-09-19).

| staged | 07-09 | 07-18 | 07-25 | 08-01 | 08-08 | 08-15 | 08-22 | 08-29 | 09-05 | 09-19 |
|---|---|---|---|---|---|---|---|---|---|---|
| rows | 54 | 106 | 78 | 50 | 55 | 49 | 46 | 43 | 31 | 75 |

## What the window keeps at each Saturday run

Rows whose `ts` is not older than the run time minus N weeks (computed with
the run at 23:00 UTC the day before).

| run (08:00 JST) | N = 8 | N = 12 (current) | N = 16 |
|---|---|---|---|
| 2026-10-31 | 106 | 299 | 533 |
| 2026-11-07 | 75 | 244 | 533 |
| 2026-11-14 | 75 | 195 | 427 |
| 2026-12-12 | 0 | 75 | 195 |
| 2026-12-19 | 0 | 0 | 149 |

## The first run under N = 12 (2026-10-31 08:00 JST)

`--- Summary: 0 candidates (110 already covered; 0 duplicate, 0 insufficient,
0 nothing_promotable, 0 reconfirm, 2 revise; duplicate judge answers 0 / 30)`.
The novelty gate judged 110 of 112 clusters covered with the window in place,
against 191 of 211 on the run before. The window did not by itself let new
candidates through this week; one run is not evidence either way.

## Proposal for the gate

Keep N = 12. The ledger has had no new rows for six weeks, so N only sets the
date on which a rejected theme can return: 12 let about half (288 rows) back at this
run and empties the ledger by 12-19; 8 would have dropped 481 rows at once; 16 changes
almost nothing until December. The owner confirms or changes the constant in
`core/insight_novelty.py`.

# distill window gap: the 06:00 JST session was never distilled (P0-04.2)

Frozen 2026-10-24 for roadmap item P0-04.2 and decision D-P0-04-1 (backfill: yes or no, due 2026-11-21).
This file records the size of the loss and the paragraph to publish. It does **not** backfill anything.

## Method (reproducible, counts only)

`python3 scripts/distill_window_gap_count.py --data <public data repo checkout>`, run on data repo
commit `d44544a` (sync of 2026-10-23T20:30Z). Two public sources, neither of them the episode logs:

1. `knowledge.json`, field `provenance.source_episode_ids`: the UTC hour of every distinct episode that
   **was** distilled.
2. `reports/comment-reports/comment-report-*.md`: only the entry heading lines
   (`### N. [YYYY-MM-DD HH:MM:SS] ...`, UTC); bodies are never read.

The cut-off is 18:30Z, the daily distill start (JST 03:30). The old window was today's UTC day-file at
that moment, so everything stamped after 18:30Z on any day was in no window.

## Result

| reading | value |
|---|---|
| distinct episode ids cited by stored patterns | 7,260 |
| of those, stamped at or after 18:30Z | **0** |
| distilled ids by UTC hour | 03Z 2,506 / 04Z 107 / 09Z 2,218 / 10Z 84 / 15Z 2,249 / 16Z 82 / other 14; **21-22Z: 0** |
| comment-report entries, 2026-03-07 .. 2026-10-23 | 16,199 |
| of those, stamped at or after 18:30Z | **3,917** (24.2%) |
| by hour | 21Z 3,310 / 22Z 474 / 23Z 74 / 18:30-20:59Z 59 |
| by month (at/after 18:30Z) | 03: 508, 04: 559, 05: 406, 06: 324, 07: 647, 08: 559, 09: 524, 10: 390 |
| by kind (reports from June on carry a kind) | comment 1,160 / reply 977 / post 156 / unlabelled (Mar-May format) 1,624 |

Reading notes.

- The loss is one session per day. 21Z holds 3,310 of the 3,917; the 22Z and 23Z entries are the tail of
  that session, and the 59 entries between 18:30Z and 21:00Z are manual or off-schedule runs. The 03Z, 09Z and
  15Z bands (3,491 / 3,299 / 3,266 entries) are all present in the store.
- A report entry is one published comment, reply or post; an episode is the log record behind it. The count is
  therefore the number of published items lost, which is the measure of what the dataset is missing; the
  episode count is not read (episode logs are off limits to Claude Code sessions). The roadmap's 3,000-4,000
  estimate and this 3,917 are the same size.
- The roadmap quoted 12,859 ids for the store. That figure counts every id occurrence across patterns; the
  distinct count is 7,260 (one episode can seed several patterns).
- The first entry of the dataset (2026-03-07 21:27Z) is itself in the gap, so the span is the whole
  dataset, not a recent regression.
- The knowledge store contains patterns distilled from other agents' and the agent's own text. The table
  above carries no text from either.

## Paragraph to publish (DATACARD, or the P3-02 boundary table)

> **Undistilled session.** From 2026-03-07 until the repair date (distill windows widened to
> processed-episode ledger on <repair date>, ADR-0060 amendment of 2026-10-24), the agent's 06:00 JST
> session (21:00-23:59 UTC) was never distilled into `knowledge.json`: the daily distill ran at
> 18:30 UTC over the current UTC day-file only, so episodes written after it were outside every window.
> Comment-report headings count 3,917 of 16,199 reported entries (24%) stamped at or after 18:30 UTC in that
> period; no stored pattern cites an episode from that band. The patterns therefore describe three of the
> four daily sessions. From the repair date the band is distilled on the next run. Whether the earlier
> episodes are distilled retrospectively is recorded as a separate decision (D-P0-04-1).

This is a ready-to-apply edit for `DATACARD.md` in the data repo. The data repo is overwritten by the Mac's
morning sync, so it is applied there (P0-03 data-repo session), not from the cloud.

## What is not done

- No backfill (D-P0-04-1, recommended B: record only). If A or C is chosen, the run is a Mac task with the
  steps in the roadmap (`knowledge.json` and `pattern-embeddings.sqlite` copied to `knowledge.backups/`,
  sync job stopped, dry-run count written to `gate_item`, then the run).
- The repair date is filled in when the fix merges and the first 18:30Z run has used the ledger.
- The first weekly census line after the repair should show a non-zero 21-22Z band in
  `source_episode_ids`; that is the bundle's completion condition.

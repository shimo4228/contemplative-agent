# ADR-0123: The Knowledge Live Pool Is Kept Whole — No Garbage Collection, a 50 MB Trigger, and an Age Reading

## Status

accepted

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session (roadmap P2-07.4)
decided-by: owner (D-P2-07-3 = a, "as recommended", 2026-10-24)
date: 2026-10-24

## Layer

mechanism

## Context

`knowledge.json` holds about 11,000 patterns, 675 of them tombstones
(`valid_until` set), and the file only grows. Three facts decide what a
retention policy can be:

- The dedup comparison population is `effective_importance >= 0.05`, which is
  `0.95^days`, about 58 days (`core/distill.py`, ADR-0056). A live row older
  than that is retrievable but is no longer compared when a new pattern is
  distilled, so a re-observed insight can re-enter beside it (ADR-0053 §4).
- `KnowledgeStore` prune removes only orphan vectors from the sidecar; there
  is no compaction of rows (ADR-0108), and ADR-0060 keeps the no-delete line.
- `scripts/state_invariant_check.py` warns at 40% tombstones and does nothing
  else.

The options were (a) keep as is and name the trigger, (b) move live rows
older than N days into yearly shards, keeping ids, (c) widen the dedup
population to all live rows.

## Decision

**(a), and say so.** The live pool is not garbage-collected and nothing moves
out of `knowledge.json` on age. The trigger for revisiting is the one ADR-0108
already wrote: `knowledge.json` (text only, post-sidecar) crossing about
50 MB, or the sidecar no longer being the smaller half. Crossing it reopens
(b) versus (c); it does not by itself choose.

(b) and (c) are not chosen now because neither has evidence yet. (c) is a
mechanism widening (a larger comparison population changes what is counted as
a duplicate, and costs time per distill); it is justified only if re-entry of
beyond-floor rows shows up as a measurable `skipped_known` increase. (b)
changes where rows live and so touches every reader of the file.

**The age reading.** The weekly instrument census gains one line,
"Knowledge live-pool age": live rows, how many are within the dedup floor and
how many beyond (with the no-timestamp count, which is treated as beyond),
tombstones, and the file size against the 50 MB trigger
(`scripts/instrument_census.py::render_knowledge_age`). It reads
`knowledge.json` once per census and never raises: an unreadable file prints
"not read" with the reason. Two periods of this line (about 8 weekly readings)
are the evidence the choice between (b) and (c) waits on.

## Review-when

- `knowledge.json` crosses about 50 MB (the stated trigger).
- Two reading periods show the beyond-floor share rising while distill's
  `skipped_known` rises with it — then (c) has its evidence.
- Tombstones exceed the 40% warn of `state_invariant_check` for a month.

### Consumption plan

(a) The Saturday gate reads the one census line with the rest of the census
(weekly-report Phase 0 reads the census through). (b) Two periods of readings
decide (b), (c) or staying at (a), once, at the 2027-02-27 gate or later.
(c) Removed when (b) or (c) is adopted and the new mechanism carries its own
reading, or after four quiet quarters with the file under the trigger.

## Alternatives Considered

- **(b) yearly shards for old live rows.** Deferred: touches every reader,
  no evidence the size is a problem before the trigger.
- **(c) widen the dedup population.** Deferred: a capability widening with a
  per-distill time cost; wants the `skipped_known` evidence first.
- **Delete old rows.** Contradicts ADR-0060's no-delete line; not considered.

## Consequences

- No change to production behaviour; one more line in the census.
- The retention policy is now a sentence a stocktake can find, with its
  trigger and its evidence plan, instead of an absence.

## References

- `ADR-0108` (`0108-knowledge-embedding-sidecar.md`) — the 50 MB Review-when
- `ADR-0060` (`0060-per-episode-grounded-distill.md`) — no-delete
- `ADR-0056`, `ADR-0053` — decay-only importance, re-entry of old insights
- `ADR-0101` — consumption plans; `ADR-0107` / `ADR-0110` — the census

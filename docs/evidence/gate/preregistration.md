# Gate longitudinal record — pre-registration (ROADMAP P3-06.2)

Registered 2026-10-24, before any private approval row was read for these
metrics. The numbers below come only from the aggregate sentence in
`README.md` (as of 2026-10-08) and from the public `pipeline/value-layer/*.json`
projections in the data repository. The author of this file did not open
`logs/audit.jsonl` or `logs/pipeline-metrics.jsonl`.

## What this record is for

It is the main data of the first planned paper (subject A in the paper-plan RFC:
the responsibility structure of the harness layer). The claim it tests is
that the owner's approval is an **act of responsibility**, not quality control:
the gate does not remove what a recommender would have removed anyway; it puts a
named decision, with a recorded reason and a recorded load, in the loop.
Everything below is a reading. No metric here is a target, and none feeds back
into the agent (observation-over-steering, ADR-0080).

## Metrics, predictions, falsification

`reanalysis` uses the four values of the research-question rule: `public` (can be
recomputed by anyone from published files), `private-rows` (needs the private
decision log), `rerun-local`, `rerun-cloud`. Rows that are `private-rows` today
become `public` only when the approval-record projection exists (P2-05.2), and
the column is updated then.

| id | metric | public file today | reanalysis | prediction | falsified if |
|---|---|---|---|---|---|
| G1 | **Adoption rate**, per kind (skill / identity / constitution), per quarter | `README.md` "See it running" sentence: 82 adopted and 547 rejected skill proposals, 6 of 11 identity, 2 of 4 constitution (the only public aggregate); `pipeline/value-layer/value-layer-*.json` carries `last_adopted_ts` | aggregate `public`; per-quarter `private-rows` | skill adoption stays in 8-20 % (82 of 629 = 13.0 % at 2026-10-08) and identity / constitution adoption is higher than skill adoption | a quarter above 30 % or below 5 % for skills, or identity / constitution at or below the skill rate |
| G2 | **Rejection-reason distribution** | none (the reason field is null in every logged row; the field arrives with P1-12) | `private-rows` | once the field exists, at least two reason classes each cover 20 % or more of rejections (the gate is deciding on more than one ground) | a single reason class covers 80 % or more, or 90 % of reasons stay empty after the field exists |
| G3 | **Recommendation-ruling concordance** (the owner's ruling against the briefing's recommendation) | none | `private-rows` | 95 % or more concordance in every quarter (ADR-0099 already reads about 100 %, flagged there as an effective-filter warning), and the non-concordant rulings sit on identity / constitution items more often than on skill items | concordance below 85 % in any quarter, or non-concordant rulings spread evenly over kinds |
| G4 | **Hold rate** (staged items neither adopted nor rejected at the next gate) | `staging_pending` in `pipeline/value-layer/value-layer-{end}.json` (0 at 2026-10-16) | `public` | `staging_pending` is 0 at the Saturday gate in 90 % or more of weeks | three consecutive weeks above 0 |
| G5 | **Weekly load** (items decided and amount read per Saturday) | item count: none public; materials size: `reports/analysis/weekly-*-materials.md` is not published | `private-rows` | the load definition of P2-01 (not yet landed) will be quoted here verbatim; until then no prediction is made | n/a until the definition lands; then the prediction is written before the first reading, in this file |

## Why G3 is registered with a two-sided reading

A concordance near 100 % can mean two opposite things: the recommender is good,
or the gate has become an effective filter that adds nothing. The metric alone
does not separate them. The prediction therefore adds the second clause (where
the rulings that do differ fall), and the paper reports both clauses, not the
rate.

## Reading schedule and closing

- Read at the owner's discretion once per quarter, beside the P2-01 load
  reading, and once at the paper cutoff.
- At the cutoff (P3-06.3) the aggregates are frozen; after that this file is
  closed and the later record is the P2-05.2 projection.
- If a metric turns out unreadable from the files it names, that is recorded as
  "not readable" with the reason; the prediction is not rewritten afterwards.

## Updates owed by other work

- P1-12 (approver and reason fields): fills G2, changes G2's `reanalysis`
  when the projection is public.
- P2-01 (load definition): fills G5.
- P2-05.2 (approval-record projection): turns G1-G3 per-quarter rows `public`.

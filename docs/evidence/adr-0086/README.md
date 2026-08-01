# ADR-0086 evidence — submolt scope, 2026-08-01

Every numeric claim in [ADR-0086](../../adr/0086-submolt-scope-instrument-before-autonomy.md)
comes from one read-only measurement on 2026-08-01. The runtime log it was taken
from lives under `MOLTBOOK_HOME` and is gitignored, so the envelope records are
copied here — otherwise the numbers would exist nowhere a clone can check
(ADR review, 2026-08-01).

## `scan-envelope-2026-08-01.jsonl`

The `scan_start` and `scan_end` records of scan `acfc59573228`
(`run_id` `fd006e2ec9654210a26f0c36282845ae`), verbatim. The `score` records
from the same run are **not** copied: they carry base64-encoded post bodies —
untrusted external content that belongs in the runtime log, not in the repo.

| Claim in the ADR | Field |
|---|---|
| 20 submolts listed | `scan_start.discovered`, and 20 names in `candidates` |
| 12 outside the subscribed eight | `candidates` minus `subscribed` |
| the subscribed set is the hand-picked eight | `scan_start.subscribed` |
| the sweep reads every candidate | `scan_end.scanned` = all 20, `skipped` empty |
| one feed page = 20 posts | *not* shown here — this run used `sample_size: 2` |

## What this run does and does not establish

It was a smoke run of the shipped instrument at `sample_size: 2`, not a
measurement at the production default of 20. So it establishes the platform
facts (how many submolts exist, which are outside the scope, that unsubscribed
feeds are readable without subscribing, that a full sweep completes in ~100
seconds at 38 scored posts) and **not** the relevance distribution — 2 posts
per submolt is far too few to read a hit rate from. The first reading worth
interpreting is the one after several weekly sweeps at the default.

The "one feed page = 20 posts" figure behind the ~400-calls-per-sweep estimate
comes from the earlier discovery probe against `GET /submolts/{name}/feed`, not
from this file. It sets a contention estimate, not a decision gate.

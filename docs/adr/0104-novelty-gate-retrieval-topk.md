# ADR-0104: The Novelty Gate Judges Against Retrieved Candidates, Not the Whole Inventory

## Status

accepted — partially-supersedes ADR-0074

## Date

2026-09-07

## Context

The insight novelty gate (ADR-0074 D6) asks one LLM call "which of these
candidate clusters does an existing skill already cover?". Until now every
judge chunk carried the FULL known inventory — adopted skill files plus the
staged ledger, 485 lines as of the 2026-09-04 run — in the prompt's `{known}`
slot. Two costs followed from that shape:

- The prompt's measured median was **30,516 estimated tokens against a 32,768
  window** (`core/llm/backend.py`, input and output share it) — 93% of the
  window for the whole prompt, of which the inventory is the bulk (RFC-0023
  read it as roughly 70%). The 2026-07-18 weekly run had already overflowed
  the window once and fail-opened all 117 clusters, which is why the packer
  exists at all.
- Judging is "find the needle in the haystack" rather than "compare against a
  few".

RFC-0023 measured retrieval over the same store on 2026-09-04
(`docs/evidence/rfc-0023/`). Retrieval is **not** good enough to be a gate:
recall@5 was 0.61 at best across arms (lexical / bm25 / cosine / RRF fusion),
no similarity threshold separates covered from uncovered clusters (thresholds
drawn from the singleton top-1 distribution mark 85–100% of clusters
"covered" in the `cosine_*` and `bm25_*` arms — the `rrf` arm reads 17–53% and
does not rescue the design — against an LLM covered rate of 0.186 measured
over unrelated historical batches), and generic skills become hubs
(`cosine_full`: 3 skills take 28% of 912 top-1 slots; `bm25_full`: one skill
takes 25%). ADR-0074's finding — that embedding separation for "same theme?"
does not exist — was re-confirmed, not falsified.

That recall was measured in a different configuration from the one shipped
here, and the difference runs the pessimistic way: the reading ranked **57
adopted skill files** (whole file text, median 1,775 chars) against
reviewer-rejected candidate skills, so top-10 was the top 18% of its corpus.
The gate ranks **515 inventory lines** (`name: description`, the line the
judge is shown) against a cluster block, where top-10 is the top 2%. The
dry-run shows the two document representations are not interchangeable
(cluster top-1 p50: 0.7358 for the line, 0.7653 for the file). Recall for the
shipped configuration is therefore **unmeasured**; 0.77 is the nearest
neighbour reading and is used below as an order of magnitude, not a bound.

The remaining question was whether shortening the prompt changes the judge's
answers. A replay answered it on 2026-09-05
(`docs/evidence/rfc-0023/novelty-replay-ab-20260905.md`, 90 calls, one run of
63 comparable clusters reconstructed byte-identically from the audit log):

- Same-arm noise floor: three reps of the unchanged 485-line arm disagreed
  with each other by a symmetric difference of **22.0 clusters of 63** on
  average, and 52% of clusters had a split vote.
- Arm-to-arm difference (485 vs top-5 / top-10 / top-15): **19.3 / 19.8 /
  21.5** — below that floor. The three k values are not distinguishable from
  each other either.
- Prompt size: median **30,516 → 4,364 (k=5) / 5,838 (k=10) / 7,141 (k=15)**
  estimated tokens, −77% to −86%.
- `fail_open_llm`: 1 in 30 full-arm calls (a 28.7k-token call that died after
  269 s), 0 in 60 top-k calls.
- What the replay cannot see: whether the covering skill was in the top k at
  all. That is the recall question above, unmeasured in this configuration —
  the nearest reading (0.77 at k=10, other corpus) says roughly a quarter of
  reviewer-named skills sit outside a top 10, and no small k removes that
  class of miss.

## Decision

1. **Retrieval generates candidates; the LLM still returns the verdict.**
   The `{known}` slot of each judge chunk carries the union of its clusters'
   cosine (nomic) top-k inventory lines instead of the whole inventory. No
   line is dropped by score anywhere else, no similarity threshold is
   introduced, and ADR-0074's judge, output contract (`{"covered": [ids]}`),
   "when in doubt call it NEW" calibration, id validation, per-chunk
   fail-open, and human approval gate are unchanged. The prompt file gains
   one sentence saying the listed themes are the near ones, not the store.
2. **k = 10** (`_NOVELTY_TOPK`). The replay found no accuracy difference
   across k ∈ {5, 10, 15}, so k sits at the low end of the RFC's 10–15 band:
   above it the prompt grows for no measured gain, below it the covering
   skill leaves the window sooner (the 0.77 reading, in its own
   configuration, put roughly a quarter of the reviewer-named skills outside
   the top 10 already).
3. **Ranking rule**: cosine descending, ties broken by name ascending; the
   retrieval document is the rendered inventory line (`name: description`) —
   the same text the judge is shown, so nothing is scored that the prompt
   would not carry. A chunk's known lines are emitted in inventory order, so
   shortening is the only variable the judge sees.
4. **The packer charges each cluster block for the known lines it ADDS.**
   A line another cluster in the same chunk already brought is free, so
   chunk boundaries follow the real prompt cost. A chunk also stops at
   **10 clusters** (`_NOVELTY_MAX_CLUSTERS_PER_CHUNK`) whatever the budget
   allows: the freed ~28k tokens would otherwise pack ~39 clusters into one
   call at the 2026-09-04 scale, which is both an unmeasured judging regime
   (the replay judged 64 clusters in 10 chunks, ~6.4 each) and a six-fold
   increase in what one fail-open costs.
5. **Embedding failure falls back to the full inventory, loudly.** When
   `embed_texts` is unavailable, returns the wrong number of rows, or returns
   a non-finite or zero-norm row (which would silently rank alphabetically),
   the run judges against the whole inventory as before, logs
   `reason=retrieval_unavailable`, and records the fallback in the audit.
   No retry: the gate runs weekly and a degraded reading is worse than a
   larger prompt. **This fallback is the pre-retrieval behaviour, overflow
   included**: at the current 515 lines the inventory alone exceeds the
   budget, so a run without embedding judges nothing and fails every cluster
   open unjudged (`fail_open_budget` — the state the packer already produced
   before this ADR, and the reason retrieval was needed). Extra review load
   at the human gate, never a silently dropped theme; a bounded fallback
   (first k lines, no ranking) was considered and left out because an
   arbitrary slice presented as candidates is a worse input than a stated
   absence of them.
6. **The audit log says what the judge saw** (ADR-0075). Each record gains
   `known_selection` (`mode` topk|full, `k`, `reason`, `embedding_model`) and
   `inventory_count`; `known_themes_count` now means "lines shown to THIS
   chunk" (0 for `fail_open_budget`, which builds no prompt). A reading can
   therefore separate "the judge never saw it" from "the judge saw it and
   called it new" — the failure mode this decision introduces.

## Review-when

- **Candidate recall stops reproducing the reviewer's judgment.**
  `scripts/retrieval_recall_measure.py` is re-run **in the shipped
  configuration** (documents = inventory lines, queries = cluster blocks,
  the current store) and reports recall@10 < 0.8 twice in a row, with the
  script version, the corpus and the reviewer ground-truth set held fixed
  between the two readings. The 2026-09-04 v1 (0.83) / v2 (0.77) pair does
  NOT start this count: the two used different name-resolution code and a
  different corpus shape from the gate's. Widening or dropping k is the
  response — not a similarity threshold.
- **The fallback becomes the normal path**: `known_selection.mode == "full"`
  in a majority of a run's records at the Saturday gate. What needs fixing is
  then the embedding dependency, not the retrieval.
- **The judge's covered rate leaves the band the gate has produced so far.**
  Baseline: the 2026-09-04 run judged 27 covered of 64 clusters (0.42); the
  replay's noise floor says a single run's rate is worth ±0.1 at best (three
  reps of the same prompt gave 26 / 22 / 27 covered). Two consecutive runs
  outside 0.42 ± 0.2 mean the shortening is doing something the replay could
  not see. (The 0.186 figure in the dry-run aggregates 7 runs with a
  different clustering window and is not a per-run baseline.)
- **The inventory stops growing** (retirement outpaces adoption) and fits the
  window again: the mechanism is then unnecessary and should be deleted, not
  tuned.

### Consumption plan

The two audit fields this ADR adds (`known_selection`, `inventory_count`) are
an audit surface, so ADR-0101 applies.

- **(a) Who reads them, when**: the Saturday `/weekly-gate`, from
  `logs/insight-novelty.jsonl` of the week's insight run — one line per chunk,
  read together with the existing `verdict` counts.
- **(b) What number of readings decides what**: two readings decide the second
  and third Review-when triggers above (fallback majority; covered rate out of
  band). A single reading decides nothing.
- **(c) Removal**: the fields go when the mechanism goes — either the
  inventory shrinks back inside the window (trigger 4, retrieval deleted) or
  retrieval is replaced. If four consecutive weekly gates read
  `mode == "topk"` with no anomaly, `known_selection` collapses to the reason
  code alone (`mode` and `k` become derivable from this ADR) and
  `inventory_count` stays, since it is the denominator the other triggers need.

## Alternatives Considered

**Keep the full inventory.** Rejected on cost, not accuracy: a prompt filling
93% of the window whose accuracy is indistinguishable from the 4–7k version,
plus the one observed `fail_open_llm` on a 28.7k-token call and a growing
store that walks back into the 2026-07-18 overflow.

**Make retrieval the gate (drop clusters whose top-1 similarity is high).**
Rejected by measurement: no threshold separates the populations (in the
`cosine_*` / `bm25_*` arms 85–100% of clusters fall "covered" at thresholds
drawn from the singleton distribution, against a historical LLM covered rate
of 0.186), and the hub reading says the least specific skill would suppress
the most clusters (`bm25_full`: one generic skill takes 25% of all top-1
slots). This is ADR-0074's finding, re-confirmed.

**Fuse BM25 with cosine (RRF).** Rejected: fusion did not beat cosine alone at
any rrf_k in the v2 reading (recall@10 0.76 vs 0.77), so it adds an index and
a parameter for nothing. BM25 stays available in the measurement scripts.

**k = 15, or k tuned per run.** Rejected for now: the replay cannot tell the k
values apart, so a larger k buys prompt size against noise. A per-run k would
need a signal the readings do not provide.

**Retry the embedding call before falling back.** Rejected: the gate is
weekly and the fallback is correct-if-expensive, so a retry only lengthens a
failing run. The measurement script retries because a stopped reading has no
fallback; production has one.

## Consequences

- The judge prompt drops from ~30.5k to ~5.8k estimated tokens at k=10 on the
  2026-09-04-sized store. `fail_open_budget` stops firing on the normal path
  and stays reachable on the fallback one (D5), which is why the code that
  handles it stays.
- A new dependency in the gate's hot path: the embedding host. Its failure is
  a logged, audited degradation to the old behaviour — never a silent one.
  At the present inventory size that old behaviour no longer judges anything
  (D5), so an embedding outage costs the week's verdicts and hands the whole
  batch to the human gate unjudged. That is a real operational cost of this
  decision, pinned by
  `tests/test_insight.py::TestNoveltyFullInventoryFallbackAtScale`.
- A recurring cost the old shape did not pay: every run embeds the whole
  inventory plus one query per cluster, in batches of 64 with no cache (the
  inventory is re-embedded each run). At 515 lines this is seconds, and it
  competes with the resident generation model inside the weekly window — a
  large single POST has been refused by Ollama in exactly that state
  (2026-09-05, the replay script's batching note), which is why the batch
  size is small. Caching the inventory vectors is a later change with its own
  invalidation question (an edited description must re-embed); it is not
  taken here.
- **New failure mode**: a covering skill outside a cluster's top 10 is
  invisible to the judge, so a duplicate skill can reach the human gate that
  the full-inventory prompt might have caught. Its size is unmeasured in this
  configuration (see Context); the replay bounds the *aggregate* effect
  instead — every cluster the full arm covered unanimously was covered by at
  least one top-k rep. The human approval gate remains the last filter, and
  `known_selection` in the audit is what a post-hoc reading uses to attribute
  such a case.
- `scripts/novelty_replay_ab.py` reconstructs a run by requiring one shared
  inventory across its records — a pre-existing guard, untouched here, that
  stops with an explicit error rather than comparing unlike chunks when
  pointed at a top-k run. It is frozen evidence for the 2026-09-04 run and was
  not migrated.
  `scripts/novelty_retrieval_dry_run.py` reads only `verdict` / `covered` and
  is unaffected.
- Chaos coverage gains one row (F-NOV-6, embedding host down) at an inventory
  that still fits; the at-scale fallback is pinned separately in
  `tests/test_insight.py`. The existing fail-open rows are unchanged.
- The prompt file changed, so the ADR-0089 eval baseline
  (`comment_golden-2026-08-31.json`) reads STALE until it is re-run and
  re-approved. `verify.sh` reports this as advisory; the re-run is a human
  decision, not part of this change.
- RFC-0023's rare lane (singletons whose nearest skill is far, held for
  weekly re-clustering) is NOT part of this change and remains open.

## References

- [ADR-0074](./0074-weekly-staged-insight.md) — the novelty gate this
  partially supersedes: its 2026-07-18 Amendment D1 ("every chunk sees all
  known themes") no longer holds, and a dated note there points here. Its
  "embedding separation does not exist" finding is re-confirmed, not
  retired
- [ADR-0075](./0075-observability-by-default.md) — the audit record whose
  schema gains `known_selection` / `inventory_count`
- [ADR-0101](./0101-instrument-dissolution-mandate.md) — the audit fields
  added here are consumed by the Saturday gate readings named in Review-when
- [RFC-0023](../../rfcs/0023-novelty-gate-retrieval-and-rare-lane.md) — the
  proposal, the 2026-09-05 decision, and the rare lane left open
- `docs/evidence/rfc-0023/novelty-replay-ab-20260905.md` — the 90-call replay
  (noise floor, arm differences, prompt sizes, fail-open counts)
- `docs/evidence/rfc-0023/retrieval-recall-v2-rrf5-20260904.json` and
  `novelty-retrieval-dry-run-20260904.json` — recall by arm, and the
  threshold / hub readings that keep retrieval out of the gate

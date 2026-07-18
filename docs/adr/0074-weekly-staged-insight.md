# ADR-0074: Weekly Staged Insight — Theme Detection, Pending Guard, Marker-on-Stage, LLM Novelty Gate, Exact Fast Clustering

## Status

accepted

## Date

2026-07-09

## Context

`insight` last ran on 2026-05-30 (audit.jsonl). Since then
[ADR-0060](./0060-per-episode-grounded-distill.md)'s per-episode distill has
raised pattern inflow to ~90–115/day; on 2026-07-09 the live non-gated pool
stood at 1,798 patterns. The extraction design — one-shot global recluster,
one skill per cluster, `MAX_BATCH=10` slice, dropped singletons never
re-clustered — was sized for a static few-hundred-pattern corpus. The scale
mismatch is structural, not a one-off: any batch window exceeds the design
envelope within weeks.

Four defects compounded it, all confirmed on live data
([evidence](../evidence/adr-0074/window-simulation-20260709.md)):

1. **Lost marker, silent full recluster.** The `.last_insight` marker
   disappeared when skill-stocktake rebuilt `skills/` on 2026-06-02. The
   incremental path silently fell back to "process all patterns" — bypassing
   the `FULL_RECLUSTER_WARN_N` advisory, which was wired only to the `--full`
   branch.
2. **Naive merge cost.** The submatrix-mean agglomeration measured 17.2 s at
   N=293; at N=1,798 (~O(N³), Python-loop dominated) it extrapolates to hours
   before the first LLM call.
3. **Staging wipe + frozen marker.** `_stage_results` wiped the staging dir on
   every call, so a scheduled run would silently destroy an unreviewed batch;
   and the `--stage` path never called `write_last_insight`, so staged runs
   reprocessed the same ever-growing window forever.
4. **No novelty control.** Window simulations produced 26 (3-day), 65
   (7-day), and 118 (14-day) clusters ≥ 3; adjacent 4-day windows matched
   32/32 clusters at centroid cosine 0.795–0.90 — every window reproduces the
   corpus's ~30 standing themes. Without a novelty gate, each run re-stages
   the same candidates.

A calibration attempt showed the novelty question cannot be answered by
embeddings: same-theme adjacent-window matches and distinct-theme
intra-window neighbours fully overlap at both the centroid level (0.795–0.902
vs median 0.830) and the member-mean level (0.646–0.709 vs up to 0.698). In a
vocabulary-homogeneous corpus, "is this cluster's theme already skilled?" is a
semantic question — the same lesson as
[ADR-0036](./0036-sunset-skill-as-memory-loop.md) (similarity ≠ applicability)
and [ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.md) (stocktake's revert from
vapor-dominated cosine to a single LLM grouping call).

One constraint anchors the redesign: the skill store is all-injected into the
action-time system prompt, so it must stay small. At ~100 patterns/day in and
a handful of skills total, insight's role cannot be "convert knowledge to
skills proportionally" — it is **detecting when a new stable theme has
accumulated**.

## Decision

1. **Weekly staged cadence.** `install-schedule --weekly-insight` installs a
   launchd job (default Mon 08:00 — one hour before weekly-analysis, outside
   the 0/6/12/18 agent-session hours) running `insight --stage`. Candidates
   land in staging; the operator reviews them per item with `adopt-staged`
   (interactive, TTY) in the same weekly ritual as the analysis report.
2. **Exact fast clustering.** `_merge_clusters` now runs the identical
   average-linkage agglomeration via the Lance-Williams update — one
   vectorized row update per merge instead of a Python rescan of every
   cluster pair. Partitions are unchanged (equivalence pinned in tests
   against a port of the naive implementation); N=1,798 clusters in under a
   second. This delivers the review-2026-06-27 M4 upgrade now that it is
   measured.
3. **Marker guard.** A missing `.last_insight` marker refuses the incremental
   run with an explicit message instead of silently reclustering the whole
   corpus. `--full` remains the deliberate whole-pool path (its warning now
   speaks of review-batch size, the cost that actually scales).
4. **Pending guard.** `_stage_results` refuses to write (and no longer wipes)
   when unreviewed `*.meta.json` items sit in staging; the insight handler
   fast-fails on the same condition *before* extraction so a blocked run
   costs zero LLM calls. Invariant: staging holds at most one unreviewed
   batch. A skipped review week makes the scheduled run a no-op; the next
   successful run covers the accumulated window (clustering is cheap now).
   Cross-model review hardening (codex, 2026-07-09): guard + wipe + write
   run under a non-blocking `flock` (`.staged.lock`, outside the staging
   dir) because the bare guard is a check-then-act race between the weekly
   launchd job and a manual run; and `adopt-staged` **quarantines** invalid
   sidecars (rename to `*.meta.json.invalid`, bytes preserved) instead of
   leaving them in place, where a single corrupt sidecar would count as
   pending forever and permanently block every staging producer.
5. **Marker advances at review-submission, not adoption.** `insight --stage`
   writes the marker after staging succeeds; the interactive path writes it
   after the approval loop completes regardless of how many candidates were
   accepted. Rejection is a verdict on the skill, not an instruction to
   reprocess the patterns — and the measured recurrence guarantees a
   mistakenly rejected real theme returns through new patterns.
6. **LLM novelty gate.** After clustering and before extraction, one grouping
   call (`insight_novelty.md` + `insight_novelty_system.md`; judgment
   paragraph authored by the executing model, prompt-model-match) compares
   candidate clusters (3 sample patterns each) against the known-theme
   inventory: adopted skill frontmatter (`skills/*.md`) plus the staged
   ledger. Covered clusters are skipped (`skipped_known` in the result);
   the gate **fails open** — an LLM failure or unparseable verdict keeps all
   clusters, because the human gate catches duplicates but a wrongly
   suppressed theme is never seen. When every cluster is covered the run
   returns an empty result and still advances the marker.
7. **Staged ledger.** `logs/insight-staged.jsonl` records one
   `{ts, name, description, filename}` row per candidate that reached review,
   decision-agnostic (ADR-0012's audit log stays the approval record; the
   ledger is the novelty gate's memory). Generation itself remains
   unconditioned on the skill corpus (audit H6): the gate reads themes, the
   extraction prompt never does. Write ordering (codex, 2026-07-09): ledger
   first, marker last — a failure between the two leaves the window
   unconsumed rather than consumed-but-unremembered.
8. **Vocabulary discipline in extraction.** `insight_extraction.md` gains a
   model-authored "Naming and vocabulary" section banning decorative
   prefixes (`fluid-`/`dynamic-`) and recycled abstractions. This reopens the
   2026-05-30 "root D" acceptance deliberately: that acceptance predated
   [ADR-0072](./0072-echo-chamber-interventions.md)'s proof that upstream
   register instructions measurably shift output.
9. **Singleton rescue closed as "no rescue".** The re-cluster-lane question
   left open by the 2026-07-03 checkpoint is resolved by the recurrence
   evidence: real themes re-cross the `min_size=3` floor in later windows,
   so a dropped singleton is deferred, not lost. The 7-day window keeps the
   sensitivity floor at ~0.4 patterns/day per theme while staying under the
   `MAX_BATCH` truncation regime (demoted tails: 0 at 3d, 4 at 7d, 47 at
   14d).
10. **Bootstrap.** The operator recreates the marker at 2026-07-02 (a 7-day
    first window) and runs the first `insight --stage` manually off-schedule.
    The first review batch is a one-time standing-theme snapshot (upper
    bound ~65 candidates); every later week stages only novel themes.

## Alternatives Considered

- **Selective skill loading** (proposed trigger of this cycle): rejected —
  it regenerates the ADR-0036 router and does not change what is in the
  corpus; a homogeneous corpus yields the same vocabulary from any loaded
  slice. The all-injected values reading (2026-06-01) stands.
- **Embedding novelty gate** (centroid or member-mean vs a stored ledger):
  rejected on calibration — no separation exists between same-theme and
  distinct-theme similarities on this corpus (evidence dir). Deciding theme
  coverage is semantic → LLM, per the mechanism-vs-value split.
- **Priority-queue speedup alone, keeping one-shot full recluster as the
  operating mode**: rejected — solves cost but leaves the candidate flood,
  the `MAX_BATCH` truncation of giant clusters, and the review burden
  untouched.
- **Marker advance at adoption time**: rejected — a reject-all review would
  reprocess the same patterns and re-stage the same candidates next run,
  looping the reviewer.
- **Per-run staging subdirectories** instead of the pending guard: rejected —
  unbounded accumulation of mostly-duplicate batches; the guard plus the
  ledger keeps one batch pending and remembers considered themes.
- **Streaming assignment of new patterns to skill centroids** (views with
  skills as consumers): deferred — architecturally attractive under
  ADR-0019's "classification is a query", but a large rework, and the same
  embedding-separation evidence that killed the embedding gate undercuts
  centroid assignment today.

## Consequences

- Steady state: one weekly run, seconds of clustering, one novelty call, LLM
  generation only for genuinely new themes; quiet weeks print "0 novel
  clusters" and advance the marker.
- The pending guard also protects skill-stocktake / rules-distill /
  distill-identity staging (shared `_stage_results`); their marker semantics
  are unchanged in this ADR.
- First staged run is a deliberately heavy one-time review (standing-theme
  snapshot). The reviewer should expect dozens of candidates once, then a
  trickle.
- New runtime artifact: `logs/insight-staged.jsonl` (0600, append-only).
  New prompts: `insight_novelty.md`, `insight_novelty_system.md` — loaded
  prompt count 32 → 34 (canonical inventory:
  `docs/CONFIGURATION.md#pipeline-prompts--view-seeds`, updated in this
  change).
- `insight` without a marker now errors where it previously "worked" — an
  intentional behavioural break documented in the error message itself.
- Evidence (window simulations, calibration numbers, equivalence method):
  [docs/evidence/adr-0074/](../evidence/adr-0074/window-simulation-20260709.md).

## Amendment (2026-07-18): token-bounded chunked judging + fail-open extraction cap

### Context

The first scheduled weekly run (2026-07-17T23:00 UTC) exposed a capacity
failure in Decision 6: the single novelty call packed the full known-theme
inventory (60 themes) plus 117 cluster samples into one 40,074-token prompt
against the 32,768-token window. `llm.py`'s C2 preflight refused the call
(no output floor left), the gate followed its fail-open policy, and all 117
clusters flowed to extraction — 106 staged candidates, reviewed
**0 adopted / 106 rejected** (`.notes/insight-candidate-review-2026-07-18.md`,
archive `insight-staged-20260718-before-review.tar.gz`). The mismatch is
steady-state, not first-run-only: the incremental window averages ~118 new
live patterns/day, and the known inventory grows monotonically because the
ledger is decision-agnostic.

### Decision

1. **Token-bounded chunked judging.** The judge prompt is split into
   budgeted chunks (`_pack_novelty_chunks`): greedy, deterministic,
   order-preserving packing of cluster blocks under
   `window − output reserve (2048) − fixed cost`, where the fixed cost is
   the template plus the FULL known inventory (every chunk sees all known
   themes; only the cluster blocks are partitioned). Covered ids are
   validated per chunk — a judge cannot suppress a cluster it was not
   shown. Fail-open becomes **per chunk**: an LLM failure or unparseable
   verdict keeps only that chunk's clusters unjudged; other chunks'
   verdicts stand. A cluster block that alone exceeds the budget is retried
   with truncated samples, then fails open individually
   (`fail_open_budget`) — the audit signal that the known inventory has
   outgrown chunking and a retrieval-assisted gate needs (re)evaluation.
   Replay of the incident prompt: 2 chunks (86 + 31 clusters), both within
   budget, no cluster lost.
2. **Fail-open extraction cap.** Clusters that reach extraction UNJUDGED
   (through a fail-open chunk) are bounded at
   `MOLTBOOK_INSIGHT_FAILOPEN_CAP` (default 20) by a deterministic,
   code-owned priority (member count desc → time-decay importance sum desc
   → topic name). Judged-novel clusters are never capped, so normal weeks
   are unlimited — the cap is a review-budget circuit breaker for broken
   gates, not a quality filter (the operator's no-numeric-caps rule).
   Deferred clusters are not extracted, not staged and **not
   ledger-written** — "considered" status is never granted to a theme no
   human saw — so a real theme recurs in a later window and gets judged
   then (Decision 9's recurrence evidence). Every deferral is recorded in
   `insight-novelty.jsonl` (`reason=review_budget_deferred`, with topics,
   sizes and pattern ids); nothing is silently truncated.
3. **Audit schema.** `insight-novelty.jsonl` records one row per chunk
   (`batch_index` / `batch_count` added), verdict vocabulary extended with
   `fail_open_budget` (a separate event type outside the chunk sequence —
   its batch fields are null, cross-model review 2026-07-18), plus the
   deferral record above. Existing fields are unchanged, so prior records
   remain replayable. The packing budget follows the same context-window
   source as the generate preflight (an injected backend advertising a
   smaller window lowers it), so a packed chunk is never refused by the
   preflight it was sized for.

### Explicitly out of scope

This amendment does **not** reverse the embedding-gate rejection: no
similarity threshold suppresses anything. Retrieval-assisted judging
(embedding as enumeration, LLM as verdict), daily consolidation layers, and
`recall@k` evaluation stay open questions
(`.notes/insight-novelty-gate-redesign-open-questions-2026-07-18.md`),
deliberately deferred until the ADR-0076 skill-selection shadow reading
(~2026-07-24) settles the injection economics and the next scheduled run
measures whether chunking alone suffices — the 106 rejected candidates now
sit in the ledger as known themes, so the gate's first judged run is the
natural experiment.

### Consequences

- The 2026-07-18 failure shape becomes structurally impossible: an
  oversized window costs more judge calls (one per chunk), and a broken
  gate floods review with at most 20 candidates instead of 106.
- Weekly cost in the current regime: ~2–5 judge calls instead of 1.
- Fault column: `tests/test_insight_chaos.py` (F-NOV-1..5 — chunk-isolated
  fail-open for backend loss / malformed / truncated output, budget
  overflow without a call, cap after total fail-open) per ADR-0077.

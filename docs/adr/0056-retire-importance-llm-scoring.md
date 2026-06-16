# ADR-0056: Retire the Distill-Time Importance LLM Rating — Extraction Weight Is Pure Time Decay

## Status

accepted

## Date

2026-06-17

## Context

[ADR-0053](./0053-importance-encoding-time-significance.md) redefined the stored `importance`
field as a record of encoding-time significance and, in Decision 6, established a **measurement
gate** for retiring the distill-time LLM rating while keeping pure time decay. The gate carried
the evidence already collected — an ablation on 764 production patterns (Kendall tau 0.851 vs a
decay-only variant, identical top-3/top-5 insight batch order, ≤1-of-10 kept-set swaps) — but
deferred the retirement decision behind one open condition: the §B1 threshold-retune observation
window closing (experiment hygiene — one pipeline variable at a time). A second gate, the AKC
position paper shipping, was removed by ADR-0053's same-day amendment.

As of 2026-06-17 all gate conditions are met:

- **§B1 window closed and validated.** The 2026-06-05 relevance retune was confirmed effective
  over a 12-day window (`.notes/b1-retune-effect-2026-06-17.md`): pass rate 26.9% → 57.7%, comment
  frequency recovered, no clamp contamination. The observation window is no longer open, so a
  second variable can be introduced.
- **Ablation re-run on the grown corpus.** Re-running
  `docs/evidence/adr-0053/importance-ablation.py` against 822 patterns (up from 764) holds the
  pre-registered "small difference" criterion: Kendall tau **0.843**, identical top-3/top-5 batch
  order, at most 2-of-12 kept-set swaps. The LLM rating's marginal contribution beyond decay
  remains ~zero.

The propagation map (ADR-0053 Decision 5) confirms `importance` is consulted in exactly two
places — insight cluster ordering / intra-cluster slice (`clustering.py`, `insight.py`) and the
dedup floor (`distill.py`) — and nowhere in retrieval (`views._rank` is pure cosine since
ADR-0051) or curation. The LLM rating costs one constrained-decoding call per distill batch and
buys, on the current corpus, nothing the insight pipeline can observe.

## Decision

1. **`effective_importance` is pure time decay.** The base-rate multiply is dropped:
   `effective_importance = 0.95^days_elapsed` (known timestamp) or `0.1` (unknown timestamp).
   The stored `importance` value is no longer read. This is the load-bearing change — it makes the
   whole corpus, old rows included, behave exactly as the ablation's `decay-only` variant.
   Post-change the ablation's `current` and `decay-only` policies are identical (tau = 1.000, zero
   demotion swaps), confirming the retirement *is* the validated variant rather than an
   approximation of it.

2. **Remove the distill-time importance LLM call.** `_score_importance`, `_parse_importance_scores`,
   `IMPORTANCE_SCHEMA`, the `DISTILL_IMPORTANCE_PROMPT` template (`config/prompts/distill_importance.md`),
   its `prompts.py` / `domain.py` registrations, and the `evals/` step-3 regression suite are
   deleted. The distill pipeline is now **2-step** (extract → summarize) rather than 3-step.

3. **The `importance` field is no longer written.** `add_learned_pattern` drops the parameter and
   the entry key; `_entry_from_dict` no longer restores it. A legacy row carrying `importance`
   sheds it on the next save (zero information loss — the field is a defunct rating, not a
   reconstructable function of preserved data), exactly as ADR-0051 shed `trust_score`.

4. **The three judgment points of ADR-0053 collapse to two.** Encoding-time significance (distill
   time, LLM) is retired. The surviving two are untouched: current relevance (query time, embedding
   cosine) and promotion worth (insight time — the LLM still accepts or drops each full cluster on
   its merits; `insight.py:124` "drops the cluster if no skill can be distilled"). The stored score
   only ever pre-ordered the insight queue; that queue is now ordered by recency alone.

5. **Dedup-floor re-entry becomes time-uniform.** `DEDUP_IMPORTANCE_FLOOR` (0.05) now drops a row
   from the dedup comparison scope at a single age — `0.95^days < 0.05` ⇒ ~58 days — for every
   pattern, instead of 14–58 days modulated by the (now-retired) rating. This is a direct,
   analytic consequence of Decision 1, not a separate measurement: re-observation re-entry
   (ADR-0053 Decision 4) is governed by time alone. Honoring the retired signal only for re-entry
   timing would be the inconsistency; uniform time-governed re-entry is the coherent outcome.

## Alternatives Considered

### Thin retire — stop writing the score but keep `effective_importance` reading the base

Neutralize only the write path (store a constant), leaving the read formula `importance × decay`.
Rejected: legacy rows retain their LLM scores, so old high-rated patterns keep out-ranking new
ones — the corpus would *not* match the ablation's decay-only variant that justifies this decision,
and the dead plumbing (threading a constant through batch / dedup / store) would remain. Retiring
the read is what makes old and new patterns uniform.

### Keep the status quo — document the propagation map only

Leave the LLM call in place and accept the per-batch cost. Rejected: the ablation has now been run
twice across a growing corpus with the same verdict; keeping a call that demonstrably changes
nothing the pipeline observes contradicts the project's bias toward removing inert mechanism
(simplicity over fossils).

### Migrate existing scores to a fixed baseline

Rewrite every stored `importance` to a constant in a one-shot migration. Rejected: unnecessary —
dropping the read makes the stored value inert immediately, and rows shed the field naturally on
the next save. A migration command would be code to write, run, and then retire.

## Consequences

### Positive

- One fewer LLM call per distill batch (3 → 2 steps); lower latency and less constrained-decoding
  surface, with no measured loss of insight quality.
- Documentation and implementation agree: ADR-0053's "encoding-time significance" judgment point is
  explicitly closed rather than left as a redefined-but-inert field.
- Net code removal — the scoring function, parser, schema, prompt, eval suite, and the
  importance-threading through the dedup/store pipeline all go.

### Negative

- A row's dedup-scope lifetime is now uniform (~58 days) rather than importance-modulated. A
  pattern the old LLM rated low used to leave dedup scope sooner (~14 days) and thus allow a
  re-observation to re-enter as fresh sooner; that earlier second chance is gone. This is a
  deliberate, documented cost — the earlier timing was itself driven by the signal being retired.

### Neutral / Follow-ups

- `graph.jsonld` gains an ADR-0056 node (`refines` ADR-0053, `alignsWith` ADR-0051); the ADR-0009
  and ADR-0053 node descriptions and the AKC phase-mapping node (distill "3-step … + importance" →
  "2-step") are updated in the same change per the dual-update convention.
- `docs/CODEMAPS/` Data Flow (distill Step 3, insight ordering, `effective_importance`) is refreshed
  in the same PR per the CLAUDE.md freshness rule.
- `docs/evidence/adr-0053/importance-ablation-20260606.md` records the 2026-06-17 re-run and the
  post-change identity (tau = 1.000).
- AKC is unaffected: ADR-0053's amendment closed the AKC P1-5 promotion question as won't-do and
  established that AKC — the position paper included — does not cover the importance mechanism.

## Related

- [ADR-0053](./0053-importance-encoding-time-significance.md) — Importance as Encoding-Time
  Significance; established the measurement gate this ADR satisfies. Its three-judgment-point
  canonicalization is reduced to two here; its decay design, write-once stance, and
  promotion-by-re-extraction survive.
- [ADR-0009](./0009-importance-score.md) — Importance Score; the rating originates here. Its decay
  factor is the sole survivor; the LLM rating it introduced is retired.
- [ADR-0051](./0051-retire-trust-weighting.md) — Retire Trust Weighting; the precedent for shedding
  a retired ranking factor on next save and for "origin is recorded, never weighted." After this
  ADR, `effective_importance` is the bare `0.95^days` that ADR-0051's Neutral section anticipated.
- [ADR-0026](./0026-retire-discrete-categories.md) / [ADR-0027](./0027-noise-as-seed.md) — the
  embedding admit gate that owns the binary keep/drop decision importance was never used for.
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — named the self-reingestion echo
  loop; the re-observation mechanism in Decision 5 stays write-once to avoid that surface.
- `docs/evidence/adr-0053/importance-ablation-20260606.md` — ablation evidence; the 2026-06-06 run
  and 2026-06-17 re-run that satisfy the gate.

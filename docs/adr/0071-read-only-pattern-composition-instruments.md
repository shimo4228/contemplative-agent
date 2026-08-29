# ADR-0071: Read-Only Pattern-Composition Instruments (View Supply / Diversity / Grounding)

## Status

accepted

## Date

2026-07-03

## Context

Memory-distillation pipelines across the field are converging on the same
three-layer-plus-distill structure — surveyed in arXiv 2512.13564, "Memory
in the Age of AI Agents," and formalized as a write–manage–read loop in
arXiv 2603.07670. This repo's differentiator
against that convergence is the views layer
([ADR-0019](./0019-discrete-categories-to-embedding-views.md)). An audit
found that differentiator is mostly unused: of the 7 shipped views, only 2
are actually queried — `self_reflection` by `distill-identity` (`distill.py`)
and `constitutional` by `amend-constitution` (`constitution.py`). The other
five — `noise`, `communication`, `reasoning`, `social`, `technical` (former
insight batch axes and the former ingest noise gate) — are orphaned
definitions consumed by nothing.

The audit also found documentation asserting a mechanism that does not
exist: `distill.py`'s comment and `docs/CODEMAPS/` (`architecture.md`,
`core-modules.md`) claimed a query-time noise-view filter and per-pattern
view telemetry fields (`last_view_matches`, `last_classified_at`) that are
not present in code. This is not stale wording around a real mechanism — it
is documentation describing a live mechanism that is fiction.

Three open observations were sitting without data to resolve them. First, an
echo-chamber / register-collapse effect forming at the distill stage
(handoff 2026-06-22) —
[ADR-0057](./0057-identity-from-self-reflection-corpus-alone.md),
[ADR-0058](./0058-value-injection-at-action-time.md), and
[ADR-0060](./0060-per-episode-grounded-distill.md) corrected course on it,
but the effect itself was never quantified. Second, review 2026-06-27
finding M3: `insight` silently drops singleton patterns, and a rescue lane
for them needs a floor chosen from the real distribution, not a guess.
Third, review 2026-06-27 finding M2: `epistemic_counts.observed` is
structurally zero after ADR-0060 and gets misread as "no external
grounding," when it is in fact an artifact of the schema change.

The production generation model had swapped to `gemma4:e4b` five days
earlier
([ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md)),
which means any behavior change made now, without a baseline, would be
unattributable to the swap versus the change itself. The operator's
response was to sequence the work: instrument first, intervene second —
quantify the current state, then choose interventions from the readings
rather than from intuition.

## Decision

1. **Add `core/view_metrics.py`.** A new read-only pattern-composition
   instrument module; nothing else in the pipeline changes behavior.
2. **Measure view supply for the two consumed views only.** Compute
   cosine-to-seed distributions — pass rate at the view threshold,
   p50/p90/max — restricted to
   `CONSUMED_VIEWS = (self_reflection, constitutional)`. Do not measure the
   five unconsumed views: a distribution over an orphaned seed measures
   seed staleness, not corpus structure, and its reading changes no
   downstream action (signal-first).
3. **Measure seed-independent diversity as the echo-chamber detector.**
   Compute pairwise-cosine homogeneity (mean/p50/p90) plus the cluster
   structure `insight` would see, using the same threshold/min/max AND the
   same `gated`-row exclusion as `insight` (codex review P2); skip cluster
   stats above `CLUSTER_STATS_MAX_N=500` (mirrors
   `insight.FULL_RECLUSTER_WARN_N`, kept as a literal to avoid an import
   cycle and cross-checked by a test). Rising homogeneity + supply
   concentration + inward grounding together read as register collapse,
   without any hand-written axis.
4. **Measure grounding composition.** Tally provenance `source_type`, the
   ADR-0050 epistemic tally (carrying the explicit caveat that
   `observed == 0` is structural post-ADR-0060, per review 2026-06-27 M2),
   and the legacy gated count.
5. **Wire the instruments into three call sites, not into behavior.**
   `distill --dry-run` logs the instruments for the would-be-added set —
   post-dedup, so skipped duplicates are not counted (codex review P3) —
   through a new public param `instrument_views` (deliberately not named
   `view_registry`, to respect the ADR-0060 regression test that pins the
   gate-era threading out of `distill`'s signature). `report --patterns`
   (new opt-in flag) renders the same instruments over the whole live pool.
   `insight` logs dropped singletons with their nearest consumed view via
   `nearest_view` (`extract_insight` gains `instrument_views`).
6. **Keep every instrument observability-only.** Distributions and
   compositions are for the operator; none feed gates, ranking, retrieval,
   or promotion — the same shape as AKC ADR-0015 Decision 2 (visibility
   without intervention), consistent with this repo's
   [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) /
   [ADR-0051](./0051-retire-trust-weighting.md) rejections of metric
   write-back. Instrument output carries a fixed ambiguity note (empty/low
   supply = missing patterns OR a stale seed, undecidable by the instrument
   itself), per the AKC ADR-0016 lesson that a systematically biased
   instrument is worse than none. Instruments also degrade instead of
   raising — a malformed or wrong-dimension embedding row is skipped with a
   WARNING, never allowed to abort the host command (python-reviewer
   CRITICAL, 2026-07-03) — and bound their own memory (pairwise stats run on
   a deterministic stride sample above `PAIRWISE_STATS_MAX_N=3000`).
7. **Correct the stale documentation in the same change.** Fix the
   `distill.py` comment, the `insight.py` module docstring, the Data Flow
   section of `architecture.md`, and the schema example in
   `core-modules.md`.

> **Note (2026-08-29, ADR-0101)**: the dissolution mandate — every new
> instrument states a consumption plan — was added as this ADR's balancing
> rule; ADR-0101 names this ADR as the rule's eventual home.

## Alternatives Considered

### Measure all 7 views as instrument axes

Rejected by the operator during planning: the 5 orphaned seeds have no
consumer, so a coverage distribution over them answers no action — it
mostly measures how stale the seed text is (a signal-first violation).
Their disposition (prune / reseed / promote clusters into new views with
consumers) is deferred to the intervention phase, with readings in hand.

### Implement interventions directly, without instruments first

Rejected: a rare-singleton rescue lane, a seed rewrite, or view pruning
would have their floors and designs chosen blind (the numeric-cap
anti-pattern), and — five days after the gemma4:e4b swap — any resulting
behavior change would be unattributable to the intervention versus the
model swap.

### Adopt an embedding-drift monitoring stack (evidently, whylogs)

Rejected: the pandas/scikit-learn dependency footprint conflicts with the
requests+numpy-only policy, and reference-vs-current drift primitives
answer a different question than per-view membership against fixed seed
embeddings. The needed aggregation is ~100 lines over already-stored
vectors — search-first verdict: Build.

### Re-wire the orphaned topic views into insight batching

Rejected: this re-litigates the settled move from predefined view axes to
bottom-up embedding clustering. If topical views return, they should be
grown from observed cluster structure and given a consumer first — a
candidate for the intervention phase, shaped like the AKC cycle's Promote
phase.

### Keep a production-run instrument (log instruments on every scheduled distill)

Deferred, not rejected: phase 1 scopes instruments to `distill --dry-run`
and the opt-in `report` flag. Longitudinal wiring into every scheduled run
is a cheap follow-up once the readings prove useful.

## Consequences

### Positive

- First corpus baseline is immediately actionable — live pool n=1463:
  `self_reflection` supply 1108/1463 (76%) and `constitutional` 986/1463
  (67%) pass at threshold 0.55 with near-identical distributions (p50=0.58,
  p90=0.64 both), while corpus pairwise cosine mean/p50=0.554 — i.e. the
  view threshold sits at the corpus homogeneity floor and `top_k` does all
  the real selection.
- A same-day control experiment (three unrelated texts: floor 0.33–0.46
  vs. corpus, 0.42–0.52 vs. seeds) shows the homogeneity is genuinely
  ~0.1–0.2 above the embedding-model floor — a real echo signature, not
  nomic-embed anisotropy — and that 0.55 does reject truly foreign text.
- Grounding composition surfaced `external_reply=0` among live patterns and
  195 legacy gated rows.
- These readings give the intervention phase calibrated evidence (floor /
  corpus mean / view top ≈ 0.68–0.77).
- Singleton visibility (importance distribution + nearest consumed view)
  turns the M3 rescue-lane design into a data-driven choice.
- Documentation no longer claims fictional mechanisms.

### Negative

- ~330 new lines plus tests to maintain.
- The `CLUSTER_STATS_MAX_N` mirror constant can drift from
  `insight.FULL_RECLUSTER_WARN_N` — guarded by a test, not by an import.
- Instruments themselves improve nothing: if the readings are ignored, the
  only value delivered is honest docs.
- Operators must resist wiring these numbers into gates; the module
  docstring, this ADR, and the output's ambiguity note are the only guard
  against that.

### Neutral / Follow-ups

- `report --patterns` is opt-in and costs two seed embeddings via Ollama.
- Scheduled production runs are byte-identical in behavior — instruments
  fire only on the dry-run and opt-in paths.
- The ADR-0060 regression test still pins the gate-era signature out of
  `distill`.

## References

- arXiv 2512.13564 — "Memory in the Age of AI Agents"
- arXiv 2603.07670 — "Memory for Autonomous LLM Agents": formalizes agent
  memory as a write–manage–read loop
- AKC ADR-0015 — Decision 2, visibility without intervention
  (github.com/shimo4228/agent-knowledge-cycle)
- AKC ADR-0016 — a systematically biased instrument is worse than none
  (github.com/shimo4228/agent-knowledge-cycle)
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — the views
  layer this repo differentiates on
- [ADR-0031](./0031-classification-as-query.md)
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — epistemic
  tally consumed by the grounding-composition instrument
- [ADR-0051](./0051-retire-trust-weighting.md) — prior rejection of metric
  write-back
- [ADR-0056](./0056-retire-importance-llm-scoring.md)
- [ADR-0060](./0060-per-episode-grounded-distill.md) — gate-era `distill`
  signature; source of `epistemic_counts.observed == 0`
- [ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md)
  — production model swap that made uninstrumented interventions
  unattributable
- review 2026-06-27 — M2 (`epistemic_counts.observed`), M3 (singleton drop)

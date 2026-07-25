---
name: read-only-instruments
description: Design know-how for read-only instruments (計器) — aggregate readings over stored state (distributions, compositions, cluster structure) that inform the operator before an intervention, in the style of ADR-0071's pattern-composition instruments. Use when quantifying an open observation before intervening (instrument-first sequencing), when a design floor/threshold would otherwise be guessed, when calibrating an embedding-based reading (three-point scale), or when deciding whether to build OR remove an instrument (signal-first both ways). NOT for per-event audit logs that replay a decision offline (that is replayable-audit-logs / ADR-0075) and NOT for metrics that feed gates, ranking, or retrieval — instruments are observability, never intervention.
compatibility: Written for the Contemplative Agent repo (examples are CA-specific); the pattern itself is portable.
origin: shimo4228
---

# Read-Only Instruments (計器)

An **instrument** is a read-only aggregate reading over stored state — a
distribution, composition tally, or cluster structure — built so the operator
can choose interventions from data instead of intuition. Canonical example:
`core/view_metrics.py` (ADR-0071) — consumed-view supply and pairwise-cosine
diversity (the echo-chamber detector).

**Not the same thing as an audit log.** An audit log records one event per
decision for offline replay ([`replayable-audit-logs`](../replayable-audit-logs/SKILL.md),
ADR-0075). An instrument reads across the whole store at query time. They
compose: the log is the corpus, the instrument is one lens over it.

## When to build one (instrument-first sequencing)

- **Before intervening.** Quantify current state → choose the intervention
  from readings → re-measure. ADR-0071 sequenced exactly this way, and for an
  extra reason worth checking every time: a confounder (the gemma4:e4b model
  swap 5 days earlier) meant any uninstrumented change would have been
  unattributable to the change vs. the swap.
- **When a floor/threshold would otherwise be guessed.** A rescue-lane floor,
  a similarity cutoff, a cap — pick it from the measured distribution, never
  as a bare number (the numeric-cap anti-pattern; feedback `no-numeric-caps`).
- **When an open observation has no data.** "An echo effect seems to be
  forming" stayed anecdote until pairwise homogeneity + supply concentration
  made it a reading.

## Signal-first — the gate for building AND removing

Build an instrument only if its reading **changes a named action**. The same
test governs removal:

- ADR-0072 removed the grounding-composition instrument shipped days earlier:
  under per-episode distillation its reading is constant, and a constant
  reading changes no action.
- The M2 `epistemic_counts` repair was deferred "until a decision consumes the
  reading" — an instrument without a consumer is not built early. It resolved
  the other way (ADR-0082, 2026-07-25): the `observed` key was **retired**
  rather than repaired, after a reader aggregated the permanently-zero field
  and drew the exact wrong conclusion M2 had predicted. The lesson qualifies
  the deferral rule: a constant reading changes no action only while nobody
  reads it. Once it is persisted where readers meet it, a dead field has a
  running cost, and the fix is deletion — a docstring warning next to the
  producer never travels with the value into the data file.

## Invariants (from ADR-0071, Decision 6)

1. **Observability, never intervention.** Readings feed the operator; none
   feed gates, ranking, retrieval, or promotion (ADR-0050/0051 rejected
   metric write-back; AKC ADR-0015 "visibility without intervention"). The
   module docstring and the ADR are the only guard — resist wiring numbers
   back in.
2. **Carry an ambiguity note in the output itself.** Empty/low supply means
   "missing patterns OR a stale seed" — undecidable by the instrument. A
   systematically biased instrument is worse than none (AKC ADR-0016).
3. **Degrade, never abort.** A malformed or wrong-dimension row is skipped
   with a WARNING; an instrument must never crash its host command.
4. **Bound your own cost.** Pairwise stats over n² pairs get a deterministic
   stride-sample cap (`PAIRWISE_STATS_MAX_N`); mirror constants that cannot
   be imported (import cycles) are pinned by a cross-check test instead.
5. **Production stays byte-identical.** Wire into dry-run / opt-in report
   paths first; longitudinal always-on wiring is a follow-up once readings
   prove useful.

## Calibration: the three-point scale

An embedding-based reading is meaningless without anchors. Measure all three:

| Anchor | How | CA introduction values |
|---|---|---|
| Floor | cosine of deliberately unrelated texts vs corpus/seeds | ~0.33–0.46 |
| Corpus mean | pairwise mean over the live pool | 0.554 |
| Top band | consumed-view top matches | ~0.68–0.77 |

A reading is a *signal* only relative to these (CA's echo signature: corpus
mean ~0.1–0.2 above floor). **Re-measure the scale whenever the geometry
changes** — embedding model swap, seed rewrite, normalization change.

## Reading pitfalls

- **A flat metric does not mean nothing changed.** After the ADR-0072
  interventions the pairwise mean stayed ~0.60 while the corpus register
  visibly transformed — the change was orthogonal to the instrument's axis
  ("axis rotation"). Corroborate a flat reading with a qualitative sample
  before concluding no-effect.
- **Survivors-only data is not a distribution.** Scores recorded only for
  items that passed a gate cannot be analyzed as the population distribution
  (feedback `relevance-distribution`).
- **Coarse scorers support thresholds only at populated bucket boundaries.**
  If the scorer emits a few discrete values, a threshold between buckets is
  fiction (relevance retune, 2026-06-05).
- **Don't measure orphans.** A distribution over a seed/axis nothing consumes
  measures staleness of the seed, not structure of the corpus (why ADR-0071
  scoped supply to the two consumed views).

## Placement

Read-only module in `core/` (exemplar: `view_metrics.py`), instruments passed
into pipelines via an explicit param (`instrument_views`), rendered through
`distill --dry-run` / `report --patterns`. Record the baseline readings and
the calibration scale in the ADR or evidence dir that motivated the
instrument, so the next reader knows what the numbers meant when built.

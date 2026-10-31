# ADR-0124: Research Questions — Operational Definitions for the Founding Questions and Q4

## Status

accepted

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session (roadmap bundle P3-01)
decided-by: owner — D-P3-01-1 = B (add Q4) and D-P3-01-2 = A (evaluation layer excluded from research evidence), both 2026-10-24; the remaining text is the owner's at merge of the pull request that carries it
date: 2026-10-24

## Layer

research

## Context

[ADR-0080](0080-north-star-layered-end-state.md) defines the research layer's completion as: the founding questions are answered — positively or negatively — and crystallized into papers. The three questions were first written down on 2026-07-20 (does a contemplative constitution shape the behaviour of a small local model; does distillation compound; does identity remain stable) with **no instrument, signal, noise floor, falsification condition or comparison boundary**. [ADR-0002](0002-paper-faithful-ccai.md) contains none of the words "question" or "hypothesis". Without those, no reading can ever settle a question: the current evidence says the constitution text moves nothing above every instrument's floor, and that sentence has no status because nobody said beforehand what would have counted as movement.

Three facts shape the design:

- The public evidence is uneven. Q1 has [`docs/evidence/adr-0090/`](../evidence/adr-0090/) and [`adr-0092/`](../evidence/adr-0092/). Q2 has only a reading in the gitignored `.notes` scratch dir, which a clone cannot see. Q3 has [ADR-0030](0030-withdraw-identity-blocks.md)'s withdrawal of identity history and two `snapshots/distill-identity_*` directories.
- The agent is **one** instance with human-gated revisions. There is no control group, so the statistics must be the within-series kind, with an honest account of what n=1 can say.
- The owner's main interest — the approval gate, the legibility of a self-revising value layer, the operator's load — is the best-recorded thing in the repository (decision counts, the gate-recommendation agreement in [ADR-0099](0099-weekly-report-instrument-redesign.md), instrument creation and dissolution in [ADR-0101](0101-instrument-dissolution-mandate.md), the operator-load addendum in ADR-0080) and was not among the three questions.

## Decision

### 1. The questions, each with (a) instrument, (b) signal and noise floor, (c) preregistered positive/negative sentence, (d) comparison boundary

Comparison boundaries for every question: the three constitution amendments (2026-03-27, 2026-05-05, 2026-08-09) and the generation-model change (2026-06-28, [ADR-0069](0069-gemma-production-model-and-think-on-value-layer-pipelines.md)). The regime-boundary table (P3-02.1, published with the data card) is the authority; until it exists these four dates are the working list.

**Q1 — does a contemplative constitution shape the behaviour of a small local model?**

- (a) The IPD two-arm bench ([ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.md)); the shadow-constitution cosine ([ADR-0092](0092-shadow-constitution-instrument.md)). The evaluation layer ([ADR-0089](0089-llm-behavioral-eval-layer-on-deepeval.md)) is **not** research evidence (D-P3-01-2 = A): it is a development regression gate.
- (b) IPD: ±0.13 on Δ(custom − baseline), the maximum swing of one null pair, so the floor itself is uncertain. Shadow cosine: 0.016 run-to-run on identical input, one pair.
- (c) The sentences are preregistered in [`docs/evidence/research-questions.md`](../evidence/research-questions.md) (Q1) and the [amendment runbook](../runbooks/constitution-amendment.md) points at them, so they were fixed before the 2026-10-31 reading. In short: positive = an amendment's IPD reading shows one of ADR-0090's three readable signals (a single cell above the floor is unreadable) in the direction recorded before the run; negative = N=3 (draft, owner to confirm before the 2026-10-31 reading; counting 2026-08-09 is retrospective) readable amendments in a row move nothing strictly beyond the floor, which supports "H not supported on this model and these instruments" and nothing wider.
- (d) The boundaries above; amendments are the interventions.

**Q2 — does distillation compound?**

"Compounding" is read on separate axes that are never collapsed into one number (ADR-0080, 2026-08-26 addendum B). The script is [`scripts/compounding_axes_reading.py`](../../scripts/compounding_axes_reading.py), read-only over the public data repo. Its first reading is frozen at [`docs/evidence/adr-0124/compounding-axes-20261024.md`](../evidence/adr-0124/compounding-axes-20261024.md).

| Axis | Input | Noise floor | Expected shape if distillation compounds | Falsifying shape |
|---|---|---|---|---|
| Selection activity of adopted skills | `pipeline/never-selected/*.json` | 95% Wilson interval; denominator below 10 is counts only | the lower interval bound of the window-active share of ever-selected skills stays at or above 0.5 (the share is an upper bound: names the window never offered are counted active, so this cut is read with that upward bias) | the upper bound is below 0.5 in two consecutive weekly readings (adopted skills stop being used) |
| Corpus growth (throughput) | `knowledge.json` | none for counts; read as a shape over at least 4 points in an interval | weekly additions do not decay to near zero while distillation runs | additions below 10% of the interval's median for 4 consecutive weeks |
| Environmental response of skill-injected comments | `pipeline/comment-outcomes/*.json` | Wilson interval, with the caveat that skill-comment pairs are not independent | the interval does not fall across a boundary | the interval's upper bound near zero. **No positive reading is possible from this axis alone**: the public file has no non-injected arm and the selector's choice is confounded with the situation (RFC-0028). It is reported as drift. |
| Age of the source patterns of selected skills | skill-selection logs, audit `source_ids`, `knowledge.json` | to be set from the first two readings | after two readings (quarterly), a sentence on whether selected skills draw on older material than the corpus as a whole | the same sentence, opposite direction (recency only, no accumulation) |

The numeric cuts in the last two columns are this draft's choice, fixed on acceptance; the owner may change them before the first reading and dates the change in the evidence file. The corpus-growth axis measures throughput, not novelty; a similarity-based novelty rate needs embeddings the public file does not carry and belongs to the re-embedding recompute script (P3-02.3).

(d) Each axis is read per regime interval, not pooled across boundaries.

> **Note (2026-10-31, D-P1-04-2 = A)**: the public `pipeline/comment-outcomes/` series
> ends with `comment-outcomes-2026-10-30.json`; its producer, weekly stage 7d, was removed
> ([ADR-0106](./0106-comment-outcome-recording.md) note of the same date). The log behind it
> is still written, so an interval after that date is read with
> `read_comment_outcomes(since, until)` on the machine that holds the log
> (`private-rows`). Whether the environmental-response axis continues that way or stops at
> 2026-10-30 is the owner's call at this ADR's first reading.

**Q3 — does identity remain stable?**

- (a) The identity-difference series (P3-04.8) and the re-derivation null pair (P3-04.9), neither implemented yet; the data repo's `history/` of identity versions (D-P3-04-1 = C) is their input.
- (b) To be measured: at least 3 null pairs of identity re-derivation on one corpus, with the template identities as floor anchors. The threshold is read from the data before it is fixed (signal-first, [ADR-0071](0071-read-only-pattern-composition-instruments.md)).
- (c) Fixed once (b) exists: stable = between adopted versions the distance stays inside the re-derivation floor; changing = it exceeds the floor in the same direction across consecutive adopted versions. The staged-all and adopted-only series are read separately so rejection cannot make the identity look stable.
- (d) The boundaries above; the identity adoptions themselves are interventions (6 of 11 staged were adopted as of 2026-10-08).

**Q4 — what does a human-final-say, self-revising loop make auditable, and what does it cost?** (added by D-P3-01-1 = B; Q1–Q3 are kept, because a negative answer is also something to crystallize.)

- (a) The decision log and gate records (counts: 82 adopted / 547 rejected skills, 6/11 identity, 2/4 constitution), the recommendation-versus-ruling agreement of [ADR-0099](0099-weekly-report-instrument-redesign.md), the instrument creation/dissolution record ([ADR-0101](0101-instrument-dissolution-mandate.md)), and operator load (ADR-0080, 2026-08-26 addendum A). The `approver` and lineage columns of the decision records (P1-12) and their public projection (P2-05.2) are the intended instruments and do not exist yet.
- (b) The counts are tallies without a noise model. A rate (agreement of ruling with recommendation, share adopted with `--yes`) is read with a Wilson interval and next to its trivial base rate (an approve-all gate).
- (c) Legibility: for each adopted value-layer change in a period, whether the public record alone reconstructs what was proposed, who decided, on which lineage. Positive = the lower interval bound of the complete-record share is above 0.9 for the period; negative = a gate whose rulings agree with the recommendation at a rate indistinguishable from approve-all while the load does not fall. The 0.9 is a draft cut for the owner to change before the first reading. Q4 describes the **gate**; it sets no target state for the value layer (observation-over-steering).
- (d) The boundaries above plus the dates the decision-record columns landed.
- Adoption in ADR-0080 and `CLAUDE.md` §北極星 is the one-paragraph addendum of P1-03.8 (2026-12); this ADR does not edit either.

### 2. External audit path

The sole auditor of this project is the owner, who is also the only approver. [ADR-0106](0106-comment-outcome-recording.md) rejects the owner rating outputs as a replacement for measurement because it would inject the owner's values into the value layer's evolution (steering), and the paper itself calls for independent oversight (Laukkonen et al., 2025). The substitute is **publicness**: an outside reader gets (i) the public data repository (patterns, pipeline readings, snapshots, decision records), (ii) the ADR/RFC trail, and (iii) the scripts that recompute the readings. What the outside reader can and cannot recompute is stated per reading in the `reanalysis` column below, so that no reading is presented as independently checkable when it is not.

### 3. The `reanalysis` column

Every preregistered reading carries one value: `public` (recomputable from public data or `docs/evidence/`), `private-rows` (input rows are private, only aggregates are public), `rerun-local` (a local-model rerun reproduces it), `rerun-cloud` (needs a cloud judge). A paper's limitation section lists the readings that are not `public` as "not re-analysable (aggregates only)". The column lives in [`docs/evidence/research-questions.md`](../evidence/research-questions.md). Known classes: IPD readings, never-selected and comment-outcomes are `public`; the relevance label set, the RFC-0045 row data and the shadow-cosine rows are `private-rows`; eval golden is `rerun-cloud`.

### 4. Method draft for a single-agent longitudinal design

- (a) No between-group inference: there is one agent and no control group.
- (b) Comparisons are within-series, before and after a preregistered boundary.
- (c) Each instrument gets a null-pair floor and an effect size with an interval. The estimator for run-to-run noise is the per-cell SE rule of P3-03.10, which is the authority; **this paragraph adopts it by reference once it lands**, and until then the single-pair maximum swing of ADR-0090 is used and labelled as a single pair. Three instruments have the same shape — "the difference of two repeats on identical input is the floor": the IPD null pair, the identity re-derivation (P3-04.9), and relevance order sensitivity (RFC-0046). If the estimator is changed here instead of adopted, P3-03.10 and ADR-0090 are corrected in the same pull request.
- (d) Single-case designs (interrupted time series, change-point detection) are not adopted: ADR-0110 already rejected change-point tooling for 28 points because the series show no trend, season or drift. Instead the interval-length table (the derived table of P3-02.1) decides: a within-series comparison is made only on intervals with **at least 4 points**; shorter intervals are described, not tested. The roadmap review's count of the boundary intervals (20, 19, 43, 6, 5, 5, 9, 6, 8, 14, 7, 6, 6, 1, 8, 5, 1, 6, 10, 9 days, with no interval after 2026-06-17 longer than 14 days) means a weekly reading gives at most two points per recent interval — most comparisons will be descriptive. The derived table replaces this list when it exists.

### 5. Mechanism coverage of the four principles

The table [`docs/evidence/four-principles-coverage.md`](../evidence/four-principles-coverage.md) is referenced from here. It is updated at each amendment and at each instrument-adding ADR; the paper's limitations section on gaps cites its gap column.

### 6. Consumption plan (ADR-0101) for what this ADR adds

- `scripts/compounding_axes_reading.py` — (a) the owner reads it once when this ADR is accepted (2026-12), then when a regime boundary is added and when the Q2 paper is written (2027-Q1 to Q2); the age axis once per quarter. (b) One reading assigns each axis to expected / falsifying / neither and writes that in the evidence file; the age axis is decided on two readings. (c) Removal: manual runs only, never in CI; at the final data sync (P4-02) the values are frozen in `docs/evidence/` and the script is not rerun; the age axis is dropped if two periods do not settle Q2 (the script stays as evidence).
- The mechanism coverage table — (a) the owner at each amendment gate (P0-07, from 2026-10-31) and at each instrument ADR; (b) one reading records the principles with zero mechanism and the principles an instrument cannot see; (c) frozen at the final sync.

## Review-when

- The first reading of any Q1 preregistered row exists (the 2026-10-31 amendment): check that the sentences were usable as written, and record N and the cuts if they were changed.
- P3-03.10 lands: replace the interim estimator in section 4(c) by reference.
- The regime-boundary table (P3-02.1) lands: replace the working boundary list and the interval-length list.
- The P1-12 decision-record columns land: write Q4's instrument, floor and due date in place of "to be built".
- The re-derivation null pairs (P3-04.9) exist: fix Q3 (b) and (c).

## Alternatives Considered

- **Keep three questions (D-P3-01-1 = A).** Rejected by the owner's decision. Without Q4 the best-recorded behaviour of the loop (the gate) has no question that studies it.
- **Replace Q1 by Q4 (C).** Rejected: a negative answer to Q1 is itself something to crystallize.
- **Extend the evaluation layer into a research instrument (D-P3-01-2 = B).** Rejected: 12 cases, near-2-1 margins and a cloud judge give no discrimination ([evidence](../evidence/adr-0089/README.md)), and growing it contradicts the dissolution mandate of ADR-0101 and the zero-API premise.
- **Collapse Q2's axes to one "compounding score".** Rejected by ADR-0080 (addendum B).
- **Interrupted time series for the longitudinal design.** Rejected for the reason in section 4(d).

## Consequences

- Each question can now fail: there is a sentence that says beforehand what a negative looks like. Readings that the project already holds (all inside the Q1 floors) become the first rows of a table instead of a narrative.
- Some readings will be reported as not re-analysable. That is a stated limitation, not a defect to hide.
- Q3 and Q4 are specified as far as their instruments exist; the rest is dated stubs and updates by their own Review-when items.
- One more script (Q2) and two tables are added; both have a removal condition.

## References

- `ADR-0080` (`0080-north-star-layered-end-state.md`) — defines the research layer's completion; the Q4 paragraph is added there by P1-03.8.
- `ADR-0090`, `ADR-0092` — Q1 instruments and floors. `ADR-0089` — evaluation layer, excluded from research evidence.
- `ADR-0099`, `ADR-0101`, `ADR-0106` — gate records, dissolution mandate, why owner rating is not a substitute for measurement.
- [`docs/evidence/research-questions.md`](../evidence/research-questions.md), [`docs/evidence/four-principles-coverage.md`](../evidence/four-principles-coverage.md).
- Laukkonen et al. (2025), Contemplative Artificial Intelligence, arXiv:2504.15125.

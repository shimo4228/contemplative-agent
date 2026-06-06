# ADR-0053: Importance as Encoding-Time Significance — Three Judgment Points and Re-observation Promotion

## Status

accepted

## Date

2026-06-06

## Context

[ADR-0009](./0009-importance-score.md) introduced the importance score on 2026-03-24 with
two intended roles. First, a retrieval weight: `get_context_string` switched from
latest-N injection to top-K by `effective_importance`. Second, a foundation for a future
distillation quality gate — the ADR-0009 Consequences named the score "the foundation for
future Phase 2 (distillation quality gate)". In that original design, gate and score were
conceived as one continuum: a graded signal would eventually sharpen into a binary admit
decision.

Both roles have since dissolved without ADR-0009 being updated. [ADR-0019](./0019-discrete-categories-to-embedding-views.md)
moved retrieval from importance-ranked injection to embedding views; `get_context_string`
no longer exists. [ADR-0051](./0051-retire-trust-weighting.md) removed the trust
multiplier, leaving `views._rank()` as pure cosine (`views.py:268-296`) — importance is
not consulted at retrieval. The binary admit gate was realized as a separate mechanism: the
`_is_valid_pattern()` structural check (`distill.py:580`) combined with the noise-view
embedding gate ([ADR-0026](./0026-retire-discrete-categories.md) /
[ADR-0027](./0027-noise-as-seed.md)) — importance is consulted in no admit decision.
`DEDUP_IMPORTANCE_FLOOR` (0.05) is not an admit gate but a dedup-scope cutoff.

A production measurement taken 2026-06-06 against 764 patterns shows the rating
distribution is top-skewed and coarse: 44% rated 0.9–1.0; 26% at 0.5 where the fallback
default collides with genuine 5/10 ratings; only 9% low-tail (0.1–0.4) carries an
unambiguous signal. Mean = 0.729, stdev = 0.243.

An ablation (`docs/evidence/adr-0053/importance-ablation-20260606.md`) ran on identical
raw clusters comparing the current insight ordering against a decay-only variant with the
LLM base held constant. Kendall tau = 0.851; top-3/top-5 batch order is identical; at most
1-of-10 member swaps occur in the kept sets of the 5 oversize clusters. The anti-chatter
rationale recorded in `clustering.py:104` docstring ("Size-only biases toward chatter") is
real, but the ablation shows it is driven by time decay rather than by the LLM rating: the
size-18 cluster c2 ranks 1st under size-only, 14th under decay-only, and 18th under the
current formula.

This ADR was triggered by AKC pre-paper gap analysis item P1-5 (in the
agent-knowledge-cycle repository), which flagged that the importance score's phase
ownership and the gate-vs-score distinction were unspecified at the mechanism level. The
author decided to settle the question substrate-side first; the AKC promotion verdict is
deferred.

## Decision

1. **Canonicalize the three judgment points.** Each value judgment happens at the only
   moment its input exists and is never recomputed later:

   | Judgment | When | By | Input (exists only then) |
   |---|---|---|---|
   | Encoding-time significance | distill time | LLM | episode context |
   | Current relevance | query time | embedding (cosine) | the query |
   | Promotion worth | insight time | LLM | the full cluster |

   On the third row: insight's LLM extraction already accepts or drops each cluster on its
   merits — `insight.py:124-126` docstring: "LLM extraction drops the cluster if no skill
   can be distilled". The stored score only pre-orders that queue.

2. **Gate and score are separate mechanisms, and stay separate.** Binary admit = structural
   check + noise-view gate (embedding). Graded score = LLM. ADR-0009's "Phase 2 quality
   gate" foundation was never realized through importance; this ADR records that as the
   settled outcome — a natural convergence onto the mechanism-vs-value split of
   [ADR-0019](./0019-discrete-categories-to-embedding-views.md): mechanism (similarity,
   dedup, gating) belongs to embedding/code; value judgment belongs to the LLM.

3. **Redefine the stored field's meaning.** `importance` is the record of encoding-time
   significance — "how strongly this registered, with full episode context, at the moment
   of distillation" — not a current-utility signal and not a retrieval weight. The field
   name `importance` stays; no migration is required. The word "salience" is deliberately
   not used for this score: [ADR-0027](./0027-noise-as-seed.md) already uses salience for
   an embedding-distance measure (1 − max cosine to view centroids); overloading the term
   would create a naming collision.

4. **Promotion of dormant knowledge happens by re-extraction, never by score mutation.**
   Stored scores are write-once; decay is computed at read time. When an old record decays
   below `DEDUP_IMPORTANCE_FLOOR` (0.05) it leaves the dedup comparison scope, so a
   re-observed insight re-enters as a fresh record with a fresh score
   (`distill.py:629-638`, `thresholds.py:47`). Decay is therefore not forgetting — it is
   yielding the dedup seat to re-observation. The rejection of post-hoc re-scoring is
   upgraded from an accuracy argument (ADR-0009 Alternatives #1: "evaluation accuracy is
   low without episode context") to an integrity argument: a path where the agent re-reads
   its own stored records and rewrites their scores is the write surface of the
   self-reingestion echo loop named by
   [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) and
   [ADR-0052](./0052-retire-session-insight.md), and its absence is deliberate.

5. **Record the propagation map — where the score does and does not flow:**

   | Consumer | Use | Source |
   |---|---|---|
   | retrieval (`views._rank`) | NOT consulted — cosine only | [ADR-0051](./0051-retire-trust-weighting.md), `views.py:268-296` |
   | dedup (distill) | `effective_importance ≥ 0.05` keeps a record inside dedup scope; below it, re-entry opens | `distill.py:634`, `thresholds.py:47` |
   | insight clustering | intra-cluster sort; overflow past `max_size` demoted | `clustering.py:104-107` |
   | insight batch order | `size × mean(effective_importance)`, ordering only — clusters are never dropped by score | `insight.py:101-111`, `insight.py:155` |
   | rules_distill | deliberately neutralized at 0.5 — no importance weighting on skill clusters | `rules_distill.py:202-212` |
   | stocktake (curation) | NOT consulted | `stocktake.py` |

6. **Establish a measurement gate for retiring the LLM rating.** The ablation evidence
   (`docs/evidence/adr-0053/importance-ablation-20260606.md`) meets the pre-registered
   "small difference" criterion and supports retiring the distill-time LLM rating while
   keeping pure time decay. The retirement decision itself is deferred until two conditions
   clear: (a) the §B1 threshold-retune observation window (relevance gates retuned
   2026-06-05) closes, and (b) the AKC position paper ships, since AKC ADR-0003's Layer-2
   spec currently names the importance score and retiring mid-paper would churn the spec.
   The ablation script should be re-run before deciding — the corpus grows and the result
   may shift.

## Alternatives Considered

### Retire the LLM rating immediately

Rejected: it would require rewriting AKC ADR-0003 Layer-2 mid-paper and would inject a
variable into the open §B1 threshold-retune observation window. At the time the decision
was framed, the harm estimate was unmeasured. The ablation has since been run; its result
feeds the gate condition established in Decision 6, not an immediate retirement.

### Record all of this as an ADR-0009 addendum

ADR-0009 has an established Calibration History section precedent for incremental updates.
Rejected: the three distinct findings (dissolved roles, settled gate-vs-score question, and
measurement gate with deferred decision) plus the propagation map exceed addendum scale.
One artifact, one responsibility.

### Add an introspective re-scoring mechanism

A mechanism where the agent promotes sleepers it deems important in hindsight — reading
stored records and rewriting their scores retroactively. Rejected: this is the echo-loop
write surface described in Decision 4; it contradicts the observation-over-steering
principle ([ADR-0051](./0051-retire-trust-weighting.md) lineage) that origin is recorded
but never weighted.

### Keep the status quo with no reinterpretation

Document the propagation map only; leave ADR-0009's prose as-is. Rejected: it leaves the
"is the rating earning its keep?" question permanently open and ADR-0009's two dissolved
roles (retrieval weight, future gate) permanently misleading.

## Consequences

### Positive

- Documentation and implementation agree again. ADR-0009's two dissolved roles — retrieval
  weight and future gate — are explicitly closed; ADR-0009 receives a forward link and
  remains accepted (its decay design and write-once stance survive unchanged).
- The retirement question now has evidence and a gate instead of an open-ended doubt. The
  pending decision is tracked in `.notes/remaining-issues` (§C experiments) with the two
  named gate conditions.
- The gate-vs-score disambiguation (Decision 2) and the propagation map (Decision 5) give
  future readers a single place to trace where importance does and does not operate —
  replacing the scattered, partially obsolete ADR-0009 prose.

### Negative

- A true sleeper — a pattern observed once and never re-observed — is not rescued. This is
  a deliberate cost. Any rescue mechanism would open the echo-loop write surface described
  in Decision 4.
- ADR-0009's Consequences prose remains on-record as originally written; it is closed here
  by forward reference rather than retracted. Readers must follow the link to understand
  the current state.

### Neutral / Follow-ups

- The AKC P1-5 promotion verdict remains deferred (WON'T DO stands). Its re-evaluation
  triggers are this ADR stabilizing, the gate in Decision 6 resolving, and the AKC paper
  shipping. Were it to promote, the candidate content is: assign-once at extract time /
  immutable store / read-time decay / gate-vs-score disambiguation / promotion-by-re-extraction
  — the "retrieval weight" phrasing would be dropped, since score consumers are
  substrate-specific.
- `graph.jsonld` gains an ADR-0053 node with edges to
  [ADR-0009](./0009-importance-score.md),
  [ADR-0019](./0019-discrete-categories-to-embedding-views.md),
  [ADR-0026](./0026-retire-discrete-categories.md),
  [ADR-0027](./0027-noise-as-seed.md),
  [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md),
  [ADR-0051](./0051-retire-trust-weighting.md) per the dual-update convention, in the same
  change as this ADR.
- The mechanism-vs-value split alignment noted by
  [ADR-0051](./0051-retire-trust-weighting.md) Neutral ("ranking returns to a pure
  embedding mechanism; value judgment lives in importance and time-decay") is now precise:
  encoding-time LLM judgment lives in the stored `importance` field; structural and
  embedding judgment owns the admit gate; cosine owns retrieval rank.

## Related

- [ADR-0009](./0009-importance-score.md) — Importance Score; the decision this ADR
  reinterprets. Its two Consequences roles (retrieval weight, future gate) are closed here;
  its decay design and write-once stance survive. ADR-0009 should carry a forward reference
  to this ADR.
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — Discrete Categories →
  Embedding + Views; introduced the mechanism-vs-value split that the gate-vs-score
  disambiguation (Decision 2) aligns with. Moved retrieval to embedding views, dissolving
  ADR-0009's retrieval-weight role.
- [ADR-0026](./0026-retire-discrete-categories.md) / [ADR-0027](./0027-noise-as-seed.md)
  — Noise gate and noise-as-seed; the embedding-based admit gate that realized the
  binary admit decision ADR-0009 expected importance to eventually supply.
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md) — Retire Pattern-Level
  Forgetting and Feedback; established write-once score semantics and removed the feedback
  update surface that ADR-0009 originally anticipated.
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — Epistemic Taxonomy and
  Approval Lineage; named the self-reingestion echo loop that makes introspective re-scoring
  a structural hazard.
- [ADR-0051](./0051-retire-trust-weighting.md) — Retire Trust Weighting; removed the trust
  multiplier from `views._rank`, leaving pure cosine — the retrieval-weight dissolution
  that makes Decision 5's "NOT consulted" entry final.
- [ADR-0052](./0052-retire-session-insight.md) — Retire Session Insight; removed the
  ungated self-narrative input source; shares the echo-loop write-surface reasoning cited
  in Decision 4.
- `docs/evidence/adr-0053/importance-ablation-20260606.md` — Ablation evidence; Kendall
  tau = 0.851 on identical raw clusters, identical top-3/top-5 batch order, supplies the
  measurement basis for the gate in Decision 6.

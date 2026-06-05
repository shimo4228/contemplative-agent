# ADR-0051: Retire Trust Weighting — Pure Cosine Retrieval and Bitemporal-Only Liveness

## Status

accepted

## Date

2026-06-05

## Context

[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md), accepted one day earlier
(2026-06-05), decided "no trust cap; trust values and all trust-consuming code paths
unchanged," treating the recorded `generated`/`observed` composition as a baseline for a
possible future cap. That decision answered the question "cap or no cap?" but rested on
an unexamined premise: that trust was a meaningful, living quantity. A same-day inventory
of the trust mechanism — prompted by the owner ("そもそも trust 意味なくないか？") —
found otherwise across five mutually reinforcing observations.

**Trust is write-once.** It is assigned at distill time (`knowledge_store.py`
`add_learned_pattern`) and never updated. The update machinery (`feedback.py`:
`record_outcome`, trust-delta constants) was deleted by
[ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md), whose own evidence was
that 377/377 production patterns had never been adjusted post-creation. The
`trust_updated_at` field has only ever held the creation timestamp.

**The trust floor is unreachable.** `is_live()` gates retrieval at `TRUST_FLOOR = 0.3`
(`forgetting.py:19`), but the lowest assigned base is `mixed = 0.5`
(`TRUST_BASE_BY_SOURCE`, `knowledge_store.py:33–38`). No pattern can fall below the
floor; the gate has never fired and can never fire.

**The `external_reply` arm is empty in production.** Live store at inventory time: 619
patterns = `unknown` 274 (trust 0.6, legacy) + `self_reflection` 180 (0.9) + `mixed` 165
(0.5) + `external_reply` **0**. The structural cause is `_derive_source_type`
(`distill.py`): it returns `external_reply` only when all records in a 30-record distill
batch are externally received. Because batches always interleave the agent's own posts,
insights, and activity records, a pure-external batch effectively never occurs. External
contact surfaces instead as `mixed` — which carries the lowest assigned trust.

**The only living effect of trust** is therefore the cosine × trust multiplier in view
ranking (`views.py` `_rank`, with `top_k` truncation) and the `effective_importance`
factor in `insight`'s cluster-member ordering and slice. The net result: pure
self-monologue batches (`self_reflection`, trust 0.9) systematically outrank anything
carrying a trace of external contact (`mixed`, trust 0.5) by ×1.8. That is precisely the
H3 echo-chamber amplifier identified by the 2026-06-04 audit — pointing in the worst
possible direction, with zero offsetting security benefit, because the rows the weighting
was meant to dampen do not exist.

**The security rationale is already obsolete by the project's own record.**
[ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.md) designed trust as
an injection-resistance weighting, but [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md)
states the MINJA defense was "already structurally achieved via `summarize_record`
quarantine", and [ADR-0029](./0029-retire-dormant-provenance-elements.md) retired dormant
provenance elements on the grounds that the primary external-content defense is quarantine
at the summarize boundary, not trust-weighting.

This retirement is distinct from ADR-0050's rejection of a trust cap, which still stands
in spirit. A cap would have pressed an origin-based thumb on the scale in the opposite
direction — steering in response to observed behavior. Full retirement removes the
designer's thumb entirely — instrument calibration. The observation stance, watch the
agent's unforced behavior, is better served by a substrate with no origin bias at all.
The post-retirement mechanism is deliberately small enough to trace causally: ranking =
cosine only; extraction order = cluster size × mean(importance × time-decay); liveness =
`valid_until` only; origin = `provenance.source_type`, recorded and observed via the
ADR-0050 lineage instrumentation but never weighted.

## Decision

1. **Retire the trust multiplier everywhere.** `views.py` `_rank` scores by cosine alone
   (threshold and `top_k` unchanged). `effective_importance` (`knowledge_store.py`)
   becomes `importance × 0.95^days_elapsed`. `is_live()` gates on `valid_until is None`
   alone.

2. **Stop writing trust fields.** `add_learned_pattern` no longer accepts or writes
   `trust_score` / `trust_updated_at`; the `load()` whitelist no longer carries the two
   fields, so legacy rows shed them on the next save. Zero information loss: every
   historical trust value is a pure function of the preserved `provenance.source_type`
   (via the retired `TRUST_BASE_BY_SOURCE` table, recorded in this ADR and in
   [ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.md)), and the
   data-research repository preserves full history.

3. **Delete `forgetting.py`.** After retirement `is_live()` is a one-line bitemporal
   gate; it moves into `knowledge_store.py` next to the pattern schema and
   `get_live_patterns()`. The module name had been a misnomer since
   [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md) renamed the concept to
   "retrieval gate" while keeping the file.

4. **Delete the dead surface.** `TRUST_BASE_BY_SOURCE`, `DEFAULT_TRUST`, `TRUST_FLOOR`,
   `_trust_for_source` (`distill.py`), the unused `SOURCE_TYPES` tuple, and the
   never-called `KnowledgeStore._effective_importance` wrapper are removed.

5. **Keep `provenance.source_type` and its derivation untouched.** `_episode_source_kind`
   and `_derive_source_type` still classify batches and write `source_type`;
   [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md)'s `epistemic_kind_for`
   derives `{observed, generated}` from it, and the `audit.jsonl` lineage fields
   (`source_ids` / `epistemic_counts`) are unaffected. Origin remains recorded, never
   weighted.

## Alternatives Considered

### Trust cap at 0.6 or 0.7 on generated patterns

Already rejected by [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md).
Additionally now understood to have been the wrong question: capping presupposes the
weighting deserves to exist at all.

### Re-arming dynamic trust (restore feedback updates)

Rejected: [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md) established that
the agent has no per-turn retrieval, hence no usage signal from which to update trust.
Memory dynamics live at the skill layer (reflection bookkeeping). Reintroducing
pattern-level feedback would reverse ADR-0028 with no new signal source.

### Keep only the external_reply damping (drop the self_reflection boost)

Rejected: the arm it would protect against is empty (0 rows in production, structurally
near-unreachable at batch granularity), and the canonical injection-defense layer is the
`summarize`-boundary quarantine ([ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md),
[ADR-0029](./0029-retire-dormant-provenance-elements.md)). Defense-in-depth with a
certain constant cost in origin distortion and a contingent, currently-zero benefit is a
bad trade. If identity-steering via crafted external content ever becomes a live threat,
the right response is an explicit origin filter at the identity-input site, not a global
rank multiplier.

### Keep legacy trust fields on disk (load-and-carry without consuming)

Rejected: redundant with `source_type`, contradicts the simplification goal, and would
leave a misleading fossil in the schema.

### Rename instead of retire (acknowledge as a static origin prior)

Rejected: the ×1.8 self-preference would keep operating. The problem is the effect, not
the name.

## Consequences

### Positive

- Retrieval causality becomes fully readable: a pattern reaches identity or constitution
  input if and only if its embedding clears the view's raw-cosine threshold and survives
  `top_k` by cosine rank. No hidden origin factor.
- The `mixed`-origin handicap (×1.8 relative to `self_reflection`) disappears from
  identity and constitution input selection; patterns carrying traces of external contact
  compete on semantic relevance alone. The audit's H4 phrasing ("undilutable from
  outside") loosens structurally, without any steering intervention.
- Approximately 100 lines and one module (`forgetting.py`) are deleted; the surviving
  mechanism is small enough to hold in one's head — cosine / importance × decay /
  `valid_until` / `source_type`.
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md)'s lineage instrumentation
  is untouched and keeps accumulating; `epistemic_counts` remains the observation metric
  for identity-input composition.

### Negative

- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) Decision 2 is partially
  superseded one day after acceptance. Accepted: the premise was a misreading of trust
  dynamics. The repository has precedent for fast correction (ADR-0024/0025 withdrawn by
  ADR-0030), and the Emptiness axiom favors revising a decision over reifying it.
- The theoretical external-content rank handicap is gone. Mitigated by the quarantine
  boundary as the canonical defense and by the empirical fact that the handicap protected
  zero rows.
- Legacy rows shed `trust_score` / `trust_updated_at` on their next save;
  `knowledge.json` schema slims by two fields. Anyone diffing historical data snapshots
  should expect this.

### Neutral / Follow-ups

- This ADR completes the trust retirement arc begun by
  [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md) (dynamics retired) and
  [ADR-0029](./0029-retire-dormant-provenance-elements.md) (dormant provenance retired);
  the static residue is removed here.
- The `TRUST_BASE_BY_SOURCE` constant table — `unknown: 0.6`, `self_reflection: 0.9`,
  `mixed: 0.5`, `external_reply: 0.55` — is recorded here and in
  [ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.md) for historical
  traceability. Any historical `trust_score` value in a snapshot is recoverable as a pure
  function of `provenance.source_type` via this table.
- Independent of this retirement, the caveat inherited from ADR-0050's taxonomy stands:
  because `_derive_source_type` operates at batch granularity and pure-external batches
  essentially never occur, the `observed` arm of `epistemic_counts` will read ≈ 0 in
  practice. Interpret `observed ≈ 0` as "no pure-external distill batches exist
  structurally", not as "no external input reached memory" — external contact is present
  inside `mixed` → `generated` counts.
- `graph.jsonld` and CODEMAPS should be updated per the dual-update convention to reflect
  the removal of the trust weighting node and the inline migration of `is_live()`. Not
  done in the initial commit.
- The ranking formula post-retirement aligns with the mechanism-vs-value split of
  [ADR-0019](./0019-discrete-categories-to-embedding-views.md): ranking returns to a pure
  embedding mechanism; value judgment (which patterns matter) lives in `importance` and
  time-decay, not in origin-assigned constants.

## Related

- [ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.md) — Pattern
  Schema Extension (Provenance / Bitemporal / Forgetting / Feedback); introduced the trust
  surface retired here. Its IV-7 trust sub-section is superseded; `source_type` and
  bitemporal semantics survive.
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md) — Retire Pattern-Level
  Forgetting and Feedback; retired trust dynamics. This ADR removes the static residue
  left by that retirement.
- [ADR-0029](./0029-retire-dormant-provenance-elements.md) — Retire Dormant Provenance
  Elements; established the `summarize`-boundary quarantine as the canonical
  injection-defense layer, making trust-based dampening redundant.
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — Epistemic Taxonomy and
  Approval Lineage; Decision 2 ("no trust change") is partially superseded by this ADR.
  The taxonomy, `epistemic_kind_for`, and `audit.jsonl` lineage instrumentation remain in
  full effect.
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — Discrete Categories →
  Embedding + Views; the mechanism-vs-value split to which pure-cosine ranking returns.
- [ADR-0009](./0009-importance-score.md) — Importance Score; `importance` survives
  unchanged and continues to contribute to `effective_importance` alongside time-decay.

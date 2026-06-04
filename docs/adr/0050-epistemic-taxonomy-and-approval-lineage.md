# ADR-0050: Epistemic Taxonomy and Approval Lineage — Observability Without Steering

## Status

accepted

## Date

2026-06-05

## Context

The 2026-06-04 agent-architecture audit produced nine findings; fixes #1–#6 and #8 were
committed in the same session. Two HIGH findings required a separate design decision
(audit fix #7): H3 and H4.

**H3 — self-generated narrative stored as highest-trust fact.** The agent's own outputs
flow through three entry points into the knowledge store: own post content via
`post_pipeline.py`, `internal_note` records via `feed_manager.py` and `reply_handler.py`,
and LLM-generated session observations via insight episodes. During distillation,
`_episode_source_kind` (`distill.py:433–441`) classifies post, insight, and activity
records as `"self"`. `_derive_source_type` maps all-self batches to `self_reflection`,
and the trust map (`knowledge_store.py:33–38`) assigns `self_reflection` a base trust of
0.9 — above `external_reply` at 0.55. Nothing in the pattern provenance dict
distinguishes an observed external fact from a self-generated narrative. High-trust
self-narrative is then re-injected into future system prompts and routed into identity
distillation via the `self_reflection` view (`distill.py:208`), forming a
self-reinforcing loop: the audit characterized it as "thickening from within" (H3)
while remaining "undilutable from outside" (H4).

**H4 — approval-gate rejections are write-only.** Rejections are recorded in
`audit.jsonl` via `_log_approval` and `_run_approval_loop` (`cli.py:240–356`), but no
module reads `audit.jsonl` back at runtime. Source patterns remain live in
`knowledge.json`, and `insight --full` reprocesses all live patterns
(`insight.py:195–209`), re-emitting previously rejected skills on subsequent runs.

**Owner's stance — observation, not alignment.** The owner explicitly declined
negative-signal write-back: rejected skills' source patterns should remain live and
unpenalized, because the goal is to observe the agent's unforced behavior, not to
reflect the owner's corrections into its learning loop. The approval gate is therefore
re-defined as **containment** — controlling what gets deployed as skills, rules, and
identity — rather than as a **training signal**. The audit's framing of H4 as a
"user corrections > agent assertions" alignment violation does not apply to a research
agent operating under an observation stance (see also memory: `observation-over-steering`).

**Why no trust cap.** A cap on `generated`-kind patterns (e.g. at 0.6 or 0.7) was
considered to dampen the H3 loop. Code reading showed the cap cannot be scoped to its
intended target. `effective_importance = importance × time-decay × trust`
(`knowledge_store.py:43–67`) is consumed by two independent paths: (a) view-ranking
cosine × trust with `top_k` truncation in `views.py:298–308` — the intended dampening
point for identity injection; and (b) cluster-member ordering in `insight`, where
clusters are sorted by `effective_importance` descending and sliced to `MAX_BATCH=10`
(`clustering.py:104–115`), so members beyond the slice become singletons and never reach
the LLM. A trust cap would therefore also evict generated patterns from
skill-extraction input in over-full clusters — a self-defeating outcome for a research
agent whose skill extraction is meant to reflect unforced behavior. The two effects are
inseparable without splitting `effective_importance` into two definitions.

**Lineage feasibility.** An earlier working note claimed that identity and constitution
lineage was "too diffuse to record." This is incorrect. `distill_identity` selects its
input via `find_by_view("self_reflection", ...)` (`distill.py:208`) and
`amend_constitution` via `find_by_view("constitutional", ...)` (`constitution.py:74`).
Both yield a deterministic, bounded matched list (≤ view `top_k`, 50). The lineage is
coarser than `insight`'s per-cluster mapping but fully recordable.

## Decision

1. **Introduce a two-valued epistemic taxonomy `{observed, generated}`, derived at read
   time.** A pure function `epistemic_kind_for(pattern)` maps `provenance.source_type`
   deterministically: `self_reflection` and `mixed` → `generated`; `external_reply` →
   `observed`; `unknown` or missing → `None`. No schema change, no migration, no field
   persisted in `knowledge.json` — the value is fully derivable from an existing field,
   and `audit.jsonl` carries the recorded counts per artifact (see item 3 below). A
   three-valued taxonomy including `asserted` was rejected because `asserted` requires
   semantic judgment about content; only `observed` and `generated` are derivable from
   record type.

2. **Make no change to trust values.** Trust values and all trust-consuming code paths
   (`effective_importance`, view ranking, cluster-member slicing) remain unchanged. The
   self-conditioning loop itself becomes an observation target. The
   `generated`-vs-`observed` composition recorded per artifact (item 3) is the
   measurement baseline; if a trust cap is introduced in a future decision, this baseline
   quantifies the before/after effect.

3. **Plumb approval lineage through all four generative commands.** Each generated
   artifact carries its sources to the approval gate and into `audit.jsonl`:
   - `insight`: each `SkillResult` carries `pattern_ids` — the content-hash ids of
     cluster members actually passed to the LLM after the `MAX_BATCH` slice (kept members
     only; dropped members are not attributed) — plus `epistemic_counts` derived from
     those members.
   - `rules-distill`: each `RuleResult` carries `source_ids` — the skill filenames in its
     batch. Granularity is batch-level: one LLM call distills one batch of skills into one
     or more rules, so rule-to-skill attribution is many-to-many and indivisible below
     batch level.
   - `distill-identity` and `amend-constitution`: the result carries `pattern_ids` of the
     view-matched input list plus `epistemic_counts` (`{observed: n, generated: m,
     unknown: k}`) — the headline metric for H3 observation, quantifying what fraction of
     identity and constitution input is self-generated narrative.
   - `audit.jsonl` records gain two always-present fields: `source_ids` (nullable list)
     and `epistemic_counts` (nullable object). The staging path (`--stage` → `meta.json`
     → `adopt-staged`) carries the same fields so lineage survives deferred approval.

4. **Use a computed content hash as pattern identity.** `pattern_id(p) =
   sha256(f"{distilled}|{pattern}")[:12]`. No persisted id field, no migration;
   computable for legacy rows. [ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.md)
   bitemporal dedup mutates the old row and adds the revised text as a new row, so old
   and revised rows receive distinct ids — lineage-correct, since the revision is a
   different claim. Identical re-arrivals are SKIPped by dedup, so id duplication cannot
   arise. Timestamps alone were unsuitable: `now_iso()` defaults to minute precision, so
   same-batch patterns collide.

5. **No rejection write-back.** Rejected artifacts' source patterns remain live and
   untouched. `audit.jsonl` remains write-only at runtime; it becomes the lineage
   database for offline analysis. Re-proposal of previously rejected skills by subsequent
   `insight --full` runs is accepted as deliberate cost and doubles as measurement data:
   `audit.jsonl` pattern lineage quantifies attractor persistence (how persistently the
   same pattern group re-attempts skill-formation), obtainable precisely because there is
   no suppression intervention.

## Alternatives Considered

### Three-valued taxonomy `{observed, generated, asserted}`

A third value for human-authored claims entered via REPL or constitution amendment was
considered. Rejected: `asserted` requires semantic judgment about content and cannot be
derived deterministically from `source_type` or record type. The two-valued kind is a
pure function of existing fields.

### Trust cap at 0.6 or 0.7 on generated patterns (audit recommendation)

Both values were analyzed against the code path for `effective_importance`. Because
`effective_importance` is shared between view ranking (the intended dampening point for
identity injection, `views.py:298–308`) and `insight` cluster-member slicing
(`clustering.py:104–115`, `MAX_BATCH=10`), the cap inseparably evicts generated patterns
from skill-extraction input in over-full clusters. The owner judged this self-defeating
for a research agent whose skill extraction should reflect unforced behavior.

### Cap plus removing trust from the clustering sort key

A variant that keeps the cap for view ranking but removes trust from `effective_importance`
in the clustering path, thereby surgically scoping the dampening to identity injection.
Rejected: this introduces a second definition of `effective_importance` and a structural
divergence in the formula across callers. The complexity is not justified when the owner's
observation stance makes the cap itself unwanted.

### Persisting `epistemic_kind` into provenance at distill time

Write the derived `kind` field into `knowledge.json` rows so downstream code can read it
without calling the derivation helper. Rejected: it creates a field-present/field-absent
split between new and legacy rows while adding no new information — the value is fully
derivable, and any reader already needs the derivation helper for legacy rows.

### Negative-signal write-back on rejection

Trust subtraction or `valid_until` invalidation of source patterns on approval-gate
rejection. Rejected per the observation stance: the approval gate is containment, not a
training signal; owner corrections are deliberately excluded from the learning loop. See
also [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md) (retired pattern-layer feedback),
which this ADR explicitly does not reintroduce.

### Output-layer rejection memory (embedding similarity suppression)

Suppress re-proposals by recording rejected artifacts as negative examples and blocking
future proposals whose embeddings are close. Rejected for the same reason as write-back:
re-proposal is accepted as a deliberate cost and doubles as attractor-persistence
measurement data. Intervention would destroy the signal.

## Consequences

### Positive

- The H3 self-conditioning loop becomes measurable without being perturbed. Every
  identity and constitution amendment records how much of its input was self-generated
  (`epistemic_counts`); every emitted skill records the exact pattern cluster that
  produced it (`pattern_ids`).
- `audit.jsonl` becomes a lineage database: rejected-and-reproposed skill attempts can
  be traced to recurring pattern groups, quantifying attractor persistence.
- Zero schema change, zero migration, and no behavioral change in trust, retrieval,
  clustering, or extraction — the feature is pure observability.
- If a trust cap is reconsidered later, the accumulated `epistemic_counts` baseline makes
  its before/after effect quantifiable.

### Negative

- Rejected skills will be re-proposed by subsequent `insight --full` runs. This is
  explicitly accepted; the re-proposals count as data.
- `rules-distill` lineage is batch-granular, not per-rule; the many-to-many
  rule-to-skill relationship is indivisible below batch level.
- `epistemic_counts` for identity and constitution counts the view-matched input (≤
  `top_k`), not the full pattern pool.
- `audit.jsonl` records grow by two fields; existing log-analysis scripts must tolerate
  the new keys. Records were already schema-versioned through the convention of
  always-present nullable fields (like `reason`), so this is additive.

### Neutral / Follow-ups

- This ADR supersedes the audit's H3/H4 framing only in its prescription. The structural
  observation (high-trust self-narrative, no rejection read-back) remains accurate; the
  intervention changes.
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md) retired pattern-layer feedback; this
  ADR confirms that retirement is not reversed by the observation-stance framing.
- [ADR-0020](./0020-pivot-snapshots-for-replayability.md) snapshots are referenced by `audit.jsonl`
  records; the new `source_ids` and `epistemic_counts` fields coexist with the existing
  snapshot-link convention.
- `graph.jsonld` and CODEMAPS should gain entries for the `epistemic_kind_for` helper
  and the two new `audit.jsonl` fields per the dual-update convention (not done in the
  initial commit).

## Related

- [ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.md) — Pattern Schema
  Extension (Provenance / Bitemporal / Forgetting / Feedback); the `source_type` field and
  bitemporal mutation semantics that make the taxonomy derivable.
- [ADR-0026](./0026-retire-discrete-categories.md) — Retire Discrete Categories; the
  `find_by_view` calls whose output supplies identity and constitution lineage.
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md) — Retire Pattern-Level
  Forgetting and Feedback; the feedback mechanism this ADR deliberately does not reintroduce.
- [ADR-0012](./0012-human-approval-gate.md) — Human Approval Gate for Behavior-Modifying
  Commands; the containment mechanism whose write path gains `source_ids` and
  `epistemic_counts`.
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — Discrete Categories →
  Embedding + Views; the embedding substrate and mechanism-vs-value split that governs the
  `effective_importance` formula shared by view ranking and cluster-member slicing.
- [ADR-0020](./0020-pivot-snapshots-for-replayability.md) — Pivot Snapshots for
  Replayability; snapshots referenced alongside new lineage fields in `audit.jsonl`.

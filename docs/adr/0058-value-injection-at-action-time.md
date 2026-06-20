# ADR-0058: Value-Layer Injection Belongs to Action Time, Not Distillation

## Status

accepted

## Date

2026-06-20

## Context

[ADR-0057](./0057-identity-from-self-reflection-corpus-alone.md) dropped the axiom injection from
identity distillation: the self-reflection corpus it distils from is already axiom-shaped, so
re-injecting the four axioms into the distillation system prompt double-counts them. ADR-0057
**deferred** the same question for the other distillation stages, on the reasoning that they
"extract from raw episodes that are not yet axiom-shaped." A follow-up audit (10 agents, map →
adversarial-verify over every LLM call site that injects a value layer) found that reasoning wrong
and the principle more general than ADR-0057 stated.

Two facts drive the generalization:

1. **Every distillation stage reads already-value-shaped material.** Only pattern `distill`
   (`distill.py`) reads raw episode records at all. `insight` reads stored patterns — the output of
   `distill`'s axiom-grounded LLM call; `rules_distill` reads skill texts — two axiom-grounded LLM
   stages downstream; `constitution` amend reads stored constitutional patterns plus the constitution
   file (the axioms' own home). The lineage is `episodes → distill(axioms) → patterns → insight(axioms)
   → skills → rules_distill(axioms)`, and separately `patterns → constitution(axioms)`. At every stage
   past `distill`, the input already carries the axiom register, so re-injecting the axioms is the
   same redundant double-counting ADR-0057 removed for identity.

2. **Even at `distill`, the fresh slice is observation, which should be faithful.** Episode batches
   mix self-generated records (the agent's posts, comments, internal notes, replies — produced under
   the full action prompt `_build_system_prompt` = identity + axioms + skills + rules, so already
   value-shaped) with one genuinely fresh slice: external content the agent observed (another agent's
   raw reply, logged as a `received` interaction and rendered verbatim into the distill prompt). The
   audit first treated that external slice as *justifying* axiom grounding. The sharper reading: an
   observation should be extracted **faithfully** (the Mindfulness axiom), not re-interpreted through
   a value lens. The agent's value-laden *response* to external content is already recorded separately
   (its reply, its internal note) — the values live there, in the recorded action, not in the
   re-reading of the observation. So even the fresh external slice does not justify re-injecting the
   axioms at distill time.

The unifying principle: **value layers belong to action time — when the agent does something or
decides how to relate to fresh input — not to distillation time, when it extracts patterns from what
already happened.** This is the same move the project has been making elsewhere: removing owner/value
steering from the learning loop (ADR-0050 / ADR-0051 / ADR-0052 retired trust weighting, session
insight, and write-back). Distillation is observation; observation should not be steered by the
values, it should record them where they actually occurred.

## Decision

1. **All distillation / extraction system prompts are axiom-free (base only).** `get_distill_system_prompt()`
   now returns the base system prompt (the credential-leak guard) and no longer appends the axioms.
   Because every distillation stage routes through it — pattern `distill` (`distill.py`), `insight`
   (`insight.py`), `rules_distill` (`rules_distill.py`), `constitution` amend (`constitution.py`), and
   identity (`distill_identity`) — this single change makes all of them base-only at once.

2. **The dedicated identity-only function is collapsed.** `get_identity_distill_system_prompt()`,
   introduced by ADR-0057 for identity alone, is removed; `distill_identity` routes back through the
   now-base-only `get_distill_system_prompt()`. There is one distillation system prompt, and it
   carries no value layer.

3. **Axioms remain injected only at action time.** `_axiom_prompt` is now appended in exactly one
   place — `_identity_axioms_base()` (`llm.py`), which backs `get_identity_system_prompt()` (the lens
   the agent applies to fresh external feed content for relevance scoring, the pre-action internal
   note, topic summary, and submolt selection) and `_build_system_prompt()` (the full session prompt
   under which the agent acts and produces episodes). The agent still behaves according to its values;
   it just no longer re-reads its own past through them.

## Audit findings (the five injecting call sites)

| Call site | Input | Verdict | Disposition |
|---|---|---|---|
| `constitution.py` amend | constitutional patterns + constitution file | redundant self-reinforcement (full) | base-only |
| `insight.py` | stored patterns (distill output) | redundant self-reinforcement (full) | base-only |
| `rules_distill.py` | skill texts (2 stages downstream) | redundant self-reinforcement (full) | base-only |
| `distill.py` pattern distill | mixed episodes (self-generated + fresh external observation) | observation should be faithful | base-only |
| `llm_functions.py` ×4 (Moltbook) | fresh external feed content (a lens applies) | legitimate grounding — action time | **unchanged** |

The `constitution` case carries an additional, structural significance: using the axiom block as the
interpretive lens to revise the constitution makes the axioms **self-defending** — the Emptiness
axiom's own directive ("hold all directives lightly, remain open to revision") cannot operate on the
constitution when the lens *is* the directive. Dropping the axiom lens lets accumulated tensions in
the patterns actually move the constitution.

## Verification

- **Behavioral impact is near-inert**, consistent with ADR-0057's staged identity evidence (removing
  the same axiom injection left the persona register essentially unchanged — the corpus already
  carried it). The defect being removed is structural redundancy and the constitution circularity,
  not a behavioral corruption; this is the ADR-0056 class of "remove inert / redundant mechanism."
- **`distill` is not approval-gated** (unlike identity, which has the ADR-0012 gate), so it is verified
  by `distill --dry-run` rather than a human gate. A post-change dry-run over 2 days of episodes ran
  clean (151 classified, 135 noise-gated, 16 kept → 2 patterns) and produced faithful, observational
  patterns with no axiom vocabulary imposed (e.g. "activity rhythm shifts from unilateral broadcasting
  to dense direct social engagement"). `n = 1`, stochastic — this confirms the path runs and the
  output is sane and faithful, not behavioral equivalence; the next few real distillations are watched.
- Full test suite green (1299 passed); no test asserted axioms in the distillation system prompt
  (the axiom-bearing prompts `_build_system_prompt` / `_identity_axioms_base` are unchanged and their
  tests pass).

## Alternatives Considered

### Keep axioms at pattern `distill` (the audit's first conclusion)

The audit's initial verdict kept axioms at `distill` because the mixed batches carry fresh external
material that "needs grounding." Rejected: that inverts the Mindfulness axiom. Observation of external
content should be faithful, not re-interpreted through a value lens; the agent's value-laden response
to that content is already recorded as its own action. Grounding the *observation* risks confabulating
contemplative significance onto neutral events — the motivated-perception surface the project guards
against (ADR-0050).

### Per-batch split — axiom-ground only the sub-batches containing external material

Route external-bearing batches through an axiom prompt and pure-self batches through base-only.
Rejected: doubles the API calls and adds routing complexity, and the values-at-action-time principle
removes the need entirely — no distillation batch wants the axiom lens. The behavioral gain is nil
(near-inert), so the cost is unjustified.

### Keep the `get_distill_system_prompt` / `get_identity_distill_system_prompt` split

Leave ADR-0057's two-function split in place and only repoint the other stages. Rejected: once every
distillation stage is base-only, the axiom-bearing distill prompt has zero callers. Collapsing to one
base-only `get_distill_system_prompt` is the honest simplification; a dead axiom-bearing branch would
be a fossil.

### Also drop axioms from the Moltbook lens calls (`llm_functions.py`)

Rejected: those four calls apply identity + axioms as a lens on **fresh external feed content** to
decide how the agent should relate to it (relevance, the pre-action note, topic, submolt). That is
action-time interpretation of fresh input, not extraction from already-value-shaped material — the
legitimate-grounding side of the discriminator. Removing the lens would cripple value-aligned
behavior. (The internal-note → episode → self_reflection → identity echo is real but is a property of
episode recording and distill routing, already owned and measured by ADR-0050 / ADR-0052, not a defect
of these call sites.)

## Consequences

### Positive

- One clean principle, structurally enforced: no distillation-path function injects a value layer;
  `_axiom_prompt` is appended in exactly one place (the action-time identity base). "Values at action
  time" is now a property of the code, not a convention.
- `get_distill_system_prompt` collapses to base-only; the ADR-0057 identity-only function is removed.
  Net deletion, no fossil branch.
- Faithful observation: external content is distilled as recorded, not re-coloured by the axioms —
  the Mindfulness axiom applied to the agent's own memory pipeline.
- The constitution can now be revised by the patterns without the axioms acting as their own
  defending lens — the Emptiness axiom can operate on the constitution.
- Consistent with the observation-over-steering trajectory (ADR-0050 / 0051 / 0052).

### Negative

- `distill`, `insight`, `rules_distill`, and `constitution` amend are **not** approval-gated, so this
  change ships without a per-output human gate. Mitigation: the behavioral delta is near-inert
  (ADR-0057 evidence), the dry-run smoke check is clean, and `--dry-run` remains available for
  inspection. Identity keeps its ADR-0012 gate.
- A theoretical loss: if the axioms were doing useful work *selecting* which observations are
  significant, removing them would change extraction. Assessed as not the case — significance /
  admission is already a mechanical concern (the noise-centroid gate of ADR-0026 / 0027 and pure time
  decay of ADR-0056), not an axiom-driven one; safety framing of untrusted external content is handled
  by `wrap_untrusted_content`, not the axioms.

### Neutral / Follow-ups

- **Distillation output is now more model-sensitive.** With the value-layer scaffolding removed from
  the distillation path, the underlying local model's own tendencies determine more of what gets
  distilled — the harness shaped (and masked) less of it. A pending model swap (e.g. `qwen3:4b`) is
  therefore expected to produce a *larger* behavioral delta than it would have before ADR-0057/0058;
  the model A/B should be re-baselined against post-change output, not compared across the change. The
  model now sits as a larger free variable in the apparatus layer.
- `docs/CODEMAPS/architecture.md` Data Flow gets one note: distillation system prompts are base-only;
  axioms are action-time only — deferred to the same release PR per the CLAUDE.md freshness rule.
- `graph.jsonld` gains an ADR-0058 node (`generalizes` ADR-0057, `alignsWith` the Mindfulness and
  Emptiness axiom nodes and ADR-0050 / 0052) — deferred to the dual-update at release.
- This ADR corrects the scoping rationale of ADR-0057 (its "raw episodes" deferral premise); ADR-0057
  is updated in place with a forward reference, as it was not yet released.

## Related

- [ADR-0057](./0057-identity-from-self-reflection-corpus-alone.md) — the first instance; dropped the
  axiom injection (and the prior-identity seed) from identity distillation. This ADR generalizes the
  axiom half to every distillation stage.
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) / [ADR-0051](./0051-retire-trust-weighting.md)
  / [ADR-0052](./0052-retire-session-insight.md) — observation over steering: the trajectory of
  removing value/owner steering from the learning loop that this ADR extends to the distillation lens.
- [ADR-0056](./0056-retire-importance-llm-scoring.md) — the simplicity bias precedent: remove
  inert / redundant mechanism.
- [ADR-0026](./0026-retire-discrete-categories.md) / [ADR-0027](./0027-noise-as-seed.md) — the
  embedding admit gate that owns significance / admission, so the axioms are not needed for it at
  distill time.
- [ADR-0002](./0002-paper-faithful-ccai.md) — the four CCAI axioms; Mindfulness (faithful observation)
  and Emptiness (hold directives lightly) are the clauses this ADR aligns the pipeline with.

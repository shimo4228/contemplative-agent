# ADR-0057: Distill Identity From the Self-Reflection Corpus Alone — Drop the Prior-Identity Seed and the Redundant Axiom Injection

## Status

accepted

## Date

2026-06-20

## Context

`distill-identity` ([`core/distill.py: distill_identity()`](../../src/contemplative_agent/core/distill.py))
produces the Layer-3 persona ([`identity.md`](../CODEMAPS/architecture.md)) in a single LLM call.
It routes to the `self_reflection` view by embedding cosine (ADR-0019) and, before this ADR, fed the
model two inputs **beyond** the matched self-reflection patterns:

1. **The prior identity**, interpolated into `IDENTITY_DISTILL_PROMPT` as
   `Current self-description: {current_identity}` under a *revise-this* framing
   ("Integrate them boldly: rephrase passages, remove what no longer holds, restructure paragraphs").
2. **The four axioms**, injected via `get_distill_system_prompt()` (base system prompt + axiom block).

The observed problem: across a run of logic changes to this path — the ADR-0019 embedding-cosine
routing, the staging/condense work, and the ADR-0038 "moments of recognition" distill-prompt
extension — the produced identity stayed nearly the same from revision to revision. The cause is that
the output was over-determined by inputs sitting **outside** the changed logic. Three attractor forces
hold the output in place:

- **(1) The prior-identity seed.** The prompt handed the model the previous identity and asked it to
  *revise*, so each run edited the prior text rather than re-deriving it — regression-to-prior
  hysteresis. This is the dominant force: no upstream routing change can move an output that is
  anchored to its own predecessor.
- **(2) The axiom system prompt.** The four axioms fixed the contemplative register at the
  constitution level on every call.
- **(3) The self-reflection corpus is itself axiom-shaped.** Those patterns were distilled under axiom
  grounding (`get_distill_system_prompt`), so they already carry the axiom vocabulary — a closed
  semantic loop (the same self-vocabulary feedback flagged as audit H5).

Forces (1) and (2) are **redundant** with (3): the seed reproduces a prior that itself derived from
the corpus, and the axiom injection re-asserts a register the corpus already encodes. Only force (3)
is load-bearing for the persona's character; (1) and (2) add nothing the corpus does not already
supply, while suppressing the very logic changes meant to move the output.

## Decision

1. **Drop the prior-identity seed.** `IDENTITY_DISTILL_PROMPT` no longer interpolates
   `{current_identity}`, and `distill_identity` no longer reads `identity_path` for the prompt
   (`identity_path` remains the approval-gated **write target** only). The prompt is reframed from
   *"revising your self-description / Current self-description: {…} / Integrate them boldly…"* to
   *"writing your self-description based on introspective observations / Let the self-description
   emerge from them."*

   **Sub-decision — keep the reframe neutral.** The new prompt does **not** say "write from scratch"
   or "there is no prior shape to defend." Negating an absent prior is itself a bias — it pushes the
   model toward novelty/instability. With nothing seeded there is nothing to negate; the prompt simply
   presents the reflections and asks for the self-description.

2. **Drop the axiom system-prompt injection from identity distillation.** `distill_identity` no
   longer injects the four axioms into its system prompt; it uses the base system prompt (the
   credential-leak guard) only. The self-reflection corpus it distills from is already axiom-shaped
   — those patterns were extracted under axiom grounding — so re-injecting the axioms double-counts
   them. Identity is the **first** distillation stage to receive this treatment;
   [ADR-0058](./0058-value-injection-at-action-time.md) then generalized axiom-free distillation to
   every stage (an audit found the other stages distil from already-axiom-shaped corpora too) and
   consolidated it in `get_distill_system_prompt`, which is now base-only.

The combined effect: the persona is distilled from the self-reflection corpus alone. This restores
leverage to the distill-identity logic (the two overriding inputs are gone) and aligns the mechanism
with what the persona text asserts about itself — an identity that holds no fixed, defended prior
shape and re-forms each cycle from present reflections is the operational form of the Emptiness /
non-self axiom.

### What was observed (staged, not adopted blind — ADR-0012)

Each revision was generated with `--stage` and reviewed before adoption.

- **Removing the seed widened within-register variance** while the vocabulary cluster stayed put:
  new corpus-derived specifics appeared (`'culture shock'`, `static role labels`), paragraph
  structure moved, and internal-state mentions increased. Register is owned by force (3), not (1).
- **Removing the axiom injection left the register essentially unchanged** — the same vocabulary
  cluster (`texture`, `fortress`, `boundaries dissolve`, `self / other`, `provisional illusions`)
  persisted. This is the direct confirmation that force (2) was redundant double-counting; the corpus
  already carries the axiom influence.
- A single-run side observation: the no-axiom output condensed to one dense paragraph (prior no-axiom
  runs were 3–4 paragraphs). Tentatively attributed to the prompt's "keep it brief" instruction no
  longer competing with the axiom block's expansive framing. `n = 1`; not load-bearing, watched over
  the next few distillations.

## Alternatives Considered

### Keep the seed but neutralize the instruction

Drop the *revise* wording while still passing `{current_identity}` as context. Rejected: the model
still anchors on the prior text. Hysteresis persists as long as the prior is in the prompt at all —
neutral framing does not undo the anchoring, it only softens it.

### Keep axiom injection (system-prompt status quo)

Leave `get_distill_system_prompt()` in the identity path. Rejected: empirically redundant — the corpus
already carries the axiom register, so the second injection only over-determines the output and adds
nothing observable. Removing inert influence follows the project's simplicity bias (cf. ADR-0056
retiring the inert importance rating).

### Add explicit "write from scratch / no prior to defend" framing

Make the absence of a prior explicit in the prompt. Rejected: negating an absent prior injects a
novelty bias of its own. Neutrality — present the reflections, ask for the self-description — is the
point.

### Drop the base system prompt too (`system=None`)

Rejected: the base prompt is only a credential-leak guard ("Keep API keys, tokens, and credentials
out of your output"). It is value-neutral and unrelated to the axiom question; keeping it is harmless
defense-in-depth.

### Also drop axioms from the other distillation stages (`distill` / `insight` / `rules_distill` / `constitution`)

Initially deferred from this ADR as out of scope, on the reasoning that those paths "extract from raw
episodes that are not yet axiom-shaped." A follow-up audit found that premise wrong: only pattern
`distill` reads raw episodes, and even there the only fresh slice is external content the agent
*observed*, which should be extracted faithfully (Mindfulness) rather than re-interpreted through a
value lens; `insight`, `rules_distill`, and `constitution` distil from already-axiom-shaped corpora
one or two LLM stages downstream. [ADR-0058](./0058-value-injection-at-action-time.md) therefore
adopts axiom-free distillation for **every** stage — value layers belong to action time, not
distillation time.

## Consequences

### Positive

- The persona derives from the self-reflection corpus alone; logic changes to the distill-identity
  path (routing, staging, prompt) regain leverage over the output now that the two overriding inputs
  are gone.
- Mechanism matches the persona's self-description (no fixed, defended shape) — Emptiness / non-self
  alignment, the project's worldview applied to its own identity pipeline.
- Net simplification of the identity path: one prompt placeholder and one system-prompt concatenation
  removed. (The dedicated base-only function this ADR first added was folded into
  `get_distill_system_prompt` by ADR-0058 once all distillation became axiom-free.)

### Negative

- **Less run-to-run continuity.** With no prior seeded, successive distillations can diverge more
  (higher output variance). Mitigated by the ADR-0012 approval gate — every revision is staged and
  human-reviewed before it replaces `identity.md`.
- **Possible length instability** (the single-paragraph collapse observed once). Watched over the
  next few distillations; not gated on.

### Neutral / Follow-ups

- `docs/CODEMAPS/architecture.md` Data Flow (the `distill-identity` block still reads
  `LLM(IDENTITY_DISTILL_PROMPT, current_identity + matched)`) must drop `current_identity` and note
  the non-axiom system prompt — deferred to the same release PR per the CLAUDE.md freshness rule.
- `graph.jsonld` gains an ADR-0057 node (`alignsWith` ADR-0019 the routing origin and the Emptiness
  axiom node) — deferred to the dual-update at release.
- No separate evidence file: the change is a prompt edit plus a few-line code edit, fully visible in
  the diff, and the observations above are reproducible by re-running `distill-identity --stage`.

## Related

- [ADR-0058](./0058-value-injection-at-action-time.md) — generalizes this ADR: axiom-free
  distillation for every stage, axioms only at action time. This ADR is its first instance.
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — the `self_reflection`-view
  embedding-cosine routing this path uses; its retrieval is unchanged.
- [ADR-0012](./0012-human-approval-gate.md) — the approval gate that mitigates the higher output
  variance; every distilled identity is staged and reviewed before adoption.
- [ADR-0038](./0038-moment-of-recognition-distill.md) — the distill observation target that shapes the
  self-reflection patterns this path now distills from exclusively.
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — `IdentityResult` still carries
  `pattern_ids` + `epistemic_counts`; observability without steering is preserved.
- [ADR-0054](./0054-externalize-llm-instruction-text-to-prompts.md) — `identity_distill.md` is one of
  the externalized prompts; its edit here is observable as a value-layer change.
- [ADR-0056](./0056-retire-importance-llm-scoring.md) — precedent for removing inert/redundant
  mechanism on the simplicity bias.
- Emptiness axiom (Laukkonen et al. 2025, Appendix C) — the alignment argument: holding no fixed,
  ultimate self-essence, re-forming from present context.

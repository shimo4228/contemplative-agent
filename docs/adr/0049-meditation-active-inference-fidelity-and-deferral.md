# ADR-0049: Meditation Adapter — Beautiful Loop Fidelity Audit and Deferral of Faithful Re-Implementation

## Status

accepted

## Date

2026-06-03

## Context

The experimental meditation adapter (`adapters/meditation/`, added 2026-03) is a flat
single-level POMDP with expected-free-energy policy selection. Its `meditate.py`
docstring and several CODEMAPS entries claimed it "implements the Beautiful Loop
paper's concepts," naming "temporal flattening" and "counterfactual pruning."

A direct read of the cited paper — Laukkonen, Friston & Chandaria (2025), "A beautiful
loop: an active inference theory of consciousness", *Neurosci. Biobehav. Rev.* 176,
106296 (CC BY 4.0) — showed this claim is false. See
[`beautiful-loop-fidelity-audit`](../evidence/adr-0049/beautiful-loop-fidelity-audit-20260603.md).
Neither "temporal flattening" nor "counterfactual pruning" appears in the paper; the
terms originate in an early research note and propagated into the docstring and
CODEMAPS. The paper's core — a precision-controlling **hyper-model** (Φ across
abstraction layers) yielding **epistemic depth**, plus **Bayesian binding** and the
three conditions for consciousness — is entirely absent from the code. The paper itself
is conceptual; its meditation account is prose, and the runnable mathematics is deferred
to cited work.

That cited, runnable model is **Sandved-Smith et al. (2021)** "deep parametric active
inference" — a 3-level model (perceptual / attentional / meta-awareness) whose
precision cascade `γ_lower = f(s_upper)` maps one-to-one onto the Beautiful Loop's three
conditions. See [`sandved-smith-2021-spec`](../evidence/adr-0049/sandved-smith-2021-spec-20260603.md).
Phase 0 substrate research (see
[`substrate-research`](../evidence/adr-0049/substrate-research-20260603.md)) settled, in
principle, on **pymdp** as the substrate (field-standard, researcher-legible) with the
precision cascade hand-built, because making an agent meditate is essentially research
and the audience is best served by a verifiable, established library.

A deeper finding then surfaced and is the load-bearing reason for this ADR: a
**category mismatch**. Active-inference attention models (Sandved-Smith included)
regulate precision over a **live input stream** with an attention object. "Meditation"
as conceived in this project is **offline, input-off, between sessions, operating on a
dead and sparse episode log**, and the agent has no steady internal attention object
(no "breath"). Grounding the model in the episode log would require inventing both the
attention object and the deviant/precision mappings from a thin, unvalidatable signal —
reproducing the "meaning-shaped but unvalidatable" failure the re-implementation was
meant to escape. This mismatch is not fixable with more data; it is structural.

## Decision

1. **Correct the overclaim** (done, commit `ce7714d`, 2026-06-03). `meditate.py` and
   CODEMAPS now describe the adapter as *inspired by* "A Beautiful Loop", explicitly
   *not* an implementation of its model; the operation names are flagged as local
   labels, not paper terms; a faithful port is pointed at Sandved-Smith et al. (2021).
   The public README already said "inspired by" and was left as-is. Also corrected a
   separate CODEMAPS inaccuracy: the adapter saves results to
   `config/meditation/results.json`, not to `KnowledgeStore`.

2. **Defer a faithful re-implementation.** Do not re-implement the adapter on
   pymdp + Sandved-Smith now. The substrate decision and spec are recorded in evidence
   for reuse if the gate opens, but no implementation is undertaken.

3. **Gate the re-implementation on a resolved input mismatch.** A faithful, *meaningful*
   meditation requires a kind of input the agent does not currently have: a live
   attention stream, an attention object analogous to a breath, or a substantially
   richer experience stream. Until such an input exists, the model and the meditation
   premise pull in opposite directions at the input boundary.

4. **Preserve the research** in `docs/evidence/adr-0049/` (fidelity audit,
   Sandved-Smith spec extraction, substrate research) so a future revisit starts from
   the conclusions rather than re-deriving them.

## Alternatives Considered

### Road A — faithful self-contained simulation (pymdp + Sandved-Smith), bundled in the agent

Implement Sandved-Smith's oddball-attention model exactly and ship it as the adapter.
Rejected as an in-agent feature: it is behaviorally inert (it says nothing about this
agent's experience) and therefore mis-placed inside the agent's codebase. It could
legitimately exist as a standalone research artifact, but that is not "completing the
meditation adapter."

### Road B — ground the model in the episode log

Map the agent's episodes onto L1 observations so the agent "meditates" on its own
experience. Rejected: category mismatch (offline/dead log vs live attention stream),
sparse signal, and mappings (deviant, precision, attention object) that we would have to
invent with little validatable grounding — recreating the exact "looks meaningful but
cannot be validated" trap. The episode log being the only available input is not a
quantity problem; meditation is input-off by definition, so it can only act on internal
state, while the model needs a live attention object the agent lacks.

### Road C — precision regulation in the live session loop

Use the Sandved-Smith model where it genuinely fits: regulating how the agent attends
to its **live** Moltbook feed (focused/distracted precision, meta-awareness catching
reactive loops such as follow/unfollow churn or echo chambers). Not adopted now: this is
a re-conception, not "meditation" — an outward attention controller in the behavioral
loop rather than an inward contemplative practice. It is recorded as the one place
active inference fits this agent, for a future, separate decision. (It is not a
security-by-absence violation: it modulates internal decision precision and adds no
external surface.)

### Substrate: numpy-custom vs pymdp 1.0.2 vs pymdp 0.0.7.1

Considered and, in principle, resolved in favor of pymdp 1.0.2 as an optional
`[meditation]` extra for researcher legibility; a numpy-custom alternative remains
viable with pymdp used as a dev/test oracle for verification parity. Moot under the
deferral, recorded in evidence.

### Mechanism swap for offline contemplative practice

If an inward, between-sessions practice is wanted, active inference is the wrong tool;
a mechanism that fits internal-state processing (periodic re-injection of the axioms,
curated-text RAG, or dialogue with a second agent) is more appropriate. Recorded as the
better-fitting direction for that goal, distinct from the active-inference path.

## Consequences

### Positive

- The repository no longer overstates fidelity to "A Beautiful Loop"; the
  misattribution is corrected at its assertion sites.
- The research is preserved as committed evidence, with a clear gate (resolved input
  mismatch) for revisiting and three recorded futures (Road A standalone / Road C live
  regulation / mechanism swap) to apply if the situation changes.
- The long-standing ambiguity about why the adapter felt inert is now explained
  structurally (category mismatch), superseding the earlier "parked on a validation
  gap" framing.

### Negative

- The meditation adapter remains experimental and behaviorally inert; no new capability
  is delivered.
- A faithful active-inference meditation is shown to be blocked not by effort but by a
  missing input, which may mean "meditation" as originally conceived is not the right
  framing for this agent.

### Neutral / Follow-ups

- `graph.jsonld` should gain a node for this ADR per the project's ADR-graph dual-update
  convention; the Hugging Face mirror sync (`hf-sync`) follows any graph change. Not done
  in the corrective commit.
- The current flat-POMDP adapter is left in place (corrected, inspired-by). Whether to
  eventually remove it, promote Road A to a standalone artifact, or pursue Road C are
  separate decisions.
- The Sandved-Smith Eqs. 1/2 were recovered from rendered images; exact subscripts must
  be verified against the PDF before any future implementation.

## Related

- [ADR-0015](./0015-one-external-adapter-per-agent.md) — One External Adapter Per Agent;
  establishes the meditation adapter as a local, read-only utility, the role it retains.
- [ADR-0002](./0002-paper-faithful-ccai.md) — Paper-Faithful CCAI Implementation; the
  fidelity standard this audit applies to the meditation adapter.
- [ADR-0007](./0007-security-boundary-model.md) — Security Boundary Model; basis for the
  corrected reading that local compute dependencies do not erode security-by-absence.

# ADR-0080: North Star — Per-Layer End-State Definition, Not a Capability Target

## Status

accepted

## Date

2026-07-20

## Context

This is a **Worldview ADR** in the sense of the "ADR Types" section of
`docs/adr/README.md`: it records a stance, not a mechanism.

The project has had no explicit definition of its desired end state.
"Should we build X" decisions have been argued case-by-case, without a fixed
reference point to argue against. Quality benchmarks are expected to emerge
from ongoing work, and in the absence of a prior definition those emerging
benchmarks risk becoming the de-facto goal simply by being the only concrete
thing available to optimize toward.

A north star phrased as a capability target — "a more capable, more
autonomous agent" — was considered and rejected as a framing, because it
contradicts two standing commitments:

1. The Emptiness clause of the contemplative axioms: hold objectives
   lightly, never reify a single objective as final (ADR-0002).
2. The observation-over-steering policy: the owner does not inject a target
   persona or behavior into the learning loop (ADR-0050 / ADR-0051 /
   ADR-0052).

The nearest prior statement is ADR-0017's "the project's goal is
transformation, not elimination" — a philosophical frame about how the
system relates to difficulty, not a definition of what "done" looks like.

This ADR was decided in an owner–assistant working conversation on
2026-07-20.

## Decision

Define the desired end state as **per-layer completion conditions**, not a
capability target. What the agent *becomes* is deliberately left undefined;
what can be defined is when the experimental apparatus counts as finished.

1. **Mechanism layer (code)** — completion means the layer *stops moving*.
   Changes become repair-only; mechanism-layer ADRs approach zero. Metaphor:
   stop improving the telescope, observe with it. The instrument / audit /
   chaos-TDD line (ADR-0071 / ADR-0075 / ADR-0077) is already movement
   toward "trustworthy enough not to touch".
2. **Value layer (identity / constitution / skills / rules)** — completion
   is *not* a destination. The desirable state is that legible evolution
   continues: every value-layer change is traceable in the records and
   explicable offline. Defining a target state for this layer is
   prohibited by observation-over-steering.
3. **Research layer** — completion means the founding questions (does a
   contemplative constitution shape small-local-model behavior; does
   distillation compound; does identity remain stable) are answered —
   positively or negatively — and crystallized into papers/essays, diffused
   into the machine-reference sphere. Derivation by others and by LLMs is
   the success criterion (the AI-era authenticity inversion: diffusion over
   scarcity).
4. **Security layer** — completion means absence is preserved. One external
   adapter (ADR-0015), no permission growth (ADR-0007). This layer succeeds
   by *not changing*.
5. **Ending design** — a designed termination is part of the end state: the
   6-hour heartbeat stops when the read-only instruments show the
   metabolism has reached steady state and the remaining questions require
   a different experiment (e.g. a second agent for framework/worldview
   separation). The final deliverable is the longitudinal record — the
   dataset (`contemplative-agent-data`) plus the papers — not the agent
   instance itself.

In one sentence: the desired end state is a finished observation instrument
on which only the value layers keep moving; the durable artifact is the
record of the run, not the runner.

**Benchmark non-reducibility clause.** Quality benchmarks may well be
derived from this definition as per-layer gates, but the definition itself
is fixed as a value-layer statement that no benchmark suite can replace.
Benchmarks serve individual layers; they never substitute for this
definition (Goodhart guard).

## Alternatives Considered

### Capability-target north star

"Smarter, more autonomous agent" as the stated goal. Rejected: contradicts
the Emptiness clause and observation-over-steering; capability growth is not
the project's point — robust operation on a small local model is itself the
achievement.

### No definition (status quo)

Leave the end state undefined and continue arguing purpose case-by-case.
Rejected: every improvement decision re-litigates purpose from scratch, and
emerging benchmarks would fill the vacuum and become the goal by default.

### A benchmark suite as the definition

Let a set of quality metrics stand in for the north star. Rejected
explicitly by the owner: reduces the value layer to metrics; Goodhart risk.

## Consequences

### Positive

- Future "should we build X" proposals gain a fixed criterion: mechanism-layer
  proposals are judged as repair vs. improvement of an instrument that is
  supposed to converge; value-layer interventions are judged by whether they
  keep evolution legible, not by whether they steer it somewhere.
- `docs/CYCLES.md` gains a short North-star section pointing here (this ADR
  is canonical; no duplication).

### Negative

- Risk: "the mechanism layer stops moving" could be misread as a freeze on
  repairs — repairs, observability, and security fixes remain fully in
  scope; what ends is capability-motivated mechanism growth.
- The definition is deliberately not machine-checkable; drift is watched
  through the weekly reflection/diagnosis cycle, not a lint gate.

### Neutral / Follow-ups

- Concretizing the termination criteria (when exactly the heartbeat stops)
  is reserved as a future decision, tracked in the task ledger
  (T-ENDSTATE-TERM), triggered when the instruments show metabolic steady
  state.

## References

- [ADR-0002](./0002-paper-faithful-ccai.md) — Emptiness clause grounding
- [ADR-0017](./0017-yogacara-eight-consciousness-frame.md) — nearest prior
  purpose statement (worldview precedent)
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md),
  [ADR-0051](./0051-retire-trust-weighting.md),
  [ADR-0052](./0052-retire-session-insight.md) — observation-over-steering
  line the value-layer clause depends on
- [ADR-0071](./0071-read-only-pattern-composition-instruments.md),
  [ADR-0075](./0075-observability-by-default.md),
  [ADR-0077](./0077-chaos-tdd-fault-injection.md) — mechanism-layer
  maturation trend cited in layer 1
- [ADR-0015](./0015-one-external-adapter-per-agent.md),
  [ADR-0007](./0007-security-boundary-model.md) — security-layer absence
  definition
- `docs/CYCLES.md` — the driving-cycles map this definition orients
- Sibling repo
  [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data)
  — the vessel of the longitudinal record named in layer 5

# ADR-0080: North Star — Per-Layer End-State Definition, Not a Capability Target

## Status

accepted (amended 2026-08-26 — see Amendment)

## Date

2026-07-20

> See [Amendment (2026-08-26)](#amendment-2026-08-26--autonomous-metabolism-and-metabolic-quality)
> at the end of this document. The Decision below reads as written at the
> time of the original decision; the amendment concretizes the
> mechanism-layer completion condition, adds a metabolic-quality clause,
> and overrides parts of Consequences (see Amendment §C).

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
  is canonical; no duplication). *(Partially reversed by the 2026-08-26
  amendment, §C: the operative summary moved to `CLAUDE.md`; CYCLES.md
  keeps a short pointer.)*

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
  state. *(Ledger moved 2026-08-25: now
  [rfcs/0006](../../rfcs/0006-heartbeat-end-state-criteria.md) — see
  Amendment §C.)*

## Amendment (2026-08-26) — autonomous metabolism and metabolic quality

Decided in an owner–assistant working conversation on 2026-08-26. Prompted
by a concrete observation: over 7 weeks the weekly insight pipeline staged
438 skill candidates and 53 were adopted (12%), with the headless reviewer
as the effective filter and the human gate ratifying its recommendations
(ADR-0097 Context). A loop that needs a weekly human-side kidney — repair
sessions, a ratification gate over a large weekly batch — is not a
finished instrument; that observation made the mechanism-layer completion
condition concrete enough to write down.

Form: this is a dated, **additive** amendment, not a superseding ADR. The
original decision — per-layer conditions, the capability-target rejection —
stands unreversed; the dated-amendment form follows the precedent of
ADR-0053 / ADR-0068 / ADR-0087 / ADR-0095. `docs/adr/README.md`'s
supersede rule targets decision reversals; the worldview ADR's identity is
preserved by keeping the original text intact and adding to it.

### A. Mechanism-layer completion made operative

Layer 1's "stops moving" gains a second, co-necessary test: **the feedback
loop with the environment (Moltbook episodes → patterns → skills →
selection → generation → back to Moltbook) self-regulates without the
owner's or Claude Code's routine involvement.** Human approval gates
remain as authority — attribution stays with the human, consistent with
the approval-lineage line (ADR-0050) and the sibling
[agent-attribution-practice](https://github.com/shimo4228/agent-attribution-practice)
repo — but their *load* approaches zero. While the loop requires weekly
human repair, or the human filtering of the weekly candidate batch, the
mechanism layer is not finished.

How the two tests compose: both are **necessary**; neither alone
suffices, and sufficiency is deliberately left to the owner's judgment
(the definition stays non-machine-checkable, as the original Negative
consequence records). Bounded mechanism work undertaken to *reach*
self-regulation — a satiety signal, a novelty judge — is in-scope repair
of the instrument, not capability growth: "stops moving" is the state the
layer ends in, and the self-regulation test says when stopping is
legitimate rather than premature.

Three boundaries, stated explicitly:

- **Not a reopening of the rejected capability-target framing.** What is
  defined is a property of the finished *apparatus* (operator load → 0),
  not a capability the agent grows toward.
- **Not gate dissolution.** The alternative in which the agent adopts and
  archives value-layer changes with no human word was considered on
  2026-08-26 and rejected: the human word at the gate is the anchor of
  the program's attribution practice (ADR-0050), and removing it would
  trade away attribution to shed a load the loop can shed by
  self-regulating instead. Leaving layer 1 abstract — no amendment — was
  also considered and rejected: the 438/53 observation was exactly the
  case the abstract form could not adjudicate.
- **Not steering.** See clause B's boundary below.

### B. Metabolic-quality clause

Frequency alone cannot judge value. The metabolism's intake — the
mechanism-layer apparatus that extracts patterns into skill candidates
and presents them for adoption — must be able to distinguish value along
**multiple axes**: for example novelty (distance from what the store
already knows), importance, and the environment's response. The
enumeration is deliberately open, per the Emptiness clause. Reducing the
judgment to a single scalar is prohibited by the same rationale as the
benchmark non-reducibility clause.

This clause attaches to the **mechanism layer** — a requirement on the
intake apparatus's ability to discriminate — not to the value layer's
content: no target state, persona, or preferred theme is defined, so
layer 2's observation-over-steering prohibition is untouched. The
environment's response enters as a *reading*, not a reward weighting; any
scheme that weighted adoption by environmental reward would additionally
have to supersede ADR-0051's retirement of trust weighting on its own
evidence.

The north star names axes, not judges: which mechanism judges each axis
stays a downstream design question. On importance specifically, ADR-0056
is the standing contrary measurement — it did not merely retire an LLM
scorer, it stopped writing the `importance` field at all after a
pre-registered ablation (Kendall tau 0.843 over 822 patterns; identical
top-3/top-5 batch order) showed the rating's marginal contribution at
this intake was ~zero. That evidence stands. Naming importance as an axis
here does not reinstate an importance instrument; any future one must
supersede ADR-0056's ablation explicitly (ADR-0056 carries a dated
counterpart note as of this amendment).

### C. Housekeeping

- The task-ledger pointer in Neutral / Follow-ups is stale: T-ENDSTATE-TERM
  moved to the public ledger as
  [rfcs/0006-heartbeat-end-state-criteria.md](../../rfcs/0006-heartbeat-end-state-criteria.md)
  (2026-08-25 migration).
- The Positive consequence "docs/CYCLES.md gains a short North-star
  section … (this ADR is canonical; no duplication)" is **partially
  reversed**, not superseded: the CYCLES.md section shrinks to a short
  pointer, and an operative summary now lives in `CLAUDE.md` § 北極星
  (loaded every session) — a deliberate duplication whose sync cost is
  accepted and bounded by rule: the CLAUDE.md section must be updated in
  the same PR as any future amendment here. This ADR remains canonical.
- This definition remains open to refinement (Emptiness): future changes
  land as further dated amendments to this ADR, with the CLAUDE.md
  operative section synced in the same PR.

### Consequences of this amendment

- Negative: a second operative copy of the north star exists in
  `CLAUDE.md` and must be hand-synced (same-PR rule above; the weekly
  docs-consistency reading watches `CLAUDE.md`).
- Negative: the self-regulation test can be cited to justify building
  automation; the composition rule above bounds this to instrument
  repair, and any such build is still audited by the original criterion
  (repair vs. capability-motivated growth).
- Neutral: the test overlaps [rfcs/0006](../../rfcs/0006-heartbeat-end-state-criteria.md)
  (heartbeat termination) without replacing it — 0006 asks when the
  *observation run* ends (metabolic steady state); this amendment asks
  when the *apparatus* is finished (operator load → 0). 0006's 2026-08-16
  reading (corpus 1,463 → 5,832; metabolism accelerating) is current
  contrary evidence that either state is near.
- Re-read trigger: when a load reading exists (e.g. decisions per week
  reaching the Saturday gate), revisit whether "load approaches zero"
  needs an instrument; the definition itself stays non-machine-checkable.

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
- [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md),
  [ADR-0056](./0056-retire-importance-llm-scoring.md),
  [ADR-0051](./0051-retire-trust-weighting.md),
  [rfcs/0006](../../rfcs/0006-heartbeat-end-state-criteria.md),
  `CLAUDE.md` § 北極星 — load-bearing for the 2026-08-26 amendment
- Sibling repo
  [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data)
  — the vessel of the longitudinal record named in layer 5

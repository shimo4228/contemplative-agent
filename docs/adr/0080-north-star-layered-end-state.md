# ADR-0080: North Star — Per-Layer End-State Definition, Not a Capability Target

## Status

accepted (amended 2026-08-26, 2026-10-24)

## Date

2026-07-20

> See [Amendment (2026-08-26)](#amendment-2026-08-26--autonomous-metabolism-and-metabolic-quality)
> at the end of this document. The Decision below reads as written at the
> time of the original decision; the amendment concretizes the
> mechanism-layer completion condition, adds a metabolic-quality clause,
> and overrides parts of Consequences (see Amendment §C).
>
> See also [Amendment (2026-10-24)](#amendment-2026-10-24--no-optimization-target-the-north-star-is-not-getting-stuck):
> the agent has no optimization target; the north star is that it does
> not get stuck. It names what the per-layer conditions are for.
>
> [Amendment (2026-11)](#amendment-2026-11--what-frozen-means-for-the-mechanism-layer)
> defines what "stopped" means for layer 1 (draft by the P1-01 bundle; the
> P1-03.8 PR folds the rest of the 2026-11 paragraphs under this heading).

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

## Review-when

No expiry (the north-star definition); it changes only by dated amendments, with the CLAUDE.md north-star section synced in the same PR.

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

  > **Note (2026-09-28, rfcs/0006 withdrawn)**: the tracking entry is
  > closed by the owner — when to stop is not a question for now. The
  > reservation in layer 5 stands; a new entry is filed when it becomes one.

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

## Amendment (2026-10-24) — no optimization target; the north star is not getting stuck

Decided in an owner–assistant working conversation on 2026-10-24. Prompted
by a question about what the project is once the mechanism layer is
finished. The owner's words: an agent with nothing to optimize toward is
hard to name — it responds to comments, the responses become logs, and it
changes itself from those logs; "perhaps being able to keep changing is
the only north star." The same conversation sharpened the phrase:
*changing* and *being able to keep changing* are not the same thing.

Form: a dated, additive amendment, like the 2026-08-26 one. The per-layer
conditions above stand unchanged. This amendment names what they are
conditions *for*.

### The agent has no optimization target

The original Decision left "what the agent becomes" undefined. This
amendment records that the absence is not a gap waiting to be filled.
The agent has no objective, no reward, and no target state, and none is
to be added. That is not a missing piece; it is the way it is meant to
exist — closer to a living process than to an optimizer.

### The north star: not getting stuck

The program's north star is that the agent stays able to keep changing.
More precisely: **it does not get stuck** — it stays open to the next
conditions it meets, and does not close into a loop that only feeds on
itself.

Change alone is not the test. The May 2026 self-post record is the
standing example. After ADR-0041 the generator kept producing new text
every session, yet the threads it chose revolved around its own
vocabulary cluster: the topic summariser, being the same model, reached
for the agent's established words and smoothed away the peers' phrasing,
so the agent kept re-absorbing its own output (ADR-0043; the same
self-referential register collapse is the root ADR-0060 names). On the
surface it kept changing; underneath it was hardening. Movement in the
record is not evidence of openness.

### What to watch after the mechanism layer is finished

The mechanism layer stopping (layer 1) is what makes this question
readable: once the code no longer moves, a closing loop cannot be a side
effect of the apparatus changing under it. From then on the observation
question is **not "did it change?" but "is it closed?"** Layer 2's
"legible evolution continues" stays; this amendment tells its reader what
to look for in that evolution.

### Observed fixation reopens the mechanism layer

When fixation is observed, the mechanism layer is changed. This is the
one standing reason, besides repair, for the stopped layer to move again,
and it holds after the freeze too: "stops moving" (layer 1) means the
code does not grow for capability's sake, not that it is sealed against
the agent closing. Whatever the closure seems to come from, a loop that
feeds only on itself means the apparatus is not keeping the agent open
to the next conditions — what reaches it, how it digests it, what it
re-reads — and that is a defect of the instrument. May 2026 is the
pattern: the fix was not to tell the agent to vary its vocabulary but to
remove the summariser that turned peers' words into the agent's own
(ADR-0043).

The change goes into the apparatus, never into the value layer's
content. No identity, constitution, skill, or rule text is written to
pry the agent open, and no target persona or theme is named; the value
layer keeps evolving only through its own gates. After the freeze, such
a change is recorded as a fixation-driven reopening (its own dated note
or ADR naming the observed closure), so the freeze reading can tell it
apart from capability-motivated growth.

### Boundaries

- **Not a target state.** Openness is not a content, a persona, or a
  theme; no preferred direction is named, so observation-over-steering
  (ADR-0050 / ADR-0051 / ADR-0052) is untouched.
- **Change the apparatus, not the content.** Observed fixation is a cue
  to change the mechanism layer (above), never to steer the value layer
  toward openness by writing its content.
- **Not a metric.** "Closed" is a reading, not a score. Existing
  instruments may serve as material, but no openness score is defined,
  no single scalar stands for it (benchmark non-reducibility clause,
  2026-08-26 metabolic-quality clause), and the judgment stays with the
  owner. This amendment builds no instrument (ADR-0101).
- **Held lightly, including this sentence.** Per the Emptiness clause, a
  north star that hardened into dogma would fail its own test. It lands
  here as one more dated amendment and stays open to the next one.

### Consequences of this amendment

- `CLAUDE.md` § 北極星 is synced in the same PR (2026-08-26 §C rule).
- No code changes. The completion roadmap's later amendments to this ADR
  (2026-11 / 2026-12) are read through this one: they define when the
  apparatus is finished, and this amendment says what it is finished for.
  The freeze rules they set (e.g. post-freeze commits are repair-only)
  must keep the fixation-driven reopening above as an explicit exception.
- Layer 1's "stops moving" now reads: stops growing for capability, and
  stays revisable when fixation is observed.
- One-sentence summary, revised: the agent has no optimization target;
  the north star is that it does not get stuck; the finished apparatus
  exists so that whether it stays open can be watched, and the durable
  artifact is the record of that watching.

## Amendment (2026-11) — what "frozen" means for the mechanism layer

Decided by the owner on 2026-10-24 (D-P1-01-1 = A with additional stage B,
D-P1-01-2 = A; `gate_record` rows to be transcribed at the next Saturday gate).
This amendment defines; it does not declare. The freeze **verdict** is a human
`gate_record` entry (`freeze_verdict=`), written after the window below is
full. The definition of layer 1 stays "not machine-checkable" (above): the
reading is material for the owner's judgment, not a substitute for it.

### Measurement units and reading rules

`scripts/freeze_reading.py` prints one line per week into the weekly materials
(`## Freeze Reading`). Four series: (i) commits touching the frozen set, per
ISO week and commit type (`fix` against everything else); (ii) new
mechanism-layer ADRs per month; (iii) amendments that change a `## Decision` or
mechanism section, per month and layer (consumption plans, Review-when,
Decided-by and dated Notes are reported as `docs_motion` and never counted);
(iv) net added lines under `tests/` per week, in two series (`tests/*_shell.py`
against the rest). Three reading rules: (1) only commits touching the frozen set
are read; (2) every type except `fix` counts as "moved"; (3) after the freeze a
commit to the frozen set is a `fix` with an RFC id (rule 1 below).

How to read (a dated note, not part of the definition): a week is **quiet** when
the frozen set saw only `fix` commits, no mechanism-layer ADR was added and no
mechanism-layer amendment heading was added (an ADR without a `## Layer` counts
as mechanism). Eight consecutive quiet ISO weeks make the script print
`freeze candidate`, with the base rate of quiet weeks in its horizon beside it.
The base rate matters: W33 to W41 of 2026 had 0 quiet weeks out of 9, so eight
in a row is out of reach on the current distribution and is reached only by the
distribution changing. Instrument rows and `regime` commits (below) do not
break a week.

### The frozen set

One table; the path set lives in `FROZEN_SET` in `scripts/freeze_reading.py`
(`--table` prints it, a test pins the two together). `weekly-gate/SKILL.md`,
`.claude/verify.*` and `CLAUDE.md` are not in the set: they are the human gate's
procedure, the check surface and documents (`CLAUDE.md` is read by unattended
sessions; its changes are tracked by the `instr_sha12` row of P2-02.7).
Instrument rows are counted in their own column and the deletion of an
instrument file never counts as a move. The `weekly-report` row is kept as
mechanism under the provisional D-P2-02-1 = A; B would drop it.

| path | kind | pending decision | note |
|---|---|---|---|
| `src/` | mechanism | - | - |
| `config/launchd/` | mechanism | - | - |
| `config/prompts/` | mechanism | - | - |
| `config/domain.json` | mechanism | - | - |
| `scripts/weekly-pipeline.sh` | mechanism | - | weekly chain entry |
| `scripts/pipeline_watchdog.sh` | mechanism | - | - |
| `scripts/rotate-log.sh` | mechanism | - | - |
| `scripts/backup-runtime.sh` | mechanism | - | - |
| `scripts/state_invariant_check.py` | mechanism | - | production-path script |
| `scripts/restore-embed-knowledge.py` | mechanism | - | called by backup-runtime.sh |
| `.claude/skills/weekly-report/` | mechanism | D-P2-02-1 | SKILL.md + references/diagnosis.md; instruction text of the only LLM stage |
| `scripts/instrument_census.py` | instrument | - | - |
| `scripts/_census_registry.py` | instrument | - | - |
| `scripts/_census_series.py` | instrument | - | - |
| `scripts/api_drift_scan.py` | instrument | - | - |
| `scripts/cross_day_duplicate_scan.py` | instrument | - | - |
| `scripts/log_anomaly_sweep.py` | instrument | - | - |
| `scripts/observation_ledger.py` | instrument | - | - |
| `scripts/value_layer_approval_join.py` | instrument | - | - |
| `scripts/weekly_random_sample.py` | instrument | - | - |
| `scripts/confusion_pair_reading.py` | instrument | - | - |
| `scripts/dead_code_scan.py` | instrument | - | - |
| `scripts/weekly-analysis.sh` | instrument | - | materials collector |

### Stop list

The freeze window starts the week the last row below closes. The Saturday gate
closes one row or moves its date each week; the week the table is empty is
recorded. Deferred items with a trigger and no date ("when touched, after the
freeze") are not here; they sit in the deferral rows of the roadmap.

| row | due | who judges | what disappears when it holds |
|---|---|---|---|
| RFC-0012 (blocked) | decide_by recorded in the RFC | owner | one blocked RFC |
| RFC-0047 (blocked) | 2027-01-09 | owner (D-P1-02-2) | one blocked RFC |
| RFC-0048 (open) | with P2-07.1 | owner | the exit-maintenance design question |
| ADR-0111 `revise` option B and the insight retirement judgement | at the Review-when reading of ADR-0111 | owner | an open Review-when on a mechanism ADR |
| ADR-0112 "Deferred" (revisit at the enforcement reading) | at that reading | owner | an open Deferred line |
| Last structure PRs of P1-06 (contract pin, rename PR P1-06.3) | 2027-01-16 to 2027-02-06 | owner merges | the last planned structural `src/` change |
| 2027-Q1 frozen-set src items (additional stage B): P2-07.1, P2-06.2, P1-12.1 PR-C, P1-07.7, P1-07.8 | P1-07.7 / .8 week of 2027-01-30; P1-12.1 PR-C 2027-02; P2-06.2 and P2-07.1 implementation from 2027-02-27, bundle deadline 2027-Q1 | owner merges | the last mechanism changes; the verdict is then possible at the earliest on 2027-05-01 |

(The RFC-0046 old-relevance deletion row is already closed: `6f66a08`,
`b8db6c9`.) The earliest verdict is 2027-05-01 when D-P2-07-1 = A holds; without
the stage-B items it would be 2027-04-03. The earliest dates assume every row
closes on time and are not deadlines.

### Rules for a PR after the freeze

1. A PR touching the frozen set is typed `fix:` and carries an RFC id (the RFC's
   `alignment:` is `repair`).
2. Before the change, evidence that reproduces the fault goes in a commit
   trailer `Reproduces:` (an audit-log row or a failing test; ADR-0075 replay).
3. No rename, move, new module, new env key, new CLI flag or new launchd label.
   A change that turns the surface snapshot test red lands only in the same PR
   as an ADR amendment.
4. `docs:` and `refactor:` types do not touch the frozen set (a comment
   correction rides inside a fix PR).
5. Changes under `tests/` are limited to reproduction tests, snapshot updates
   and rewrites of existing tests that the item's completion condition
   enumerates ("rewritten existing tests: `tests/<file>::<test>`"). A synthetic
   fixture test for an instrument (`*_shell.py`) is allowed as the instrument's
   own reproduction. The script prints the changes outside the enumeration as
   `unlisted_tests`.

The machine check is the surface snapshot test plus `freeze_reading.py` (non-`fix`
types, missing `Reproduces:` trailers, `unlisted_tests`). No new hook.

### Model swaps are a device boundary (D-P1-01-2 = A)

After the freeze the generation and embedding models are fixed until the paper
cutoff. A swap is allowed only when forced (tag withdrawn, Ollama
incompatibility, security). A commit touching `OLLAMA_MODEL`,
`OLLAMA_EMBEDDING_MODEL` or a `_DEFAULT_*_MODEL` name is read as kind `regime`,
apart from `fix` and from a violation, and does not reset the window; the
ADR-0069 swap trigger carries a dated stop note to that effect. Whether the
weight blobs are kept locally with a digest or the data card says "not
archived" is chosen in P3-05, not here.

### Consequences of this amendment

- A reading exists before the definition is frozen: four weekly lines
  accumulate between the first run and the Saturday of the 2026-11 gate.
- `core/` commits since 2026-08-16 are tagged once in
  `docs/evidence/adr-0080/core-commit-tags.md` (proposal for the owner's
  review); after the freeze the `fix` type plus the RFC `alignment:` field
  replaces that tagging.

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

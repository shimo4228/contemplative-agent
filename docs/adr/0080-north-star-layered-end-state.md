# ADR-0080: North Star — Per-Layer End-State Definition, Not a Capability Target

## Status

accepted (amended 2026-08-26, 2026-10-24, 2026-10-31)

## Date

2026-07-20

> See [Amendment (2026-08-26)](#amendment-2026-08-26--autonomous-metabolism-and-metabolic-quality)
> and [Amendment (2026-10-24)](#amendment-2026-10-24--ending-design-review-events-not-conditions)
> at the end of this document. The Decision below reads as written at the
> time of the original decision; the amendment concretizes the
> mechanism-layer completion condition, adds a metabolic-quality clause,
> and overrides parts of Consequences (see Amendment §C).
>
> See also [Amendment (2026-10-24)](#amendment-2026-10-24--no-optimization-target-the-north-star-is-not-getting-stuck):
> the agent has no optimization target; the north star is that it does
> not get stuck. It names what the per-layer conditions are for.
>
> [Amendment (2026-10-24) — freeze](#amendment-2026-10-24--what-frozen-means-for-the-mechanism-layer)
> defines what "stopped" means for layer 1 (the P1-01 bundle).
>
> [Amendment (2026-10-31)](#amendment-2026-10-31--where-the-human-word-stays-the-skill-store-exit-layer-1-and-how-run-length-triggers-are-read)
> fixes the three points where the human word stays, names layer 1 of the
> skill-store exit as the one exception to "Not gate dissolution", and reads the run-length triggers against their base rates.

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

  > **Note (2026-10-31, Amendment 2026-10-31 below)**: one exception
  > is carved out of this boundary, skill-store exit layer 1 (deterministic,
  > reversible, reported the same week, self-stopping; ADR-0122). Every other
  > value-layer adoption and archive keeps the human word.

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

## Amendment (2026-10-24) — what "frozen" means for the mechanism layer

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
mechanism section (heading-level proxy: the script counts amendment headings, not section content), per month and layer (consumption plans, Review-when,
Decided-by and dated Notes are reported as `docs_motion` and never counted);
(iv) net added lines under `tests/` per week, in two series (`tests/*_shell.py`
against the rest). Three reading rules: (1) only commits touching the frozen set
are read; (2) every type except `fix` counts as "moved"; (3) after the freeze a
commit to the frozen set is a `fix` with an RFC id (rule 1 below).

> **Note (2026-10-31, P1-08.10)**: beside series (iv) the line also prints
> `caplog_text`, the number of `caplog.text` occurrences in `tests/*.py` at the
> reading week's last commit — the text assertions the test convention migrates
> to reason codes when a test is touched. A reading only, with no threshold; it
> follows series (iv)'s reader and removal.

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
(`--table` prints it, a test compares the script's set with this table). `weekly-gate/SKILL.md`,
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

Exception: a change made because fixation was observed (the amendment "no
optimization target; the north star is not getting stuck" above) is not bound by
rules 1–5. It is recorded as a fixation-driven reopening (its own dated note or
ADR naming the observed closure), so the freeze reading can tell it apart from a
capability-driven expansion.

### Model swaps are a device boundary (D-P1-01-2 = A)

After the freeze the generation and embedding models are fixed until the paper
cutoff. A swap is allowed only when forced (tag withdrawn, Ollama
incompatibility, security). A commit touching `OLLAMA_MODEL`,
`OLLAMA_EMBEDDING_MODEL` or a `_DEFAULT_*_MODEL` name is read as kind `regime`,
apart from `fix` and from a violation, and does not reset the window; the
ADR-0069 swap trigger carries a dated stop note to that effect. Whether the
weight blobs are kept locally with a digest or the data card says "not
archived" is chosen in P3-05, not here.

### How "load" and "metabolism not stopped" are read (D-P2-01-1 = B, D-P2-01-3 = B)

Both decisions taken as recommended by the owner on 2026-10-24 (P2-01.3 / .5 /
.13). The definition of load stays a human judgement and is not mechanised
(see the 2026-08-26 amendment); what is fixed here is **how it is read**.

- **Load is three series, read side by side and never composed**: (i) rulings
  per gate (`gate_record`), (ii) reading volume (the Inventory's five numbers
  and the Exceptions / Ledger / findings line counts), (iii) work outside the
  gate (files touched other than `rfcs/README.md`, whitelist and registry
  edits). Beside them: `origin: gate` drafts filed, repair PRs, and the gate's
  minutes. "Rulings are 0 to 2 per gate" alone would read the mechanism layer
  as finished while the repository changes every week, which is why a single
  series was rejected (D-P2-01-1 option A).
  **What the script reads**: (ii) reading volume is a second table with the
  same eight weeks (P2-06.1) — per week, the report that week's gate reads
  (`reports/analysis/weekly-{Friday}.md`), its Inventory five numbers, the lines
  of its Inventory / Ledger / Deviations / Exceptions / Discarded sections, the
  carried fold, and the report and findings line counts. The
  recommendation-decision agreement is a column (`agree`, and `rm_agree` for the
  roadmap's own rows; the census "Gate record" section splits it per category).
  Their consumption plans are in `docs/evidence/adr-0080/README.md`. (iii)
  `outside` is approximated by the files of
  **every Saturday commit without a `Roadmap:` trailer**, because gate commits
  are not otherwise identifiable; it over-counts non-gate Saturday work (and
  squash-merged bundle PRs), a bias that can only block a candidate, never
  declare one. Tighten it at the 2026-11-28 gate.
- **One reader**: `scripts/self_regulation_reading.py` prints the eight-week
  table into the weekly materials. It declares `self-regulating candidate` when
  (i) + (ii-drafts) + (iii) is 0 for N consecutive weeks (N = 8 until the owner
  sets it); a week with no `gate_record` is an absent gate, not a quiet one.
  Sufficiency is the owner's, written as `self_regulation_verdict=` in the next
  `gate_record`.
- **The roadmap's own execution is read apart** (P2-01.13): `roadmap_start` /
  `roadmap_end` minutes, `category=roadmap` rulings and the files of commits
  carrying a `Roadmap:` trailer sit in their own columns and are outside the
  three series, so executing this roadmap cannot postpone or cause a
  self-regulating candidate.
- **A floor for "metabolism has not stopped"** (D-P2-01-3 = B): `adopted = 0`
  and `archived = 0` and no identity update for eight consecutive weeks makes the
  reader print `metabolism floor reached`. That is the trigger for filing the
  end-of-run consideration event under P4-01 (a deliberation, layer 2 reading);
  it neither declares steady state nor stops anything. Without the floor, "stopped"
  and "self-regulating" are indistinguishable from the logs.
- **Consumption plan (ADR-0101)**: (a) the Saturday gate reads the table in the
  weekly materials (`## Self-Regulation Reading`) every week; (b) the 2026-11-28
  gate decides D-P2-01-1 / -3 (which columns stay), and afterwards every "load to
  zero" proposal is judged against the eight rows; (c) retire the weekly table
  once the owner's verdict is recorded and N candidate weeks have passed, the
  quarterly T4 reads it afterwards. The reader treats a last week whose Saturday
  gate has not run (the chain passes Friday) as "gate pending", outside the
  candidate run and the floor.
- **Re-read trigger**: the 2026-08-26 amendment reserved a re-read of whether the
  load instrument is needed once a load reading exists. The first frozen
  eight-week table (`docs/evidence/adr-0080/self-regulation-2026-10-31.md`, frozen
  read-only after the 2026-10-31 gate) is that reading; the re-read is taken at the
  first gate that reads it and recorded in that gate's `gate_record`.

### Consequences of this amendment

- A reading exists before the definition is frozen: four weekly lines
  accumulate between the first run and the Saturday of the 2026-11 gate.
- `core/` commits since 2026-08-16 are tagged once in
  `docs/evidence/adr-0080/core-commit-tags.md` (proposal for the owner's
  review); after the freeze the `fix` type plus the RFC `alignment:` field
  replaces that tagging.

## Amendment (2026-10-24) — ending design: review events, not conditions

Decided by the owner on 2026-10-24 (D-P4-01-1 = D, D-P4-01-2 = A,
D-P4-01-3 = A with N = 4 weeks, D-P2-01-3 = B with an 8-week floor; all
taken as recommended). Form: a dated, **additive** amendment, as the
2026-08-26 one; the original Decision stands unreversed. The CLAUDE.md §
北極星 operative summary is synced in the same commit (the 2026-08-26
rule). Headings stay date-form; the sub-headings A / B / C of the earlier
amendment are not reused.

Context: layer 5 reserved *when* the heartbeat stops and *how* together,
and [rfcs/0006](../../rfcs/0006-heartbeat-end-state-criteria.md) was
withdrawn on 2026-09-28 (it bet on one condition and the check passed
twelve times without firing; "look at the steady state first, then decide
how to stop" is the reverse of pre-registration). This amendment separates
the two and reserves only what can be reserved without deciding an end
condition.

**When and how are separated.**

- **No end condition is filed.** rfcs/0006 stays withdrawn. Nothing in this
  amendment defines "steady state" or says the run should stop.
- **How** (the order of steps once the owner has decided to stop) lives in
  the wind-down runbook, `docs/runbooks/wind-down.md`,
  which has no trigger of its own.
- **When** is replaced by *review events*: an observable event opens a
  session in which the owner considers whether to stop. An event **does not
  imply stopping**; a false firing costs one session, which is why several
  events are reserved (any-of) instead of one.

**Review events (any one opens a review session).**

1. *Research answers in.* The research layer's founding questions have
   public answers (layer 3 above; the second of the two conditions in layer
   5, "the remaining questions require a different experiment"). Observed in
   the answer table kept with the research-layer plan (`docs/plans/roadmap-2026-10/`
   P2-01 / P3-01); until that table exists this event is read by the owner at
   the Saturday gate.
2. *Value-layer metabolism flat.* Eight consecutive weeks with value-layer
   adoptions 0, archives 0 and identity updates 0 (the floor of D-P2-01-3;
   the first condition in layer 5, "read-only instruments show steady
   state"). Material: the weekly self-regulation reading (P2-01.5, planned)
   and the value-layer change series `pipeline/value-layer/changes.json`
   (P2-05.7, planned).
3. *Moltbook unreachable for 7 days.* Detection surface: the planned
   `scripts/pipeline_watchdog.sh` row "no comment-report for 7 days"
   (P2-04.4 (c)) shown as a failure in `PIPELINE-STATUS.md`. Until the row
   exists, the owner reads reachability in `PIPELINE-STATUS.md` at the
   Saturday gate Step 0.
4. *Platform terms or closure notice.* A row in the human re-reading ledger
   of the platform specification (`docs/evidence/moltbook-platform-readings.md`,
   P1-07.19, planned) records a terms change or closure notice. The unattended
   chain does not fetch the platform specification
   (`scripts/api_drift_scan.py`), so the observation source is the human ledger.
5. *Gate absence.* No Saturday gate record for 4 consecutive weeks (N = 4,
   D-P4-01-3). The run continues on approved value-layer state — as ADR-0012
   designed — and no automatic read-only mode or stop is introduced; the
   decision to stop stays a human act. The "Operator unavailability" section of
   [`docs/GOVERNANCE.md`](../GOVERNANCE.md#operator-unavailability) records N and
   the correspondence to agent-attribution-practice ADR-0008 (value layer /
   external surface / stop authority).

**Decider, material, record.** The decider is the owner. The material is the
weekly instrument JSON of the last N weeks (the self-regulation reading,
pattern-layer increments, the value-layer change series, staged counts); no
new instrument or script is built for this amendment. "Steady state" is not
defined here: when an event fires, the state definition is pre-registered in
the review session from those columns, not built afterwards. One reading is
recorded as a caveat — the pattern layer (+300..+700 patterns per week) and
the value layer (staged 0 while snapshot digests changed for identity and
skills in September) currently disagree about whether the metabolism is
flat. The record of a review is this amendment (a dated note), the commit
message of the `final` tag in the data repository if the owner decides to
stop, and the CHANGELOG "Ending" section.

**Moltbook's end is the end of this run.** A closure or permanent
unreachability of Moltbook terminates the observation run; the agent is not
ported to another platform (a new experiment is a new repository), and no
SNS-side Protocol is built (D-P4-01-2). Should an RFC for porting be filed,
cite this paragraph and withdraw it.

Each reading named above is material for judgment; whether a threshold has
been reached is written by the owner in the gate record.

**Re-read trigger.** When the first review session is held, record its date
and outcome here as a dated note.

## Amendment (2026-10-24) — two kinds of Claude Code involvement

Decision D-P2-02-1 = A, provisional (owner, 2026-10-24; revisited at the
2027-Q1 review). The 2026-08-26 amendment §A defines the mechanism layer as
unfinished while the loop needs "the owner's and Claude Code's daily
involvement" — but the unattended Saturday chain starts one headless
`claude -p` session every week (`scripts/weekly-pipeline.sh`, ADR-0085 /
ADR-0098), and the repair loop is itself a Claude Code session. The phrase
therefore names two different things:

- **(i) Interactive sessions for repair and judgement** (the owner's
  working sessions and the harness task-triage loop). This is what the
  completion condition drives toward zero.
- **(ii) The unattended reader session** (the one weekly `claude -p`
  that writes the observation document and files draft RFCs). It is
  recognised as part of the mechanism layer, not as the owner's working
  environment: reproducing the loop needs a Claude Code subscription (stated
  in README / CONFIGURATION), the writer model and CLI version are recorded
  (audit `chain_start` `model=` / `claude_version=`, the document's
  `writer:` stamp), and it is **counted in the operator-load series** rather
  than assumed to be zero — its count and `duration_ms` / `num_turns` are
  read beside the gate's own load. A week it cannot run degrades to the
  instruments-only chain (`REPORT_ABSENT`), never to silence.

Not chosen: treating the headless session as the owner's tool (B — would move
the synthesis into the Saturday gate and raise the reading load) and a
local-model shadow run of the synthesis (C — deferred; the RFC-0041
cross-model contrast gives it little prior). Re-read trigger: the headless
session stops, or its duration / denial counts drift (P2-02.8).

## Amendment (2026-10-31) — where the human word stays, the skill-store exit layer 1, and how run-length triggers are read

Drafted on 2026-10-31 for the owner (roadmap P1-03.8 / P1-03.9) and adopted by
the owner's merge on 2026-10-31, in an attended session, under the owner's
2026-10-31 instruction to run every item that is not waiting on an observation
period. The roadmap first placed these decisions at the 2026-11-28 and
2026-12-05 gates, and the schedule later at the 2026-10-31 gate; the owner took
the decisions on 2026-10-24, so only the adoption of the text was left. It carries two decisions the owner took on
2026-10-24 as recommended: D-P2-05-3 = A and D-P2-07-1 = A. The other inputs
the roadmap lists for this amendment (D-P1-01-1 definition and additional stage
B, D-P2-01-1 = B, D-P2-01-3 = B, D-P2-02-1 = A) are already recorded in the
2026-10-24 amendments above, so this one does not restate them. Form: additive
and dated, like the earlier ones. The original Decision stands. The CLAUDE.md §
北極星 summary is synced in the same commit. Sub-headings do not reuse the
letters A / B / C of the 2026-08-26 amendment. The 2026-12 amendment (the second
half of P1-03.8) carries the Q4 adoption of D-P3-01-1 and the human-gate range
under D-P1-13-1 = C.

### The human word stays at three points (D-P2-05-3 = A)

The 2026-08-26 amendment keeps the approval gates as authority while their load
approaches zero, and rejects gate dissolution. That leaves open which steps are
"the human's" whenever a step is moved off the human (RFC-0048's exit layers
are the first case). Three points are fixed. At each of them the human word
stays:

1. **A write to the value layer**: any write that changes skills, rules,
   identity or the constitution, or that declares an observation baseline.
   The commands today are `adopt-staged` (including `--archive-names`),
   `remove-skill`, `restore-skill`, `amend-constitution`, the approval prompts
   of `distill-identity` and `insight`, and `observation_ledger.py
   declare-baseline`. The record forms are ADR-0012 and ADR-0116.
2. **A commit that publishes**: the commit of `rfcs/` drafts and of
   `reports/analysis/`. The unattended chain writes them to the working tree
   only, and the Saturday gate commits them after its sensitivity check
   (ADR-0085 / ADR-0098).
3. **Building or removing an instrument**: under ADR-0101's consumption plan.

These three are what a proposal to move a *pipeline* step off the human is
checked against. A pipeline step outside them can be automated without asking
again whether it is human work. A step inside them keeps the human word unless
an amendment of this ADR names an exception. There is one exception so far, the
next section. The list does not cover the owner's own acts, which are not
pipeline steps and stay human under their own records: decisions and verdicts
written in `gate_record` (including every reading below), merges of the
protected class (ADR-0115) and the approval of `.claude/verify.sh`.

### Skill-store exit layer 1 (D-P2-07-1 = A)

**Layer 1 of the skill store's exit is an exception to "Not gate dissolution", on
three conditions and no others.** The human word at the gate stays the anchor of
the attribution practice (ADR-0050), and reversibility alone is not a reason to
skip it. What is skipped is narrower. It is the retirement of a skill that was
never selected in its whole history and was judged-exposed at least 600 times,
by a rule that is code with no model in it. Such a skill was never injected
into a generation, so no published sentence is attributable to it, and there is
no attribution for the human word to anchor. Its removal still changes the
catalog the selection judge sees, so its effect on generation is indirect, not
zero. The premise holds only while "never selected" means "never injected":
a selector or injection change that breaks that equation voids this
paragraph (ADR-0122 Review-when). The exception holds only while
(1) the verdict is deterministic, (2) the move is reversible and a person keeps
a right of return (`restore-skill`), and (3) the names and count reach the
Saturday gate in the same week under an audit source that no human command
writes (`archive-l1-unattended`). It stops itself when two layer-1 archives are
restored within 28 days. Every exit that needs judgement (layer 2) and every
value-layer addition keeps the human word at the gate. The design is
[ADR-0122](./0122-skill-store-layer1-unattended-exit.md), which partially
supersedes ADR-0105's "Nothing in the unattended chain touches the store". The
stage itself lands at the 2027-02-27 gate.

Not chosen (recorded): layer 1 stays with the human word, the chain only lists
the strict never-selected candidates with their numbers, and a person runs
`adopt-staged --archive-names`. Its case was that reversibility makes the step
cheap, not optional. It lost because it keeps on the human, every week, the
most routine ruling of the gate, one with no attribution to anchor, so the
rulings series (i) of the self-regulation reading cannot reach 0 while the
store still has strict candidates.

### How the run-length triggers are read (P1-03.9)

Five of the run-length rules fire on "N consecutive weeks of X" and are tabled
here (the self-regulating candidate and review event 5, gate absence, are not);
the table has six lines because
review event 2 reuses the metabolism floor. Each line below gives the base rate
of X now and what that rate implies when nothing changes. The lines are a
reading, not part of any definition, and they change no threshold.

The distribution is an **assumption** on every line: weeks are treated as
independent with a constant rate p. Then the chance that one given window of L
weeks holds is p^L. The expected wait from a fresh start is
(1 − p^L) / ((1 − p) · p^L) weeks. Intervals are Wilson 95%
(`scripts/_stats.wilson_ci`). Below 10 weeks only counts are given (P2-01.9).
Data as of 2026-10-31, read-only. W44 is a partial week in the freeze and
metabolism rows (it ends 2026-11-01; the last value-layer snapshot is
2026-10-30).

| rule | X, base rate now | chance one window holds | expected wait |
|---|---|---|---|
| Freeze, 8 quiet weeks (D-P1-01-1 = A) | quiet week: 0/13, W32–W44 (`freeze_reading.py --end 2026-10-31 --weeks 13` → `base_rate_quiet=0/13`), upper bound 23% | ≤ 7.4 × 10⁻⁶ | ≥ about 1.8 × 10⁵ weeks |
| Metabolism floor, 8 weeks with adopted 0 ∧ archived 0 ∧ identity 0 (D-P2-01-3 = B) | week with no value-layer change in `pipeline/value-layer/changes.json`: 7/13, W32–W44 = 54% [29–77%]; a proxy stricter than the floor's conjunction, which the evidence file's (vi) line supports (7 of 7 covered weeks agree) | 0.7% [5 × 10⁻⁵ – 12%] | about 300 weeks [31 – 2.7 × 10⁴] |
| Review event 2 (D-P4-01-1 = D, part B) | the same rule as the floor above, kept at 8 weeks | as above | as above |
| Band, 2 consecutive weeks below / above (P1-05.2) | not measurable yet: none of the 7 active baselines in `observation-ledger.jsonl` has a `band` | nominal, if each band were a 95% band and an exit on either side counts: 0.25% per baseline (0.125% if both weeks must be on the same side), 1.75% for any of 7 | nominal 420 weeks per baseline |
| Deviations empty 4 weeks (ADR-0099 Review-when) | gate week whose report has no Deviations item: 3/10, W35–W44 (W38, W42, W44) = 30% [11–60%] | 0.8% [0.01–13%] | about 175 weeks [17 – 8,300] |
| Outlier list empty 4 weeks (ADR-0110 Review-when) | week whose `### Within-week outliers` lists no row: 0/7, W38–W44 (count only, under 10 weeks) | ≤ 1.6% at the upper bound (35%) | ≥ about 97 weeks |

What the lines say, row by row:

- **Freeze.** Eight quiet weeks in a row cannot happen by chance on the present
  distribution. Reaching it means the distribution changed, which is the
  intended reading. `freeze_reading.py` already prints `base_rate_quiet=` on
  its candidate line.
- **Metabolism floor and review event 2.** The independence assumption is
  weakest here. Identity is staged by the weekly chain every four weeks
  (ADR-0091, the 27-day default) and was adopted on 2026-08-15, 09-12 and
  10-10. No skill has been adopted since W37, archived since W39 or staged
  since W39 (the self-regulation evidence file named below). So the run is structural, not random. The floor is
  reached at W49 (the week ending 2026-12-06) when the identity proposal of
  about 2026-11-07 is not adopted and no skill moves. The current run is 3
  weeks (W42–W44). The independent-weeks line understates how near it is. The
  roadmap's earlier figure (about 5%, from the 13-day median of the *manual*
  identity gaps in ADR-0091) does not apply to the unattended four-week lane.
- **Band.** The rule cannot be evaluated until the bands are declared. That is a
  step of P1-05.2 on the production machine. The nominal line assumes 95% bands.
  The writer's Deviations section is the nearest proxy: it named at least one
  deviation in 7 of the 10 weeks above. If those were band exits of the same
  baseline in consecutive weeks, the rule would fire within weeks. The band
  declaration is what settles the gap between the two readings.
- **Deviations.** The second clause of the ADR-0099 rule ("and the longitudinal
  record reads as starved") is the owner's reading, so the line bounds only the
  first clause. Method: gate week n reads the latest
  `reports/analysis/weekly-*.md` from the previous Saturday to that Friday
  (P2-06.1). A section whose only content is the writer's "No deviations
  against declared baselines" line counts as empty. The current run is 1 (W44).
- **Outliers.** Every week so far lists rows. Seven weeks give only a count, so
  the upper-bound line is the most the data allows; it is not "unreachable".
  ADR-0110 already reads an empty run
  either as the mechanism layer having stopped or as `_Z_THRESHOLD` being too
  high for a 28-point population.

`self_regulation_reading.py` does not yet print a base rate beside its
`self-regulating candidate` and `metabolism floor` lines. That is a follow-up
of P1-03.9 on the script's owner branch, inside the reader's existing
consumption plan (the 2026-10-24 load section); it adds no instrument. Once
both readers print the rate, the table here is not maintained: it stays as the
2026-10-31 reading, and the live rate is the readers' line.

Each reading in this section is material for a judgement. Whether a condition
has been reached is written by the owner in `gate_record`.

### Re-read triggers: what has fired

- **2026-08-26 load re-read: fired.** The trigger was "when a load reading
  exists". The first frozen eight-week table is
  `docs/evidence/adr-0080/self-regulation-2026-10-31.md` (merge order: that
  branch lands before this amendment, or the path is dead). It is taken with
  `--end 2026-10-31` and lands with the self-regulation reader's round-2
  columns (P2-01.3 / P2-01.5, merged 2026-10-31 in #82). The load series it
  prints, read side by side and never summed:
  - (i) `rulings`, with `gate_min` beside it;
  - (ii) the reading-volume table: `report`, the Inventory's five numbers, the
    line counts of `Inventory` / `Ledger` / `Deviations` / `Exceptions` /
    `Discarded`, `carried`, `doc` and `findings`;
  - (iii) `outside`.

  Beside them are `drafts`, `repairs`, `agree` / `rm_agree` and the
  `recommender recorded` footer. First values, W37–W44:

  | series | first values |
  |---|---|
  | rulings | 0–75 |
  | outside | 0–309 files |
  | doc (report length) | 245–350 lines |
  | Exceptions | 66–99 lines |

  Numbering note: in the reader's docstring, (ii) means reading volume for the
  load series (P2-01.3) and `origin: gate` drafts for the candidate sum
  (P2-01.5, "(ii-drafts)" above). The re-read itself is the owner's: does "load
  approaches zero" need this instrument? So is `self_regulation_verdict=`. Both
  go in the `gate_record` of the gate that freezes the table, which is the
  first gate that reads it.
- **2026-10-24 ending design (first review session): not fired** as of
  2026-10-31. No review session is recorded.
- **2026-10-24 two kinds of involvement (headless session stops or drifts): not
  fired** as of 2026-10-31. The headless session wrote a weekly report
  (`reports/analysis/weekly-*.md`) every week from 2026-08-28 through
  2026-10-30. The drift reading is P2-02.8.

### Consequences of this amendment

- A proposal to move a step off the human is judged against three named points
  and does not need the boundary argued again. The cost is that a fourth kind of
  human step needs an amendment here before it can be held.
- Skill-store exit layer 1 runs without a human word only under the three
  conditions and the self-stop. Any wider unattended exit needs a new
  amendment. The cost: the store's composition now changes before the human
  sees it, and the self-stop works only if someone actually restores a wrong
  archive.
- The run-length rules now carry their chance of firing on the present
  distribution. The freeze rule is unreachable by chance, the outlier rule
  nearly so, the metabolism floor is near for a structural reason, and the band
  rule is not yet evaluable. The cost: the ADR holds a dated copy of base rates
  that the readers also print (CLAUDE.md a third, shorter one). All six lines
  rest on the independence assumption; the table is the 2026-10-31 reading and
  is not updated, the readers' lines are.

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
- [ADR-0122](./0122-skill-store-layer1-unattended-exit.md),
  [ADR-0105](./0105-skill-store-exit-confusion-pairs.md),
  [ADR-0101](./0101-instrument-dissolution-mandate.md),
  [ADR-0099](./0099-weekly-report-instrument-redesign.md),
  [ADR-0110](./0110-instrument-series-projection.md),
  [ADR-0091](./0091-value-layer-cadence-in-the-weekly-chain.md),
  [ADR-0116](./0116-approval-gate-records-as-acts-of-responsibility.md),
  [ADR-0115](./0115-judge-merge-authority-and-human-admission-and-push.md),
  [rfcs/0048](../../rfcs/0048-skill-store-self-maintenance.md) — load-bearing
  for the 2026-10-31 amendment
- Sibling repo
  [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data)
  — the vessel of the longitudinal record named in layer 5

# ADR-0101: Instrument Dissolution Mandate — New Instruments Must Name Their Consumption

## Status

accepted

## Date

2026-08-29

## Context

This project has mandates for *construction* and none for *dissolution*.
Measure before you intervene ([ADR-0071](./0071-read-only-pattern-composition-instruments.md))
tells us to build an instrument first; observability by default
([ADR-0075](./0075-observability-by-default.md)) tells us to ship its log in
the same PR. Nothing anywhere says when either comes down. Folding is
optional: only 4 of 99 ADRs carry a `## Review-when` section, and the exit
conditions that do exist are scattered through prose where no gate reads them.
Instruments have shipped with no scheduled reader at all — the co-selection
family scan and the retrieval-recall measure were both built, run once or
twice, and left standing.

The result is measurable. As of 2026-08-29 the weekly machinery alone is
~17,769 lines (scripts 6,286 / src 3,178 / tests 8,305). Over the window
2026-05-01 → 2026-08-29 the tracked Python corpus grew by a net +64,541 lines,
and instrument slices dominate that growth: the read-only readings introduced
by [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) added
roughly +6.4k lines across three commits — that is, *more lines were built to
justify a retirement than the retirement removed*. Each such slice was individually
justified; the aggregate was never anyone's decision.

The asymmetry is the defect, not any single instrument. When construction is
mandatory and dissolution is optional, inventory increases monotonically no
matter how good each local judgment is. That runs against the north star
([ADR-0080](./0080-north-star-layered-end-state.md)): the mechanism layer is
finished when it stops moving.

## Decision

1. **Every new instrument must state a consumption plan.** An instrument here
   means any read-only reading, distribution, calibration scale, or audit
   surface built to be read rather than to act. Its ADR (or RFC, if it enters
   through the ledger) must state:
   - **(a) who reads it and when** — a named consumer and a cadence or a
     triggering event, not "when we need it";
   - **(b) how many reads decide what** — the decision the readings feed and
     the number of readings that closes it;
   - **(c) the retire-on-completion condition** — what makes this instrument
     finished, after which it comes down.

   **An instrument whose consumption plan cannot be stated is not accepted at
   the gate.** Inability to answer (a)–(c) is the signal that the instrument
   has no consumer, which is the failure mode this ADR exists to catch.

2. **The plan lives in the ADR's `## Review-when` section** (or, for a
   ledger-born instrument, in the RFC's frontmatter or body). One location per
   instrument, next to the decision that created it — not in a separate
   register that would itself need maintaining.

3. **Rollout — tranche T4 of the shrink program.** A retroactive stocktake
   over instruments that already exist, beginning with the weekly machinery,
   run at a future Saturday gate. For each instrument, either its consumption
   plan is stated (and recorded) or it becomes a retirement candidate.
   Verdicts are recorded as dated annotations in the owning ADRs, following
   the ADR-0044 reading discipline: an instrument whose stated exit condition
   has already fired has no claim to remain.

4. **This mandates a statement, not machinery.** No new code, no scheduler, no
   lint gate, no register file. The obligation is discharged by writing three
   sentences in a document that is already being written, and it is enforced
   by the same human gate that accepts the ADR.

## Review-when

- Two consecutive retroactive stocktakes find zero retirement candidates and
  zero new instruments lacking a consumption plan → the habit is internalized;
  fold this mandate into ADR-0071's prose as a sentence and retire this ADR.
  (Scaffold Dissolution, inward: the rule stops being load-bearing once the
  practice carries it.)

## Alternatives Considered

### A declared reduction moratorium

Freeze new instrument construction for a fixed period and spend it removing.
Rejected by the owner on 2026-08-29: a time-boxed freeze buys a one-time
reduction and then expires, leaving the asymmetry that produced the inventory
intact. The owner chose the standing rule over the freeze.

### A same-mechanism third-amendment redesign rule

"When the same mechanism reaches its third amendment, redesign it instead of
patching." Not adopted. It is a real pattern, and narrower than the defect
being fixed — it addresses repeated repair of one mechanism, while the
measured driver is unconsumed construction across many. It can be proposed on
its own evidence later.

### A numeric cap on instrument lines

E.g. "no instrument may exceed N lines" or "instrument code may not exceed X%
of src". Rejected: an evidence-free numeric gate is exactly what the
measurement discipline forbids, and the defect is an instrument with no
reader, which a line count cannot see. A 200-line instrument nobody reads is
the problem; a 2,000-line instrument with a weekly consumer is not.

### Status quo

Rejected on the measurements in Context. Construction-only mandates plus 4
`Review-when` sections across 99 ADRs is not a system that converges.

## Consequences

### Positive

- The gate gains the ability to refuse an instrument at birth, on the
  strongest available evidence — that nobody can say who would read it.
- The ~17.8k-line weekly complex gets a scheduled reckoning (T4) rather than
  an indefinite reprieve.
- Exit conditions become greppable in one place per instrument, so a later
  stocktake reads `Review-when` sections rather than re-deriving intent from
  prose.

### Negative / accepted

- A consumption plan can be written optimistically. Nothing verifies that the
  named reader ever read anything; the plan is a claim, and the stocktake is
  where the claim is tested against what happened.
- The retroactive stocktake is judgment work performed at the gate. It is not
  automatable, and deliberately so — automating it would build the machinery
  this ADR declines to build.

### Neutral

- CLAUDE.md 開発原則 gains one bullet.

## Related

- [ADR-0071](./0071-read-only-pattern-composition-instruments.md) — the
  construction-side mandate this one balances; the eventual home of this rule
  if the Review-when condition fires
- [ADR-0075](./0075-observability-by-default.md) — as amended 2026-08-29
  (obligation narrowed to resident production paths)
- [ADR-0080](./0080-north-star-layered-end-state.md) — the mechanism-layer
  completion criterion the asymmetry violates
- [ADR-0095](./0095-retire-task-ledger-machinery.md) — precedent: bloat is
  solved by removal plus a rule, not by machinery
- [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) — the
  measured instance (readings built to justify a retirement outgrew it)
- [ADR-0100](./0100-retire-chaos-tdd-by-default-mandate.md) — the
  mandate-side counterpart decided the same day

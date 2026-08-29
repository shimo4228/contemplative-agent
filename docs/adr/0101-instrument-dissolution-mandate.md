# ADR-0101: Instrument Dissolution Mandate — New Instruments Must Name Their Consumption

## Status

accepted

## Date

2026-08-29

## Context

This project has mandates for *construction* and none for *dissolution*.
Measure before you intervene
([ADR-0071](./0071-read-only-pattern-composition-instruments.md)) says an
intervention must be preceded by a reading; observability by default
([ADR-0075](./0075-observability-by-default.md)) says the log ships in the same
PR. Removal is not unwritten — ADR-0071's Decision 2 makes construction
signal-first in both directions, the project skill `read-only-instruments`
states "signal-first both ways", and ADR-0086 carries its own retirement
clause. The defect is that these exit conditions are **scattered prose that no
gate reads**: unread, not unwritten. Folding is therefore optional in practice.
Only 4 of the 99 ADRs predating 2026-08-29 carry a `## Review-when` section
(0069 / 0097 / 0098 / 0099 — `grep -l '^## Review-when' docs/adr/*.md`
excluding the `.ja.md` twins; the same-day 0100 / 0101 are excluded as not yet
predating). Instruments have shipped with no scheduled reader at all: the
co-selection family scan (`scripts/coselection_families.py`) had its outputs
read exactly once — the numbers were frozen in ADR-0097's unit-C note — and the
script was retired the same day as this ADR (commit `a06c6be`, 2026-08-29);
`scripts/retrieval_recall_measure.py` likewise has no scheduled reader, its
ADR-0097 Review-when arm still pending a future manual run.

The result is measurable. As of 2026-08-29 the weekly machinery alone is
~17,769 lines (scripts 6,286 / src 3,178 / tests 8,305). Membership, measured
2026-08-29:

- **scripts (≈6,286, including rounding)** — `weekly-pipeline.sh` 861,
  `weekly-analysis.sh` 602, `value_layer_approval_join.py` 998,
  `value_layer_due_check.py` 552, `log_anomaly_sweep.py` 551,
  `docs_consistency_scan.py` 513, `api_drift_scan.py` 376,
  `cross_day_duplicate_scan.py` 356, `observation_ledger.py` 321,
  `state_invariant_check.py` 288, `pipeline_watchdog.sh` 216,
  `dead_code_scan.py` 163, `weekly_random_sample.py` 118, `pipeline_audit.py`
  60, helpers `_audit` / `_stats` / `_md` / `_scan` 179
- **src (≈3,178)** — `report.py` 329, `selection_metrics.py` 1,059,
  `never_selected_metrics.py` 808, `view_metrics.py` 388, `metrics.py` 189,
  `selection_window.py` 170, `episode_render.py` 235
- **tests (≈8,305)** — shell-guard suites 2,255, value-layer 2,026, per-script
  fault columns 2,671, report / metrics 1,353

Over the window 2026-05-01 → 2026-08-29 the tracked Python corpus grew by a net
+64,541 lines (measured at `3a759d4`; endpoint method — the totals at the two
endpoints differenced, not per-commit diffs summed). Instrument slices are the
**largest single identified slice** of that growth: the read-only readings
introduced by
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) added a net
+6,355 `.py` lines across commits `186dee6` / `8757683` / `c9a1df4`, exceeding
the −5,672 that the retirement they justified removed at `47616da` — that is,
*more lines were built to justify a retirement than the retirement removed*.
The aggregate instrument share of the window was not measured, so this is one
measured instance, not a claim that instruments dominate the total. Each such
slice was individually justified; the aggregate was never anyone's decision.

The asymmetry is the defect, not any single instrument. When construction is
mandatory and dissolution is optional, inventory increases monotonically no
matter how good each local judgment is. That runs against the north star
([ADR-0080](./0080-north-star-layered-end-state.md)). The 2026-08-26 amendment
to that ADR is the operative form: the mechanism layer is not finished while
the feedback loop fails to self-regulate without routine owner involvement, and
the amendment explicitly allows bounded mechanism work that advances
self-regulation — so "we built more mechanism" is not by itself a violation.
The asymmetry still cuts against the amended criterion, because an *unconsumed*
instrument raises operator load — the amendment's own metric, human approval
load approaching zero — without advancing self-regulation at all.

## Decision

1. **Every new instrument must state a consumption plan.** An instrument here
   means any read-only reading, distribution, calibration scale, or audit
   surface built to be read rather than to act. Its ADR (or RFC, if it enters
   through the ledger) must state:
   - **(a) who reads it and when** — a named consumer and a cadence or a
     triggering event, not "when we need it";
   - **(b) how many reads decide what** — the decision the readings feed and
     the number of readings that closes it. *Exemption*: an exploratory
     instrument in the ADR-0071 sense — built precisely because the
     intervention cannot be chosen until the reading exists — may state a
     **dated review point** instead of a closing read count. The plan must
     still name the reader and the review date; only the count is waived;
   - **(c) the retire-on-completion condition** — what makes this instrument
     finished, after which it comes down.

   **An instrument whose consumption plan cannot be stated is not accepted at
   the gate.** Inability to answer (a)–(c) is the signal that the instrument
   has no consumer, which is the failure mode this ADR exists to catch.

2. **The plan lives inside the owning ADR's `## Review-when` section, under a
   `### Consumption plan` sub-heading** (or, for a ledger-born instrument, in
   the RFC's frontmatter or body). One location per instrument, next to the
   decision that created it — not in a separate register that would itself need
   maintaining. The sub-heading keeps expiry triggers and consumption plans
   distinguishable to a grep, so a stocktake can find plans without reading
   every expiry condition.

3. **The refusing actor is the human at the gate that accepts the ADR or RFC.**
   For instrument drafts filed by the unattended weekly chain, that is the
   Saturday `/weekly-gate` session; for interactive ADRs, it is the owner at
   commit, with the `adr-reviewer` pass instructed to flag a missing
   consumption plan. Refusal is recorded as the draft **staying unaccepted with
   a one-line reason** — no new artifact, no rejection ledger.

4. **Rollout — tranche T4 of the shrink program.** A retroactive stocktake over
   instruments that already exist, beginning with the weekly machinery. The
   subject set is **re-derived at each run** by the same consumer/intent sweep
   used on 2026-08-29: `git ls-files scripts/`, plus the CLI command table,
   plus the instruments named in `docs/CODEMAPS/architecture.md`'s Data Flow
   section, cross-referenced against the launchd plists / pipeline scripts /
   runbooks for consumers and against owning-ADR `Review-when` sections and RFC
   states for live intent. **No standing register is kept**, because the set is
   re-derivable by that procedure and a register would be one more artifact to
   maintain. First run: commissioned 2026-08-29 (the whole-repo semantic
   stocktake dispatched with this tranche). Recurrence: at the first Saturday
   gate after each quarter boundary. For each instrument, either its
   consumption plan is stated (and recorded) or it becomes a retirement
   candidate. Verdicts are recorded as dated annotations in the owning ADRs,
   following the ADR-0044 reading discipline: an instrument whose stated exit
   condition has already fired has no claim to remain.

5. **Grandfathering.** Instruments accepted before 2026-08-29 — including
   ADR-0099's observation ledger and its seeded random sample — enter through
   the T4 backfill, not through retroactive refusal. Decision 1 binds new
   construction only.

6. **This mandates a statement, not machinery.** No new code, no scheduler, no
   lint gate, no register file. The obligation is discharged by writing three
   sentences in a document that is already being written, and it is enforced by
   the same human gate that accepts the ADR.

**Tranche labels** used by the 2026-08-29 shrink program, for readers of the
sibling records:

- **T0** — the immediate deletions of 2026-08-29 (this tranche).
- **T1** — unassigned; the mandate commits landed unnumbered.
- **T2a / T2b** — read-window adjudications on 2026-09-03 and 2026-09-05, via
  RFC-0011 and RFC-0014 + RFC-0015 respectively.
- **T3** — RFC-0012, shadow-constitution consumption, adjudicated at the next
  amendment gate (~2026-11).
- **T4** — this ADR's retroactive stocktake (Decision 4).

## Review-when

- Two consecutive retroactive stocktakes — T4 runs under the Decision 4
  derivation procedure, judged at the Saturday gate — find zero retirement
  candidates and zero new instruments lacking a consumption plan → the habit is
  internalized; fold this mandate into ADR-0071's prose as a sentence and
  retire this ADR. (Scaffold Dissolution, inward: the rule stops being
  load-bearing once the practice carries it.)

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

### Extend the deterministic ADR checks to assert section presence

Make `scripts/docs_consistency_scan.py` (or
`tests/test_adr_status_consistency.py`) fail an instrument ADR that has no
`### Consumption plan`. Not adopted: presence is mechanically checkable but
**sufficiency is not**, and a presence-only gate invites boilerplate plans
written to satisfy the grep — which is worse than no gate, because it converts
a judgment into a green check. Revisit if the human gate demonstrably misses a
missing plan.

### Delete the unconsumed instruments now and write no standing rule

The ADR-0095 shape: solve the bloat by subtraction and skip the rule. The
deletion did run — that is tranche T0, the same day. It is not sufficient on
its own, because a one-time deletion cannot reach the **inflow**; the next
unconsumed instrument is unaffected by it. The rule targets what the deletion
structurally cannot.

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
  stocktake reads `### Consumption plan` sub-sections rather than re-deriving
  intent from prose.

### Negative / accepted

- A consumption plan can be written optimistically. Nothing verifies that the
  named reader ever read anything; the plan is a claim, and the stocktake is
  where the claim is tested against what happened.
- The retroactive stocktake is judgment work performed at the gate. It is not
  automatable, and deliberately so — automating it would build the machinery
  this ADR declines to build.
- **The same-day ADR-0075 amendment removes the artifact that would have
  verified a consumption claim.** That amendment exempts read-only instruments
  from the replayable-log obligation, so at T4 there is often no log proving an
  instrument was read. Accepted tension: consumption claims are judged on gate
  records — what the Saturday session actually decided from the reading —
  rather than on the instrument's own telemetry.
- **The exploratory exemption in Decision 1(b) narrows enforcement.** An
  instrument whose intervention is genuinely unknown can satisfy the mandate
  with a reader plus a date and no closing count, which is a weaker commitment
  than (b) otherwise demands. It is the price of not blocking ADR-0071-style
  work, and the dated review point is what keeps it from being open-ended.

### Neutral

- CLAUDE.md's development-principles section gains one bullet.
- `.claude/skills/weekly-gate/SKILL.md` gains one line wiring Decision 3 into
  the gate's own checklist.

## References

- [ADR-0071](./0071-read-only-pattern-composition-instruments.md) — the
  construction-side mandate this one balances; the eventual home of this rule
  if the Review-when condition fires
- [ADR-0075](./0075-observability-by-default.md) — as amended 2026-08-29
  (obligation narrowed to resident production paths)
- [ADR-0080](./0080-north-star-layered-end-state.md) — the mechanism-layer
  completion criterion, as amended 2026-08-26, that the asymmetry violates
- [ADR-0086](./0086-submolt-scope-instrument-before-autonomy.md) — an
  instrument that already carries its own retirement clause in prose
- [ADR-0095](./0095-retire-task-ledger-machinery.md) — precedent: bloat is
  solved by removal plus a rule, not by machinery
- [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) — the
  measured instance (readings built to justify a retirement outgrew it)
- [ADR-0100](./0100-retire-chaos-tdd-by-default-mandate.md) — the
  mandate-side counterpart decided the same day

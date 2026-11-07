# ADR-0100: Retire the Chaos-TDD By-Default Mandate — Fault Columns Return to Opt-In Judgment

## Status

accepted — partially-supersedes ADR-0077

## Date

2026-08-29

## Context

Measured at `3a759d4` (2026-08-29) over the window 2026-05-01 → 2026-08-29
(487 commits). Tracked `.py` totalled 93,620 lines at `3a759d4` against a
baseline of 29,079 at `3cee749`, the last commit before 2026-05-01 — a net
`+64,541` by the **endpoint method** (the two endpoint totals differenced, not
per-commit diffs summed, so refactors that move lines between files do not
inflate it). Monthly net: −2,338 / +9,718 / +21,616 / +35,545 — accelerating,
with the largest month ever landing in August. Tests took +36,572 of the
window's net growth — **57%** — leaving an inventory of 51,438 test lines
against 29,435 of src (1.75:1).

Commits carrying the "Review fixes" trailer in subject or body account for
4.1% of the window's added `.py` lines (4 commits). That figure is a **lower
bound**, not a measurement of review churn: this repo deliberately folds review
fixes into the feature commit they belong to (the ADR-0095 discipline), so most
of them are invisible to a trailer grep. The only claim it licenses is the
negative one — *review churn alone cannot account for the growth*. The positive
evidence is slice composition: the top-15 adding commits in the window are ADR
feature slices and package-split refactors, each carrying the two by-default
mandates (ADR-0075 audit logs, ADR-0077 fault columns), which attach a fault
catalog to every feature that touches an LLM call, external I/O, or untrusted
parsing — read-only instruments and one-shot measurement scripts included. This
runs against the north star (ADR-0080: the mechanism layer is finished when it
stops moving).

**What the mandate actually banked.** Of the five faults in the operational
catalog that motivated ADR-0077, three are classes an injector can reproduce
and are pinned by chaos columns: `done_reason=length` mid-cuts (the
`TRUNCATED` schedule in `tests/chaos.py`), the embed HTTP faults, and a 429
from Ollama itself. The other two were never column work. `num_ctx` silent
truncation is pinned by an ordinary assertion
(`tests/test_llm.py::test_num_ctx_fixed_at_32768`); dedup's silent no-fire was
a calibration finding read off an instrument and was never injectable at all;
Moltbook-side 429 was never column-pinned. So the banked value is **the
injectable classes plus the production guards the mandate shipped** (distill
abstain reason codes, `error_kind` telemetry) — not universal coverage of the
original list. Those columns keep running regardless of this decision.

**What the mandate itself costs.** The chaos-named test files total 2,987
lines at `3a759d4` — `tests/chaos.py` 565, `test_llm_chaos` 703,
`test_verification_chaos` 660, `test_distill_chaos` 439, `test_reply_chaos`
347, `test_insight_chaos` 273 — about **5.8%** of the test inventory. Columns
embedded in non-chaos-named test files are not separable by filename and are
unquantified. The 57% figure therefore characterizes test growth overall, not
this mandate's share of it, and this ADR does not claim otherwise. What is
being removed is a **standing per-feature obligation** whose marginal value is
low now that the injectable classes are pinned, while its marginal cost recurs
on every feature — and the features are increasingly read-only instruments
rather than resident pipeline code.

Owner decision in the 2026-08-29 working conversation: remove the mandate
entirely rather than narrow its scope.

## Decision

1. **The by-default mandate is retired.** A fault column stops being a
   required part of every feature PR; whether a deterministic fault test is
   worth writing returns to ordinary TDD judgment at implementation time. The
   development-principles bullet in CLAUDE.md is removed in the same commit as
   this ADR.
2. **The project skill `.claude/skills/chaos-tdd-fault-injection/` is
   retired** (deleted from the repo; recoverable from git history). The
   generalized public fork repository is unaffected.
3. **Nothing the mandate produced is retired with it.** Existing fault columns
   are kept as regression armor for real, observed faults, and are deleted only
   together with the code they test. `tests/chaos.py` (ChaosBackend,
   `responses` helpers, hypothesis strategies) stays as long as it has
   importers — 11 test modules at `3a759d4`.
4. **The surviving scope of ADR-0077 is stated once, on ADR-0077's Status
   line** — the backward half of this partial supersession, which is the only
   face that stays correct as later supersessions land (the "which half states
   which scope" convention in `docs/adr/README.md`). This ADR names only what
   it retires and does not restate the survivor list. On the three Decisions
   whose residue is not self-evident: ADR-0077 D3 (steady state asserted on the
   observable telemetry channel, never on implementation internals) and D6
   (fail-fast on a 429 from Ollama — no retry, no `Retry-After` sleep; a
   production policy, not a test convention) survive unchanged, and D4's TDD
   contract survives *conditionally* — whenever someone opts in to writing a
   fault test, test-first plus the minimal guard in the same PR still governs
   that work. Only the obligation to write one is retired.

## Review-when

- **A silent fault gets past twice.** After this date, a fault in a class an
  existing column pins, or a fault of the kind the retired mandate would have
  covered, is found to have passed silently on two separate occasions. The
  named detectors are the telemetry `error_kind` reads and the weekly
  `scripts/log_anomaly_sweep.py` intake; the judgment is made at the Saturday
  `/weekly-gate` session and recorded as a dated note on this ADR. → revisit
  the mandate for that pipeline (not globally).
- **`tests/chaos.py` reaches zero importers** (11 at `3a759d4`). The reader of
  that count is the retroactive consumption stocktake defined by ADR-0101's
  tranche T4. → delete the kit in the same change.

## Alternatives Considered

### Narrow the mandate to resident production paths

Keep the obligation for run / distill / publish / verification and exempt
instruments and scripts. Rejected by the owner. The deciding argument is a
difference in the *kind* of value the two by-default mandates carry: replayable
audit logs are the backbone of the longitudinal research record, so their value
is banked and persists, whereas a fault column is a per-feature cost that
recurs — which is why the same conversation narrowed ADR-0075 this way and
retired ADR-0077's mandate outright. The owner's authority settles the rest.

### Keep the mandate as-is

Rejected. The classes being pinned are repeats of classes already pinned, and
the north star says this layer should be converging, not compounding.

### Retire the mandate but keep the project skill as opt-in know-how

Rejected by the owner. The skill's own trigger condition *was* the mandate
("when shipping a feature with LLM calls / external I/O"), so with the mandate
gone its wiring dangles: nothing would fire it, and a skill nothing fires is
inventory. The know-how it carried remains discoverable in this ADR and in
ADR-0077's body, and the generalized public fork keeps it available outside
this repo.

### Also delete the instrument-directed existing fault tests

Rejected for now. They are cheap to keep, their deletion is coupled to their
subjects' retirement (the read-window tranches of the same shrink program),
and deleting green regression tests to save lines is the one move that can
silently un-pin a real fault.

## Consequences

### Positive

- The marginal cost of a new feature drops by the fault-column tax; test
  inventory stops compounding by mandate.
- Review chains can no longer require a fault column by citing a blanket
  rule; a request for one must argue a concrete failure scenario — the same
  closure discipline ADR-0095 installed for review findings.

### Negative / accepted

- A future feature with genuinely novel fault exposure may ship without a
  fault test. The first Review-when line is the recovery path, scoped to the
  pipeline that demonstrates the need.
- **Reversal is more expensive than retention.** Re-imposing a default once it
  has been retired costs more than keeping one that is already running — the
  habit dissolves, and the first Review-when line deliberately restores the
  obligation only for the pipeline that demonstrated the need, never globally.
  If the retirement turns out to be wrong, the path back is per-pipeline and
  slow.
- **The know-how loses discoverability.** Deleting the project skill removes
  the artifact an agent would have found by browsing `.claude/skills/`. Git
  history makes it recoverable but not discoverable, and the public fork covers
  only the generalized half.

### Neutral

- CLAUDE.md loses one development-principles bullet and one project-skill
  table row; `llm-pipeline-layering`'s NOT-for pointer now cites ADR-0077 only.
- `hypothesis` stays a dev dependency (existing columns use it).

## References

- [ADR-0077](./0077-chaos-tdd-fault-injection.md) — partially superseded (the
  by-default mandate). Its Status line carries the canonical list of what
  survives
- [ADR-0075](./0075-observability-by-default.md) — the sibling mandate,
  scope-narrowed by a dated amendment the same day
- [ADR-0101](./0101-instrument-dissolution-mandate.md) — the flow-side
  counterpart decided the same day (construction/dissolution symmetry)
- [ADR-0080](./0080-north-star-layered-end-state.md) — the completion
  criterion this decision serves
- [ADR-0095](./0095-retire-task-ledger-machinery.md) — precedent: bloat is
  solved by removal plus a closure rule, not machinery

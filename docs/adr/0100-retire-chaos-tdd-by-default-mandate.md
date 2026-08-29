# ADR-0100: Retire the Chaos-TDD By-Default Mandate — Fault Columns Return to Opt-In Judgment

## Status

accepted — partially-supersedes ADR-0077

## Date

2026-08-29

## Context

Measured on 2026-08-29 over the window 2026-05-01 → 2026-08-29 (487 commits):
tracked `.py` grew from 29,079 to 93,530 lines (net +64,541), monthly net
−2,338 / +9,718 / +21,616 / +35,545 — accelerating, with the largest month
ever landing in August. Tests took +36,572 of the window's net growth — **57%**
— leaving an inventory of 51,438 test lines against 29,435 of src (1.75:1).
Direct review-fix commits account for only 4.1% of additions; the volume
driver is feature/instrument slices, each carrying the two by-default mandates
(ADR-0075 audit logs, ADR-0077 fault columns), which attach a fault catalog
plus four-digit test-line counts to every feature that touches an LLM call,
external I/O, or untrusted parsing — read-only instruments and one-shot
measurement scripts included. This runs against the north star (ADR-0080: the
mechanism layer is finished when it stops moving).

The mandate's value is front-loaded and already banked. The operational fault
catalog that motivated ADR-0077 — `num_ctx` silent truncation,
`done_reason=length` mid-cuts, dedup's silent no-fire, Moltbook 429s,
CAPTCHA-gate drift — is pinned by the existing columns (the distill pilot,
F-VER-1…7, F-NOV-1…5, the F8 thinking-trace column, the embed HTTP faults),
and those tests keep running regardless of this decision. What remained of the
mandate was its marginal cost: each new feature — increasingly a read-only
instrument rather than resident pipeline code — paid the same tax to re-pin
fault classes already pinned elsewhere.

Owner decision in the 2026-08-29 working conversation: remove the mandate
entirely rather than narrow its scope.

## Decision

1. **The by-default mandate is retired.** A fault column stops being a
   required part of every feature PR; whether a deterministic fault test is
   worth writing returns to ordinary TDD judgment at implementation time. The
   CLAUDE.md 開発原則 bullet is removed in the same commit as this ADR.
2. **The project skill `.claude/skills/chaos-tdd-fault-injection/` is
   retired** (deleted from the repo; recoverable from git history). The
   generalized public fork repository is unaffected.
3. **Everything the mandate produced stays.** Existing fault columns are kept
   as regression armor for real, observed faults, and are deleted only
   together with the code they test. `tests/chaos.py` (ChaosBackend,
   `responses` helpers, hypothesis strategies) stays as long as it has
   importers — 11 test modules as of this date.
4. **What survives of ADR-0077 unchanged**: the injection-seam design
   (`LLMBackend` Protocol + `requests` layer, no production hooks), the
   determinism discipline (seeded schedules, derandomized hypothesis, no real
   sleeps), and the production deltas it shipped (distill abstain reason
   codes, `error_kind` telemetry).

## Review-when

- A production incident recurs in the same fault class twice after this date,
  where a fault column of the retired kind would have caught the second
  occurrence → revisit the mandate for that pipeline (not globally).
- `tests/chaos.py` reaches zero importers → delete the kit in the same change.

## Alternatives Considered

### Narrow the mandate to resident production paths

Keep the obligation for run / distill / publish / verification and exempt
instruments and scripts. Rejected by the owner: it keeps a per-feature tax and
adds a scope dispute to every PR. The same conversation narrowed ADR-0075 that
way instead of retiring it, because replayable audit logs — unlike fault
columns — are the backbone of the longitudinal research record; the two
mandates carry different kinds of value and get different treatments.

### Keep the mandate as-is

Rejected. Tests are 57% of all net growth, the classes being pinned are
repeats of classes already pinned, and the north star says this layer should
be converging, not compounding.

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

### Neutral

- CLAUDE.md loses one 開発原則 bullet and one project-skill table row;
  `llm-pipeline-layering`'s NOT-for pointer now cites ADR-0077 only.
- `hypothesis` stays a dev dependency (existing columns use it).

## Related

- [ADR-0077](./0077-chaos-tdd-fault-injection.md) — partially superseded (the
  by-default mandate; its seams, discipline, and shipped guards survive)
- [ADR-0075](./0075-observability-by-default.md) — the sibling mandate,
  scope-narrowed by a dated amendment the same day
- [ADR-0101](./0101-instrument-dissolution-mandate.md) — the flow-side
  counterpart decided the same day (construction/dissolution symmetry)
- [ADR-0080](./0080-north-star-layered-end-state.md) — the completion
  criterion this decision serves
- [ADR-0095](./0095-retire-task-ledger-machinery.md) — precedent: bloat is
  solved by removal plus a closure rule, not machinery

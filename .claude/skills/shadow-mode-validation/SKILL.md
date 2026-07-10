---
name: shadow-mode-validation
description: Design know-how for shadow-mode validation — running a candidate decision mechanism (typically an LLM judgment) in observe-only parallel with the live path, recording what it WOULD have decided per event, and letting the accumulated record decide enforcement, in the style of ADR-0076's skill-selection shadow instrument. Use when an unvalidated stochastic mechanism is about to replace or filter a live behavior (a one-way door for output quality), when a selector/classifier/gate has no published reliability evidence for the model class in play, or when designing the isolation, kill-switch, and exit criteria for a shadow deployment. NOT for aggregate readings over stored state (that is read-only-instruments / ADR-0071), NOT for the audit-log record schema itself (that is replayable-audit-logs / ADR-0075 — a shadow log IS one of those logs), and NOT a substitute for unit tests — shadow mode validates decision quality in production traffic, not code correctness.
compatibility: Written for the Contemplative Agent repo (examples are CA-specific); the pattern itself is portable.
origin: shimo4228
---

# Shadow-Mode Validation

**Shadow mode** runs a candidate decision mechanism alongside the live path,
records its would-be decision per event, and changes nothing. The live
behavior stays exactly as it was; the only output is an append-only record of
"here is what the new mechanism would have done." Enforcement — actually
letting the mechanism steer behavior — is a separate, later decision made
from the accumulated record. Canonical example: `core/skill_selection.py`
(ADR-0076) — a pass-1 LLM skill-applicability selection observed for 2–4
weeks before any change to system-prompt injection.

**How it composes with the sibling skills.** The shadow record is a
replayable audit log ([`replayable-audit-logs`](../replayable-audit-logs/SKILL.md)
owns the schema: b64+sha256 untrusted text, verdict reason codes, no silent
fallbacks). The go/no-go reading over that log is an instrument
([`read-only-instruments`](../read-only-instruments/SKILL.md) owns
instrument-first sequencing and signal-first). What THIS skill owns is the
middle layer: the discipline of running a live-path mechanism in
observe-only mode without perturbing what it observes.

## When to reach for shadow mode

- **The mechanism's decision quality is the unknown, not its code.** Unit
  tests prove parsing and wiring; they cannot prove that a 4–9B local model
  selects the right skills, or that a heuristic gate fires on the right
  posts. When the failure mode is "plausible but wrong judgment," only real
  traffic answers.
- **Enforcement is a one-way door for behavior.** If wiring the mechanism in
  changes what the model reads or publishes, a bad mechanism degrades output
  *silently* — and with the old path gone, there is no baseline left to
  notice the degradation against. Shadow-first preserves the baseline while
  the evidence accumulates.
- **A prior attempt died wired-but-unobserved.** ADR-0023's router shipped
  into the live path with no usable failure signal and was sunset without
  ever informing a decision (ADR-0036). Shadow mode is the exact inversion:
  observability ships first and alone; the mechanism earns its wiring.

## Design elements (each earned the hard way)

1. **Observe-only entry point, guaranteed by type.** The shadow hook returns
   nothing (`-> None`): callers *cannot* consume the selection even by
   accident. The record is the only output.
2. **Isolation from shared failure machinery — the observer must not
   suppress what it observes.** The shadow call runs inside
   `circuit_shield()`: without it, a repeatedly failing shadow call
   incremented the shared LLM circuit breaker and the *publish generation
   it preceded* was skipped as `circuit_open` (cross-model review finding,
   2026-07-10 — both same-model reviewers missed it). Audit every piece of
   shared state the shadow path touches: circuit breakers, rate-limit
   budgets, caches, retry counters. "Degrade never abort" inside the shadow
   function is not enough if its failures leak out through a side channel.
3. **Validate, don't trust, the stochastic output.** Match the mechanism's
   answer against the closed set of legal values (catalog names);
   out-of-set answers are rejected from every downstream field but
   *recorded* (`rejected_names`) — hallucination rate is first-class
   enforcement-decision data, distinct from parse failure. Keep the verdict
   taxonomy honest: "the answer didn't parse" (`fail_open_parse`) and
   "every pick was wrong" (`judged` + empty selected) are different events.
4. **Bake would-be metrics at record time.** Any metric computed against
   mutable state (token totals against a corpus that adopt/stocktake will
   change) must be written into the record, not recomputed at report time —
   otherwise the record cannot replay what the decision would have meant
   *then*.
5. **Kill switch = configuration absence.** Leaving the shadow config unset
   disables the whole path (no LLM call, no file). No feature flag to
   maintain; tests and one-shot CLI paths stay clean by default.
6. **Reserve exit criteria at launch, decide later.** Name the readings the
   enforcement decision will consume (hallucination rate, fail-open rate,
   stability of never-selected, realized reduction distribution) and the
   window (2–4 weeks) in the ADR — but do not pick thresholds before the
   data exists (feedback `no-numeric-caps`, `one-run-not-evidence`).

## Pitfalls

- **Observer cost is real and must be recorded.** A shadow LLM call adds
  latency per event (+7–15 s/action for CA's selector). Record it in
  telemetry so the enforcement decision weighs cost against benefit from
  the same corpus — and so "the instrument is too expensive to keep" is
  itself a data-backed verdict.
- **The shadow input must be what the live path sees.** CA passes the same
  untrusted-wrapped situation text to the selector that the generation
  reads. Trimming the shadow input to save tokens makes the recorded
  decisions unfaithful to the enforcement-time decisions — if you must trim,
  record that as an open question (ADR-0076 did, for the 15K-char seed
  case), don't silently diverge.
- **First-run enthusiasm.** One clean session (7/7 judged, zero
  hallucinations) proves the wiring, not the mechanism. The recurring
  question the window must answer: are ever-present picks genuinely
  general-purpose, or "generally useful" drift the prompt forbids?
- **Shadow mode that never ends is a zombie.** The record exists to be
  consumed by a dated decision (CA: task ledger entry T-SKILLSEL,
  2026-07-24). A shadow path with no consumer and no exit date is exactly
  the wired-but-unread scaffolding this pattern was built to avoid —
  signal-first applies to the shadow itself.

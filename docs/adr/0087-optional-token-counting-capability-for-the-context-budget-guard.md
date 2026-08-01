# ADR-0087: An Optional `count_tokens` Capability for the Context-Budget Guard

## Status

accepted — extends [ADR-0066](./0066-backend-aware-context-budget-guard.md)

This ADR adds a measurement source to the guard ADR-0066 built. It **alters none of ADR-0066's
decisions**: `_estimate_tokens` keeps the constants §5 hardened, `MIN_CLAMPED_NUM_PREDICT` keeps its
value, and `context_window` stays a member of `LLMBackend`. ADR-0066 remains `accepted` as written.
The one place this ADR declines to follow its precedent — putting the new member on `LLMBackend` —
is argued in Decision 1 and the first alternative, not assumed.

## Date

2026-08-01

## Context

[ADR-0066](./0066-backend-aware-context-budget-guard.md) made the C2 context-budget pre-flight
backend-aware and, in §5, deliberately hardened `_estimate_tokens` into a genuine upper bound in
both character classes: ASCII at ~3 chars/token, non-ASCII/CJK at **2 tokens/char**. That was the
right call for the failure it faced. The guard's only job was to refuse over-window input, an
*under*-count was the failure that let a CJK-heavy prompt slip into Ollama front-truncation or an
MLX KV-cache overrun, and no tokenizer was available to do better — the project ships only
`requests` + `numpy`.

**What is new is a measurement.** On 2026-08-01 the estimator was compared for the first time
against a real tokenizer — macOS 26.6's `apple-fm-sdk` `SystemLanguageModel.token_count` — on this
agent's own corpora:

| input | `_estimate_tokens` | measured | ratio |
|---|---|---|---|
| `identity.md` | 232 | 134 | 1.73x |
| `constitution/` | 867 | 453 | 1.91x |
| `rules/` | 516 | 264 | 1.95x |
| `skills/` (37 files) | 31,009 | 17,958 | 1.73x |
| 10 patterns | 479 | 263 | 1.82x |

The over-count is not a defect — it is the documented contract working as designed, and it tracks
the CJK rule directly: this agent's value layer is Japanese-dominant, and 2 tokens/char against a
real ~1.1 is where the ratio comes from.

**The evidence behind that table was not preserved, and that is a defect in this record.** The probe
ran in a scratchpad directory that does not survive a restart, so there is no
`docs/evidence/adr-0087/` to link and no script to re-run — contrary to this repo's own convention
that an ADR needing evidence carries it under `docs/evidence/adr-XXXX/`. Both inputs can move
independently (the corpora grow every week; the Apple runtime ships with the OS), so a reader cannot
reproduce these ratios or even identify the exact files they were taken over. Treat the table as a
one-time observation of the right order of magnitude, not as a reproducible measurement. What the
decisions below actually rest on is weaker and more durable than the table: that the estimator
over-counts CJK by construction, and that the size of the error is a property of the backend's
tokenizer rather than something this repo can know. Anyone re-deriving the numbers should write the
probe into `docs/evidence/adr-0087/` and link it here.

**The cost of that safety margin scales with the inverse of the window.** The guard skips a call
outright when the input leaves less than `MIN_CLAMPED_NUM_PREDICT` (2048) of output budget. On a
4,096-token backend that puts the effective input ceiling at 2,048 *estimated* tokens ≈ **1,140 real
tokens, 28% of the window**. Two independent things consume the rest, and it matters not to conflate
them:

| | input ceiling at a 4,096 window | share of window |
|---|---|---|
| estimator, current | ~1,140 real tokens | 28% |
| exact count (this ADR) | 4096 − 2048 − 64 = **1,984** real tokens | 48% |
| ceiling if the output floor were also 0 | 4,096 | 100% |

So the estimator's over-count costs about **21 percentage points**, and the `MIN_CLAMPED_NUM_PREDICT`
output reservation costs the remaining ~50% — a separate variable this ADR deliberately does not
move (decision 9). Measuring for real recovers the first, not the second; it roughly **doubles** the
usable input, which is worth doing and is also less than the raw gap suggests. On the 32,768-token
Ollama path the same ratio clamps `num_predict` earlier than the hardware requires, with no observed
call ever suppressed by it.

**Why the built-in Ollama path cannot simply be fixed.** Two independent reasons, checked rather
than assumed:

1. Ollama exposes no tokenization endpoint. `/api/tokenize` and `/api/detokenize` both return 404 on
   the running 0.30.11; upstream [ollama#12030](https://github.com/ollama/ollama/pull/12030) has
   been open since 2025-08-22 (last touched 2026-06-04, unmerged), and the request issue
   [ollama#12031](https://github.com/ollama/ollama/issues/12031) is still open. This is prior to any
   dependency question: there is no API to call.
2. `/api/generate` returns `prompt_eval_count`, the real input-token count — but only *after* the
   call. A pre-flight cannot consult it.

A Phase 0 external-research pass studied how mature libraries express the same non-uniformity.
LangChain's `BaseLanguageModel.get_num_tokens(text) -> int` ships an approximate default that
model-specific subclasses override — the same precedence this ADR needs, expressed through
inheritance. LlamaIndex carries the capability as a *nullable field* on the LLM object
(`OpenAILike.tokenizer: Union[Tokenizer, str, None] = None`, documented as "If left as None, then
this disables inference of max_tokens") — capability absent, dependent inference degrades, the rest
unaffected; that is the same object ADR-0066 already borrowed `context_window` from. LiteLLM's
`token_counter` falls back to tiktoken when no model-specific tokenizer exists, which confirms
fallback-on-absence as the norm but cannot be copied here, since its fallback is itself a real
tokenizer.

## Decision

1. **Add `count_tokens(text: str) -> int` as a separate optional capability Protocol**,
   `TokenCountingBackend(LLMBackend, Protocol)`, **not** as a member of `LLMBackend`. Protocols are
   structural: a member declared on `LLMBackend` is required of every implementer regardless of
   whether it carries a default body, so putting it there would make the sibling
   `contemplative-agent-cloud` and `contemplative-agent-mlx` backends non-conformant at type-check
   time for a capability neither can honor. Splitting it out gives a backend that *can* count a
   typed target pyright verifies, while backends that cannot stay valid `LLMBackend`s unchanged.
   This is one notch looser than `context_window`, which ADR-0066 did place on `LLMBackend` and
   which therefore created a real "update both repos" obligation (ADR-0066, Consequences/Negative).
   A tokenizer is not a one-line property; the obligation is not appropriate here.

2. **Resolve the capability structurally at runtime**:
   `counter = getattr(_backend, "count_tokens", None)`, used only when `callable(counter)`. Mirrors
   ADR-0066's `getattr(..., None)` sentinel idiom, with the callable check added because an
   attribute can exist without being a method. No `isinstance` against the runtime-checkable
   Protocol: that would accept a non-callable attribute.

3. **Prefer the backend's count, but never trust it blindly.** `_measure_input_tokens` returns a
   frozen `_InputTokenMeasurement` (`system`, `prompt`, `source`, `fallback_reason`). A returned
   value is rejected — falling back to `_estimate_tokens` — when it is not a plain `int` (`bool` is
   excluded explicitly, being an `int` subclass a broken backend could return as `True`), is
   negative, or is `0` for text that has content. The asymmetry is deliberate: over-counting only
   wastes budget, whereas under-counting sends over-window input into precisely the front-truncation
   / KV overrun the guard exists to prevent, so an implausible count is treated as no count.

4. **Bound the count's magnitude, not only its shape** (`MAX_CHARS_PER_TOKEN = 50`). Shape
   validation alone accepts a well-typed, positive, wildly-too-small count — a backend answering `5`
   for a 50,000-character prompt passes every check in decision 3 and then tells the guard the input
   is nearly free. The realistic source of that is not malice but a **mis-calibrated tokenizer** in a
   sibling backend under active development (wrong unit, wrong divisor, an order-of-magnitude bug),
   which makes it the most likely way this guard gets silently defeated. The bound is expressed as
   tokenization density rather than as a ratio against the estimator: no production vocabulary
   contains tokens anywhere near 50 characters, so a count implying a longer average token is
   reporting something that is not tokens. A ratio against `_estimate_tokens` was considered and
   rejected — it would false-reject genuinely efficient tokenizations of repetitive text, filling
   telemetry with faults that are not faults, and it would bake this corpus's measured 0.51–0.58
   real/estimate band into a check that must hold for arbitrary input. Blank text is exempt: it
   carries no content to under-report.

5. **Withhold framing headroom when the input was counted for real**
   (`BACKEND_FRAMING_RESERVE = 64`). `count_tokens` measures the two texts, but the backend then
   renders them into a chat template whose role separators and control tokens no caller-side count
   sees. Clamping `num_predict` to the exact measured remainder puts input + output flush against
   `context_window` with nothing left for that framing, which is enough to tip a request over on the
   small-window backends this ADR exists to serve. The reserve applies **only** on the
   backend-counted path; the estimator path keeps its arithmetic byte-for-byte, since its
   1.73–1.95x over-count is already a reserve orders of magnitude larger. This is also what keeps
   the Ollama path's clamp values unchanged (decision 10).

6. **Measure both halves, validate afterwards, adopt or reject them together.** Mixing a measured
   system prompt with an estimated user prompt produces a budget that describes neither. Both counts
   are always attempted (never short-circuited), which also makes the call sequence deterministic
   for fault tests. When both fail, the system-side reason is reported — a stable choice a replay
   can predict rather than whichever ran last.

7. **A counter fault never touches the circuit breaker.** Failing to *measure* a call is not the
   call failing. Scoring it would let a broken tokenizer trip the breaker and suppress healthy
   generation — the same reasoning that already keeps over-budget skips off the breaker.

8. **Record the source, not just the verdict.** Telemetry gains two dense fields —
   `token_count_source` (`"backend"` / `"estimator"` / `None` when the guard did not run) and
   `input_tokens` (the total the guard actually used) — plus a sparse
   `token_count_fallback_reason` drawn from a fixed vocabulary (`counter_exception`, `counter_none`,
   `counter_type`, `counter_negative`, `counter_degenerate`, `counter_implausible`). Absence of a
   counter is *not* in that
   vocabulary: it is the default, not a fallback from something, and stamping a reason for it would
   bury the real faults. Without the source a clamp value is unreadable offline, because the two
   measures differ by up to 1.95x on this agent's inputs (ADR-0075).

9. **`MIN_CLAMPED_NUM_PREDICT` is not touched.** The clamp floor is the subject of a separate open
   question (whether 2048 is still the right floor once input is measured for real). Moving the
   measurement and the floor in one change would make their contributions indistinguishable —
   the experiment-hygiene rule of one pipeline variable at a time
   ([ADR-0053](./0053-importance-encoding-time-significance.md), applied in
   [ADR-0056](./0056-retire-importance-llm-scoring.md)). The floor keeps its current value and
   meaning here.

10. **The Ollama path is unchanged.** It has no counter to reach for (see Context), so it resolves to
   the estimator and its telemetry says so explicitly rather than leaving a reader to infer it.

The fault column ships in the same change ([ADR-0077](./0077-chaos-tdd-fault-injection.md)):
`TokenCountingChaosBackend` in `tests/chaos.py` injects each failure mode on a schedule, and a
hypothesis strategy fuzzes the return type. The base `ChaosBackend` is deliberately left without
the capability so the existing suite keeps exercising the estimator path.

## Alternatives Considered

### Put `count_tokens` on `LLMBackend` itself, as `context_window` was

The symmetric-looking option, and the one "match the `context_window` discipline" reads as at first
glance. Rejected on the type-level consequence: structural conformance would then require every
backend to supply a tokenizer, including the two sibling backends that cannot. ADR-0066 accepted
that obligation for `context_window` because a context window is a constant a backend always knows
and can declare in one line. A tokenizer is neither. The runtime half of the discipline —
`getattr` + tolerate absence — is kept in full; only the static requirement is dropped.

### Give the Protocol member a default body so implementers may omit it

Rejected as a misunderstanding of how Protocols work: a default body makes a member non-abstract for
explicit subclasses, but structural conformance still requires it. External backends injected via
`configure(backend=...)` are structural, so this would break them exactly as option 1 does, while
looking like it does not.

### Correct the estimator with a fixed divisor instead (e.g. CJK at 1.1 tok/char)

Cheapest possible change, and it would recover most of the wasted budget on Japanese input.
Rejected: the correction factor is model-specific (the 1.73–1.95x band was measured against Apple's
tokenizer, not gemma4's), it is measured on this agent's current corpora rather than on arbitrary
untrusted input, and tightening a *safety* bound on a sample is how the under-count failure ADR-0066
closed gets reopened. A backend that knows its own tokenizer is the correct authority; an average is
not. The estimator keeps its conservative contract for the case where nothing better exists.

### Call `/api/tokenize` on Ollama for the built-in path

Rejected as unavailable, not as undesirable: the endpoint 404s on 0.30.11 and the upstream PR is
unmerged (see Context). Recorded as a follow-up with an explicit trigger rather than dismissed.

### Do nothing — keep the estimator-only guard and accept the margin

The status quo is defensible on its own terms, and it is the option this ADR has to beat. The
1.73–1.95x over-count costs nothing observable today: the Ollama path runs at 32,768 tokens, where
the margin clamps `num_predict` earlier than necessary but no production call has ever been
suppressed by it, and every backend that currently exists has a large window. The wasted 72% is
entirely hypothetical until a small-window backend ships. Against that, this change adds real
machinery — a second Protocol, two constants asserting things about systems that do not exist yet,
two telemetry fields, and a chaos backend — and the pre-commit review showed the change is subtler
than it looks (the guard was relying on an unnamed safety margin that switching to exact counts
silently removed).

Rejected, but on narrower grounds than "the seam must come first." Strictly, the seam and an Apple
backend could land in one change; nothing forces this order. What the order buys is that the
backend's *measurements* are then about the backend. `T-APPLE-FM-BACKEND` measured Apple's window at
**4,096** and, with the estimator in place, an effective ceiling of 28% of it — a number that is
partly this repo's over-count and partly Apple's window, with no way to tell which from inside that
task. Shipping the seam first makes the backend's subsequent readings attributable. That is a real
benefit and a modest one.

Two things this rejection does **not** claim. It does not claim the status quo has an observable
cost today — it does not; no production call has been suppressed by the margin. And it does not
claim this unblocks Apple comment generation: with the output floor unchanged, the input ceiling at
4,096 is 1,984 real tokens, while the measured Japanese comment prompt is ~4,202. That case needs
the floor question (`T-NUMPREDICT-FLOOR`) or an 8,192 window, neither of which is here. What is
honestly on the other side of the ledger is that deferring also defers the *discovery* the review
round produced — that the guard was relying on an unnamed margin — and that discovery cost two
reviewers to surface, not one reading.

### Use `BackendResult.prompt_tokens` to calibrate the estimator

`prompt_tokens` / `prompt_eval_count` is the real input-token count and is already recorded. But it
arrives after the call, so it cannot serve a pre-flight; its use is a read-only calibration
instrument, which belongs to the separate clamp-floor question and is deliberately not built here.
The `input_tokens` field added by decision 6 does put the guard's number on the same telemetry row
as `prompt_eval_count`, so that instrument becomes a matter of reading existing rows later.

## Consequences

### Positive

- A backend with a real tokenizer gets the window it actually has. On a 4,096-token backend the
  effective input ceiling moves from ~1,140 real tokens (28% of the window) to the window minus the
  clamp floor.
- Existing external backends are untouched: implementing nothing keeps the previous behavior
  exactly, and a regression test pins that (a `ChaosBackend` without the capability must still
  reach the estimator verdict, and a `count_tokens` attribute that is not callable must be ignored).
- The guard is not weakened. Every rejection path falls back to the conservative estimator, so a
  broken counter degrades to the pre-existing behavior rather than disabling the ceiling — asserted
  per fault family, including the case where the counter raises on every call.
- Telemetry answers "which measure produced this clamp?" offline, and `input_tokens` sits beside
  `prompt_eval_count` on the same row.

### Negative

- Two measurement paths now exist for the same quantity, and they disagree by up to 1.95x. A reader
  comparing `input_tokens` across rows must read `token_count_source` alongside it; the field is
  dense precisely so this cannot be skipped, but it is a real added burden on analysis.
- A backend's tokenizer is now on the critical path of every guarded call. A slow `count_tokens`
  costs latency on every generation, and nothing in this change bounds that — the capability is
  assumed cheap (in-process), which is true for `SystemLanguageModel.token_count` but would not be
  for an HTTP-backed counter.
- `TokenCountingBackend` is a second Protocol covering the same objects. Someone adding a future
  capability now has a precedent for a third, and a proliferation of one-method capability Protocols
  would be worse than the single interface ADR-0066 assumed.
- Decisions 4 and 5 introduce two numbers that are *judgments about other systems*, not measurements
  of this one. `MAX_CHARS_PER_TOKEN = 50` is an assertion about what production tokenizer
  vocabularies contain, and `BACKEND_FRAMING_RESERVE = 64` is an assertion about chat-template
  overhead. Both are set far enough from any plausible real value that being somewhat wrong is
  harmless, and both fail toward the pre-existing behavior — but neither was measured against the
  backends that will actually be affected, because those backends do not exist yet.

### Provenance

Decisions 4 and 5 were not in the approved plan; they come from the pre-commit review round, where
two independent reviewers reached the same structural gap from different directions. The cross-model
reviewer (Codex) raised the framing overhead: summing `system` and `prompt` separately omits what
`generate()` adds around them, and the guard then clamps to the exact remainder. The
security reviewer raised magnitude: shape validation accepts any plausible-*shaped* count, so a
count of `5` for a 50,000-character prompt is trusted. Both are the same root cause — switching from
an over-counting estimate to an exact count silently removed a safety margin the guard had been
relying on without ever naming it. That the margin was load-bearing became visible only once it was
gone.

### Neutral / Follow-ups

- **Ollama real counting**, gated on upstream: if `ollama#12030` merges and reaches the running
  version, the same seam accepts it with no change to the guard body — but each generation would
  then cost an extra HTTP round-trip, so adopting it should follow a latency measurement on the
  unattended schedule, not the endpoint's mere existence.
- **The clamp floor** (`MIN_CLAMPED_NUM_PREDICT`) remains open, now with better inputs: once rows
  carry `input_tokens` next to `prompt_eval_count`, the estimator's real-world ratio can be read off
  production telemetry instead of a one-off corpus sample.
- **`core/insight_novelty.py`** still packs judge chunks against `_estimate_tokens`. It is left
  alone on purpose: the guard relaxing means the packer is now *tighter* than the pre-flight, which
  is the safe direction its own contract already names ("packing tighter than the preflight is
  safe"). Following the packer along is a separate change.

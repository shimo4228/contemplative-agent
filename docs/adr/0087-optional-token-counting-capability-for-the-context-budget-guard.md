# ADR-0087: An Optional `count_tokens` Capability for the Context-Budget Guard

## Status

accepted — extends [ADR-0066](./0066-backend-aware-context-budget-guard.md)

This ADR adds a measurement source to the guard ADR-0066 built. It **alters none of ADR-0066's
decisions**: `_estimate_tokens` keeps the constants §5 hardened, `MIN_CLAMPED_NUM_PREDICT` keeps its
value *(superseded 2026-08-01 by the Amendment — the floor is now 128; ADR-0066 never decided this
constant, so the claim about ADR-0066 still holds)*, and `context_window` stays a member of
`LLMBackend`. ADR-0066 remains `accepted` as written.
The one place this ADR declines to follow its precedent — putting the new member on `LLMBackend` —
is argued in Decision 1 and the first alternative, not assumed.

**Amended 2026-08-01** (same day, separate change): the clamp floor Decision 9 deliberately left
alone is now resolved — `MIN_CLAMPED_NUM_PREDICT` drops from 2048 to 128. See
[Amendment: the clamp floor resolved](#amendment-2026-08-01--the-clamp-floor-resolved) at the end of
this document. Decision 9 and the second Follow-up read as written *at the time of the original
decision*; the amendment supersedes both.

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

9. **`MIN_CLAMPED_NUM_PREDICT` is not touched.** *(Superseded 2026-08-01 — see the Amendment. The
   separation of variables this decision protects was honored: the floor moved in its own change,
   after this one landed.)* The clamp floor is the subject of a separate open
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
- **The clamp floor** (`MIN_CLAMPED_NUM_PREDICT`) — **resolved 2026-08-01, see the Amendment**
  (2048 → 128). It was settled from *output*-side measurement (comment sizes p50 352 / p90 507),
  which needed no telemetry accumulation. The input-side reading this bullet anticipated is still
  worth taking and still open: once rows carry `input_tokens` next to `prompt_eval_count`, the
  estimator's real-world ratio can be read off production telemetry instead of a one-off corpus
  sample. That reading now informs `_estimate_tokens`, not the floor.
- **`core/insight_novelty.py`** still packs judge chunks against `_estimate_tokens`. It is left
  alone on purpose: the guard relaxing means the packer is now *tighter* than the pre-flight, which
  is the safe direction its own contract already names ("packing tighter than the preflight is
  safe"). Following the packer along is a separate change.

## Amendment (2026-08-01) — the clamp floor resolved

Decision 9 held `MIN_CLAMPED_NUM_PREDICT` fixed at 2048 so that measurement and floor did not move
in the same change. With the measurement change landed (`a60a0e8`), the floor moves on its own:
**2048 → 128, and the clamp stays.**

**The floor was doing two jobs.** One is cheap and correct: refuse to start a generation on an
absurd remainder (six tokens of headroom buys nothing). The other was a **prediction** — "a usable
answer needs 2048 tokens" — which was never validated, and which this ADR's own Context then
carried outside the window it was chosen for. Only the prediction is retired.

**What the prediction was worth, measured.** Comment output on this agent runs **p50 352 / p90 507
tokens** (n=2,366, counted with a real tokenizer over the last 30 days of
`reports/comment-reports/`). The floor was therefore about **6x** what its own justification
required. Two other values bound the answer from below: `generate_for_api` derives its own minimum
as `ceil(max_length / chars_per_token) + 50`, and Ollama's default output length is 128 — an unsent
`num_predict` is cut there, which is why this code always sends one. 128 is the point below which
the floor would start turning away a **complete** comment (p90 507), not merely a long one.

**That percentile measurement was also not preserved**, and the same confession the Context makes
about the tokenizer-ratio table applies here: the count was taken in a scratchpad against Apple's
`SystemLanguageModel.token_count` over a date-bounded slice of `reports/comment-reports/`, with no
script written into `docs/evidence/adr-0087/`. A reader can recount the corpus but will not
reproduce `n=2,366` exactly without the same window and the same entry-type filter. What the choice
of 128 actually needs from that measurement is weak and robust: that real comment output is in the
*hundreds* of tokens, not thousands. The two independent bounds (`+50`, Ollama's 128) do not depend
on it at all. Anyone re-deriving the percentiles should write the probe into
`docs/evidence/adr-0087/` and link it here.

**Other floor values considered.**

- **507 (comment p90), or some margin above it** — the value that would guarantee the floor never
  turns away a comment it could have served. Rejected because it re-commits the mistake being
  retired: it makes the floor predict output size again, just with a better-sourced number. The
  percentile is a property of one caller (comments) on one model at one point in time; baking it
  into a constant shared by every caller reintroduces the "chosen inside one context, used outside
  it" failure. A floor that turns a long comment into a truncation-drop costs one generation and
  leaves a telemetry row; a floor that predicts costs suppressed actions and leaves nothing.
- **Remove the floor entirely, clamp to whatever remains** — the cleanest-looking option, and the
  one the reasoning above almost argues for. Rejected on the 2026-07-09 evidence read the other way:
  the cheap job is real. A clamp to six tokens spends a full prompt-eval on a generation that cannot
  say anything, and does so repeatedly, since the condition that produced it persists. Keeping a
  small floor costs one constant and preserves the `budget_exceeded` telemetry row that makes the
  condition visible.
- **Keep 2048** — rejected because nothing supports it. Its stated justification (a chars-to-tokens
  conversion done with the over-counting estimator) measures ~6x over against a real tokenizer, and
  the constant has since been carried into a 4,096-token context where it inverts into an input
  ceiling consuming half the window. The value is not defended by this ADR's own Context; it is
  criticized by it.
- **Make the floor a fraction of `context_window`** (e.g. 3%) — attractive because it would scale
  with the backend instead of being window-specific, which is the exact defect being fixed.
  Rejected as premature: it is a second variable moving in the same change, and there is one data
  point (4,096) to fit it to. Reconsider if a third window size ever ships.

**The clamp is untouched, and must be.** `num_predict` reserves nothing; it is a stop condition.
Sending a value larger than the remaining window does not fail — generation simply runs past the
edge, and Ollama evicts from the **front**, taking the system prompt's value layer (identity /
axioms) first. Clamping to the exact remainder stops generation at the boundary instead. Nothing in
this amendment weakens that; only the threshold at which the guard prefers skipping over clamping
moves.

**Why the question belongs downstream.** "Is this generation long enough to be usable?" is answered
by `drop_truncated` (audit M2) from the actual `done_reason=length`, on every API publish path.
That gate measures; the floor guessed. With both present, the guess was the redundant half — and
the expensive one, because a skip suppresses an action outright whereas a truncation drop costs one
generation and is visible in telemetry as `truncated_dropped`. The change is from *predicting* to
*trying and measuring*.

**Blast radius: near-zero on Ollama, real on a small window.** The floor can only fire once the
input exceeds `NUM_CTX - floor`. At 32,768 that boundary moves from 30,720 to 32,640 tokens — both
far above the largest system prompt this agent has ever built (~20.3K tok, the 2026-07-09 outage),
so no production-shaped Ollama call changes verdict. This is asserted, not assumed:
`TestClampFloorIsInertOnOllama` pins the boundary against that high-water mark and pins the outage
shape as unchanged. The change bites where this ADR's Context said it would — on a 4,096-token
backend, where the same constant consumed **50%** of the window as an output reservation and, per
that Context, cost more than the estimator's over-count did.

**Fault column** (ADR-0077): the behavior that changes is *calls that used to be skipped now run*,
so the newly reachable failure is a clamped generation cut mid-sentence.
`TestNarrowHeadroomTruncationF7` injects it at the `LLMBackend` seam (existing `TRUNCATED` fault,
no new vocabulary) and asserts the publish path drops the fragment, the drop is not scored against
the circuit breaker, an internal caller still keeps its partial text, and the floor still skips just
below itself.

**Left alone deliberately:** `_NOVELTY_OUTPUT_RESERVE` in `core/insight_novelty.py` keeps its 2048,
now as the judge's own reservation rather than a copy of the floor (its comment is corrected to say
so). Packing tighter than the pre-flight remains the safe direction, as the third Follow-up above
already argued.

### Consequences of this amendment

#### Positive

- A small-window backend gets back the ~50% of its window this ADR's own Context identified as
  consumed by the output reservation — the half the original change explicitly could not recover.
- The guard stops making a claim it has no basis for. What remains ("this remainder is too small to
  spend a generation on") is cheap and locally checkable; what left ("a usable answer needs N
  tokens") was a caller-specific property living in a shared constant.
- A failure that used to be invisible becomes a telemetry row: where the floor silently skipped, a
  too-small budget now produces `truncated_dropped` with the clamped value recorded, so the
  condition is legible offline instead of inferable only from an absence.

#### Negative / accepted risks

- **Truncation-drops replace skips in the newly opened band, and they are not free.** A call clamped
  to a small budget spends a full prompt-eval before the M2 gate discards its output. On a
  small-window backend under sustained pressure this converts a silent suppression into a repeated
  cost. Bounded by the floor still existing, and visible in telemetry — but it is a real cost the
  old behavior did not pay.
- **Internal callers see short partial text more often.** `drop_truncated=False` paths
  (distill / insight) keep a length-capped generation by design and fall back on their own. Their
  fallbacks now trigger on shorter fragments than before. No external surface is affected; this is a
  data-quality exposure inside the value-layer pipelines, and it is worth a look if a small-window
  backend ever runs them.
- **The M2 gate that now carries this responsibility is conditional on a signal the Protocol makes
  optional.** `BackendResult.finish_reason` may be `None`, and `_drop_for_output_truncation` returns
  `False` in that case — so a backend that reports no finish reason bypasses the fail-closed drop
  entirely and can publish a cut fragment. This is a **pre-existing gap, not one this amendment
  creates**: it holds at any floor value, and every backend shipping today reports the signal
  (Ollama `done_reason`; the MLX sibling forwards `finish_reason`). What this amendment changes is
  *frequency* — the newly opened band is exactly where truncation is likely, so the gap is reachable
  more often. Tracked separately as `T-FINISHREASON-GATE` rather than folded in here, because
  closing it is a Protocol-contract decision, not a floor decision.
- **Explicitly NOT a consequence: the margin against a mis-calibrated backend tokenizer.** A first
  review pass argued the floor had been a 2048-token backstop against `count_tokens` under-counting,
  reduced ~11x. That is wrong, and the correction is recorded here because the intuition is
  natural: the clamp *spends* the remaining budget rather than leaving it as slack, so with an
  under-count of `delta` the window overrun is `delta − BACKEND_FRAMING_RESERVE` **regardless of the
  floor**. A probe at both floors confirmed it — identical 335-token overrun at 2048 and at 128 for
  the same `delta`. `BACKEND_FRAMING_RESERVE` is that backstop and is untouched. The floor only
  decides skip-versus-clamp; it never appears in the overrun arithmetic.

#### Provenance

- Decided by the repository owner on 2026-08-01 from the output-side measurement above; implemented
  the same day. Reviewed by python-reviewer (approve), security-reviewer (one HIGH, disproved by the
  probe recorded above; one MEDIUM, recorded as the internal-caller item), a cross-model reviewer
  (the `finish_reason` item), and adr-reviewer, whose NEEDS REVISION verdict produced this
  Consequences section, the alternatives above, and the evidence-gap paragraph.

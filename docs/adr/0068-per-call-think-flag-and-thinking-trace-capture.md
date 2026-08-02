# ADR-0068: Per-Call `think` Flag and Reasoning-Trace Capture to the Episode Log

## Status

accepted (amended 2026-08-02)

**Amended 2026-08-02**: Decisions 2 and 3 recorded the think *request* and the trace-capture
fallback chain, but nothing recorded whether the requested trace actually arrived. A call could
ask for a trace, get none, and leave a telemetry row saying `think: true` beside a snapshot with
no `reasoning.md` — a silent fallback under [ADR-0075](./0075-observability-by-default.md)
Decision 3. See [Amendment: the capture outcome becomes
observable](#amendment-2026-08-02--the-capture-outcome-becomes-observable) at the end of this
document. Decisions 2 and 3 read as written *at the time of the original decision*; the amendment
extends both. The capture chain itself is unchanged.

## Date

2026-06-28

## Context

The LLM generation path hard-coded thinking **off** on every backend: the Ollama
payload sent `"think": False` ([`core/llm.py` (now `core/llm/`)](../../src/contemplative_agent/core/llm/)
`_post_ollama`) and the MLX backend sent `chat_template_kwargs={"enable_thinking": False}`
(`core/mlx_backend.py` (retired to contemplative-agent-mlx, [ADR-0070](0070-retire-mlx-to-sibling-repo-and-remove-docker.md))). There
was no way to enable a reasoning trace per call, and even if a model emitted one,
`_sanitize_output` → `_strip_thinking` discarded it and `generate()` returned only
the published text.

Two needs motivated a change. First, an upcoming **A/B comparison** of a thinking
model (Gemma 4 E4B think-on vs think-off vs the current think-off baseline) needs
think to be controllable per call **and** needs the think state recorded so the two
conditions are distinguishable in telemetry. Second, when thinking is on, the
reasoning **content** is research material worth keeping — but it must not land in
the per-call telemetry record (`logs/llm-calls-*.jsonl`), which is contractually
metadata-only ([ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md):
"never the prompt body"). Writing untrusted model output into that file would both
break the contract and create a second prompt-injection path when analysis sessions
read telemetry back.

The episode log already stores agent-generated content (comments, replies, posts)
and `internal_note` ([ADR-0045](./0045-pre-action-internal-note.md)) under the
established untrusted regime (direct-read forbidden; distilled artifacts consumed),
so it is the right home for the trace — a reuse of an existing artifact rather than
a new one.

## Decision

1. **Add a per-call `think: bool = False` parameter** threaded through `generate` →
   `_generate_full` → `_generate_impl` → `_post_ollama` / `_generate_via_backend`,
   and added to the `LLMBackend` Protocol's `generate()` keyword-only group.
   `MlxLmBackend` honors it via `chat_template_kwargs={"enable_thinking": think}`.
   Default False = the production behavior; no call site enables it in this change.

2. **Record `think` in telemetry as a boolean flag only.** *(Extended 2026-08-02 — see the
   Amendment. The flag records the request; two provenance fields now record the outcome. The
   metadata-only contract is unchanged: still no trace content.)* The `tel` record gains a
   `"think"` field (metadata, like `model`/`temperature`); the trace *content* is
   never written there. This extends the ADR-0065 telemetry contract by one field
   and lets analysis tell think-on from think-off rows apart (e.g. for the A/B).

3. **Capture the trace and surface it through the publish seam.** *(Extended 2026-08-02 — see the
   Amendment. The read order is unchanged; each step of it now records which channel it used and
   why it fell through.)* A new frozen
   `GenerationOutput(text, thinking)` is returned by the shared core
   (`_generate_full`) and by `generate_for_api`. `generate()` keeps returning
   `Optional[str]` (projects to `.text`), so the 14 non-publish call sites are
   untouched. The trace is read from Ollama's dedicated `thinking` response field
   (or `BackendResult.thinking` / inline `<think>` fallback), secret-scrubbed
   (`_scrub_secrets`, extracted from `_sanitize_output`) but never `<think>`-stripped
   or length-capped, since it is stored, not published.

4. **Store the trace on the episode and render it in the report.** `generate_comment`
   / `generate_reply` / `generate_cooperation_post` and `ContentManager.create_*`
   return `GenerationOutput`; the publish paths (`feed_manager`, `reply_handler`,
   `post_pipeline`) attach a `thinking` field to the `comment` / `reply` / `post`
   `activity` episode beside `internal_note`. `report.py` renders it as a
   `**Thinking:**` block (URL-defanged like every other field; hidden when empty).

The trace is None under the default `think=False`, so episodes, reports, and
production behavior are unchanged until a caller opts in (deferred to the A/B
outcome).

## Alternatives Considered

### Write the trace content directly into the telemetry record

Rejected: violates the ADR-0065 metadata-only contract for `logs/llm-calls-*.jsonl`
and turns telemetry into a second untrusted-content store / injection path. The
boolean flag stays in telemetry; the content goes to the episode log.

### Create a new `logs/llm-thinking-*.jsonl` artifact

Single-responsibility-clean, but adds a new file and a new untrusted-content
lifecycle to manage when the episode log already stores agent-generated content
under an established trust regime. Reusing the episode log (the author's explicit
preference) is the lower-surface choice.

### Change `generate()` itself to return `(text, thinking)`

Rejected: it would break all 14 internal call sites that consume `Optional[str]`.
Limiting the return-type change to the publish seam (`generate_for_api` and the
comment/reply/post wrappers) confines the blast radius to the four paths that record
episodes.

## Consequences

### Positive

- Thinking is controllable per call and observable in telemetry, enabling the
  think-on/off A/B with distinguishable records.
- The reasoning trace is preserved as research material in the episode log and the
  comment report, under the existing untrusted regime, without a new artifact.
- The telemetry metadata-only contract and the trust boundary are both preserved
  (content never enters telemetry; trace is secret-scrubbed before persistence).
- Default-off means zero production behavior change until a deliberate opt-in.

### Negative

- `think` is a Protocol contract change: every `LLMBackend` implementer (incl. the
  sibling `contemplative-agent-cloud`) must accept the keyword to gain trace capture;
  until updated, an omitting backend would raise on the new kwarg (caught as a
  generation failure). In-repo backends and all test doubles were updated.
- The publish seam's return type changed (`Optional[str]` → `GenerationOutput`),
  which required updating the comment/reply/post wrappers, `ContentManager`, the
  three episode-recording call sites, and their tests.

### Neutral / Follow-ups

- No call site sets `think=True` yet; wiring comment generation to think (and any
  decision to adopt a thinking model) is deferred to the A/B outcome. First A/B run
  (gemma4:e4b think-on/off vs qwen3.5:9b, 2026-06-28):
  [`docs/evidence/adr-0068/gemma-e4b-think-ab-20260628.md`](../evidence/adr-0068/gemma-e4b-think-ab-20260628.md)
  — codex blind judge ranks gemma_think > gemma_nothink > qwen; gemma think-OFF is a
  faster, higher-quality swap candidate; think-ON's quality edge is small vs 2.2× latency.
- The sibling `contemplative-agent-cloud` backend should add the `think` keyword and
  populate `BackendResult.thinking` to gain trace capture on the cloud path. **The first half of
  that repair is what makes the 2026-08-02 Amendment urgent** — a backend that accepts the kwarg
  without populating the field degrades all nine think-ON call sites at once.

## Amendment (2026-08-02) — the capture outcome becomes observable

Decisions 2 and 3 built a request and a fallback chain, and recorded only the request. `_finalize_ok`
resolved `BackendResult.thinking` → inline `<think>` → `None`, and the `None` at the end of that
chain was written nowhere: `tel["think"]` still said `true`, `outcome` still said `ok`. **Two
provenance fields and a three-code vocabulary now close it. The chain itself does not move.**

**The flag answered a different question than the one being asked of it.** `think: true` is a
statement about what this call *requested*. Every consumer downstream — the snapshot manifest
([ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md) Decision 5), the
`reasoning.md` writer (Decision 4), an analyst reading `llm-calls-*.jsonl` — was reading it as a
statement about what the call *produced*. Those coincide only while every backend honors the flag.

**Measured on the live store.** Of 100 snapshot runs, 6 declare `"think": true`, and one of those
six (`skill-stocktake_20260710T114758325173Z`) has no `reasoning.md`. Whether that run made no
think-ON call at all or made one that returned nothing is not recoverable from anything on disk.
One in six is not a corner case, and the record needed to tell those two apart did not exist.

**Why now, rather than when a backend actually stops honoring think.** The exposure is one task
away. `contemplative-agent-cloud` is currently non-conforming and fails *loudly* (`think` is a
required kwarg → `TypeError` → `error_kind="backend_exception"`). The minimum repair is to accept
the kwarg — at which point it becomes a backend that accepts `think=True` and returns
`thinking=None`, and all nine think-ON call sites (Decision 3 of ADR-0069) degrade silently at
once. Building the record after that repair means building it during the outage it would have
detected.

**The vocabulary, and what is deliberately outside it.** Three codes, in
`core/llm/backend.py` beside the ADR-0087 pair:

| code | meaning |
|---|---|
| `trace_absent` | neither channel carried anything |
| `trace_blank` | a channel carried content and sanitization left nothing |
| `trace_type` | the dedicated field was not a `str` |

`trace_blank` is separate from `trace_absent` on purpose: the first is a model behavior, the second
a backend that never populates the field, and they take different repairs. **`think=False` is not
in this vocabulary** — the same discipline ADR-0087 states for an absent counter ("absence is the
default, not a fallback from something"), and here it is load-bearing in the other direction: a
per-call *request* is what makes non-delivery a fallback at all, so a call that never asked has
nothing to record. Nor is the `MAX_THINKING_CHARS` cap (a declared contract), nor rows that never
reach the success tail (`outcome` already answers those).

Critically, no code says anything about a backend's **nature**. Each is a statement about what was
observed on one call. That is what keeps the vocabulary valid if a capability marker ever lands
(`T-BACKEND-CONTRACT-KIT`): a marker would only *subtract* `trace_absent` rows for backends that
never claimed to produce traces, leaving the codes and their consumers unchanged.

**Source, not just verdict** (ADR-0087 Decision 8). The dense `thinking_source` records *which*
channel delivered the trace — `field`, `inline`, or `absent` — and stays `None` when the guard
never ran. It is not a restatement of the reason: a wrongly-typed field followed by a usable inline
block records `thinking_source="inline"` **and** `thinking_fallback_reason="trace_type"`, which is
the row that tells a backend quietly failing over to text-embedded traces apart from one working
as intended.

**A second defect, closed in the same three lines.** `data.get("thinking")` reached
`_sanitize_thinking` with no type check (contrast the `isinstance(..., int)` guard on `eval_count`
four lines above). A non-`str` raised `AttributeError` inside `_scrub_secrets` — *after* the line
that stamps `outcome="ok"`, so telemetry claimed success while the caller got an exception. The
type guard sits where the value first arrives, and logs the type name only, never the value: the
value could **be** the trace, i.e. untrusted model output, on a stream swept by
`log_anomaly_sweep.py` and fed to the weekly analysis prompt
([ADR-0083](./0083-episode-logs-enter-the-weekly-prompt-as-hashes-only.md); that side path is what the
2026-08-01 `agent-launchd.log` contamination came through).

**Where emptiness is decided, and why it is not where it looks.** Cross-model review
(codex, 2026-08-02) found the first implementation letting a whitespace-only dedicated field
shadow a usable inline block: the field is *truthy*, so it won the channel choice, the fallback
was skipped, and the sanitizer then reported `trace_blank` for a trace that was sitting right
there in the text. The pre-amendment code had the same behavior (`reasoning or
_extract_inline_thinking(text)` — `"   "` is truthy in Python), so this is not a regression; it
became worth fixing because the amendment adds a *claim* about it, and a wrong reason code is
worse than none. Emptiness is now judged where each channel is read, not after one has been
chosen. A blank field falls through like an absent one and still records `trace_blank`, which is
what explains the `field` -> `inline` downgrade — the same shape as the `trace_type` case. Pinned
by `think_blank_inline`.

The same review found the warning claiming the *run's* snapshot would have no `reasoning.md`. A
run makes several think-ON calls (rules-distill 2, stocktake 4), so one missing trace does not
imply a missing file — a false diagnosis handed out from inside the observability path. The
warning now describes only its own call; which artifacts a run ended up with is
`_write_reasoning`'s to say.

**Not scored, only recorded.** A missing trace leaves `outcome` at `ok` / `truncated_kept` and does
not touch the circuit breaker. The generation succeeded; a research artifact is missing. Scoring it
would let a non-thinking backend open the breaker and suppress healthy generation — the same
reasoning that keeps counter faults (ADR-0087 Decision 7) and over-budget skips off it.

**The CLI end of the same silence.** `_write_reasoning` had one early return for two situations.
It now separates "the command made no think-ON call" (`reason=no_think_calls`, INFO — a verdict,
not a fault: `skill-stocktake` with nothing to merge) from "calls ran and every trace was empty"
(`reason=all_traces_empty`, WARNING). These are local constants, **not** the core codes: this layer
sees only empty strings and cannot tell `trace_absent` from `trace_blank`, so reusing a core code
here would assert more than the layer can support. The pointer to `llm-calls-*.jsonl` is the join.

**Left alone deliberately:**

- **The snapshot manifest.** ADR-0069 Decision 5 defines `think` there as the run's *input*
  generation config, written before any LLM call. Making it mean "a trace was captured" would fold
  output reasoning into the input record and overturn that decision — and would buy nothing, since
  the telemetry row already carries the fact and joins to the snapshot through `audit.jsonl`
  (which holds both `snapshot_path` and `run_id`).
- **`LLMBackend` / a capability marker.** `think` is already a mandatory kwarg, so the structural-
  typing pressure that forced ADR-0087's separate `TokenCountingBackend` Protocol does not exist
  here. Making `thinking`'s absence contractually *meaningful* is a Protocol-contract decision
  (`T-BACKEND-CONTRACT-KIT` / `T-FINISHREASON-GATE`); making it *observable* is not — the same cut
  ADR-0087's amendment made when it split out `finish_reason`.
- **The intermediate carriers** (`rules_distill._combine_traces`, `stocktake._generate_with_trace`).
  Each underlying call is already accounted for at the LLM layer; warning here would emit N
  warnings for one fact inside functions whose job is aggregation.

**Fault column** (ADR-0077): `TestThinkingTraceFaultsF8` in `tests/test_llm_chaos.py`, injected via
a new `ThinkingChaosBackend` in `tests/chaos.py`. A **separate subclass with its own vocabulary**,
not a member of the shared `FAULT_VOCABULARY` — that vocabulary is iterated by the distill and
insight property tests, whose per-fault tallies would have to be re-derived for a new member, and
the base `ChaosBackend` must keep never populating `.thinking` so the existing suite keeps
exercising the no-trace path. Seven faults (`think_ok` / `think_inline` / `think_missing` /
`think_blank` / `think_type` / `think_type_inline` / `think_blank_inline`) map to expected
`thinking_source` and `thinking_fallback_reason` values a parametrized test reads from the
schedule alone. No hypothesis
strategy: unlike `count_tokens` (two calls interacting within one `generate()`), trace capture has
no cross-call state, so parametrization over six members is exhaustive. `test_vocabulary_has_no_dead_codes`
asserts every declared reason is reachable by an injectable fault — a code no fault can produce is
documentation pretending to be a gate. Both guards were proved to fire by temporary violation
injection (removing the reason stamp: 8 failures; removing the type guard: 9).

### Consequences of this amendment

#### Positive

- A `think: true` row is now self-sufficient: request, channel, and the reason for any non-delivery
  sit on one line, joinable to a snapshot through `audit.jsonl`. The ADR-0075 Verify question
  ("which log answers why, and can we replay it offline?") is answered by a grep.
- The `-cloud` repair can now land without a silent-degradation window: a backend that accepts
  `think` without populating `thinking` announces itself on every row instead of quietly emptying
  every `reasoning.md`.
- A crash path that reported itself as `outcome="ok"` is closed.
- `thinking_source` gives the first read on *how often the inline channel is actually load-bearing*
  — a question Decision 3 built a fallback for without any way to see it fire.

#### Negative / accepted risks

- One more dense telemetry field on every row (`thinking_source`), the second field added to this
  record in two days. The metadata-only contract holds, but the row is no longer small, and
  `EXPECTED_FIELDS` in `tests/test_llm_telemetry.py` is an exact-match lock that every future field
  must pass through.
- The WARNING on a missing trace fires per call, not per run. Under a non-honoring backend the nine
  think-ON call sites would produce nine warnings for one condition. Judged acceptable because the
  condition is currently unreachable in production and its arrival is exactly the event that should
  be loud — but if it becomes routine, the right fix is a run-level summary, not a quieter log.
- The `field` / `inline` / `absent` distinction cannot separate "this backend never produces
  traces" from "this model produced none this time". That ambiguity is left standing deliberately
  (see *Left alone*); it is answered out-of-band by grouping rows on `model`.

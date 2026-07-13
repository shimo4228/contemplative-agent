# ADR-0077: Chaos-TDD Fault Injection — Seeded Fault Schedules as Test-First Specification (Pilot: distill)

## Status

accepted

## Date

2026-07-13

## Context

Operational bugs in this agent repeatedly share one family: an LLM or
external I/O returns an unexpected response and the pipeline degrades
silently. The project's own operational history is the evidence —
`num_ctx` silent truncation, `done_reason=length` mid-cut generations,
dedup's silent no-fire, Moltbook API rate limits, and CAPTCHA-gate drift
have each been diagnosed after the fact, not caught by a test written in
advance. The ~1830-test suite covered happy paths and a small set of
single known failures, but five fault classes remained untested:

- **F1** — mid-generation read-timeout. Only `ConnectionError` was
  covered; a timeout arriving mid-stream was not.
- **F2** — direct HTTP faults on `/api/embed` (429, timeout, ragged rows,
  short row count).
- **F3** — syntactically-valid JSON that violates the
  `{"patterns": [str]}` structured-output shape (wrong top-level type,
  wrong key, non-string list items).
- **F4** — HTTP 429 from the Ollama endpoint itself. 429 was tested only
  on the Moltbook client, not on the local LLM backend.
- **F5** — flapping backends: alternating success/failure sequences
  beyond the single-recovery case already under test.

`distill`'s failure paths predated the ADR-0075 observability discipline.
An episode whose LLM call failed was dropped silently, per-episode, with
no reason code. A wrong-shaped JSON response fell through to a bullet
scan of the raw JSON body, whose near-certain empty result was
indistinguishable from a legitimate empty extraction — the pipeline could
not tell "the model returned nothing extractable" from "the model
returned garbage we mis-parsed as nothing." Telemetry compounded this:
`outcome="error"` collapsed 429, timeout, connection failure, and bad
response body into one undifferentiated value, so the audit log could not
answer which fault actually occurred.

Phase 0 external research (2026-07-13) returned a **Compose** verdict:
`hypothesis` (a new dev dependency; deterministic via `derandomize`;
strategy-based fault generation) plus `responses` (already declared as a
dev dependency but previously unused; requests-layer HTTP fault
injection) plus a thin custom `ChaosBackend` at the existing `LLMBackend`
Protocol seam. `chaostoolkit` and `toxiproxy` are infra/daemon-level tools
built for distributed topologies — the wrong altitude for a single local
process whose faults are injectable in-process. No viable pytest chaos
plugin exists (surveyed and rejected below). `agent-chaos` (25 stars,
coupled to the Anthropic SDK and DeepEval) served only as fault-taxonomy
prior art, not as an adoptable dependency.

## Decision

1. **Injection seams are fixed to the two that already exist** — the
   `LLMBackend` Protocol (a test-side `ChaosBackend` in `tests/chaos.py`,
   schedule-driven, seed-derivable via `from_seed`) and the `requests`
   HTTP layer (`responses` registration helpers). No production chaos
   hook is added; the pipeline code under test is unaware it is being
   tested.
2. **Determinism discipline governs every fault.** Fault schedules are
   either an explicit list or seed-derived and inspectable. `hypothesis`
   runs under a `"ci"` profile (`derandomize=True`, `database=None`,
   `deadline=None`) registered in `tests/conftest.py`, with
   `HYPOTHESIS_STORAGE_DIRECTORY` relocated into the pytest sandbox
   tempdir. Latency faults are expressed as injected `ReadTimeout`
   exceptions so no test sleeps. Known failure shapes are pinned with
   explicit `@example` decorators so a shrunk hypothesis case becomes a
   permanent regression.
3. **Steady state is asserted on the observable channel**, not
   implementation internals: the telemetry channel
   (`llm-calls-{date}.jsonl` `outcome` plus a new sparse `error_kind`
   field) and machine-greppable reason-coded log tokens
   (`reason=<code>`).
4. **TDD contract**: a chaos test states the desired guarded behavior
   first — e.g., abstain with a reason code — and the minimal guard lands
   in the same PR that adds the test. The fault schedule is the
   specification; the guard is the implementation that satisfies it.
5. **Production deltas shipped by this pilot**:
   - **`distill` abstain reason codes.** `_parse_patterns` returns
     `(patterns, parse_mode)` and classifies valid-JSON-wrong-shape
     (including non-string list items, per the `items: string` schema) as
     `shape_violation`, which abstains instead of bullet-scanning. The
     bullet fallback is retained for genuinely non-JSON bodies (audit
     H2) but tagged `parse=bullet_fallback`. `_distill_one` returns
     `ABSTAIN_LLM_NONE` / `ABSTAIN_EMPTY_RENDER` / `ABSTAIN_SHAPE_VIOLATION`
     reason codes instead of a bare `None`. `_distill_episodes` tallies
     abstains per reason in the summary WARNING. The embed-degradation
     warning carries `reason=embed_failed`.
   - **`llm.py` telemetry `error_kind`.** A sparse field present only on
     failure rows — `timeout` / `connection` / `http_<status>` /
     `bad_json` / `bad_url` / `request_error` / `backend_exception`, via
     `_classify_request_error`. The existing `outcome` value set is
     unchanged (additive, backward compatible).
6. **F4 pins the fail-fast policy**: a 429 from Ollama itself gets no
   retry and no `Retry-After` sleep. For a local daemon, the circuit
   breaker — not backoff — is the recovery mechanism.

## Alternatives Considered

### chaostoolkit / toxiproxy

Rejected. Both are infra-level chaos tooling (experiment-runner daemon /
network proxy) built for distributed topologies. Wrong altitude and
dependency weight for a single-process local agent whose faults are all
injectable in-process at existing Protocol/HTTP seams.

### pytest chaos plugins

Rejected — none viable exists. `pytest-disrupt` is a 0-star, TODO-only
scaffold. `mcp-chaos-monkey` targets MCP transports, not this project's
LLM/HTTP surface.

### agent-chaos

Rejected as a dependency, kept as prior art. Closest conceptual match
(25 stars) but young, coupled to the Anthropic SDK and
DeepEval/pydantic-ai, with no pytest integration and no local-backend
support. Used only to validate the fault taxonomy (F1–F5), not adopted.

### requests-mock

Rejected — functionally redundant with `responses`, which was already a
declared but unused dev dependency.

### Place `ChaosBackend` in `src/`

Rejected. Runtime dependencies stay `requests` + `numpy` only, and
test-only code must not enter production import paths.

### Production random chaos (Netflix-style)

Rejected. Episode logs are irreplaceable research material
(`no-delete-episodes`) and the agent is a single local process — random
production fault injection risks destroying data the project cannot
regenerate. Deterministic in-process injection at the seams gives the
same fault coverage reproducibly, without touching the running system.

## Consequences

### Positive

- A wrong-shaped-but-parseable LLM output no longer silently degrades to
  an empty bullet scan; it abstains loudly with `reason=shape_violation`,
  now distinguishable from a legitimate empty extraction.
- Telemetry distinguishes 429 / timeout / connection / bad-body /
  backend-exception failures offline, where previously all four
  collapsed into one undifferentiated `outcome="error"`.
- Five previously-untested fault classes are pinned by 32 deterministic
  chaos tests (`tests/test_llm_chaos.py`, `tests/test_distill_chaos.py`,
  `TestEmbedTextsHTTPFaults` in `tests/test_embeddings.py`; count via
  `pytest --collect-only`, 2026-07-13) plus `hypothesis` fuzzing with
  pinned `@example` regressions. The flapping-
  circuit sequences and the fail-fast-on-429 policy are now executable
  specification, not tribal knowledge.
- The fault catalog (`tests/chaos.py` vocabulary) gives future pipelines
  a reusable injection kit. The know-how is captured as the project skill
  `chaos-tdd-fault-injection`.

### Negative

- `hypothesis` joins the dev dependency group (zero runtime deps
  affected; dev-only).
- `_distill_one`'s return type is now `Union[_BatchOutput, str]`; callers
  must treat a `str` return as an abstain reason code. One caller exists
  today.
- Existing top-level-array/scalar `_parse_patterns` tests were inverted
  from "returns `[]`" to "classifies `shape_violation`" — a deliberate
  spec change, recorded here rather than left as a silent test diff.

### Neutral / Follow-ups

Explicitly out of pilot scope, deferred:

- Retry/backoff for Ollama 429 (fail-fast is pinned instead by F4).
- Per-episode retry or carry-over of episodes lost to an abstain.
- A dedicated per-episode replayable audit JSONL for `distill` (ADR-0075
  discipline applied fully) — first follow-up candidate.
- Extending the fault catalog to other pipelines (`insight` / `reply` /
  `feed`).
- Sandbox chaos-mode `meditate` runs.
- Generalizing the project skill into a public fork, mirroring the
  `when-code-when-llm` / `code-and-llm-collaboration` pattern.

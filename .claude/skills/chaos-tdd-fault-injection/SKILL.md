---
name: chaos-tdd-fault-injection
description: Design know-how for ADR-0077 chaos-TDD — deterministic fault injection at existing seams (LLMBackend Protocol / requests HTTP layer) where the fault-injection test states the desired guarded behavior FIRST and the minimal guard lands in the same PR. Use when hardening a pipeline against LLM/external-I/O fault families (truncation, timeouts, 429s, wrong-shaped-but-parseable JSON, flapping backends), when building a fault catalog from operational bug history, when adding hypothesis-based fuzz over LLM output shapes, or when reviewing whether a new pipeline's failure paths abstain with reason codes. NOT for per-event audit log schema design (that is replayable-audit-logs / ADR-0075), NOT for read-only aggregate readings (read-only-instruments / ADR-0071), NOT for single-bug regression pinning after the fact (that is ai-regression-testing — this skill is its front-loaded, catalog-driven counterpart), and NOT for infra-level chaos (chaostoolkit/toxiproxy are the wrong altitude for a single local process).
compatibility: Written for the Contemplative Agent repo (examples are CA-specific); the pattern itself is portable.
origin: shimo4228
---

# Chaos-TDD Fault Injection (seeded fault schedules as test-first specification)

Principle (canonical rationale: [ADR-0077](../../../docs/adr/0077-chaos-tdd-fault-injection.md)):
**operational fault catalog → fault-injection test asserting the desired guarded
behavior (RED) → minimal guard in the same PR (GREEN)**. This is the
front-loaded form of the ai-regression-testing discipline: instead of pinning a
bug after it burned a production run, the catalog predicts the family and the
test forces the guard before the fault ever fires live. Netflix-style random
production chaos is explicitly rejected here — episode logs are irreplaceable
research material, and a single local process needs no daemon to inject faults
into itself deterministically.

## 1. Building the fault catalog

Do not invent faults from imagination — mine them from operational history.
The CA catalog came from real incidents that were all one family ("LLM /
external I/O returns something unexpected; the pipeline degrades silently"):
num_ctx silent truncation, done_reason=length mid-cuts, dedup no-fire, API rate
limits, CAPTCHA drift. Procedure:

1. List the incidents; classify each by *where the unexpected response entered*
   (LLM text? HTTP status? embedding rows? parse layer?).
2. Diff that list against what the test suite already covers (grep for the
   fault, not the feature: `done_reason`, `429`, `JSONDecodeError`, ...).
3. The uncovered remainder is the catalog. CA's pilot: F1 read-timeout
   mid-generation, F2 direct /api/embed faults, F3 valid-JSON-wrong-shape,
   F4 429 from the LLM endpoint itself, F5 flapping sequences.
4. For each fault, write the *asserted behavior* column before writing any
   test — if you cannot say what the pipeline SHOULD do, that is a design gap
   (it usually means "abstain with a reason code" per ADR-0075), and the chaos
   test is about to become the specification for a small production change.

## 2. Choosing injection seams — never add a production hook

Inject only at seams that already exist:

- **Protocol seam** — a test-side fake implementing the same Protocol the
  production backend does (`tests/chaos.py::ChaosBackend` implements
  `LLMBackend`; injected via `configure(backend=...)`, removed by
  `reset_llm_config()`). Faults are a `schedule: List[str]` consumed one entry
  per call — explicit list, or `from_seed(seed, n)` materialized at
  construction so a failing run can print it verbatim for replay.
- **HTTP layer** — the `responses` library registering fault responses on the
  URL the code actually resolves (`ollama_url()` reads the same env var the
  production code does). Covers status codes, `body=ReadTimeout(...)` exception
  injection, and malformed payloads without touching production code.

Cover *both* sides of a dispatch branch (CA: `_generate_impl` routes to
`_post_ollama` or `_generate_via_backend` — F1/F4 hit the HTTP path, F3/F5 the
backend path). Keep the injector in `tests/`, not `src/` — test-only code must
not enter production import paths, and the injector itself needs self-tests
(Protocol compliance, schedule determinism, OK-payload validity).

## 3. Determinism discipline

- Every schedule explicit or seed-derived; inspectable before the run.
- hypothesis profile in conftest: `derandomize=True, database=None,
  deadline=None`, and — the part `database=None` does NOT cover — relocate
  `HYPOTHESIS_STORAGE_DIRECTORY` into the test sandbox tempdir *before
  importing hypothesis*, or the constants/unicode caches recreate an untracked
  `.hypothesis/` in the repo (found the hard way in the pilot).
- No real sleeps: a latency fault is the *observable outcome* of a timeout —
  inject `requests.exceptions.ReadTimeout` instead of sleeping past
  `timeout=`. A `no_sleep` fixture that monkeypatches `time.sleep` to raise
  doubles as the fail-fast assertion (F4: 429 must not honor Retry-After).
- Pin every known failure shape with `@example(...)` on top of `@given(...)` —
  the property explores; the examples are permanent regressions.
- Verify determinism mechanically: run the chaos test files twice in the
  Verify step; identical output is a PASS criterion.

## 4. Steady-state assertion channels

Assert on observable channels, not implementation internals:

- **Telemetry** — CA: `llm-calls-{date}.jsonl` `outcome` + sparse `error_kind`
  (`timeout` / `connection` / `http_<status>` / `bad_json` / `bad_url` /
  `backend_exception`). If the telemetry cannot distinguish the fault kinds
  you are injecting, that indistinguishability IS a finding — the pilot's
  `error_kind` field exists because 429/timeout/connection all collapsed into
  `outcome="error"`.
- **Reason-coded log tokens** — machine-greppable `reason=<code>` WARNING
  lines (`llm_none` / `empty_render` / `shape_violation` / `embed_failed`),
  tallied per reason in the summary line so a backend fault burst is
  distinguishable from a parse-layer problem and from a clean low-yield run.
- Internal counters (circuit breaker state) only for the state machine under
  test itself, nowhere else.

Schedule-driven pipeline tests compute the expected tally *from the schedule
alone* (e.g. `LLM_NONE_FAULTS` mapping). Corollary: exclude circuit-opening
schedules from exact-count properties (`trips_circuit()` filter) — once the
breaker opens, later OK entries short-circuit and the prediction breaks; keep
one separate never-crashes property that allows the breaker to open.

## 5. The TDD contract

The chaos test asserts the DESIRED behavior, which usually does not exist yet
— that is the point. Pilot example: F3 asserted "valid-JSON-wrong-shape
abstains with `reason=shape_violation`" while the code silently bullet-scanned
the JSON body; RED was an ImportError on the reason-code constants. The
minimal guard (parse-mode classification + abstain codes + per-reason tally)
landed in the same PR. Two rules keep this honest:

- Inverting an existing test's expectation (CA: "top-level array returns []"
  → "classifies shape_violation") is part of RED — record the inversion in
  the ADR, never as a silent test diff.
- Keep legitimate degradations: the bullet fallback for *genuinely non-JSON*
  bodies stayed (H2 guarantee), tagged `parse=bullet_fallback` for
  observability. Chaos-TDD tightens the silent paths; it does not delete
  graceful ones.

## 6. What the pilot's fuzz actually caught (worked examples)

- `{"patterns": [123]}` — `str(item)` promotion let non-string schema
  violations through as garbage patterns; the `all(isinstance(item, str))`
  check plus `@example` pin closed it.
- JSON `null` body — `json.loads("null")` returns `None`, which the old
  `parsed = None`-as-failure sentinel routed to the bullet scanner; a
  distinct `_JSON_PARSE_FAILED` sentinel separates "not JSON" from "JSON
  null" (shape violation).
- Telemetry indistinguishability (429 vs timeout vs connection) — surfaced by
  writing the F1/F4 assertions before the field existed.

## When to reach for this skill

- A new pipeline touches an LLM or external API → build its fault column
  before shipping (same PR, per ADR-0075 spirit).
- A production incident closes → after the ai-regression-testing pin, ask
  "which catalog family was this, and which OTHER pipelines share the seam?"
- Reviewing a PR that parses LLM output → the F3 questions: what happens on
  valid-but-wrong-shape? Is the failure distinguishable from legitimate
  emptiness? Is there a reason code?

Deferred follow-ups live in ADR-0077 (per-episode audit JSONL for distill,
other pipelines, sandbox chaos-mode meditate, public-fork generalization).

# ADR-0088: A Shipped Conformance Kit for the `LLMBackend` Contract

## Status

accepted — operationalizes the [ADR-0066](./0066-backend-aware-context-budget-guard.md) /
[ADR-0087](./0087-optional-token-counting-capability-for-the-context-budget-guard.md)
backend seam. Changes no runtime behavior: nothing under `core/` / `adapters/`
/ `cli/` may import the kit, and a contract violation it reports was already a
violation before it could be named.

## Date

2026-08-02

## Context

`contemplative-agent-cloud` last changed on 2026-04-21 (`d6d2da7`). Between
then and 2026-08-01 the `LLMBackend` Protocol gained `temperature`, gained
`think`, changed its return type from `str | None` to `BackendResult | None`,
gained a `context_window` property, and gained an optional `count_tokens`
capability — five changes, none of which reached the sibling. Calling it from
main today raises `TypeError` at the first `generate()`.

Three months of that went unnoticed. Two facts about *why* determine what this
ADR decides.

### The sibling already had a conformance test

`contemplative-agent-cloud/tests/test_anthropic_backend.py:100` asserts
`isinstance(backend, LLMBackend)`. `AnthropicBackend` has no `context_window`,
so that assertion fails today. The test was correct and would have caught part
of the drift. Nobody ran it.

This rules out the obvious framing. The problem is not a missing test, and a
better-written test in the same location inherits the same fate. Whatever is
built has to be runnable by the party that *has* the motive — main, at the
moment it publishes a contract change — not by the repository that has been
untouched for a quarter.

### `isinstance` cannot see the second half of the drift

`LLMBackend` is `runtime_checkable`, and a runtime-checkable Protocol checks
only that members *exist*. Signatures and return types are invisible to it.
Cloud's `generate(prompt, system, num_predict, format) -> Optional[str]`
satisfies the member check completely; the only reason `isinstance` fails at
all is the separate absence of `context_window`.

So a backend can be `isinstance`-clean and still `TypeError` on the first real
call. Detecting that requires asking a different question: not "does the member
exist" but **"can this object bind the call the caller actually issues?"**

### Why the canonical helpers were never reused

`tests/chaos.py` was written as the canonical fault-injection kit (ADR-0077),
and no sibling imports it. `[tool.hatch.build.targets.wheel]` packages only
`src/contemplative_agent`, so `tests/` is not in the wheel: a sibling that
depends on `contemplative-agent` cannot import it and never could. "Main holds
the canonical copy" was true as an intention and false as a distribution
mechanism.

## Decision

1. **The kit ships.** It lives at `src/contemplative_agent/testing/`, inside
   the wheel, so a sibling reaches it through its existing dependency. `tests/`
   was considered and rejected on the distribution fact above — it does not
   satisfy the requirement, which is why the precedent it would have followed
   has zero consumers.

2. **The kit imports only the standard library and `contemplative_agent.core.llm`.**
   pytest, hypothesis, and `responses` are dev-group-only, and the runtime
   dependency set stays `requests` + `numpy`. `tests/chaos.py` already
   demonstrates that reusable test parts need no pytest; the kit follows the
   same discipline for a stronger reason, since it is in the shipped package.

3. **Two `forbidden` import-linter contracts, not a fourth `layers` entry.**
   Production layers may not import the kit; the kit may not import `cli` or
   `adapters`. A `layers` entry would state the direction correctly and *also*
   permit `testing -> adapters`, dragging the Moltbook HTTP client into a
   sibling's test dependencies. What is wanted is a narrow ban on each side.

4. **The load-bearing check is bind-ability, not membership.**
   `generate.binds_canonical_call` binds the exact call `_generate_via_backend`
   issues — four positional, `temperature` and `think` keyword-only. Parameter
   *names* are not required to match, so a backend taking `**kwargs` remains
   conforming; what is required is that the call the caller makes does not
   raise. This is the check `isinstance` cannot express.

5. **Failures are returned, not raised.** `check_backend` returns a
   `ConformanceReport`. The failure being addressed is accumulated drift, not a
   single bug: raising on the first mismatch answers "is it broken" while
   destroying "in how many ways, and which". The report implements `__bool__`
   and a multi-line `__repr__`, so `assert check_backend(b)` stays a one-liner
   and still names every failing check when it fails.

6. **Detection decides what runs; declaration is a lower bound.**
   A capability is checked because it was *detected* on the backend, so
   forgetting to declare one never silently removes coverage. Declaring one
   that is not detected fails. Detecting one that was not declared does **not**
   fail — otherwise adding a capability constant to this module would redden
   three repositories for a purely declarative reason. A declared capability
   that this level cannot observe is deferred, not refuted.

7. **`require=LEVEL_STATIC` is the permanent default.** Levels
   (`static` / `runtime` / `full`) let a sibling declare how far its coverage
   reaches, and falling short of a declared level fails. Raising the *default*
   later would redden siblings that changed nothing — precisely the breakage a
   drift-reducing kit must never cause. Coverage is raised by editing the
   sibling's own call, where it is greppable. `level_reached` is capped at the
   highest level that has registered checks: supplying a future-facing
   `BackendProbe` cannot turn today's static-only kit into a false full green.

8. **Ship in stages; freeze the API in the first one.** This release carries
   six static checks, which capture cloud's three currently observed static
   failures without sibling-side work. They do not validate the
   stale `Optional[str]` return: `result.is_backend_result` is explicitly a
   catalogued runtime check. The runtime and construction checks (23 more,
   catalogued below) follow. `check_backend`'s signature, `ConformanceReport`,
   `BackendProbe`, and the level and capability vocabularies are complete now;
   later stages add checks, never arguments.

9. **`circuit_reading()` is added to `core.llm` as a read-only instrument.**
   Sibling tests read `_circuit._consecutive_failures` directly, so a rename
   inside `_CircuitBreaker` breaks three repositories silently. The reading is
   an instrument in the [ADR-0071](./0071-read-only-pattern-composition-instruments.md)
   sense — existing state, no mechanism, feeds no gate — and sits beside the
   already-public `circuit_shield()` control.

10. **The kit runs from main, not from the siblings.** `python -m
    contemplative_agent.testing --backend pkg.mod:Name` needs no test file in
    the sibling at all, and `scripts/check-sibling-backends.sh` drives it
    across every known sibling. The enforcing gate is a human one in the
    release procedure — [`docs/runbooks/sibling-backend-conformance.md`](../runbooks/sibling-backend-conformance.md),
    invoked from the `release-doi` skill between verification and push. This
    follows [ADR-0012](./0012-human-approval-gate.md)'s pattern of putting the
    decision where a human already stands.

11. **Routine Verify never imports sibling code.** The runner imports and
    constructs Python from adjacent checkouts. Calling it automatically from
    `.claude/verify.sh` would let a compromised sibling execute during an
    otherwise main-only verification, regardless of whether its verdict was
    advisory. The release gate is explicit because that is both the point of
    human judgment and the point at which the operator accepts the sibling
    checkout as executable input.

12. **Unusable is not non-conforming.** The CLI and runner preserve the exit
    taxonomy `0` conforming / `1` non-conforming / `2` target or kit unusable;
    infrastructure failure takes precedence over a backend verdict. CLI
    constructor kwargs are limited to the `base_url` / `model` allowlist because
    argv is visible in process listings, and `base_url` accepts only a
    credential-free HTTP(S) origin. Every other value requires a local factory.
    Exception types are reported without arbitrary
    module or constructor exception text.

### Authoring rule for new checks

**Assert only against symbols `contemplative_agent.core.llm` publicly
re-exports.** A check that hard-codes a telemetry field name or an estimator
constant converts every internal rename into three red repositories for no
contractual reason. Route such values through a constant the kit exports, or
derive them — the over-budget check sizes its prompt from
`backend.context_window`, never from the estimator's chars-per-token.

### The check catalogue

Shipping now (6):

| check_id | level | capability |
|---|---|---|
| `protocol.members` | static | — |
| `model.type` | static | — |
| `context_window.positive_int` | static | — |
| `generate.binds_canonical_call` | static | — |
| `generate.kwonly_defaults` | static | — |
| `count_tokens.signature` | static | `counts_tokens` |

Plus two meta checks that report on the run rather than the backend:
`meta.level_reached` and `meta.declared_capabilities_present`.

Catalogued, not yet implemented (23). "core" checks assert that the caller's
guarantees hold for this backend; "direct" checks assert that the backend
itself honors the contract. The distinction matters because the two failures
mean different things:

| check_id | level | path | capability |
|---|---|---|---|
| `result.is_backend_result` | runtime | direct | — |
| `result.finish_reason_passthrough` | runtime | direct | `reports_finish_reason` |
| `result.counters_absent_stay_none` | runtime | direct | — |
| `result.null_content_becomes_empty_string` | runtime | direct | — |
| `result.prefill_accounting_parsed` | runtime | direct | `reports_prefill` |
| `result.thinking_parsed` | runtime | direct | `produces_thinking` |
| `sampling.top_p_top_k_sent` | runtime | direct | — |
| `sampling.temperature_default_one` | runtime | direct | — |
| `request.empty_system_omitted` | runtime | direct | — |
| `parse.malformed_raises` | runtime | direct | — |
| `transport.error_propagates` | runtime | direct | — |
| `core.sanitization_applies` | runtime | core | — |
| `core.temperature_reaches_backend` | runtime | core | — |
| `core.drop_truncated_returns_none` | runtime | core | `reports_finish_reason` |
| `core.truncated_kept_when_not_dropped` | runtime | core | `reports_finish_reason` |
| `core.truncation_is_not_circuit_failure` | runtime | core | `reports_finish_reason` |
| `core.transport_failure_counts_as_circuit_failure` | runtime | core | — |
| `core.over_budget_skips_before_backend` | runtime | core | — |
| `core.telemetry_records_model` | runtime | core | — |
| `core.telemetry_records_prefill` | runtime | core | `reports_prefill` |
| `construct.rejects_untrusted_host` | full | construction | — |
| `construct.rejects_non_http_scheme` | full | construction | — |
| `construct.rejects_non_positive_context_window` | full | construction | — |

Three of these resist the obvious placement and are recorded here so the
reasoning is not rediscovered:

- `request.empty_system_omitted` cannot run through core. `_generate_impl`
  evaluates `request.system or _build_system_prompt()`, so an empty system
  string is falsy and gets replaced before the backend sees it. Only a direct
  call can observe what the backend does with one.
- `transport.error_propagates` cannot run through core either. Core records a
  circuit failure whether the backend raises or returns `None`, so the two are
  indistinguishable from there. The contract is that the backend *raises* —
  otherwise telemetry's `error_kind="backend_exception"` collapses into
  `outcome="empty"` and the diagnosis is lost.
- `core.over_budget_skips_before_backend` must size its prompt from
  `backend.context_window`, not from a literal. A literal encodes the
  estimator's current chars-per-token and breaks when that is retuned — the
  authoring rule above, in its concrete form.

## Alternatives Considered

### Keep sibling-local tests and manual checks

Rejected for the present state: cloud already had a sibling-local conformance
test, but no actor ran or updated it for three months. A manual comparison has
the same missing trigger and leaves no named, repeatable verdict. This option
becomes viable if every sibling gains an active maintainer and an independently
enforced release gate; that evidence does not exist today.

### Put the kit under `tests/` and have siblings vendor it

The stated precedent (`tests/chaos.py`). Rejected on a distribution fact rather
than a preference: `tests/` is not in the wheel, so a sibling cannot import it.
Vendoring by copy reproduces the hand-copy that caused the drift.

### Add GitHub Actions to each sibling

The original plan, and the first instinct. Rejected on discovery that **no
repository in this family has any CI** — `.github/workflows/` does not exist in
main, `-mlx`, or `-cloud`. Adding it would introduce infrastructure the project
has never used, into the two repositories that go untouched for months, to
detect a problem caused by those repositories going untouched for months. The
gate belongs where the motive is: main, at release.

### Pass injection points as individual callables

`check_backend(b, sent_sampling_params=..., stub_malformed=..., ...)` — six or
seven callables. Rejected: unreadable at the call site, and it gives the
sibling no typed target for pyright. ADR-0087 split `TokenCountingBackend` off
`LLMBackend` for the same reason. `BackendProbe` is two methods, and the
obvious accessors were deliberately not among them: `sent_messages()` would
bake a chat-messages array into the kit, which Anthropic (system outside the
array) and any completion-style backend do not have.

### Have the kit read `_circuit` directly

Moves the private coupling from three repositories to one, which is an
improvement, but the kit *is* shipped — a shipped module reading its own
package's privates is itself a hole in the contract, and it would freeze
`_CircuitBreaker`'s attribute names anyway.

### Observe circuit behavior black-box instead

Fail five times and check that the sixth short-circuits. Slow, and it conflates
"was this call counted as a failure" with "does the threshold work". The check
worth lifting is the former (a truncation drop must not increment the counter),
and only a reading expresses it.

### Make a `layers` contract entry instead of two `forbidden` ones

See Decision 3: it would permit `testing -> adapters`.

## Consequences

### Positive

- Cloud's three observed static failures are now *measured*. Running the kit
  from main today: `contemplative_agent_cloud.backends.anthropic:AnthropicBackend` and
  `...openai:OpenAIBackend` exit 1 naming `protocol.members`,
  `context_window.positive_int`, and `generate.binds_canonical_call`;
  `contemplative_agent_mlx.backends.mlx:MlxLmBackend` exits 0. The kit
  distinguishes the live sibling from the stale one on its first run.
- A contract change covered by a registered check produces a red at release
  instead of silence. Runtime return semantics remain deferred to the
  catalogued runtime stage.
- `T-CLOUD-SIBLING-STALE`'s open decision (archive / rewrite / minimal repair)
  gains concrete input: a named list of what is broken, rather than a
  recollection that something is.
- Sibling tests can drop their private `_circuit` reads.

### Negative

- **A contract change covered by a registered check now reddens three repositories at once.** This is
  intended for assertions *about the contract* — that redness is the missing
  notification, and one CI-equivalent run beats three months of silence. It is
  a pure cost for assertions about *implementation details*, which is what the
  authoring rule above exists to prevent. Recording the distinction here
  matters: without it the first red gets read as "the kit is brittle" and the
  kit gets removed.
- The shipped package grows a module that no production path uses. Cost
  accepted for the distribution property that is the whole point; the two
  forbidden contracts keep the direction honest.
- 23 of 29 checks are catalogued but not implemented. A sibling reaching only
  `LEVEL_STATIC` is checked far less thoroughly than the table suggests, and
  `expected_checks()` plus the implemented-level cap prevent that from being
  read as runtime or full coverage.
- The explicit release command executes code from adjacent sibling checkouts.
  The operator must treat those checkouts as trusted code; moving this command
  into routine Verify would silently widen the execution boundary.
- Freezing a shipped API creates migration cost. A breaking kit change requires
  a major-version boundary or a compatibility shim that accepts the old call;
  retiring the kit requires first removing sibling imports and the release-gate
  invocation. The wheel module cannot simply disappear while consumers still
  import it.

### Neutral / Follow-ups

- `_core_harness.py` was planned as a fourth module to isolate core-internal
  coupling. It is **not created** in this release: with no runtime checks
  landed it would have nothing in it, and an empty private module is worse than
  an absent one. It arrives with the runtime checks.
- The kit gives `T-FINISHREASON-GATE` a home. `reports_finish_reason` turns "a
  backend without truncation gating" from an accident into a declared fact,
  which is a cheaper resolution than the option (a) / (b) / (c) framing in that
  task.
- `contemplative-agent-otel` is absent from the related-repositories table in
  `CLAUDE.md`. It does not implement `LLMBackend`, so it is out of scope here
  and out of scope for the kit, but the omission is recorded.

### Provenance

The two premise corrections in Context — that cloud already had a conformance
test, and that `tests/` is not in the wheel — were found while planning this
change, and both inverted the task as originally written in the ledger
(`T-BACKEND-CONTRACT-KIT`, which described the goal as "export the kit the way
`tests/chaos.py` does"). The CI alternative was rejected on a fact discovered
mid-implementation. The conformance results quoted under Positive are from
running the shipped kit against the checked-out siblings on 2026-08-02, not
from inspection.

## References

- `ADR-0066` (`0066-backend-aware-context-budget-guard.md`) — depends-on; established the tolerate-absence discipline this kit checks
- `ADR-0087` (`0087-optional-token-counting-capability-for-the-context-budget-guard.md`) — depends-on; `TokenCountingBackend`, and the precedent for expressing an optional capability as a separate Protocol
- `ADR-0077` (`0077-chaos-tdd-fault-injection.md`) — precedent; `tests/chaos.py` is the pytest-free style this kit follows, and the cautionary case for distribution
- `ADR-0012` (`0012-human-approval-gate.md`) — precedent; placing the decision where a human already stands
- `ADR-0071` (`0071-read-only-pattern-composition-instruments.md`) — precedent; `circuit_reading()` as an instrument, not a mechanism
- `ADR-0001` (`0001-core-adapter-separation.md`) — the import-direction rule the two forbidden contracts extend
- `ADR-0079` (`0079-module-reorganization-package-splits.md`) — the facade re-export convention `contemplative_agent/testing/__init__.py` follows
- [`docs/runbooks/sibling-backend-conformance.md`](../runbooks/sibling-backend-conformance.md) — the release gate procedure

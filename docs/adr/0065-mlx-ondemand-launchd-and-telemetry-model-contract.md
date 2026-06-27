# ADR-0065: Wire mlx_lm.server as an On-Demand launchd Job and Enforce a Served-Model-ID Contract on LLM Telemetry

## Status

accepted

## Date

2026-06-27

## Context

[ADR-0064](./0064-mlx-generation-backend.md) introduced an opt-in MLX generation backend
(`mlx_lm.server` on `:8080`, selected via `LLM_BACKEND=mlx`), benchmarked at roughly 1.8×
faster and 3.4 GB lighter in resident memory than Ollama generation on the maintainer's
M1/16 GB host. Embeddings (`nomic-embed-text`) were left on Ollama (`:11434`) because
`mlx_lm.server` exposes no embedding endpoint. ADR-0064 explicitly deferred wiring the server
into the production launchd jobs — `agent.plist` (run sessions at 0, 6, 12, and 18 h) and
`distill.plist` (at 03:30), the two scheduled plists that drive the agent's real sessions —
as future work. Two gaps had to be closed before that wiring was safe.

**Gap 1 — telemetry model field.** The LLM call telemetry record written to
`~/.config/moltbook/logs/llm-calls-*.jsonl` derived its `model` field from a class-name
sentinel: whatever Python class was injected as the backend was rendered directly as the model
identifier. An MLX call would therefore log a string such as `"MlxLmBackend"` rather than the
real served model id. Operators auditing the log to determine which model served a particular
call could not trust the field, and the field's meaning differed between the Ollama and MLX
backends.

**Gap 2 — process lifecycle for mlx_lm.server.** Unlike Ollama, which the agent treats as an
always-on host daemon, `mlx_lm.server` is a separate process that must be explicitly managed.
The question was whether to run it as a resident `KeepAlive` launchd service alongside Ollama or
to start it on demand only for the duration of each scheduled job. On a 16 GB M1 the choice is
memory-pressure-critical: a resident server holds approximately 5.2 GB idle across the full day,
including the long stretches between the four spaced-out scheduled jobs. The agent does not pass
`keep_alive` to Ollama — a search of the codebase finds zero matching call sites — so Ollama
applies its default five-minute model unload and generation-model idle memory is already near zero
between jobs. A resident `mlx_lm.server` would therefore make idle memory strictly worse than the
current Ollama-default-unload baseline, directly contradicting ADR-0064's swap-mitigation
motivation.

Both gaps were closed together because production enablement required both: the telemetry fix
ships in commit `0f2b169` and the launchd wrapper in commit `9f230d8`.

## Decision

1. **Generalize the telemetry `model` field to a real served-model-id contract enforced through
   the `LLMBackend` Protocol.** Add a read-only `model` property to `LLMBackend` in
   [`core/llm.py`](../../src/contemplative_agent/core/llm.py). The `generate()` telemetry record
   now sets `model = _backend.model if _backend is not None else _get_model()`, so every backend
   reports its actual served model id rather than a class-name sentinel. `MlxLmBackend` already
   exposes `model: str` and required no change. The property is read-only specifically to remain
   compatible with `frozen=True` on `MlxLmBackend` — a writable data attribute would be rejected
   by pyright. All test doubles (`FakeBackend`, `StubBackend`, `_RaisingBackend`) were given a
   `model` value to satisfy the updated Protocol. (Commit `0f2b169`.)

2. **Run `mlx_lm.server` on demand via
   [`scripts/run-with-mlx.sh`](../../scripts/run-with-mlx.sh), invoked from the
   `ProgramArguments` of the existing `agent.plist` and `distill.plist`, rather than as a
   resident `KeepAlive` launchd service.** The wrapper starts `mlx_lm.server`, polls `/health`
   until ready (cold M1 model load ≈ 12 s, hard cap at 60 s), runs `contemplative-agent` with
   `LLM_BACKEND=mlx`, and kills the server via `trap EXIT` so the server's lifetime exactly
   matches the job. The wrapper deliberately does **not** `exec` the agent — doing so would
   prevent the `trap` from firing. It does **not** silently fall back to Ollama generation if
   the server fails to reach health within 60 s: `LLM_BACKEND=mlx` is the operator's explicit
   choice, and a silent fallback would mask a broken server; instead the cycle exits with an
   error and the next scheduled job retries. The agent path is resolved relative to the script
   location (`<repo>/.venv/bin/contemplative-agent`). No resident `mlx-server.plist` is
   created. The existing `ollama-restart.plist` (23:55) is kept untouched; Ollama is never
   stopped, as embeddings depend on it. (Commit `9f230d8`.)

## Alternatives Considered

### Resident KeepAlive mlx-server.plist

A dedicated launchd service keeps `mlx_lm.server` running at all times, eliminating the ≈ 12 s
cold-load cost on each job. Rejected because it holds approximately 5.2 GB idle across the full
day on a 16 GB host, making idle memory strictly worse than the current baseline where Ollama's
five-minute default unload brings generation-model idle memory near zero between jobs. This
directly contradicts ADR-0064's swap-mitigation motivation; the cold-load cost is negligible
against the 6-hourly run-session cadence.

### Keep the class-name sentinel for the telemetry model field

No code change to the telemetry record; the backend class name remains the `model` value.
Rejected because operators cannot determine which model actually served a call, and the field's
meaning differs per backend, undermining the audit utility of `llm-calls-*.jsonl`.

### getattr-based model lookup instead of a Protocol property

Read the model id opportunistically via `getattr(backend, "model", ...)` without adding a
property to the `LLMBackend` Protocol. Rejected in favor of an explicit read-only Protocol
property so the obligation is type-checked and any future backend must satisfy it at definition
time rather than at runtime.

### Silent fallback to Ollama generation when mlx_lm.server fails to start

If `mlx_lm.server` does not reach health within 60 s, continue the cycle using Ollama
generation rather than aborting. Rejected because it hides a broken MLX server behind a
superficially successful run and silently violates the operator's explicit `LLM_BACKEND=mlx`
choice. Exiting with an error and waiting for the next scheduled job surfaces the failure
transparently.

## Consequences

### Positive

- Telemetry records the real served model id for every backend; operators can audit which model
  served each call in `llm-calls-*.jsonl`.
- The `model` contract is type-enforced via the `LLMBackend` Protocol; any future backend must
  expose its served model id.
- Idle memory between scheduled jobs is near zero (`mlx_lm.server` unloaded by `trap EXIT`),
  strictly no worse than the Ollama-default-unload status quo at every hour of the day.
- Memory during generation remains lighter (≈ 5.2 GB vs ≈ 8.6 GB), preserving the swap-relief
  benefit from [ADR-0064](./0064-mlx-generation-backend.md).
- Fully reversible: revert each plist's `ProgramArguments` to the direct `contemplative-agent`
  invocation and reload to return to Ollama generation; removing the wrapper and `mlx-lm`
  eliminates the backend entirely. Ollama is never stopped.

### Negative

- Each scheduled job pays a ≈ 12 s `mlx_lm.server` cold-load before generation begins.
- If `mlx_lm.server` fails to reach health within 60 s, that scheduled cycle is skipped entirely
  with no fallback; the next scheduled job retries.
- Two LLM servers now exist in the operational model — `mlx_lm.server` on demand for generation
  and Ollama resident for embeddings — increasing the number of moving parts an operator must
  reason about.

### Neutral / Follow-ups

- This ADR closes the "launchd plist is future work" item noted in the
  [ADR-0064](./0064-mlx-generation-backend.md) `### Negative / Risks` section.
- The distill pattern-yield adoption gate from [ADR-0064](./0064-mlx-generation-backend.md) — a
  dry-run comparison of mlx vs Ollama output over a live episode window — remains an open
  verification item; this ADR does not resolve it.

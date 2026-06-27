# ADR-0067: Keep Ollama as the Production Generation Backend — mlx_lm.server Is Unfit for Unattended Continuous Use on 16 GB Apple Silicon

## Status

accepted — partially-supersedes ADR-0065 (launchd-wiring portion; the served-model-id telemetry contract is retained)

## Date

2026-06-28

## Context

[ADR-0064](./0064-mlx-generation-backend.md) added an opt-in MLX generation backend
(`mlx_lm.server` on `:8080`, `LLM_BACKEND=mlx`), benchmarked ~1.8x faster and ~3.4 GB
lighter than Ollama generation on the maintainer's M1 / 16 GB host.
[ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) then wired that
backend into the two production launchd jobs — `agent.plist` (sessions at 0, 6, 12, 18 h)
and `distill.plist` (03:30) — on demand via `scripts/run-with-mlx.sh`, and generalized the
LLM telemetry `model` field into a served-model-id contract on the `LLMBackend` Protocol.
[ADR-0066](./0066-backend-aware-context-budget-guard.md) added a backend-aware
context-budget guard (MLX `context_window = 32768`).

A full-day production A/B on **2026-06-27 (M1 / 16 GB)** is decisive. Because ADR-0065
made the telemetry record the *real* served model id, the outcome breakdown is directly
recomputable from `~/.config/moltbook/logs/llm-calls-2026-06-27.jsonl`:

| backend | calls | ok | circuit_open | error | truncated |
|---|---|---|---|---|---|
| MLX (`mlx-community/Qwen3.5-9B-4bit` via mlx_lm.server) | **21,224** | **107 (0.50%)** | 21,060 (99.2%) | 53 | 4 |
| Ollama (`qwen3.5:9b`), 18-day baseline 06-09..06-26 | ~200–270 / day | **≈100%** | ~0 | ~0 | rare |

The model **loaded and ran** — 21k logged calls from the real model id prove it; the
failure is **runtime degradation, not a load failure**. The hourly profile shows the
shape: the first ~81 MLX calls (00:00–01:00 UTC) were 100% ok — the server loads and
works — then it collapses; the **09:00-UTC hour alone logged 19,520 attempts with 2 ok**,
a circuit-open + reactive-retry spin. By contrast Ollama, in the same harness across the
surrounding 18 days, essentially never trips the circuit breaker.

Root cause: **mlx_lm.server has no graceful out-of-memory degradation.** A Metal OOM
aborts the process or wedges generation rather than returning an error (the mlx-lm
[#854](https://github.com/ml-explore/mlx-lm/issues/854) /
[#883](https://github.com/ml-explore/mlx-lm/issues/883) class), which trips the agent's
circuit breaker; the breaker opens and the reactive retry path spins. Two mechanisms
compound it on 16 GB:

- **Non-linear prefill cliff.** In `mlx-server.log`, the same ~7.5k-token prompt prefilled
  in **72 s right after load, then 58 min eleven minutes later** (~75x) on the *same*
  process — only the memory situation changed. MLX's Metal allocations are wired /
  non-swappable, so under memory compression there is no graceful page-out, unlike Ollama's
  mmap'd (file-backed, pageable) GGUF. A Metal OOM abort at 18:13 UTC (prefill stopped at
  587/930) was also observed.
- **Prompt-cache churn.** The ~7.6k all-injected system prefix is evicted under
  `--prompt-cache-size 2` as reply / comment / score / internal_note user prompts rotate,
  so most generations pay a full cold prefill and absorb the cliff in full.

A standalone survey of the upstream mlx-lm failure modes
([evidence](../evidence/adr-0067/mlx-production-suitability-survey-2026-06.md)) reaches the
same conclusion. Two of its caveats do **not** apply here and are explicitly resolved so
they are not frozen into this record: (a) the "`qwen3_5` is a multimodal VLM that fails to
load in mlx_lm.server" caveat is contradicted by 21k logged calls from the real model id —
the text model loaded fine; (b) truncation framed as an MLX EOS-runaway is contradicted by
the local `verify_solve` A/B, which found MLX truncation was n=5 noise and a solver-design
property, not MLX-specific (see
[evidence](../evidence/adr-0067/a-b-telemetry-2026-06-27.md)). This ADR therefore rests on
the circuit-breaker cascade, not on truncation.

## Decision

1. **Production generation backend is Ollama (`qwen3.5:9b`).** The ADR-0065 launchd wiring
   (`agent.plist` / `distill.plist` routed through `scripts/run-with-mlx.sh`) is reverted to
   the direct `contemplative-agent` invocation (commit `b888840`, 2026-06-28). Embeddings
   remain on Ollama, unchanged.

2. **Retain the ADR-0065 served-model-id telemetry contract.** It is backend-neutral and is
   the instrument that produced this decision's evidence; only the launchd-wiring half of
   ADR-0065 is superseded.

3. **Keep the MLX backend code and every opt-in entry point** (`LLM_BACKEND=mlx`,
   `/agent-run … mlx`, `scripts/serve-mlx.sh`). Nothing is deleted. MLX stays a valid choice
   for **interactive / manual / short-lived** generation, where an operator is present and
   the session does not run long enough to reach the degradation cliff.

4. **Scope the unfitness claim** to *16 GB Apple Silicon + `Qwen3.5-9B-4bit` + unattended
   continuous operation*. It is deliberately **not** generalized to "mlx_lm.server is unfit
   for production": the decisive evidence is configuration-specific, and the upstream issues
   that make it unsafe here are open but model-, host-, and load-dependent.

## Alternatives Considered

### Mitigate and keep MLX wired into production

Apply the documented mitigations — explicit `stop` tokens, `--prompt-cache-bytes`, raise
`--prompt-cache-size` to hold the system prefix, lower the MLX wired limit, bypass the
server with in-process `mlx_lm.generate`, or move to 8-bit. Rejected for now. Each is
symptomatic; the load-bearing root (no graceful OOM degradation → process death →
circuit-breaker spin) is upstream-unfixed —
[#615](https://github.com/ml-explore/mlx-lm/issues/615) (no kv-size flag),
[#854](https://github.com/ml-explore/mlx-lm/issues/854) /
[#883](https://github.com/ml-explore/mlx-lm/issues/883) (OOM aborts), all **OPEN**. 8-bit
roughly doubles the weights with no headroom on a 16 GB host; bf16 (~18 GB) does not fit.
None is worth the unattended-production risk when Ollama already runs clean.

### State the claim broadly ("mlx_lm.server is unfit for production")

Rejected. The evidence is config-specific; an over-broad claim is brittle — it would be
falsified by interactive use, a larger-RAM host, or a standard GQA text model — and reifies
a contingent result into a rule, against the Emptiness axiom (hold objectives lightly,
revise on new context).

### Delete the MLX backend code

Rejected. Opt-in MLX is reversible and genuinely useful for manual / interactive work;
ADR-0064's benchmark (~1.8x faster, ~3.4 GB lighter) still holds for short sessions. Keeping
the code costs nothing and preserves the re-evaluation path below.

### Switch production to a smaller MLX model to fit 16 GB headroom

Out of scope. A model downgrade trades output quality for a backend that still lacks
graceful OOM handling; local-model-swap experiments were already declined on quality
grounds.

### Cloud generation backend (`contemplative-agent-cloud`)

A separate, opt-in path that relaxes security-by-absence for research only. Not the
production default and out of scope for this ADR.

## Consequences

### Positive

- Production is stable on Ollama (already reverted); the post-revert baseline shows the
  clean ≈100%-ok pattern with the circuit breaker effectively never tripping.
- The decision is reversible and self-instrumented: the retained telemetry contract will
  re-measure any future MLX re-trial against the same metric.
- MLX stays opt-in; an operator can still `LLM_BACKEND=mlx` / `/agent-run … mlx` for
  interactive runs, keeping ADR-0064's speed/memory win available where it is safe.

### Negative / Neutral

- ADR-0065's launchd-wiring half is superseded; its served-model-id telemetry contract
  remains in effect. ADR-0064 (opt-in backend) and ADR-0066 (context guard) are unchanged
  and still apply to opt-in MLX use.
- The "two LLM servers in the operational model" complexity from ADR-0065 is gone for
  production (only Ollama runs); it returns only for opt-in MLX sessions.

### Reversal thresholds

Revisit MLX for *unattended* production only when **all** of these hold:

1. `mlx_lm.server` gains a bounded KV / `--max-kv-size` (mlx-lm
   [#615](https://github.com/ml-explore/mlx-lm/issues/615) /
   [#884](https://github.com/ml-explore/mlx-lm/issues/884) merged) so a fixed-context job
   cannot grow the cache into OOM.
2. The OOM-abort issues
   ([#854](https://github.com/ml-explore/mlx-lm/issues/854) /
   [#883](https://github.com/ml-explore/mlx-lm/issues/883)) are resolved so a Metal OOM
   returns an HTTP 5xx and the process survives without a kernel panic.
3. A 24-hour / tens-of-thousands-of-calls run on the target host holds error and truncation
   rates at Ollama parity (≈0).

Until all three hold, Ollama stays the production generation backend.

## References

- [ADR-0064](./0064-mlx-generation-backend.md) — opt-in MLX backend; unchanged, still valid for opt-in / interactive use
- [ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) — partially-superseded-by this ADR (launchd wiring reverted; telemetry contract retained)
- [ADR-0066](./0066-backend-aware-context-budget-guard.md) — backend-aware context guard; unchanged
- [ADR-0007](./0007-security-boundary-model.md) — reversibility posture (clearing one env var / reverting one plist returns to the safe default)
- Evidence: [docs/evidence/adr-0067/](../evidence/adr-0067/) — A/B telemetry, prefill degradation, upstream failure-mode survey
- mlx-lm upstream issues (OPEN as of 2026-06): [#615](https://github.com/ml-explore/mlx-lm/issues/615), [#854](https://github.com/ml-explore/mlx-lm/issues/854), [#883](https://github.com/ml-explore/mlx-lm/issues/883)

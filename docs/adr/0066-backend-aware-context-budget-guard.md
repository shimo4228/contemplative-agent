# ADR-0066: Backend-Aware Context-Budget Guard via an `LLMBackend.context_window` Contract

## Status

accepted

## Date

2026-06-27

## Context

The MLX backend fix session ([commits `ebc227e` / `30f7e39` / `b3d0599`]) closed a sampler-omission
bug: the MLX payload sent only `temperature` and dropped `top_p`/`top_k`, so at the outward
`COMMENT_TEMPERATURE=1.3` the Qwen3.5-9B model degenerated into repetition loops that never emit EOS
and ran to `num_predict`, blocking posting and driving the 16 GB host into swap. The fix extracted
`SAMPLING_TOP_P`/`SAMPLING_TOP_K` to a single source of truth in
[`core/llm.py`](../../src/contemplative_agent/core/llm.py) that both the built-in Ollama path and the
injected `MlxLmBackend` import.

This ADR records the follow-up **parameter-parity audit**: a sweep of every generation parameter for
any *other* drift between the Ollama path (`_post_ollama`) and the MLX backend (`MlxLmBackend.generate`).
The audit's only finding requiring a code change was `num_ctx`.

**The gap — the injected-backend path bypasses the context-budget guard.** `core/llm.py` carries a
token-budget pre-flight (audit C2): if the estimated `system + prompt + num_predict` exceeds the
context window, the call is skipped (returns `None`) rather than sent, because Ollama would otherwise
silently front-truncate the system prompt's value layer (identity / axioms). But the guard sat *after*
the backend dispatch — `_generate_impl` ran `if _backend is not None: return _generate_via_backend(...)`
and only reached the guard on the `_backend is None` (Ollama) path. Injected backends (MLX, and the
sibling `contemplative-agent-cloud`) were never guarded.

For MLX this is a live hole, not a theoretical one. `mlx_lm.server` exposes **no** context / kv-size
flag (Apple `ml-explore/mlx-lm` issue #615 is open) and does **not** front-truncate an over-window
prompt — it grows the KV cache until the host swaps / OOMs. Qwen3.5-9B's native window is 262144
(`Qwen/Qwen3.5-9B` `config.json`), but the practical ceiling on a 16 GB M1 (≈ 5 GB weights, KV cache
bounded by `--prompt-cache-size 2`) is **memory-bounded at roughly 32k tokens**, not the model's
trained window. The over-window failure mode is therefore exactly the swap incident the MLX work set
out to prevent.

A **Phase 0 external-research pass** (`/search-first` → scout) studied how mature libraries handle
"backend capability non-uniformity": LiteLLM's `drop_params` + `get_supported_openai_params` +
`model_prices_and_context_window.json` registry (`get_max_tokens`), and LlamaIndex's per-object
`LLMMetadata.context_window` property. A prior session had tentatively agreed to thread a
`GenerationParams` DTO (`temperature`/`top_p`/`top_k`/`num_predict`/`format`) through the
`LLMBackend.generate()` Protocol to "share sampling policy across all backends." The audit plus the
research showed this is the wrong abstraction: `top_p=0.95`/`top_k=20` are Qwen3.5-specific tuning
values, and the universal Protocol is also implemented by the cloud backend, which would then be handed
Qwen's `top_k` (OpenAI does not support `top_k` at all). Sampler policy is a *model-identity* concern,
not a *provider-capability* concern.

## Decision

1. **Add a read-only `context_window: int` to the `LLMBackend` Protocol**, parallel to the `model`
   property from [ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md).
   `MlxLmBackend` declares `context_window = 32768` — memory-bounded on the 16 GB host, **not** the
   model's 262k native window — as a dataclass field (a value field satisfies the Protocol property,
   the same shape used for `model`). A cloud backend reports its provider's real limit.

2. **Make the budget guard backend-aware and move it before the dispatch.** `_generate_impl` now
   computes `ctx_window = getattr(_backend, "context_window", None) if _backend is not None else NUM_CTX`
   and runs the pre-flight first; an over-window estimate skips the call (`outcome="budget_exceeded"`)
   for *any* backend, before the HTTP request. A backend that omits the property falls back to `None`
   → unguarded → still delegates, so a not-yet-updated external backend keeps working (graceful
   degrade). The `getattr` uses a `None` sentinel (not a falsy default), so the check is unambiguous.

3. **Keep the sampler policy (`top_p`/`top_k`) as shared module constants, not Protocol parameters.**
   The audit confirms `SAMPLING_TOP_P`/`SAMPLING_TOP_K` — imported by the two local backends serving
   Qwen — are the correct seam: model-local sampling shared exactly where the same model is served, and
   never imposed on a cloud backend (which is not handed them, since they are not `generate()`
   parameters). The `GenerationParams`-through-Protocol idea is explicitly rejected.

4. **Borrow the capability-window pattern; do not adopt LiteLLM.** The Phase 0 verdict was Build: all
   three backends already speak OpenAI-compatible HTTP, so LiteLLM's dominant value (provider-format
   translation) is redundant here; its context-window registry has no local-model entries (each would
   need a manual `register_model`, i.e. the same dict by hand); and its ~28 MB / 12-core-dependency
   footprint is disproportionate to a capability that reduces to a handful of lines. The
   LlamaIndex-style "window co-located on the backend object" is borrowed verbatim in spirit.

The audit's full parity result (no code change for these): `temperature` reaches every backend
per-call (parity OK); `num_predict` maps to `max_tokens` on MLX (parity OK); `format` is an intentional
difference (Ollama native vs MLX prompt-injection, [ADR-0064](./0064-mlx-generation-backend.md)); think
is off on both via different mechanisms (`think:False` vs `enable_thinking:False`, parity OK).

5. **Harden `_estimate_tokens` to a genuine upper bound in both character classes.** Because the guard
   is now load-bearing for the MLX path, its tokenizer-free estimate must not under-count: non-ASCII /
   CJK is now counted at 2 tokens/char (Qwen3.5's real cost is ~1.5-2), where it previously counted 1
   and under-estimated CJK by 33-50% — enough for a CJK-heavy prompt (the agent reads untrusted external
   content, which may be Japanese / Chinese) to slip past the guard into the very front-truncation / KV
   OOM it exists to prevent. ASCII stays at ~3 chars/token. This is the safe (over-estimating) direction
   for a skip guard and aligns the function with its documented "conservative upper bound" contract.
   `MlxLmBackend` also now rejects a non-positive `context_window` at construction (a zero window would
   skip every call — a silent generation blackout), matching the existing fail-fast URL validation.

## Alternatives Considered

### Thread a `GenerationParams` DTO (incl. `top_p`/`top_k`) through `LLMBackend.generate()`

The prior-session direction. Rejected: it would impose Qwen-specific sampler values on cloud backends
(OpenAI has no `top_k`), change the cloud backend's `generate()` signature, and conflate a
model-identity concern with the universal interface. The acute `top_p`/`top_k` drift was already closed
by sharing constants (`30f7e39`); no Protocol change is needed to prevent its recurrence between the two
local backends, and a Protocol change would actively introduce a new, semantically wrong coupling for
cloud.

### Adopt LiteLLM as the multi-backend abstraction

Rejected: redundant format translation (every backend is already OpenAI-shaped or has its own native
adapter), no local-model entries in its context-window registry (manual `register_model` either way),
and a disproportionate dependency footprint (~28 MB, `tiktoken`/`tokenizers`/`openai`/`pydantic`/…)
against a need that is a few dicts and functions.

### A static per-(backend, model) context-window registry table

A module-level table mapping `(backend, model) → window`, separate from the backend object. Rejected in
favor of co-locating the window on the backend object — which alone knows its own host constraints —
matching the existing `model` property and the LlamaIndex `LLMMetadata.context_window` pattern.

### Set the window server-side on `mlx_lm.server`

Rejected as impossible: `mlx_lm.server` exposes no context / kv-size startup flag (issue #615;
`--max-tokens` caps generation length, not context). The client-side pre-flight is the only available
lever.

### Leave the MLX path unguarded (status quo)

Rejected: an over-window prompt grows the MLX KV cache until the 16 GB host swaps / OOMs — the exact
failure the MLX work set out to prevent. The injected-backend exclusion was a deliberate "unknown
window" choice when only a hypothetical cloud backend existed; the in-repo MLX backend makes the window
knowable and the hole concrete.

## Consequences

### Positive

- The MLX backend (and any window-declaring backend) is now budget-guarded: an over-window prompt is
  skipped before the HTTP call, preventing the KV-cache OOM / swap.
- `context_window` is type-enforced via the `LLMBackend` Protocol; future backends declare their real
  serving ceiling, the same way `model` made the served-model-id explicit.
- Sampler policy stays model-local; a cloud backend is never handed Qwen-specific `top_k`/`top_p`.
- Zero new dependencies; the capability-window pattern is a handful of lines borrowed from the
  LiteLLM / LlamaIndex research rather than a 28 MB dependency.
- Fully reversible: the backend is env-gated (`LLM_BACKEND`), and the guard degrades to the prior
  behavior for any backend that omits the property.

### Negative

- `context_window` is a Protocol contract change: every `LLMBackend` implementer must declare it. The
  in-repo backend and all test doubles (`FakeBackend`, the in-test stubs) were updated; the sibling
  `contemplative-agent-cloud` backend must add a one-line property to gain the guard. Until it does, an
  omitting backend is silently unguarded — acceptable because cloud context windows are large, but it
  is a real "update both repos" obligation.
- The MLX window value (32768) is a host-memory heuristic, not a measured hard limit; a larger-RAM host
  could safely use more, and the value is not yet auto-derived from available memory.

### Neutral / Follow-ups

- The sibling `contemplative-agent-cloud` backend should add `context_window` (returning its provider's
  context limit) to gain the guard; tracked as a follow-up, not done here.
- Task 2 from the same handoff — the `verify_solve` ~13% truncation, common to both backends and
  fail-closed — is unrelated to parity and remains deferred.

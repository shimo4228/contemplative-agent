# ADR-0064: Route Generation Through a Local mlx_lm.server on Apple Silicon

## Status

accepted

## Date

2026-06-27

## Context

The agent's default LLM transport is the built-in Ollama HTTP path in
[`core/llm.py`](../../src/contemplative_agent/core/llm.py), which talks to a local
Ollama daemon (`/api/generate` for text, `/api/embed` for embeddings). On the
maintainer's primary host — an M1 Mac with 16 GB of unified memory — the production
model `qwen3.5:9b` (Q4_K_M, 6.6 GB on disk, ~8.6 GB resident with KV cache) routinely
pushes the machine into swap, and decode runs slowly.

A controlled benchmark on that exact host ([evidence](../evidence/adr-0064/benchmark-ollama-vs-mlx.md))
compared the *same* Qwen3.5 9B weights under two runtimes, with thinking off,
temperature 0, a 256-token cap, and a 3-run median:

| metric | Ollama (Metal / GGUF Q4_K_M) | mlx_lm.server (MLX 4bit) |
|---|---|---|
| generation speed | 6.8–7.0 tok/s | 12.1–12.7 tok/s (**~1.8x**) |
| resident / peak memory | 8.6 GB | 5.2 GB (**−3.4 GB**) |

The speed gap was confirmed intrinsic, not a swap-pressure artifact: re-measuring
Ollama under low swap still yielded ~7 tok/s. Apple's MLX runtime is the faster path
on Apple Silicon, and its smaller footprint is what relieves the swap pressure on a
16 GB machine.

Three facts constrain how the runtime can be adopted:

1. **mlx_lm.server is generation-only.** It exposes the OpenAI
   `/v1/chat/completions` shape but has **no embeddings endpoint** and **no
   token-constrained structured-output mode** (no Ollama `format=` / OpenAI
   `response_format`). Embeddings (`nomic-embed-text`) must stay on Ollama.
2. **It cannot run in a container on Apple Silicon** — Docker has no Metal GPU
   passthrough — so it runs on the host, not inside the
   [ADR-0006](./0006-docker-network-isolation.md) network-isolated compose stack.
3. **`format=` is used by exactly one call site**, `distill._distill_one`
   (`{"patterns": [...]}`), which already has a JSON→bullet fallback in
   `_parse_refined_patterns`.

The agent already exposes an `LLMBackend` Protocol with a `configure(backend=...)`
injection seam (added for a hypothetical cloud backend), so generation can be
re-routed without touching any of the ~12 call sites.

## Decision

Add an opt-in **MLX generation backend** that routes *generation only* through a
local `mlx_lm.server`, keeping embeddings on Ollama.

1. **`core/mlx_backend.py` — `MlxLmBackend(LLMBackend)`**: POSTs to
   `{MLX_BASE_URL}/v1/chat/completions`, maps the OpenAI response onto a
   `BackendResult`, sets thinking off per request via
   `chat_template_kwargs={"enable_thinking": false}` (parity with the Ollama
   `think:false` default), and renders a `format` schema into a prompt instruction
   (mlx_lm.server has no native structured output; the distill JSON→bullet fallback
   absorbs any drift).

2. **`LLMBackend` Protocol extended** in `core/llm.py`: `generate()` now takes a
   keyword `temperature` and returns an `Optional[BackendResult]`
   (`text` + `finish_reason` + `eval_count`) instead of `Optional[str]`. This lets
   the injected path honor per-call temperature (0.0 for deterministic verification,
   1.3 for outward generation) and lets the **caller** — not the backend — apply the
   `drop_truncated` fail-closed gate (audit M2) from `finish_reason`, with the same
   circuit-success-on-deliberate-drop accounting as the Ollama path.

3. **Opt-in via env** in the `cli.py` composition root: `LLM_BACKEND=mlx` injects
   `MlxLmBackend(MLX_BASE_URL, MLX_MODEL)`. Unset or any other value keeps the default
   Ollama generation path, so the switch reverts by clearing one env var.

4. **Embeddings unchanged**: `OLLAMA_BASE_URL` (default `:11434`) still serves
   `nomic-embed-text`. The MLX host reuses the existing `OLLAMA_TRUSTED_HOSTS`
   SSRF allowlist via the shared `validate_trusted_url()` guard; `localhost:8080`
   passes without configuration (the port is not part of the host check).

The target topology is two host-local LLM services: mlx_lm.server (generation,
`:8080`, ~5.2 GB) and Ollama (embeddings, `:11434`, `nomic-embed-text` ~0.3 GB).
`scripts/serve-mlx.sh` starts the server; `mlx-lm` is run via `uvx` / `uv tool` and
is **not** a project dependency — the agent only makes HTTP calls, so `pyproject.toml`
stays `requests` + `numpy`.

## Alternatives Considered

### Repoint `OLLAMA_BASE_URL` to mlx_lm.server (config-only)

Rejected. Generation and embeddings share `_get_ollama_url()`, so repointing the base
URL would send embedding requests to mlx_lm.server, which has no `/api/embed`
endpoint, breaking distill/retrieval. Backend injection leaves the embedding URL
untouched.

### Keep `format`-constrained distill on Ollama (auto-fallback)

Considered and deferred. The backend could route the one `format=` call site back to
Ollama to preserve token-level JSON constraint. Rejected for the initial cut because
distill-on-Ollama is exactly the 8.6 GB path that swaps hardest on 16 GB; routing
distill to mlx is what fixes the maintainer's original pain. The simple
`{"patterns": [...]}` schema plus the existing bullet fallback make prompt-level JSON
adequate. Adoption is gated on a pattern-yield comparison (see Consequences); if yield
drops materially, distill can be reverted to Ollama via env without code change.

### Run mlx in a container

Rejected. Apple Silicon Docker has no Metal passthrough, so an in-container MLX runtime
would fall back to slow CPU inference. mlx_lm.server runs on the host; the
[ADR-0006](./0006-docker-network-isolation.md) isolation model still applies to the
Ollama service.

### Make it the default (non-opt-in)

Rejected. The MLX path is host- and platform-specific (Apple Silicon, a separately
managed server process). A default-Ollama / opt-in-MLX gate keeps the zero-config path
working everywhere and makes the switch trivially reversible, consistent with the
reversibility posture in [ADR-0007](./0007-security-boundary-model.md).

## Consequences

### Positive

- ~1.8x faster generation and ~3.4 GB lower memory on the maintainer's M1/16 GB host,
  for the same model — directly relieving the swap pressure that motivated this.
- No call-site changes: all ~12 generation callers route through the injected backend
  unchanged. `temperature` and `drop_truncated` now apply uniformly across both
  transports (previously the injected path silently dropped temperature).
- Fully reversible: clearing `LLM_BACKEND` restores Ollama generation. A
  mlx_lm.server crash trips the existing circuit breaker and the operator can revert.
- Security guard hardened in passing: `validate_trusted_url()` now also rejects
  non-HTTP schemes and is shared by both transports; the Ollama path gained
  `allow_redirects=False` for parity.

### Negative / Risks

- **Two services to run.** The host must keep both mlx_lm.server (generation) and
  Ollama (embeddings) up. Operational glue (`scripts/serve-mlx.sh`; a launchd plist
  is future work).
- **No token-constrained structured output** on the MLX path. distill relies on a
  prompt instruction plus its JSON→bullet fallback. Adoption for distill is gated on
  a dry-run pattern-yield comparison (mlx vs Ollama over the same episode window); the
  env gate lets distill fall back to Ollama if yield regresses.
- **Quantization is not byte-identical** (GGUF Q4_K_M ≠ MLX 4bit), so output quality
  may differ subtly from the Ollama baseline. Out of scope for this ADR (speed/memory
  only); `mlx-community/Qwen3.5-9B-OptiQ-4bit` (mixed precision, closer to Q4_K_M) is
  a follow-up if quality drift appears.

### Verification

- Highest-stakes path confirmed: the verification challenge solver (temperature 0,
  `drop_truncated=True`, gates publishing) solved correctly through the MLX backend
  end-to-end.
- 21 new unit/integration tests (`tests/test_mlx_backend.py`); full suite green;
  python-reviewer and security-reviewer both PASS with no CRITICAL/HIGH.
- distill dry-run over a live episode window runs on MLX without swap thrashing
  (observed swap stayed low vs the Ollama-distill baseline) — the pattern-yield
  comparison is the explicit adoption gate for keeping distill on MLX.

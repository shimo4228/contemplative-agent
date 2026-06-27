# Distill yield A/B — MLX vs Ollama (ADR-0064 adoption gate)

The one risk in routing distill to MLX is that mlx_lm.server has no
token-constrained structured output (no Ollama `format=`), so `distill._distill_one`
falls back from JSON-schema constraint to a prompt instruction (`MlxLmBackend`
renders the schema into the prompt) plus the existing JSON→bullet fallback in
`distill._parse_refined_patterns`. This A/B measures whether that degrades pattern
yield or reliability.

Same episode window (`distill --dry-run --days 2`, 40 engagement episodes),
same model weights (Qwen3.5 9B), 2026-06-27, M1 / 16 GB.

| metric | MLX (4bit, prompt-JSON) | Ollama (GGUF Q4_K_M, `format=` constraint) |
|---|---|---|
| episodes processed | 40 | 40 |
| total patterns | **105** | **95** |
| patterns / episode | 2.63 | 2.38 |
| rejected (quality gate) | 0 | 0 |
| **JSON→bullet fallbacks** | **0** | **0** |
| LLM None failures | 0 | 0 |

## Verdict

The adoption gate passes. Routing distill to MLX does **not** degrade yield: pattern
count is equal-or-higher (105 vs 95, +10.5%) with **identical reliability** — zero
bullet fallbacks and zero failures on both paths. The simple `{"patterns": [...]}`
schema plus prompt instruction is as robust as Ollama's token-level constraint for
this task; the bullet fallback never fired.

## Caveats

- Pattern *count* is a coarse proxy. The slightly higher MLX count is not necessarily
  "better" output — it may reflect benign verbosity / quantization differences (GGUF
  Q4_K_M ≠ MLX 4bit), not higher quality. Semantic quality was not deep-assessed; if
  drift appears in practice, `mlx-community/Qwen3.5-9B-OptiQ-4bit` (mixed precision,
  closer to Q4_K_M) is the follow-up.
- `--dry-run` is idempotent (no episode-log writes), so both runs processed the same
  40 episodes — a fair comparison.
- Reversible regardless: clearing `LLM_BACKEND` returns distill to Ollama with no code
  change.

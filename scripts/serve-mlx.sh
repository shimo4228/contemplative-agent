#!/bin/bash
# Start a local mlx_lm.server for the MLX generation backend (Apple Silicon).
#
# Pairs with LLM_BACKEND=mlx (see .env.example, ADR-0064): the agent POSTs
# generation to this server's OpenAI /v1/chat/completions endpoint while
# embeddings stay on Ollama. mlx-lm is NOT a project dependency (the agent
# only makes HTTP calls); it is run here via uvx so pyproject.toml stays
# requests+numpy only. Install once for a persistent server with:
#   uv tool install mlx-lm
# then replace `uvx --from mlx-lm` below with `mlx_lm.server`.
#
# Usage: scripts/serve-mlx.sh [PORT] [MODEL]
set -euo pipefail

PORT="${1:-${MLX_PORT:-8080}}"
MODEL="${2:-${MLX_MODEL:-mlx-community/Qwen3.5-9B-4bit}}"

echo "Starting mlx_lm.server: model=$MODEL port=$PORT (thinking off)"
exec uvx --from mlx-lm mlx_lm.server \
  --model "$MODEL" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --chat-template-args '{"enable_thinking": false}'

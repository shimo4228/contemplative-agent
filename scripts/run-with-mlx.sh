#!/bin/bash
# On-demand mlx_lm.server lifecycle for the MLX generation backend (ADR-0064/0065).
#
# Wraps a contemplative-agent generation command: start mlx_lm.server, wait for
# /health, run the agent with LLM_BACKEND=mlx, then kill the server via
# `trap EXIT` so the server's lifetime matches the job's. Idle memory stays ~0
# (server unloaded between jobs), which is why on-demand beats a resident
# KeepAlive server on a 16 GB host — see ADR-0065. Embeddings stay on Ollama
# (a separate always-on daemon); this wrapper manages only the mlx server.
#
# Usage (invoked from a launchd plist's ProgramArguments):
#   run-with-mlx.sh <contemplative-agent args...>
#   e.g. run-with-mlx.sh -v --auto run --session 60
#        run-with-mlx.sh distill --days 1
set -euo pipefail

PORT="${MLX_PORT:-8080}"
MODEL="${MLX_MODEL:-mlx-community/Qwen3.5-9B-4bit}"
SERVER="$HOME/.local/bin/mlx_lm.server"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT="$(dirname "$SCRIPT_DIR")/.venv/bin/contemplative-agent"
LOG="$HOME/.config/moltbook/logs/mlx-server.log"

"$SERVER" --model "$MODEL" --host 127.0.0.1 --port "$PORT" \
  --chat-template-args '{"enable_thinking": false}' >>"$LOG" 2>&1 &
MLX_PID=$!
# Kill the server on any exit (success, failure, or signal) so it never
# outlives the job. Do NOT `exec` the agent below, or this trap won't fire.
trap 'kill "$MLX_PID" 2>/dev/null || true' EXIT

# Wait for the model to load (cold M1 load ~12s; cap at 60s). If it never comes
# up, skip this cycle — the next scheduled job retries. We deliberately do NOT
# fall back to Ollama generation: LLM_BACKEND=mlx is the operator's explicit
# choice, and a silent fallback would mask a broken server.
ready=
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ -z "$ready" ]; then
  echo "run-with-mlx: mlx_lm.server health timeout on :$PORT — skipping cycle" >&2
  exit 1
fi

export LLM_BACKEND=mlx
"$AGENT" "$@"

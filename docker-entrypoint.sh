#!/usr/bin/env bash
set -euo pipefail

MODE="${MODE:-loop}"
SESSION_MINUTES="${SESSION_MINUTES:-30}"
BREAK_MINUTES="${BREAK_MINUTES:-5}"

# Validate AUTONOMY against known-safe values
case "${AUTONOMY:-}" in
    --auto|--guarded|--approve|"") ;;
    *) echo "ERROR: Invalid AUTONOMY value: ${AUTONOMY}" >&2; exit 1 ;;
esac

# Build command args as an array (safe from word-splitting)
CMD_ARGS=()
if [ -n "${RULES_DIR:-}" ]; then
    CMD_ARGS+=(--rules-dir "${RULES_DIR}")
fi
if [ -n "${AUTONOMY:-}" ]; then
    CMD_ARGS+=("${AUTONOMY}")
fi

wait_for_ollama() {
    local url="${OLLAMA_BASE_URL:-http://ollama:11434}"
    local max_attempts=60
    local attempt=0
    echo "Waiting for Ollama at ${url}..."
    while ! curl -sf "${url}/api/tags" > /dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge "$max_attempts" ]; then
            echo "ERROR: Ollama not reachable after ${max_attempts} attempts" >&2
            exit 1
        fi
        sleep 5
    done
    echo "Ollama is ready."
}

ensure_model() {
    local model="${OLLAMA_MODEL:-qwen3.5:9b}"
    local url="${OLLAMA_BASE_URL:-http://ollama:11434}"
    # Escape double quotes in model name for JSON safety
    local safe_model="${model//\"/\\\"}"
    echo "Checking model '${model}'..."
    if ! curl -sf "${url}/api/show" -d "{\"name\":\"${safe_model}\"}" > /dev/null 2>&1; then
        echo "Pulling model '${model}'... (this may take a while on first run)"
        curl -sf "${url}/api/pull" -d "{\"name\":\"${safe_model}\"}" || {
            echo "ERROR: Failed to pull model ${model}" >&2
            exit 1
        }
    fi
    echo "Model '${model}' is available."
}

init_if_needed() {
    if [ ! -f "${MOLTBOOK_HOME:-/data}/identity.md" ]; then
        echo "First run detected. Initializing..."
        contemplative-agent init
    fi
}

heartbeat() {
    touch /tmp/healthcheck
}

LAST_DISTILL="/tmp/last-distill"

run_distill_if_due() {
    local now
    now=$(date +%s)
    if [ ! -f "$LAST_DISTILL" ] || [ $((now - $(cat "$LAST_DISTILL"))) -ge 86400 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running daily distillation..."
        contemplative-agent "${CMD_ARGS[@]}" distill --days 1 && echo "$now" > "$LAST_DISTILL"
    fi
}

# --- Main ---
wait_for_ollama
ensure_model
init_if_needed

case "${MODE}" in
    loop)
        echo "Starting session loop: ${SESSION_MINUTES}min sessions, ${BREAK_MINUTES}min breaks"
        while true; do
            heartbeat
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Session starting..."
            contemplative-agent "${CMD_ARGS[@]}" run --session "${SESSION_MINUTES}" || \
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] Session exited with code $?"
            run_distill_if_due
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Next session in ${BREAK_MINUTES} minutes..."
            sleep "$((BREAK_MINUTES * 60))"
        done
        ;;
    single)
        heartbeat
        contemplative-agent "${CMD_ARGS[@]}" run --session "${SESSION_MINUTES}"
        ;;
    command)
        exec contemplative-agent "$@"
        ;;
    *)
        echo "Unknown MODE: ${MODE}. Use 'loop', 'single', or 'command'." >&2
        exit 1
        ;;
esac

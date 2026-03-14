#!/bin/bash
set -euo pipefail

echo "=== Contemplative Agent Setup ==="

# Read OLLAMA_MODEL from .env safely (no source — avoid arbitrary code execution)
DEFAULT_MODEL="${OLLAMA_MODEL:-$(grep -E '^OLLAMA_MODEL=' .env 2>/dev/null | head -1 | cut -d= -f2 || true)}"
DEFAULT_MODEL="${DEFAULT_MODEL:-qwen3.5:9b}"

# Validate model name format
if ! [[ "${DEFAULT_MODEL}" =~ ^[A-Za-z0-9._:/-]+$ ]]; then
    echo "ERROR: Invalid OLLAMA_MODEL value: ${DEFAULT_MODEL}" >&2
    exit 1
fi

# Default model + any additional models passed as arguments
MODELS=("${DEFAULT_MODEL}")
for arg in "$@"; do
    if ! [[ "${arg}" =~ ^[A-Za-z0-9._:/-]+$ ]]; then
        echo "ERROR: Invalid model name: ${arg}" >&2
        exit 1
    fi
    MODELS+=("${arg}")
done

# 1. Build agent image
echo "Building agent image..."
docker compose build

# 2. Pull models via temporary ollama-init (has internet access)
echo "Starting Ollama for model download..."
docker compose --profile init up -d ollama-init

# Wait for Ollama API to be ready (instead of hardcoded sleep)
echo "Waiting for Ollama to be ready..."
until docker compose --profile init exec ollama-init curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done

for model in "${MODELS[@]}"; do
    echo "Pulling model '${model}'..."
    docker compose --profile init exec ollama-init ollama pull "${model}"
done

echo "Stopping init service..."
docker compose --profile init down

# 3. Start agent + ollama (ollama: internal network only, no internet)
echo "Starting agent..."
docker compose up -d

echo ""
echo "=== Setup complete ==="
echo "Models pulled: ${MODELS[*]}"
echo "Active model: ${DEFAULT_MODEL} (change via OLLAMA_MODEL in .env)"
echo "Logs: docker compose logs -f agent"

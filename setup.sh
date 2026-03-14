#!/bin/bash
set -euo pipefail

echo "=== Contemplative Agent Setup ==="

# Read OLLAMA_MODEL from .env if present
if [ -f .env ]; then
    # shellcheck source=/dev/null
    set -a; source .env; set +a
fi
DEFAULT_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"

# Default model + any additional models passed as arguments
MODELS=("${DEFAULT_MODEL}")
for arg in "$@"; do
    MODELS+=("${arg}")
done

# 1. Build agent image
echo "Building agent image..."
docker compose build

# 2. Pull models via temporary ollama-init (has internet access)
echo "Starting Ollama for model download..."
docker compose --profile init up -d ollama-init
sleep 5

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

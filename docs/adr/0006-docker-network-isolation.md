# ADR-0006: Docker Network Isolation

## Status
superseded-by ADR-0070 (Docker removed from main; recoverable by git revert)

## Date
2026-03-14

## Context
Ollama LLM needed to run outside localhost (in a Docker container). However, Ollama has no built-in authentication — exposing it to the network allows arbitrary prompt injection. Additionally, the agent container communicating with external APIs (Moltbook) does not require the Ollama container to have direct internet access.

## Decision
Configure two networks in Docker Compose:

- `internal`: agent ↔ ollama communication only (`internal: true`, no internet access)
- `external`: agent → Moltbook API communication

```
agent:    internal + external networks
ollama:   internal network only
```

Additional measures:
- Non-root user (UID 1000)
- `OLLAMA_TRUSTED_HOSTS` env var extends the hostname allowlist (supports Docker service names)
- `OLLAMA_MODEL` is format-validated (injection prevention)
- setup.sh provides temporary internet access only during initial model download

## Alternatives Considered
- **Run Ollama on the host, containerize only the agent**: Weakens network isolation. The host-side Ollama remains exposed to the internet
- **Single shared network for all containers**: Simpler, but allows Ollama to reach the internet
- **VPN / mTLS**: Excessive for a small-scale project

## Consequences
- Ollama is completely isolated from external access. Network-based prompt injection paths are severed
- Model downloads occur only during setup.sh initial run (offline during operation)
- `docker-compose.override.yml` can bind-mount existing data directories
- Healthchecks monitor container health

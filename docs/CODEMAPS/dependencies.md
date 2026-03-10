<!-- Generated: 2026-03-10 | Files scanned: 1 pyproject.toml | Token estimate: ~250 -->
# Dependencies

## Moltbook Agent

| Dependency | Version | Purpose |
|-----------|---------|---------|
| requests | >=2.28.0 | HTTP client for Moltbook API |
| pytest | >=7.0 (dev) | Test framework |
| pytest-cov | >=4.0 (dev) | Coverage reporting |
| responses | >=0.23.0 (dev) | HTTP mocking |

## External Services

| Service | Used By | Access |
|---------|---------|--------|
| Moltbook API | adapters/moltbook | HTTPS, Bearer auth, domain-locked |
| Ollama | core/llm | localhost:11434, model qwen3.5:9b |

## Build System

Uses **hatchling** as build backend with `uv` for dependency management.

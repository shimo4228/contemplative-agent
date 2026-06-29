<!-- Generated: 2026-06-30 | Files scanned: 1 pyproject.toml | Token estimate: ~240 -->
# Dependencies

## Runtime

| Dependency | Version | Purpose |
|-----------|---------|---------|
| requests | >=2.33.0 | HTTP client for Moltbook API |
| numpy | >=1.24.0 | Embedding arithmetic (cosine, centroids, pattern scoring, POMDP matrices) |

## Dev

| Dependency | Version | Purpose |
|-----------|---------|---------|
| pytest | >=7.0 | Test framework |
| pytest-cov | >=4.0 | Coverage reporting |
| responses | >=0.23.0 | HTTP mocking |

## External Services

| Service | Used By | Access |
|---------|---------|--------|
| Moltbook API | adapters/moltbook | HTTPS, Bearer auth, domain-locked (`www.moltbook.com`) |
| Ollama (generation) | core/llm | `localhost:11434`, `gemma4:e4b` (override: `OLLAMA_MODEL`) — default since ADR-0069; overridable via `LLMBackend` Protocol |
| Ollama (embedding) | core/embeddings | `localhost:11434`, `nomic-embed-text` (override: `OLLAMA_EMBEDDING_MODEL`) — 768-dim, deterministic |

## Optional Add-ons

| Add-on | Provides | Install |
|--------|----------|---------|
| `contemplative-agent-cloud` | Managed-LLM `LLMBackend` implementation — run without local Ollama | `pip install contemplative-agent-cloud` (separate package) |

## Build System

Uses **hatchling** as build backend with `uv` for dependency management.
Python >=3.10 required. Current version: see `pyproject.toml` and `CITATION.cff`.

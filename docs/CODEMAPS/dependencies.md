<!-- Generated: 2026-08-01 | Updated: 2026-08-09 (eval dep group + cross-repo instrument deps) | Files scanned: 1 pyproject.toml | Token estimate: ~858 -->
# Dependencies

## Runtime

| Dependency | Version | Purpose |
|-----------|---------|---------|
| requests | >=2.33.0 | HTTP client for Moltbook API |
| numpy | >=1.24.0 | Embedding arithmetic (cosine, centroids, pattern scoring, POMDP matrices) |

## Dev

| Dependency | Version | Purpose |
|-----------|---------|---------|
| pytest | >=9.0.3 | Test framework (floor is a security floor, PYSEC-2026-1845) |
| pytest-cov | >=4.0 | Coverage reporting |
| hypothesis | >=6.100 | Property-based fault injection (chaos-TDD, ADR-0077) |
| responses | >=0.23.0 | HTTP mocking |
| import-linter | >=2.0 | Import-direction gate — layers + forbidden contracts (`cli -> adapters -> core` ADR-0001; `testing/` two-way forbidden ADR-0088; adapter independence ADR-0015), run via `lint-imports` / `tests/test_architecture.py` |
| bandit | >=1.9.4 | Security gate (`verify.sh`; widens to `-r src evals` per ADR-0089) |
| pip-audit | >=2.9 | Dependency CVE gate (`verify.sh`) |
| vulture | >=2.16 | Weekly dead-code intake (`scripts/dead_code_scan.py`, detection only, T-DEADCODE-INTAKE); scans `src`/`scripts`/`tests`/`evals`, exemptions in `.vulture_whitelist.py` |
| pyright | >=1.1.380 | Type gate (`verify.sh`; full mode also syncs the `eval` group) |
| ruff | >=0.16 | Lint/format gate |

## Eval (opt-in dependency group, ADR-0089)

| Dependency | Version | Purpose |
|-----------|---------|---------|
| deepeval | ==4.1.5 | LLM behavioral eval runner (`evals/adapter_deepeval.py` + `run_eval.py` only); not synced by default `uv run` — only eval runs and `verify.sh`'s type gate pull `[dependency-groups] eval`. Telemetry forced off, `CONFIDENT_API_KEY`/`DEEPEVAL_API_KEY` stripped before import |

## External Services

| Service | Used By | Access |
|---------|---------|--------|
| Moltbook API | adapters/moltbook | HTTPS, Bearer auth, domain-locked (`www.moltbook.com`) |
| Ollama (generation) | core/llm | `localhost:11434`, `gemma4:e4b` (override: `OLLAMA_MODEL`) — default since ADR-0069; overridable via `LLMBackend` Protocol |
| Ollama (embedding) | core/embeddings | `localhost:11434`, `nomic-embed-text` (override: `OLLAMA_EMBEDDING_MODEL`) — 768-dim, deterministic |
| Claude Code CLI (`claude -p`) | `scripts/weekly-analysis.sh`, `scripts/weekly-pipeline.sh`, `evals/adapter_deepeval.py` (judge, isolated subprocess) | Unattended weekly report/diagnosis/fix chain (ADR-0040/0085) + eval-layer llm-as-judge (ADR-0089, `claude-sonnet-5`, allowlisted env, no tools/MCP) |

## Cross-Repo Instrument Dependencies

| Dependency | Repo | Purpose |
|-----------|------|---------|
| `contemplative-ipd` (`benchmarks/prisoners-dilemma`) | `contemplative-agent-rules` (sibling, own venv) | ADR-0090 IPD two-arm bench, run before every constitution-amendment approval. Checked out and invoked only by `scripts/ipd-two-arm.sh`; hard-fails with an install hint if absent. Never imported by `core`/`adapters`/`cli` |

## Optional Add-ons

| Add-on | Provides | Install |
|--------|----------|---------|
| `contemplative-agent-cloud` | Managed-LLM `LLMBackend` implementation — run without local Ollama | `pip install contemplative-agent-cloud` (separate package) |

## Build System

Uses **hatchling** as build backend with `uv` for dependency management.
Python >=3.10 required. Current version: see `pyproject.toml` and `CITATION.cff`.

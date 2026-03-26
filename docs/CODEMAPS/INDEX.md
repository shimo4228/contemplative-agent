<!-- Generated: 2026-03-24 | Total codemaps: 5 | Token estimate: ~500 -->
# Codemaps Index

Comprehensive architectural documentation for contemplative-moltbook project.
**Last Updated**: 2026-03-25 | **Codebase**: 30 modules, ~6900 LOC, 684 tests

---

## Quick Navigation

### 1. [architecture.md](architecture.md) — System Overview
**Read first.** High-level architecture, system diagram, 3-layer memory model, data flows.

**Topics**:
- Project type & stats (30 modules, ~6900 LOC, 685 tests)
- System diagram (core/ + adapters/moltbook/ + adapters/meditation/ + Ollama)
- Import rules (adapters → core, cli.py is only exception)
- Session execution flow (ReplyHandler → FeedManager → PostPipeline)
- Offline learning flow (2-stage distill + insight + meditation)
- 3-layer + agents.json memory architecture
- Entry points

**Use when**: Understanding overall system structure, data flow, memory model.

---

### 2. [moltbook-agent.md](moltbook-agent.md) — Agent Details & API
**Most comprehensive.** Module dependency graph, CLI commands, LLM functions, security boundaries.

**Topics**:
- 34-module dependency graph with line counts
- 20+ key classes (Agent, SessionContext, FeedManager, ReplyHandler, PostPipeline, etc.)
- CLI commands (init, register, run, distill, distill-identity, insight, generate-report, solve, meditate, install-schedule, rules-distill)
- LLM functions (12 in core/llm.py + insight.py + meditation)
- Prompt templates (17 templates, domain placeholders)
- Persistent state files
- 3-layer memory architecture detail
- Security boundaries & threat model
- Performance & rate limiting (3-layer defense)

**Use when**: Implementing features, understanding session flow, debugging API interactions.

---

### 3. [core-modules.md](core-modules.md) — Core Layer Deep Dive
**Platform-independent foundation.** 14 modules providing base functionality.

**Topics**:
- 14 core modules (~2600 LOC): _io, config, domain, prompts, llm, episode_log, knowledge_store, memory, scheduler, distill (2-stage + identity), insight, report, metrics
- 2-stage distill pipeline (extract → refine, identity update integrated)
- Dependency flow diagram
- 3 frozen dataclasses (Interaction, PostRecord, Insight)
- EpisodeLog schema (JSONL, record_type filter)
- KnowledgeStore schema (JSON patterns only)
- LLM functions (circuit breaker, sanitization, security)
- Scheduler (rate limit state, budgets)
- Insight pipeline (behavior extraction, skill file generation)
- Report generation (activity summaries)
- Domain configuration (submolts, keywords, rules)
- Security model (input wrapping, output sanitization, pattern validation)

**Use when**: Understanding memory/persistence, distillation, insights, LLM configuration.

---

### 4. [adapters-moltbook.md](adapters-moltbook.md) — Moltbook Adapter Layer
**Platform-specific implementation.** 11 modules for Moltbook integration.

**Topics**:
- 11 adapter modules (~2800 LOC): config, agent, session_context, feed_manager, reply_handler, post_pipeline, client, auth, verification, content, llm_functions
- Agent session orchestration (AutonomyLevel: APPROVE/GUARDED/AUTO)
- SessionContext (shared mutable state)
- FeedManager, ReplyHandler, PostPipeline
- MoltbookClient (HTTP with domain lock, 429 backoff)
- Meditation adapter (4 modules, ~700 LOC): config, pomdp, meditate, report

**Use when**: Adding Moltbook features, debugging feed/reply/post cycles, optimizing rate limiting.

---

### 5. [dependencies.md](dependencies.md) — External Dependencies
Package versions, transitive dependencies, security notes.

**Use when**: Checking versions, auditing dependencies.

---

## Key Files by Task

### Implementing a New Feature
1. Start: [architecture.md](architecture.md) — understand data flow
2. Locate module: [moltbook-agent.md](moltbook-agent.md) — module dependency graph
3. Module deep-dive: [core-modules.md](core-modules.md) or [adapters-moltbook.md](adapters-moltbook.md)
4. Check: security/tests in module codemap

### Debugging Session Flow
1. [moltbook-agent.md](moltbook-agent.md) — CLI commands section
2. [adapters-moltbook.md](adapters-moltbook.md) — Session Orchestration (Agent.run_session flow)
3. [architecture.md](architecture.md) — Session execution flow diagram

### Understanding Memory
1. [architecture.md](architecture.md) — 3-layer + agents.json overview
2. [moltbook-agent.md](moltbook-agent.md) — Persistent State Files section
3. [core-modules.md](core-modules.md) — EpisodeLog/KnowledgeStore/MemoryStore sections

### Distillation & Learning
1. [architecture.md](architecture.md) — Offline Learning flow (2-stage)
2. [core-modules.md](core-modules.md) — 2-stage distill + identity pipelines
3. [moltbook-agent.md](moltbook-agent.md) — CLI distill/distill-identity/insight commands

### Meditation (Active Inference)
1. [architecture.md](architecture.md) — Meditation adapter overview
2. [adapters-moltbook.md](adapters-moltbook.md) — Meditation adapter modules

---

## Statistics

| Metric | Value |
|--------|-------|
| Total modules | 30 (14 core + 11 adapters/moltbook + 4 adapters/meditation + cli) |
| LOC | ~6900 |
| Test files | 17 |
| Test count | 685 |
| Core modules | 14 (platform-independent) |
| Moltbook adapter modules | 11 |
| Meditation adapter modules | 4 |
| Dataclasses | 3 (Interaction, PostRecord, Insight) |
| CLI commands | 12 (init, register, status, run, distill, distill-identity, insight, generate-report, solve, meditate, install-schedule, rules-distill) |
| Prompt templates | 22 |
| Config templates | 2 (config/templates/constitution/) |
| Rate limit budgets | 2 (GET 60/min, POST 30/min) |

---

## Related Documentation

- **[docs/spec/system-spec.md](../spec/system-spec.md)** — System specification (architecture, memory, behavior, security). 「こうなっている」の正式な仕様。研究者向け + AI 向け
- **CLAUDE.md** — Project conventions, setup, Docker, security policy
- **README.md** — User-facing overview, quickstart
- **[docs/adr/](../adr/README.md)** — Architecture Decision Records. 「なぜそうしたか」の記録
- **config/templates/constitution/contemplative-axioms.md** — Constitutional clauses default (Laukkonen et al. 2025)

---

## Update Cycle

CODEMAPS と system-spec.md は context-sync で同期する:
- **system-spec.md**: 設計変更時に更新（「こうなっている」の正式仕様）
- **CODEMAPS**: コード変更時に更新（「どこにあるか」のコード索引）

Last full scan: 2026-03-26 (30 modules, 720 tests verified)

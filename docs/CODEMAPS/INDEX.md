<!-- Generated: 2026-05-25 | Total codemaps: 5 | Token estimate: ~490 -->
# Codemaps Index

Comprehensive architectural documentation for the Contemplative Agent project.
**Last Updated**: 2026-05-25 | **Codebase**: 45 non-`__init__` modules (51 total `.py`), ~12000 LOC, 1079 tests

---

## Quick Navigation

### 1. [architecture.md](architecture.md) — System Overview
**Read first.** High-level architecture, system diagram, 3-layer memory model, data flows.

**Topics**:
- Project type & stats (45 non-`__init__` modules, ~12000 LOC)
- System diagram (core/ + adapters/moltbook/ + adapters/meditation/ + adapters/dialogue/ + Ollama / pluggable backend)
- Import rules (adapters → core, cli.py is only exception)
- Session execution flow (ReplyHandler → FeedManager → PostPipeline)
- Offline learning flow (2-stage distill + insight + meditation)
- 3-layer + agents.json memory architecture
- Entry points
- Init-time copy: prompts/views/skills/rules/constitution are all user-owned under `MOLTBOOK_HOME`
- Pluggable LLM backend via `LLMBackend` Protocol (`core/llm.py`) — enables `contemplative-agent-cloud` add-on

**Use when**: Understanding overall system structure, data flow, memory model.

---

### 2. [moltbook-agent.md](moltbook-agent.md) — Agent Details & API
**Most comprehensive.** Module dependency graph, CLI commands, LLM functions, security boundaries.

**Topics**:
- Full module dependency graph with line counts (45 non-`__init__` modules)
- 20+ key classes (Agent, SessionContext, FeedManager, ReplyHandler, PostPipeline, NoveltyGate, etc.)
- CLI commands (init, register, run, distill, distill-identity, insight, rules-distill, adopt-staged, skill-stocktake, rules-stocktake, generate-report, solve, meditate, install-schedule, ...)
- LLM functions (core/llm.py + insight.py + meditation)
- Prompt templates (25 active templates)
- Persistent state files
- 3-layer memory architecture detail
- Security boundaries & threat model
- Performance & rate limiting (3-layer defense)

**Use when**: Implementing features, understanding session flow, debugging API interactions.

---

### 3. [core-modules.md](core-modules.md) — Core Layer Deep Dive
**Platform-independent foundation.** 25 modules providing base functionality.

**Topics**:
- 25 core modules: _io, config, domain, prompts, llm (includes `LLMBackend` Protocol), embeddings, episode_embeddings, episode_log, knowledge_store, memory, scheduler, distill, insight, constitution, rules_distill, stocktake, views, snapshot, report, metrics, forgetting, clustering, text_utils, thresholds, artifact_extraction
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

### 4. [adapters-moltbook.md](adapters-moltbook.md) — Adapter Layer
**Platform-specific implementation.** Moltbook (14) + Meditation (4) + Dialogue (1).

**Topics**:
- 14 Moltbook adapter modules (~3500 LOC): config, agent, session_context, feed_manager, reply_handler, post_pipeline, client, auth, verification, content, llm_functions, dedup, novelty, feed_seeder
- Agent session orchestration (AutonomyLevel: APPROVE/GUARDED/AUTO)
- SessionContext (shared mutable state)
- FeedManager, ReplyHandler, PostPipeline
- MoltbookClient (HTTP with domain lock, 429 backoff)
- NoveltyGate (embedding novelty + temporal decay + Lagrangian, ADR-0039)
- feed_seeder (RNG peer-post seed selection, ADR-0043)
- Meditation adapter (4 modules, ~700 LOC): config, pomdp, meditate, report
- Dialogue adapter (`peer.py`, ~140L) — 2-agent peer-to-peer loop

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

**Counting convention**: "modules" = non-`__init__` `.py` files unless noted.

| Metric | Value |
|--------|-------|
| Total `.py` files | 51 (45 non-`__init__` + 6 `__init__`) |
| LOC | ~12000 |
| Test files | 31 (1079 tests collected) |
| Core modules | 25 (platform-independent) |
| Moltbook adapter modules | 14 |
| Meditation adapter modules | 4 |
| Dialogue adapter modules | 1 (peer.py) |
| Dataclasses | 3 (Interaction, PostRecord, Insight) + result types (see core-modules.md) |
| CLI commands | 21 active |
| Prompt templates | 25 (config/prompts/*.md) |
| View seeds | 7 (config/views/*.md) |
| Config templates | 11 (config/templates/) |
| Rate limit budgets | 2 (GET 60/min, POST 30/min) |

---

## Related Documentation

- **CLAUDE.md** — Project conventions, setup, Docker, security policy
- **README.md** — User-facing overview, quickstart
- **CHANGELOG.md** — Release history
- **[docs/adr/](../adr/README.md)** — Architecture Decision Records. 「なぜそうしたか」
- **[docs/evidence/](../evidence/README.md)** — ADR を裏付ける測定・監査・実験
- **[docs/runbooks/](../runbooks/README.md)** — 運用 know-how（migration, RCA）
- **config/templates/constitution/contemplative-axioms.md** — Constitutional clauses default (Laukkonen et al. 2025)

---

## Update Cycle

CODEMAPS はコード変更時に更新する（「どこにあるか」のコード索引）。

Last full scan: 2026-05-25 (45 non-`__init__` modules verified, post-ADR-0043 feed_seeder / ADR-0039 NoveltyGate / ADR-0044 topic-keyword removal / ADR-0045 internal_note prompt)

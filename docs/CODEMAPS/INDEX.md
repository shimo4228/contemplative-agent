<!-- Generated: 2026-06-05 | Total codemaps: 5 | Token estimate: ~1370 -->
# Codemaps Index

Comprehensive architectural documentation for the Contemplative Agent project.
**Last Updated**: 2026-06-05 | **Codebase**: 44 non-`__init__` modules (50 total `.py`), ~12700 LOC, 1211 tests

---

## Quick Navigation

### 1. [architecture.md](architecture.md) — System Overview
**Read first.** High-level architecture, system diagram, causal-chain data flows with gates and thresholds.

**Topics**:
- Project type & stats (44 non-`__init__` modules, ~12700 LOC, 1211 tests)
- System diagram (core/ + adapters/moltbook/ + adapters/meditation/ + adapters/dialogue/)
- Import rules (adapters → core, cli.py is only exception)
- Session execution flow (ReplyHandler → FeedManager → PostPipeline) with gate thresholds
- Offline learning flows — causal chain with module/function/formula/ADR at each step:
  - distill (binary noise gate + 3-step + embedding dedup)
  - distill-identity (single-stage, pure cosine retrieval)
  - insight (global clustering, NOT per-view)
  - rules-distill, amend-constitution
  - ADR-0050 approval lineage (source_ids / epistemic_counts into audit.jsonl)
- Meditation: flat single-level POMDP, no KnowledgeStore write (ADR-0049)
- 3-layer memory + is_live + effective_importance formulas
- AKC mapping

**Use when**: Understanding overall structure, tracing any data-flow mechanism, checking thresholds.

---

### 2. [moltbook-agent.md](moltbook-agent.md) — Agent Details & API
**Most comprehensive.** Module dependency graph, CLI commands, LLM functions, security boundaries.

**Topics**:
- Full module dependency graph with line counts (44 modules)
- 20+ key classes
- CLI commands (21 active)
- Prompt templates (30 active)
- Persistent state files
- Security boundaries & threat model
- Performance & rate limiting (3-layer defense)

**Use when**: Implementing features, understanding session flow, debugging API interactions.

---

### 3. [core-modules.md](core-modules.md) — Core Layer Deep Dive
**Platform-independent foundation.** 24 modules providing base functionality.

**Topics**:
- 24 core modules with LOC and purpose
- ADR-0012 Result types (with ADR-0050 pattern_ids / epistemic_counts fields)
- EpisodeLog + KnowledgeStore schemas (post-ADR-0051: no trust_score)
- Threshold table (NOISE_THRESHOLD, SIM_DUPLICATE, SIM_UPDATE, CLUSTER_THRESHOLD_*)
- Views mechanism (pure cosine rank, ADR-0051)
- LLM functions + circuit breaker
- Security model

**Use when**: Understanding memory/persistence, distillation mechanics, thresholds.

---

### 4. [adapters-moltbook.md](adapters-moltbook.md) — Adapter Layer
**Platform-specific implementation.** Moltbook (14) + Meditation (4) + Dialogue (1).

**Topics**:
- 14 Moltbook adapter modules (~3842 LOC)
- Session orchestration (AutonomyLevel: APPROVE/GUARDED/AUTO)
- PostPipeline gate chain (feed_seeder → NoveltyGate → test-content → body-hash)
- Meditation adapter: flat POMDP, ADR-0049 fidelity clarification
- Dialogue adapter: 2 independent peer processes

**Use when**: Adding Moltbook features, debugging feed/reply/post cycles.

---

### 5. [dependencies.md](dependencies.md) — External Dependencies
Package versions, external services, optional add-ons.

**Use when**: Checking versions, auditing dependencies.

---

## Key Files by Task

### Implementing a New Feature
1. [architecture.md](architecture.md) — understand data flow and gates
2. [moltbook-agent.md](moltbook-agent.md) — module dependency graph
3. [core-modules.md](core-modules.md) or [adapters-moltbook.md](adapters-moltbook.md)

### Debugging Session Flow
1. [moltbook-agent.md](moltbook-agent.md) — CLI commands + LLM surface
2. [adapters-moltbook.md](adapters-moltbook.md) — Session Orchestration
3. [architecture.md](architecture.md) — Session execution flow

### Understanding Memory / Distillation
1. [architecture.md](architecture.md) — causal-chain Data Flow (distill/identity/insight sections)
2. [core-modules.md](core-modules.md) — KnowledgeStore schema + threshold table
3. [moltbook-agent.md](moltbook-agent.md) — Persistent State Files

---

## Statistics

| Metric | Value |
|--------|-------|
| Total `.py` files | 50 (44 non-`__init__` + 6 `__init__`) |
| LOC | ~12700 |
| Test files | 32 (1211 tests collected) |
| Core modules | 24 (platform-independent; forgetting.py deleted ADR-0051) |
| Moltbook adapter modules | 14 |
| Meditation adapter modules | 4 |
| Dialogue adapter modules | 1 (peer.py) |
| CLI commands | 21 active |
| Prompt templates | 32 files / 30 loaded (config/prompts/*.md) |
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
- **[docs/runbooks/](../runbooks/README.md)** — 運用 know-how

---

## Update Cycle

CODEMAPS はコード変更時に更新する（「どこにあるか」のコード索引）。

Last full scan: 2026-06-05 (44 non-`__init__` modules verified, post-ADR-0046/0047/0048/0049/0050/0051 + forgetting.py deletion + client.py dead-code removal + embeddings.py trim)

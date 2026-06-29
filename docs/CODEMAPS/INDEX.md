<!-- Generated: 2026-06-30 | Total codemaps: 5 | Token estimate: ~1370 -->
# Codemaps Index

Comprehensive architectural documentation for the Contemplative Agent project.
**Last Updated**: 2026-06-30 | **Codebase**: 45 non-`__init__` modules (51 total `.py`), ~15570 LOC, 1479 tests collected

---

## Quick Navigation

### 1. [architecture.md](architecture.md) — System Overview
**Read first.** High-level architecture, system diagram, causal-chain data flows with gates and thresholds.

**Topics**:
- Project type & stats (45 non-`__init__` modules, ~15570 LOC, 1479 tests collected)
- System diagram (core/ + adapters/moltbook/ + adapters/meditation/ + adapters/dialogue/)
- Import rules (adapters → core, cli.py is only exception)
- Session execution flow (ReplyHandler → FeedManager → PostPipeline) with gate thresholds
- Offline learning flows — causal chain with module/function/formula/ADR at each step:
  - distill (per-episode grounded distill: one LLM call per engagement episode, no noise gate, + embedding dedup; ADR-0060, importance step retired ADR-0056)
  - distill-identity (single-stage, pure cosine retrieval)
  - insight (global clustering, NOT per-view)
  - rules-distill, amend-constitution
  - ADR-0050 approval lineage (source_ids / epistemic_counts into audit.jsonl)
- Meditation: flat single-level POMDP, no KnowledgeStore write (ADR-0049)
- 3-layer memory + is_live + effective_importance (pure time decay, ADR-0056)
- AKC mapping

**Use when**: Understanding overall structure, tracing any data-flow mechanism, checking thresholds.

---

### 2. [moltbook-agent.md](moltbook-agent.md) — Agent Details & API
**Most comprehensive.** Module dependency graph, CLI commands, LLM functions, security boundaries.

**Topics**:
- Full module dependency graph with line counts (45 modules)
- 20+ key classes
- CLI commands (21 active)
- Prompt templates (32 active)
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
- Threshold table (SIM_DUPLICATE, SIM_UPDATE, DEDUP_IMPORTANCE_FLOOR, CLUSTER_THRESHOLD_*; NOISE_THRESHOLD removed ADR-0060)
- Views mechanism (pure cosine rank, ADR-0051)
- LLM functions + circuit breaker
- Security model

**Use when**: Understanding memory/persistence, distillation mechanics, thresholds.

---

### 4. [adapters-moltbook.md](adapters-moltbook.md) — Adapter Layer
**Platform-specific implementation.** Moltbook (15) + Meditation (4) + Dialogue (1).

**Topics**:
- 15 Moltbook adapter modules (~5078 LOC)
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
| Total `.py` files | 51 (45 non-`__init__` + 6 `__init__`) |
| LOC | ~15570 |
| Test files | 37 (1479 tests collected) |
| Core modules | 24 (platform-independent; forgetting.py deleted ADR-0051, mlx_backend.py removed ADR-0070) |
| Moltbook adapter modules | 15 |
| Meditation adapter modules | 4 |
| Dialogue adapter modules | 1 (peer.py) |
| CLI commands | 21 active |
| Prompt templates | 34 files / 32 loaded (config/prompts/*.md) |
| View seeds | 7 (config/views/*.md) |
| Config templates | 11 (config/templates/) |
| Rate limit budgets | 2 (GET 60/min, POST 30/min) |

---

## Related Documentation

- **CLAUDE.md** — Project conventions, setup, security policy
- **README.md** — User-facing overview, quickstart
- **CHANGELOG.md** — Release history
- **[docs/adr/](../adr/README.md)** — Architecture Decision Records. 「なぜそうしたか」
- **[docs/evidence/](../evidence/README.md)** — ADR を裏付ける測定・監査・実験
- **[docs/runbooks/](../runbooks/README.md)** — 運用 know-how

---

## Update Cycle

CODEMAPS はコード変更時に更新する（「どこにあるか」のコード索引）。

Last full scan: 2026-06-20 (v2.6.0 release: 44 non-`__init__` modules, ~13592 LOC, 1301 tests verified; post-ADR-0053/0054/0055/0056/0057/0058 — importance LLM scoring + axiom-grounded distillation retired). Post-scan hand-updates (full re-scan pending): ADR-0059 (dead reply-history removed), ADR-0060 (distill is now per-episode grounded — one LLM call per episode, the 2-step batch + noise gate were removed), ADR-0061 (action-time untrusted caps at platform field limits), ADR-0062 (create-time verification handshake; amended with guarded expression extraction and base64 verification-audit corpus logging), ADR-0063 (NoveltyGate scoped to verified posts), ADR-0064 (opt-in MLX generation backend — `core/mlx_backend.py` added), ADR-0065 (MLX on-demand launchd wiring + telemetry served-model-id contract), ADR-0066 (backend-aware context-budget guard via context_window property), ADR-0070 (MLX backend retired to sibling repo + Docker removed — `core/mlx_backend.py`, MLX scripts, and Docker infra deleted; `LLMBackend` Protocol retained for cloud injection). Current counts after hand-updates: 45 non-`__init__` modules (51 total `.py`), ~15570 LOC, 1479 tests collected.

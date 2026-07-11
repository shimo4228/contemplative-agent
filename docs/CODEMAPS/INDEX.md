<!-- Generated: 2026-07-11 | Total codemaps: 5 | Token estimate: ~1908 -->
# Codemaps Index

Comprehensive architectural documentation for the Contemplative Agent project.
**Last Updated**: 2026-07-11 | **Codebase**: see [Statistics](#statistics)

---

## Quick Navigation

### 1. [architecture.md](architecture.md) — System Overview
**Read first.** High-level architecture, system diagram, causal-chain data flows with gates and thresholds.

**Topics**:
- Project type & stats (see [Statistics](#statistics))
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
- Full module dependency graph with line counts
- 20+ key classes
- CLI commands
- Prompt templates
- Persistent state files
- Security boundaries & threat model
- Performance & rate limiting (3-layer defense)

**Use when**: Implementing features, understanding session flow, debugging API interactions.

---

### 3. [core-modules.md](core-modules.md) — Core Layer Deep Dive
**Platform-independent foundation.** The modules providing base functionality.

**Topics**:
- Core modules with LOC and purpose
- ADR-0012 Result types (with ADR-0050 pattern_ids / epistemic_counts fields)
- EpisodeLog + KnowledgeStore schemas (post-ADR-0051: no trust_score)
- Threshold table (SIM_DUPLICATE, SIM_UPDATE, DEDUP_IMPORTANCE_FLOOR, CLUSTER_THRESHOLD_*; NOISE_THRESHOLD removed ADR-0060)
- Views mechanism (pure cosine rank, ADR-0051)
- LLM functions + circuit breaker
- Security model

**Use when**: Understanding memory/persistence, distillation mechanics, thresholds.

---

### 4. [adapters-moltbook.md](adapters-moltbook.md) — Adapter Layer
**Platform-specific implementation.** Moltbook + Meditation + Dialogue.

**Topics**:
- Moltbook adapter modules
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

As of **2026-07-11** — values are measured, never carried forward from a previous version; recompute with the commands below at every refresh. Aggregate counts live here and nowhere else in CODEMAPS.

| Metric | Value |
|--------|-------|
| Total `.py` files | 53 (47 non-`__init__` + 6 `__init__`) |
| LOC | ~18883 |
| Test files | 42 (1783 tests collected) |
| Core modules | 26 (platform-independent) |
| Moltbook adapter modules | 15 |
| Meditation adapter modules | 4 |
| Dialogue adapter modules | 1 (peer.py) |
| CLI commands | see [moltbook-agent.md](moltbook-agent.md) CLI table or `contemplative-agent --help` |
| Prompt templates / view seeds | canonical inventory in [CONFIGURATION.md](../CONFIGURATION.md#pipeline-prompts--view-seeds), guarded by `tests/test_packaged_assets.py` |
| Config templates | 11 (config/templates/) |
| Rate limit budgets | 2 (GET 60/min, POST 30/min) |

Measured by: `find src -name '*.py' | wc -l` · `find src -name '*.py' -exec cat {} + | wc -l` · `ls tests/test_*.py | wc -l` · `uv run pytest tests/ --collect-only -q | tail -1` · per package: `find src/contemplative_agent/<pkg> -name '*.py' ! -name '__init__.py' | wc -l`

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

Full re-scan: 2026-07-09 (v2.8.0 release gate; live wc/find/pytest recount — LOC + per-file line counts in [core-modules.md](core-modules.md)/[adapters-moltbook.md](adapters-moltbook.md)/[moltbook-agent.md](moltbook-agent.md) refreshed, largest drifts: `cli.py` 2364→2817L, `verification_parse.py` 472→909L post ADR-0062 6th/7th amendment grammar rounds, `insight.py` 395→651L post ADR-0074). Covers through ADR-0076 (skill-selection shadow instrument: `core/skill_selection.py` pass-1 LLM applicability observation before content generations, `logs/skill-selection-*.jsonl` + `report --skill-selection`, injection unchanged), ADR-0075 (observability-by-default: every feature with external I/O / LLM calls / heuristic decisions ships a replayable JSONL audit log in the same PR — see [architecture.md § Observability](architecture.md#observability)), ADR-0074 (weekly staged insight: theme detection, `.last_insight` pending guard, LLM novelty gate, exact fast clustering), ADR-0073 (orphaned view seeds pruned — `config/views/` ships only `self_reflection` + `constitutional`; verified no stale references remain), ADR-0072 (echo-chamber interventions — register instruction, corpus-grown seed exemplar, extraction-failure guard), ADR-0071 (read-only pattern-composition instruments — `core/view_metrics.py`). Dead-code removal (`interaction_count_with`, `Finding.example`, commit `0034980`) verified clean — no remaining references in source or docs. Current aggregate counts live in [Statistics](#statistics) only. Stats-only refresh: 2026-07-11 (live recount; no full regeneration — see [core-modules.md](core-modules.md) for the same-day ADR-0074/0076 section update).

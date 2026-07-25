<!-- Generated: 2026-07-18 | Total codemaps: 5 | Token estimate: ~2195 -->
# Codemaps Index

Comprehensive architectural documentation for the Contemplative Agent project.
**Last Updated**: 2026-07-18 | **Codebase**: see [Statistics](#statistics)

---

## Quick Navigation

### 1. [architecture.md](architecture.md) — System Overview
**Read first.** High-level architecture, system diagram, causal-chain data flows with gates and thresholds.

**Topics**:
- Project type & stats (see [Statistics](#statistics))
- System diagram (core/ + adapters/moltbook/ + adapters/meditation/ + adapters/dialogue/)
- Import rules (adapters → core, cli/ is only exception)
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

As of **2026-07-25** — values are measured, never carried forward from a previous version; recompute with the commands below at every refresh. Aggregate counts live here and nowhere else in CODEMAPS.

| Metric | Value |
|--------|-------|
| Total `.py` files | 74 (66 non-`__init__` + 8 `__init__`) |
| LOC | ~21361 |
| Test files | 60 (1984 tests collected) |
| Core modules | 32 (platform-independent; incl. `llm/` package as one row) |
| Moltbook adapter modules | 16 |
| Meditation adapter modules | 4 |
| Dialogue adapter modules | 1 (peer.py) |
| CLI package modules | 11 (`cli/` excl. `__init__.py`, split from single `cli.py` per ADR-0079; `registry.py` + `agent_cmds.py` added when subcommand declaration moved out of `main`) |
| CLI commands | see [moltbook-agent.md](moltbook-agent.md) CLI table or `contemplative-agent --help` |
| Prompt templates / view seeds | canonical inventory in [CONFIGURATION.md](../CONFIGURATION.md#pipeline-prompts--view-seeds), guarded by `tests/test_packaged_assets.py` |
| Config templates | 11 (config/templates/) |
| Rate limit budgets | 2 (GET 60/min, POST 30/min) |

Measured by: `find src -name '*.py' | wc -l` · `find src -name '*.py' -exec cat {} + | wc -l` · `find tests -name 'test_*.py' | wc -l` · `uv run pytest tests/ --collect-only -q | tail -1` · per package: `find src/contemplative_agent/<pkg> -name '*.py' ! -name '__init__.py' | wc -l`

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

Full re-scan: 2026-07-09 (v2.8.0 release gate; live wc/find/pytest recount — LOC + per-file line counts in [core-modules.md](core-modules.md)/[adapters-moltbook.md](adapters-moltbook.md)/[moltbook-agent.md](moltbook-agent.md) refreshed, largest drifts: `cli.py` 2364→2817L, `verification_parse.py` 472→909L post ADR-0062 6th/7th amendment grammar rounds, `insight.py` 395→651L post ADR-0074). Covers through ADR-0076 (skill-selection shadow instrument: `core/skill_selection.py` pass-1 LLM applicability observation before content generations, `logs/skill-selection-*.jsonl` + `report --skill-selection`, injection unchanged), ADR-0075 (observability-by-default: every feature with external I/O / LLM calls / heuristic decisions ships a replayable JSONL audit log in the same PR — see [architecture.md § Observability](architecture.md#observability)), ADR-0074 (weekly staged insight: theme detection, `.last_insight` pending guard, LLM novelty gate, exact fast clustering), ADR-0073 (orphaned view seeds pruned — `config/views/` ships only `self_reflection` + `constitutional`; verified no stale references remain), ADR-0072 (echo-chamber interventions — register instruction, corpus-grown seed exemplar, extraction-failure guard), ADR-0071 (read-only pattern-composition instruments — `core/view_metrics.py`). Dead-code removal (`interaction_count_with`, `Finding.example`, commit `0034980`) verified clean — no remaining references in source or docs. Current aggregate counts live in [Statistics](#statistics) only. Stats-only refresh: 2026-07-11 (live recount; no full regeneration — see [core-modules.md](core-modules.md) for the same-day ADR-0074/0076 section update). Full re-scan: 2026-07-18 (ADR-0079 module reorganization: `core/llm.py` → `core/llm/` package — `__init__.py` facade, `backend.py` Protocol+circuit-breaker, `prompting.py` system-prompt assembly, `guard.py` sanitize/SSRF; `cli.py` (2817L) → `cli/` package — `__init__.py` dispatch (589L) + `runtime.py`/`schedule.py`/`approval.py`/`staging.py`/`adopt.py`/`stocktake_cmd.py`/`memory_cmds.py`/`session_cmds.py`/`__main__.py` (10 files, ~3277L total); `core/insight_novelty.py` and `core/pattern_dedup.py` + `core/episode_render.py` extracted from `insight.py`/`distill.py` — gate logic unchanged, rendering/dedup only. Also folds in ADR-0078 `core/run_context.py` (run_id/session_id minting, missing from the 07-09 scan) and live LOC drift in `adapters/moltbook/` (`agent.py` 753→853L, `client.py` 824→844L, `verification.py` 536→700L, `verification_parse.py` 909→1132L, others adjusted) accumulated since 2026-07-09 across unrelated fix commits. All six codemaps + Statistics recomputed live in this pass. ADR-0080 (north star — per-layer end-state definition, 2026-07-20) is a program-level worldview ADR with no code impact; no codemap changes beyond this note (canonical: [docs/adr/0080](../adr/0080-north-star-layered-end-state.md), pointer section in [docs/CYCLES.md](../CYCLES.md)). ADR-0081 (skill-selection two-pass injection enforcement, accepted 2026-07-24 on the first shadow reading) migrates the three observed generation paths to selected-bodies-only injection, flag-gated (`MOLTBOOK_SKILL_SELECTION_ENFORCE`, default off = shadow-only); implemented same day — selector return feeds `_selection_system()` in `adapters/moltbook/llm_functions.py`, pass-2 composition via `llm.build_system_prompt_with_skills()`, post_title reuses cooperation_post's selection, fail-open falls back to full injection (canonical: [docs/adr/0081](../adr/0081-skill-selection-two-pass-injection-enforcement.md), see [core-modules.md](core-modules.md) `skill_selection.py` row and [architecture.md](architecture.md) Data Flow).

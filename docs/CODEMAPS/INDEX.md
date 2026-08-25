<!-- Generated: 2026-08-01 | Updated: 2026-08-22 | Total codemaps: 5 | Token estimate: ~3922 -->
# Codemaps Index

Comprehensive architectural documentation for the Contemplative Agent project.
**Last Updated**: 2026-08-17 | **Codebase**: see [Statistics](#statistics)

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
  - amend-constitution; skill-stocktake (quality report + usage reading + description audit — ADR-0097 retired rules-distill / rules-stocktake and the merge / clean stages)
  - ADR-0050 approval lineage (source_ids / epistemic_counts into audit.jsonl)
  - ADR-0090 IPD two-arm bench (behavioral reading before every constitution-amendment approval)
- Behavioral eval layer (`evals/`, ADR-0089 — comment-generation regression detector on DeepEval, outside the wheel)
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

As of **2026-08-17** (live recount) — values are measured, never carried forward from a previous version; recompute with the commands below at every refresh. Aggregate counts live here and nowhere else in CODEMAPS.

| Metric | Value |
|--------|-------|
| Total `.py` files | 85 (76 non-`__init__` + 9 `__init__`) |
| LOC | ~28458 |
| Test files | 99 (3827 tests collected) |
| Eval layer modules | 8 (`evals/` excl. `__init__.py`; outside `src/` and outside the wheel — measures LLM output quality, ADR-0089) |
| Core modules | 37 (platform-independent; 33 top-level modules + 4 in the `llm/` package) |
| Moltbook adapter modules | 17 |
| Meditation adapter modules | 4 |
| Dialogue adapter modules | 1 (peer.py) |
| Testing kit modules | 3 (`testing/` excl. `__init__.py`; ships in the wheel but is not production code — ADR-0088) |
| CLI package modules | 14 (`cli/` excl. `__init__.py`, split from single `cli.py` per ADR-0079; `registry.py` + `agent_cmds.py` added when subcommand declaration moved out of `main`) |
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
- **[rfcs/](../../rfcs/README.md)** — 公開タスク台帳（提案・作業・未決）。「これから何をするか / なぜやらないか」
- **[docs/evidence/](../evidence/README.md)** — ADR を裏付ける測定・監査・実験
- **[docs/runbooks/](../runbooks/README.md)** — 運用 know-how

---

## Update Cycle

CODEMAPS はコード変更時に更新する（「どこにあるか」のコード索引）。

Full re-scan: 2026-07-09 (v2.8.0 release gate; live wc/find/pytest recount — LOC + per-file line counts in [core-modules.md](core-modules.md)/[adapters-moltbook.md](adapters-moltbook.md)/[moltbook-agent.md](moltbook-agent.md) refreshed, largest drifts: `cli.py` 2364→2817L, `verification_parse.py` 472→909L post ADR-0062 6th/7th amendment grammar rounds, `insight.py` 395→651L post ADR-0074). Covers through ADR-0076 (skill-selection shadow instrument: `core/skill_selection.py` pass-1 LLM applicability observation before content generations, `logs/skill-selection-*.jsonl` + `report --skill-selection`, injection unchanged), ADR-0075 (observability-by-default: every feature with external I/O / LLM calls / heuristic decisions ships a replayable JSONL audit log in the same PR — see [architecture.md § Observability](architecture.md#observability)), ADR-0074 (weekly staged insight: theme detection, `.last_insight` pending guard, LLM novelty gate, exact fast clustering), ADR-0073 (orphaned view seeds pruned — `config/views/` ships only `self_reflection` + `constitutional`; verified no stale references remain), ADR-0072 (echo-chamber interventions — register instruction, corpus-grown seed exemplar, extraction-failure guard), ADR-0071 (read-only pattern-composition instruments — `core/view_metrics.py`). Dead-code removal (`interaction_count_with`, `Finding.example`, commit `0034980`) verified clean — no remaining references in source or docs. Current aggregate counts live in [Statistics](#statistics) only. Stats-only refresh: 2026-07-11 (live recount; no full regeneration — see [core-modules.md](core-modules.md) for the same-day ADR-0074/0076 section update). Full re-scan: 2026-07-18 (ADR-0079 module reorganization: `core/llm.py` → `core/llm/` package — `__init__.py` facade, `backend.py` Protocol+circuit-breaker, `prompting.py` system-prompt assembly, `guard.py` sanitize/SSRF; `cli.py` (2817L) → `cli/` package — `__init__.py` dispatch (589L) + `runtime.py`/`schedule.py`/`approval.py`/`staging.py`/`adopt.py`/`stocktake_cmd.py`/`memory_cmds.py`/`session_cmds.py`/`__main__.py` (10 files, ~3277L total); `core/insight_novelty.py` and `core/pattern_dedup.py` + `core/episode_render.py` extracted from `insight.py`/`distill.py` — gate logic unchanged, rendering/dedup only. Also folds in ADR-0078 `core/run_context.py` (run_id/session_id minting, missing from the 07-09 scan) and live LOC drift in `adapters/moltbook/` (`agent.py` 753→853L, `client.py` 824→844L, `verification.py` 536→700L, `verification_parse.py` 909→1132L, others adjusted) accumulated since 2026-07-09 across unrelated fix commits. All six codemaps + Statistics recomputed live in this pass. ADR-0080 (north star — per-layer end-state definition, 2026-07-20) is a program-level worldview ADR with no code impact; no codemap changes beyond this note (canonical: [docs/adr/0080](../adr/0080-north-star-layered-end-state.md), pointer section in [docs/CYCLES.md](../CYCLES.md)). ADR-0081 (skill-selection two-pass injection enforcement, accepted 2026-07-24 on the first shadow reading) migrates the three observed generation paths to selected-bodies-only injection, rolled out behind `MOLTBOOK_SKILL_SELECTION_ENFORCE` and **unconditional since the 2026-08-08 amendment retired that flag** on a second reading (15 consecutive days at 100% enforced, fail-open zero for 26 days); the same amendment retires the eval's `deployment_mismatch` check and adds enforced / judged-empty / per-day / never-selected-exposure outputs to `report --skill-selection`; implemented same day — selector return feeds `_selection_system()` in `adapters/moltbook/llm_functions.py`, pass-2 composition via `llm.build_system_prompt_with_skills()`, post_title reuses cooperation_post's selection, fail-open falls back to full injection (canonical: [docs/adr/0081](../adr/0081-skill-selection-two-pass-injection-enforcement.md), see [core-modules.md](core-modules.md) `skill_selection.py` row and [architecture.md](architecture.md) Data Flow). ADR-0083 (episode logs enter the weekly prompt as hashes only, 2026-07-25) adds `scripts/cross_day_duplicate_scan.py` as the weekly report's third deterministic intake and fixes the sweep's state ordering in the same PR — no `src/` change; the pipeline stage is described in [architecture.md § weekly-analysis](architecture.md#weekly-analysis--scriptsweekly-analysissh-adr-0040).  Stats-only refresh: 2026-08-01 (live recount pass — see [Statistics](#statistics); same-day fix commit `6d4d420` had already refreshed Statistics and appended the log-anomaly-sweep signature-keying paragraph to `architecture.md` before this pass). Full re-scan same day: LOC drift corrected across all four detail codemaps (`architecture.md`/`moltbook-agent.md`/`adapters-moltbook.md`/`core-modules.md`) — largest drifts since the 2026-07-18 full scan: `verification_parse.py` 1132→1693L (ADR-0062 11th amendment), `stocktake.py` 504→619L (ADR-0081 usage/description audit), `distill.py` 709→931L (ADR-0084 durability postgate), `llm_functions.py` 361→509L, `skill_selection.py` 472→542L (ADR-0081 enforcement), `schedule.py` 452→594L (ADR-0085 `--weekly-pipeline`/`--watchdog`); most other drift is from the repo-wide `ruff format` pass (`e7928c0`). `core/memory_repos.py` (427L, split from `memory.py` per ADR-0079, four repo classes: InteractionIndex/FollowState/PostHistory/CommentLedger) was already documented in `core-modules.md` but missing from `moltbook-agent.md`'s dependency graph and the `architecture.md` system diagram — added to both. `adapters/moltbook/publish.py` and `verification_parse.py` were similarly missing from the `architecture.md` system diagram — added. `moltbook-agent.md`'s CLI `install-schedule` flag block was stale (pre-ADR-0085) — replaced with the current `--weekly-pipeline`/`--watchdog` flag set (mutually exclusive with `--weekly-analysis`). No hand-authored prose paragraph in `architecture.md` was rewritten or dropped this pass. Stats-only refresh: 2026-08-06 (ADR-0089 LLM behavioral eval layer — new top-level `evals/` (7 modules excl. `__init__.py`: `dataset.py`/`judging.py`/`generation.py`/`compare.py` deterministic core + `adapter_deepeval.py`/`run_eval.py` deepeval wiring + `snapshot_assets.py`), 4 new test files (test count 2481→2530), `[dependency-groups] eval` with deepeval==4.1.5, verify.sh type gate now syncs the eval group; `evals/` is outside `src/` and outside the wheel — no `src/` change, so per-file LOC tables in the detail codemaps are untouched; canonical: [docs/adr/0089](../adr/0089-llm-behavioral-eval-layer-on-deepeval.md)). Full re-scan: 2026-08-09 (LOC + module counts refreshed live across all four detail codemaps — `skill_selection.py` grew most (821→1058L, ADR-0089's configured_injection_regime/selection_preconditions_unmet/observed_injection_outcomes), `submolt_scope.py` 662→761L (distinct-post counting + resample-share reporting), `verification.py` 560→649L (ADR-0062 12th amendment fault column), `_io.py`/`artifact_extraction.py`/`snapshot.py` grew roughly 15-30L each from unrelated fix commits; `adapters-moltbook.md`'s header module count corrected 16→17 moltbook modules (the table already listed 17; only the header undercounted). Two new top-level layers added to CODEMAPS for the first time: the ADR-0088 `testing/` conformance kit (3 modules, ships in the wheel, imports core only — two forbidden import-linter contracts rather than a fourth layer) and the ADR-0089 `evals/` behavioral eval layer (8 modules — `check_staleness.py` added same day as the layer, missed by the 2026-08-06 stats-only pass — deliberately outside `src/` and the wheel, DeepEval-backed, advisory-only staleness warning in verify.sh), both added to `moltbook-agent.md`'s module dependency graph and `architecture.md` gained a Data Flow — Behavioral Eval section. ADR-0090 (IPD two-arm bench for constitution amendments, adopted 2026-08-09) is new this pass: a pre-registered-calibration behavioral reading (`scripts/ipd-two-arm.sh` + `ipd_two_arm_report.py`, cross-repo dependency on contemplative-agent-rules' contemplative-ipd) attached to the human approval packet before every full-constitution amendment — documented in `architecture.md`'s amend-constitution subsection and `dependencies.md`'s new Cross-Repo Instrument Dependencies table; not wired into any gate. `dependencies.md` also gained the full dev-group tool list (hypothesis/bandit/pip-audit/vulture/pyright/ruff, previously only pytest/pytest-cov/responses/import-linter were listed) and a Claude Code CLI (`claude -p`) external-service row (weekly pipeline + eval judge). No hand-authored prose paragraph was dropped this pass; the T-DEADCODE-INTAKE / T-HOME-STANDING-INSTRUCTIONS / submolt-scan fixes / skill-selection rejected-name-tally content already landed in the 2026-08-08 pass and needed no further change beyond the LOC numbers above. Forced refresh: 2026-08-17 (drift probe, no source change since the last codemap commit — `Files scanned` header counts corrected against live `find`/non-`__init__` counts in `architecture.md` (87→79) and `moltbook-agent.md` (75→79), and two pre-existing modules missing from structural inventories were added: `core/constitution_shadow.py` (ADR-0092, existed since 2026-08-11 — present in `architecture.md`'s Data Flow prose and `moltbook-agent.md`'s CLI table but absent from all three module inventories: the System Diagram, `core-modules.md`'s table, and `moltbook-agent.md`'s dependency graph, now added to all three) and `adapters/moltbook/publish.py` (missing only from `moltbook-agent.md`'s dependency graph, added). One real mechanism-level drift found and fixed: `architecture.md`'s Untrusted Boundary section described the rendered-frame validation (`core/llm/guard.py`) as checking only that the nonce binds into both delimiters — `728f6d6` (same-day HIGH regression fix, T-UNTRUSTED-ESCAPE) added a third check, that the body itself survives rendering, after a body-dropping frame passed the nonce-only check and left the ADR-0042 completeness marker asserting a hole was whole; the codemap prose now names `_frame_is_sound` and both conditions. `adapters-moltbook.md`'s Error Handling bullet on the circuit breaker was extended with one sentence noting its 2026-08-16 second role as a per-loop pacing guard (T-REPLY-PACING/T-FEED-PACING, already fully documented in `architecture.md`'s Data Flow) — a completeness gap, not a contradiction. No other mechanism drift found: `dependencies.md` versions were checked against `pyproject.toml` directly and match; `core-modules.md`/`adapters-moltbook.md` LOC and threshold claims not touched by this pass were left as-is.)

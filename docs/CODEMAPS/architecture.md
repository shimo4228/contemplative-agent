<!-- Generated: 2026-05-05 | Files scanned: 43 | Token estimate: ~950 -->
# Architecture

## Project Type
Python application: Contemplative AI agent with core/adapter separation + 3-layer memory + embedding-based views (ADR-0019) + pivot snapshots (ADR-0020) + pattern provenance/bitemporal/forgetting/feedback (ADR-0021). Identity stays monolithic; the block schema attempt (ADR-0024/0025) was withdrawn by ADR-0030; the memory evolution + BM25 hybrid retrieval attempt (ADR-0022) was withdrawn by ADR-0034; the skill-as-memory loop (ADR-0023) was sunset by ADR-0036; the memory subsystem converged to a Yogācāra-aligned frame in ADR-0037. Generation is pluggable via the `LLMBackend` Protocol (default: Ollama HTTP; add-on: `contemplative-agent-cloud`).

**Stats**: 43 modules, ~11400 LOC, 1032 tests (test files: see [INDEX.md](INDEX.md))

## System Diagram

```
                    Contemplative Agent
                    ===================
  config/ (templates only, git-managed — seed for init)
    domain.json       prompts/*.md           templates/constitution/*.md
    views/*.md                                templates/<character>/*  (11 frameworks)
  ~/.config/moltbook/ (MOLTBOOK_HOME, runtime data — user-owned)
    knowledge.json     (learned patterns + embedding + gated + last_view_matches)
    embeddings.sqlite  (episode embedding sidecar, ADR-0019)
    identity.md        (system prompt, readonly)
    constitution/      (ethical principles; init copies from template)
    views/*.md         (user-editable seed views; init copies packaged default)
    prompts/*.md       (user-editable prompt templates; init copies packaged default)
    skills/*.md        (behavior patterns; init copies template, later insight-generated)
    rules/*.md         (universal rules; init copies template, later rules-distill)
    snapshots/*/       (pivot snapshots, ADR-0020 — manifest + full runtime context)
    logs/              (episode JSONL + audit.jsonl)
         |
         v
  +-----------------------------------------------------+
  | src/contemplative_agent/                             |
  |                                                      |
  |  core/  (platform-independent, 25 modules)          |
  |    _io.py  config.py  domain.py  prompts.py         |
  |    llm.py (+ LLMBackend Protocol)  embeddings.py    |
  |    episode_embeddings.py  episode_log.py            |
  |    knowledge_store.py  memory.py                    |
  |    views.py  snapshot.py                            |
  |    distill.py  insight.py  constitution.py          |
  |    rules_distill.py  stocktake.py  scheduler.py     |
  |    report.py  metrics.py  forgetting.py             |
  |    clustering.py                                     |
  |    text_utils.py  thresholds.py                     |  (ADR-0035 PR2 helpers)
  |    artifact_extraction.py                           |  (ADR-0035 PR3a helper)
  |                                                      |
  |  adapters/moltbook/  (platform-specific, 12 modules)|
  |    agent.py  session_context.py  feed_manager.py    |
  |    reply_handler.py  post_pipeline.py               |
  |    client.py  auth.py  verification.py              |
  |    llm_functions.py  content.py  config.py          |
  |    dedup.py                                          |
  |                                                      |
  |  adapters/meditation/  (experimental, 4 modules)    |
  |    config.py  pomdp.py  meditate.py  report.py      |
  |                                                      |
  |  adapters/dialogue/  (2-agent peer loop, 1 module)  |
  |    peer.py                                           |
  |                                                      |
  |  cli.py  (composition root, ~1826L)                 |
  +-----------------------------------------------------+
         |                              |
    Moltbook API                   Ollama (local, default)
    (www.moltbook.com)             qwen3.5:9b  (generation)
    rate-limited (60GET/30POST)    nomic-embed-text  (embedding, 768-dim)
                                   │
                                   ╰─ Pluggable via LLMBackend Protocol
                                      (contemplative-agent-cloud add-on)
```

## Import Rule

```
core/ ←── adapters/moltbook/   ←── cli.py (composition root)
 ↑         adapters/meditation/      |
 |         adapters/dialogue/        |
 |                                   |
 +--- only composition root imports from both
```

- **core/ は adapters/ を import しない** (依存方向: adapters → core)
- cli.py は唯一の例外: core/ と adapters/ の両方を import
- meditation / dialogue adapter は core/ のみに依存 (moltbook adapter を import しない)
- core/ モジュールはコンストラクタ引数で設定を受け取る (パラメータ化)
- adapters/ が core/config の定数と adapter 固有の config を組み合わせて渡す
- 協力者 (ReplyHandler, PostPipeline, FeedManager) は Agent を import しない。SessionContext + Callable で依存注入

## Init-Time Copy Policy

`contemplative-agent init [--template NAME]` copies *every* Markdown file the agent
consults at runtime from `config/` into `MOLTBOOK_HOME`:

- **Template-derived** (varies by `--template`): `constitution/`, `skills/`, `rules/`
- **Shared runtime** (not template-specific): `prompts/`, `views/`

User edits under `MOLTBOOK_HOME` surface via git-diff against `config/` and are
captured in pivot snapshots (ADR-0020) for replayability. Existing directories
are never overwritten; missing sources fall back to empty `mkdir`.

See `cli._do_init` (`copy_or_create_dir` helper) for the single execution path.

## LLM Backend Pluggability

`core/llm.py` defines the `LLMBackend` Protocol (`runtime_checkable`) with a
single `generate(prompt, system, num_predict, format, ...)` method. A single
module-level `_backend` slot is populated via `configure(backend=...)`:

- **Default** (`_backend = None`): built-in Ollama HTTP path.
- **Add-on**: `contemplative-agent-cloud` injects a managed-LLM backend so the
  same CLI works without a local Ollama.

Sanitization (`_sanitize_output`), circuit breaker, and untrusted-content
wrapping remain in `core/llm.py` and apply uniformly regardless of backend.

## Immutability

- DTO とドメインオブジェクトは `frozen=True`。例外なし
- accumulator パターンは reduce か一括生成で書く (mutation で書かない)
- 蒸留パイプラインの原典保持、承認ゲートの diff 生成、bitemporal との整合のため

## Data Flow — Session Execution

```
CLI (argparse) → Agent.run_session(autonomy_level, session_mins)
 |
 +-> ReplyHandler._run_reply_cycle()  -- notifications → reply → post
 |    └─ SessionContext (shared state)
 |
 +-> Agent._run_feed_cycle()          -- feed → score → comment
 |    └─ FeedManager (fetch, score, deduplicate)
 |
 +-> PostPipeline._run_post_cycle()   -- feed seeds → NoveltyGate → post
 |    └─ feed_seeder.select_feed_seeds() + NoveltyGate (ADR-0039, 0043)
 |
 └─ MemoryStore.record() → EpisodeLog (append-only JSONL)
    └─ ~.config/moltbook/logs/YYYY-MM-DD.jsonl
```

## Data Flow — Offline Learning (embedding classify + 3-step distill + insight + meditation)

Every behaviour-producing command below writes a pivot snapshot
(`snapshots/{cmd}_{ts}/`) at run start via `core/snapshot.py` and threads
its path into the `audit.jsonl` record (ADR-0020).

```
distill (nightly — embedding classify + 3-step per category):
  Step 0 — Embedding classify (ADR-0019, NO LLM call):
    embed_texts(episode summaries) → cosine vs noise and constitutional view centroids
    → noise | constitutional | uncategorized
    → noise excluded
  Step 1-3 per category (batch_size=30):
    → LLM (DISTILL_PROMPT / DISTILL_CONSTITUTIONAL_PROMPT) → raw patterns
    → LLM (DISTILL_REFINE_PROMPT) → JSON patterns
    → LLM (DISTILL_IMPORTANCE_PROMPT) → scores
    → _dedup_patterns() uses embedding cosine (SIM_DUPLICATE=0.92, SIM_UPDATE=0.80)
    → KnowledgeStore.add_learned_pattern(... embedding=..., gated=...)
    → write MOLTBOOK_HOME/knowledge.json

distill-identity (2-stage, view-driven input):
  Input: patterns matching the self_reflection view (top 50 by importance).
  Stage 1 — Extract:  LLM (IDENTITY_DISTILL_PROMPT) → raw identity material
  Stage 2 — Refine:   LLM (IDENTITY_REFINE_PROMPT)  → concise persona
  → update MOLTBOOK_HOME/identity.md (with archive, approval-gated)

insight (manual, approval gate, view-driven batching):
  For each loaded view (except noise / constitutional / self_reflection),
    rank non-gated patterns by cosine vs view centroid, top-10 by importance
    → LLM (INSIGHT_EXTRACTION_PROMPT) → one skill Markdown
  → generate MOLTBOOK_HOME/skills/*.md (per-file approval)

rules-distill (manual, approval gate, Practice/Rationale B-layer format):
  skills/*.md → LLM (RULES_DISTILL_PROMPT)        → principles
             → LLM (RULES_DISTILL_REFINE_PROMPT) → structured Markdown
  → generate MOLTBOOK_HOME/rules/*.md

amend-constitution (manual, approval gate):
  Patterns matching the constitutional view + current constitution
  → LLM (CONSTITUTION_AMEND_PROMPT) → amended clauses
  → update MOLTBOOK_HOME/constitution/*.md

meditate (experimental):
  EpisodeLog → POMDP matrices (A/B/C/D)
  → Active Inference cycles (temporal flattening + counterfactual pruning)
  → KnowledgeStore write via meditation report
```

## Memory Architecture (3-Layer + Sidecars)

```
Layer 1: EpisodeLog (append-only, runtime)
  ~/.config/moltbook/logs/YYYY-MM-DD.jsonl
    - "post", "comment", "interaction", "action", "insight", "session"
  ~/.config/moltbook/embeddings.sqlite
    - Episode summary embeddings (ADR-0019 sidecar for view queries)

Layer 2: KnowledgeStore (distilled patterns, daily batch)
  MOLTBOOK_HOME/knowledge.json  ← updated by distill (embedding classify + 3-step + embedding dedup)
    [{"pattern": "...", "distilled": "...", "importance": 0.7,
      "embedding": [...], "gated": false,
      "last_classified_at": "...", "last_view_matches": {...}  (ADR-0020 telemetry)}, ...]

Layer 3: Identity (system prompt, infrequent updates)
  MOLTBOOK_HOME/identity.md  ← updated by distill-identity (2-stage, self_reflection view)

Pivot Snapshots (per behaviour-producing run, ADR-0020)
  MOLTBOOK_HOME/snapshots/{cmd}_{ts}/
    - manifest.json  (thresholds, model, view names)
    - views/*.md     (lens definitions at run time)
    - constitution/*.md  (seed_from source)
    - centroids.npz  (7 × 768-dim float32 for replay)

Agents (follow state, per-session)
  ~/.config/moltbook/agents.json
```

## AKC (Agent Knowledge Cycle) Mapping

contemplative-moltbook の学習パイプラインは [AKC](https://github.com/shimo4228/agent-knowledge-cycle) の6フェーズに対応する。AKC は Claude Code ハーネスの自己改善ループ。本プロジェクトはこれを自律エージェントの文脈で再実装している。

| AKC Phase | AKC Skill | 本プロジェクトの実装 | コード | プロンプト |
|-----------|-----------|---------------------|--------|-----------|
| Research | search-first | フィード取得 + relevance scoring | feed_manager.py | relevance.md |
| Extract | learn-eval | `distill` (embedding classify + 3-step + embedding dedup) | distill.py, views.py | distill.md, distill_constitutional.md, distill_refine.md, distill_importance.md |
| Curate | skill-stocktake | `insight` (view-driven knowledge → skills) | insight.py, views.py | insight_extraction.md |
| Curate | rules-distill | `rules-distill` (skills → Practice/Rationale rules) | rules_distill.py | rules_distill.md, rules_distill_refine.md |
| Curate | — | `amend-constitution` (constitutional view → ethics) | constitution.py | constitution_amend.md |
| Promote | — | `distill-identity` (self_reflection view → persona) | distill.py, views.py | identity_distill.md, identity_refine.md |
| Measure | skill-comply | pivot snapshots + per-pattern `last_view_matches` (replay foundation, ADR-0020) | snapshot.py | — |
| Maintain | context-sync | 外部ツール (Claude Code skill) + sync-data | — | — |

**差異**:
- **Measure** (skill-comply): エージェント自身のスキル遵守率を定量計測する仕組みは未実装
- **Maintain** (context-sync): ドキュメント整合性チェックは Claude Code skill として外部化。sync-data でランタイムデータを研究リポジトリに同期

## Prior Art — Memory System Comparison

| | Generative Agents | MemGPT/Letta | A-MEM | Mem0 | **This System** |
|---|---|---|---|---|---|
| **Retrieval** | 3-score (recency + importance + relevance) | LLM function call page-in | Embedding cosine similarity | Vector + graph | importance top-K |
| **Distillation** | Reflection (automatic) | None | Memory evolution (LLM) | ADD/UPDATE/DELETE gate | 3-step + LLM dedup gate |
| **Importance** | LLM 1-10 rating | None | None | None | LLM 1-10 + time decay (0.95^days) |
| **In-session update** | Yes | Yes (function call) | Yes | Yes | No (intentional) |
| **Dependencies** | GPT-4 | GPT-4 + DB | all-minilm-l6-v2 | Multiple VectorStore | Ollama (local, 9B) |

### Cognitive Architecture Mapping (TMLR 2024 survey)

| Cognitive Architecture | This System | Notes |
|------------------------|-------------|-------|
| Working Memory | In-session MemoryStore | Lost on session end |
| Episodic Memory | EpisodeLog (JSONL) | Permanently retained as research material |
| Semantic Memory | KnowledgeStore (JSON) | importance + time decay + LLM quality gate |
| Procedural Memory | skills/*.md, rules/*.md, prompts.py | Auto-generated via insight/rules-distill |

### Paper References

| Paper | Relation |
|-------|----------|
| Park et al. (2023) Generative Agents | 3-score retrieval. Reference for importance design |
| Packer et al. (2023) MemGPT | Virtual memory approach. In-session updates deferred |
| Xu et al. (2025) A-MEM | Zettelkasten style. Reference for Phase 4 (keywords) |
| Choudhary et al. (2025) Mem0 | ADD/UPDATE/DELETE gate. Reference for quality gate |
| Sumers et al. (2024) Cognitive Architectures | 4-type memory classification framework |

## Entry Points
- `contemplative-agent` → `contemplative_agent.cli:main`
- `docker compose up` → entrypoint loop with auto-distill
- Tests: `pytest tests/ -v`

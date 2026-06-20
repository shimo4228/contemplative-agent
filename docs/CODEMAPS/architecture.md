<!-- Generated: 2026-06-20 | Files scanned: 44 | Token estimate: ~2575 -->
# Architecture

## Project Type
Python CLI agent: core/adapter separation + 3-layer memory + embedding views (ADR-0019) + pivot snapshots (ADR-0020) + pattern provenance/bitemporal (ADR-0021) + trust retirement (ADR-0051). Generation pluggable via `LLMBackend` Protocol (default: Ollama; add-on: `contemplative-agent-cloud`).

**Stats**: 44 non-`__init__` modules (50 total `.py`), ~13592 LOC, 1301 tests / 35 test files

## System Diagram

```
  config/ (templates, git-managed)       ~/.config/moltbook/ (MOLTBOOK_HOME, runtime)
    domain.json  prompts/*.md              knowledge.json  embeddings.sqlite  identity.md
    views/*.md   templates/<char>/11       constitution/  views/  prompts/  skills/  rules/
                                           snapshots/  logs/  agents.json
         |
         v
  src/contemplative_agent/
    core/  (24 modules, platform-independent)
      _io  config  domain  prompts  llm(+LLMBackend)  embeddings
      episode_embeddings  episode_log  knowledge_store  memory
      views  snapshot  scheduler  distill  insight  constitution
      rules_distill  stocktake  report  metrics  clustering
      text_utils  thresholds  artifact_extraction
    adapters/moltbook/  (14 modules)
      agent  session_context  feed_manager  reply_handler  post_pipeline
      client  auth  verification  content  llm_functions  config
      dedup  novelty  feed_seeder
    adapters/meditation/  (4 modules, experimental)  config  pomdp  meditate  report
    adapters/dialogue/  (1 module)  peer.py
    cli.py  (composition root, 2024L)
         |                       |
    Moltbook API            Ollama (local default)
    60GET/30POST/min        qwen3.5:9b + nomic-embed-text (768-dim)
```

## Import Rule
`core/ ← adapters/ ← cli.py` (one direction). `cli.py` is the only file importing both. Meditation/dialogue adapters depend on core/ only; they do not import moltbook adapter.

## Init-Time Copy
`contemplative-agent init [--template NAME]` copies every runtime Markdown from `config/` into `MOLTBOOK_HOME`. Template-derived: `constitution/`, `skills/`, `rules/`. Shared: `prompts/`, `views/`. Existing dirs never overwritten.

## LLM Backend
`core/llm.py` `LLMBackend` Protocol: `generate(prompt, system, num_predict, format, ...)`. Module-level `_backend` slot set via `configure(backend=...)`. Sanitization + circuit breaker apply uniformly.

## Immutability
All DTOs `frozen=True`. Required by approval-gate diff pipeline and bitemporal invariants.

---

## Data Flow — Session Execution

```
CLI → Agent.run_session(autonomy_level, session_mins)
 ├─ ReplyHandler._run_reply_cycle()
 │    internal_note (ADR-0045) → reply → post → EpisodeLog
 ├─ Agent._run_feed_cycle()
 │    fetch → promo filter → ID dedup → per-author cap (3/24h)
 │    → score_relevance (LLM) → comment → Scheduler budget gate
 ├─ PostPipeline._run_post_cycle()
 │    feed_seeder.select_feed_seeds()        [ADR-0043]
 │      relevance ≥ 0.4 | RNG 1-3 posts | 15000-char budget
 │    → NoveltyGate.evaluate()               [ADR-0039]
 │      cosine vs recent self-posts + temporal decay + rate-deficit Lagrangian
 │    → is_test_content() → body-hash (SHA-256[:16])
 │    → generate_cooperation_post → post
 └─ MemoryStore.record() → EpisodeLog (append-only JSONL)
```

---

## Data Flow — Offline Learning

Every behaviour-producing command writes a pivot snapshot (`snapshots/{cmd}_{ts}/`) at run start (ADR-0020) and threads its path into `audit.jsonl`.

All offline distillation LLM calls (distill / insight / rules-distill / constitution amend / distill-identity) run under a **base-only system prompt** — the four axioms are NOT injected. Value layers belong to action time only; `get_distill_system_prompt` is base-only since ADR-0058 (their inputs are already value-shaped, and fresh external observation should be extracted faithfully, not re-interpreted through a value lens). Axioms are injected only at action time (`_build_system_prompt`, `get_identity_system_prompt`).

### distill  [`core/distill.py`]

```
Input: EpisodeLog.read_range(days=N)
  type="insight" records EXCLUDED at read  [ADR-0052: retired session
  summaries; historical records stay in the log but never re-distill]

Step 0 — Binary noise gate  [ADR-0026; NO LLM]
  embed_texts(episode summaries) → cosine(summary, noise_centroid)
  ≥ NOISE_THRESHOLD (0.55)  →  gated (noise-*.jsonl, ADR-0027)
  < NOISE_THRESHOLD          →  kept

Step 1 — Extract  [batch_size=30]
  kept → LLM(DISTILL_PROMPT) → raw patterns

Step 2 — Refine
  → LLM(DISTILL_REFINE_PROMPT) → JSON {"patterns":[...]}

Step 3 — Persist  [no LLM; the importance-scoring call was retired, ADR-0056]
  → embed_texts(new patterns)
  → _dedup_patterns():
      effective_importance = 0.95^days   [pure time decay; ADR-0051, ADR-0056]
      skip rows below DEDUP_IMPORTANCE_FLOOR (0.05) → ~58 days, uniform
      cosine(new, existing):
        ≥ SIM_DUPLICATE (0.90)  →  SKIP
        ≥ SIM_UPDATE    (0.80)  →  UPDATE (soft-invalidate old, append revised — no boost)
        < SIM_UPDATE             →  ADD
  → KnowledgeStore.add_learned_pattern(..., embedding, gated=False)  [no importance field]
  → provenance.source_type recorded, NEVER weighted  [ADR-0051]
```

Threshold canonical source: `core/thresholds.py` (read by `snapshot.collect_thresholds`).

### distill-identity  [`core/distill.py: distill_identity()`]

```
ViewRegistry.find_by_view("self_reflection", get_raw_patterns())
  cosine(pattern_emb, self_reflection_centroid)
  threshold from view frontmatter | top_k=50   [PURE COSINE, no importance weight]

Single LLM call: LLM(IDENTITY_DISTILL_PROMPT, matched patterns only)
  [ADR-0057: prior identity NOT seeded — persona emerges from the corpus alone]
  [base-only system prompt; axioms not injected — ADR-0058]
→ validate_identity_content()
→ IdentityResult(text, target_path, pattern_ids, epistemic_counts)  [ADR-0050]
→ write gated by cli.py approval → MOLTBOOK_HOME/identity.md  [ADR-0012]
```

No Stage 2 refine. No importance-ranked input. One LLM call only.

### insight  [`core/insight.py: extract_insight()`]

```
Input: KnowledgeStore.get_live_patterns()   [is_live: valid_until is None]
  gated=True excluded before clustering

GLOBAL embedding clustering  [NOT per-view; ADR-0026]
  cluster_patterns(threshold=CLUSTER_THRESHOLD_INSIGHT=0.70)  [core/clustering.py]
  cluster size ≥ MIN_PATTERNS_REQUIRED (3)  →  eligible

Ordering: cluster_size × mean(effective_importance)  descending
  effective_importance = 0.95^days   [pure time decay; ADR-0056]
Slicing: each cluster → top MAX_BATCH (10) by effective_importance (= freshest)

Per cluster → LLM(INSIGHT_EXTRACTION_PROMPT, topic="cluster-N")
  system = axioms-only (no skill corpus injected — audit H6 fix, a2bebfe)
  → validate_identity_content()
  → SkillResult(text, filename, target_path, pattern_ids, epistemic_counts)  [ADR-0050]

→ InsightResult   →   write gated by cli.py per-file approval  [ADR-0012]
```

Views NOT used for batching. Every eligible cluster becomes a batch (no top-N cluster cap).

### rules-distill  [`core/rules_distill.py: distill_rules()`]

```
skills/*.md (MIN=3) → embed_texts → cluster(CLUSTER_THRESHOLD_RULES=0.65)
  → batches (MAX_BATCH=10)
  → LLM(RULES_DISTILL_PROMPT) → LLM(RULES_DISTILL_REFINE_PROMPT)
  → RuleResult(text, filename, target_path, source_ids)  [ADR-0050; source_ids=skill filenames]
→ write gated  [ADR-0012]
```

### amend-constitution  [`core/constitution.py`]

```
ViewRegistry.find_by_view("constitutional", get_live_patterns())
  MIN_PATTERNS_REQUIRED=3 gate
→ LLM(CONSTITUTION_AMEND_PROMPT) → AmendmentResult(... pattern_ids, epistemic_counts)
→ write gated  [ADR-0012]
```

### Approval lineage  [ADR-0050]

`SkillResult` / `RuleResult` / `IdentityResult` / `AmendmentResult` all carry `source_ids` / `pattern_ids` + `epistemic_counts`. On approval: `audit.jsonl` record includes `source_ids + epistemic_counts` (always present, nullable). `staging/meta.json` carries them through `adopt-staged`.

`epistemic_counts` = `{observed, generated, unknown}` tally; the kind is derived at read-time from `provenance.source_type` — never persisted. Caveat: `observed ≈ 0` is structural (pure-external distill batches don't occur at batch granularity), not "no external input" — external contact lives inside `mixed → generated`.

### meditate  [`adapters/meditation/`]

```
EpisodeLog → pomdp.build_matrices() → A/B/C/D (numpy)
→ meditate(matrices, config)
  flat single-level POMDP; expected-free-energy policy selection
  "temporal flattening" / "counterfactual pruning" = LOCAL LABELS, not paper terms
  INSPIRED BY (not implementing) Laukkonen, Friston & Chandaria (2025)  [ADR-0049]
→ report.interpret_and_save() → config/meditation/results.json
  LLM interpretation display-only; NO KnowledgeStore write; deferred  [ADR-0049]
```

---

## Memory Architecture (3-Layer)

```
Layer 1: EpisodeLog  ~/.config/moltbook/logs/YYYY-MM-DD.jsonl  (append-only)
  record_type: post | comment | interaction | action | session
               | insight (historical only — generation retired, ADR-0052)
  + embeddings.sqlite (episode embedding sidecar, ADR-0019)

Layer 2: KnowledgeStore  MOLTBOOK_HOME/knowledge.json
  {pattern, distilled, embedding[768], gated, last_view_matches,
   provenance:{source_type, source_episode_ids, pipeline_version},
   valid_from, valid_until}                               [importance field retired, ADR-0056]
  effective_importance = 0.95^days                        [pure time decay; ADR-0056]
  is_live             = valid_until is None ONLY          [knowledge_store.is_live, ADR-0051]
  origin (source_type) = recorded, NEVER weighted         [ADR-0051]
  pattern_id          = sha256(distilled|pattern)[:12]    [ADR-0050]

Layer 3: Identity  MOLTBOOK_HOME/identity.md  (distill-identity, single-stage)

Pivot Snapshots  MOLTBOOK_HOME/snapshots/{cmd}_{ts}/
  manifest.json | views/*.md | constitution/*.md | centroids.npz  [ADR-0020]
```

**Deleted**: `forgetting.py` (ADR-0051) — `is_live` moved to `knowledge_store.py` (bitemporal-only, no trust floor).
**Retired fields**: `trust_score`/`trust_updated_at` (ADR-0051), `last_accessed_at`/`access_count` (ADR-0028), `provenance.sanitized` (ADR-0029), `category` (ADR-0026).

---

## AKC Mapping

| AKC Phase | Implementation | Code |
|-----------|----------------|------|
| Research | Feed fetch + relevance scoring | feed_manager.py |
| Extract | `distill` (noise gate + 2-step + embedding dedup) | distill.py, views.py |
| Curate | `insight` (global clustering → skills) | insight.py, clustering.py |
| Curate | `rules-distill` (skills → Practice/Rationale rules) | rules_distill.py |
| Curate | `amend-constitution` (constitutional view → ethics) | constitution.py |
| Promote | `distill-identity` (self_reflection view → persona) | distill.py, views.py |
| Measure | Pivot snapshots + `last_view_matches` telemetry | snapshot.py |
| Maintain | `context-sync` (Claude Code skill) + sync-data | — |

## Entry Points
- `contemplative-agent` → `contemplative_agent.cli:main`
- `docker compose up` → entrypoint loop with auto-distill
- Tests: `pytest tests/ -v`

<!-- Generated: 2026-05-05 | Files scanned: 25 core modules | Token estimate: ~1450 -->
# Core Modules Codemap

Platform-independent foundation (no Moltbook dependencies). All imports flow: adapters → core.

## Module Overview

| Module | LOC | Purpose |
|--------|-----|---------|
| `_io.py` | 46 | `write_restricted(path, mode, content)`, `truncate(path)`, `archive_before_write(path, history_dir)` |
| `config.py` | 28 | `FORBIDDEN_SUBSTRING_PATTERNS`, `VALID_ID_PATTERN`, `MAX_COMMENT_LENGTH` |
| `domain.py` | 362 | `DomainConfig`, `PromptTemplates` (reads `MOLTBOOK_HOME/prompts/` overrides with packaged fallback), constitution loader |
| `prompts.py` | ~70 | Lazy-load proxy to `config/prompts/*.md` + placeholder resolution |
| `llm.py` | 553 | Ollama interface + `LLMBackend` Protocol (pluggable generation), circuit breaker, sanitization; `_build_system_prompt` reads identity.md as a single text blob (legacy whole-file path restored by ADR-0030) |
| `clustering.py` | ~115 | Average-linkage cosine agglomerative clustering (ADR-0019 companion, numpy-only). Used by `insight` and `rules_distill` to bucket embedded corpus without a predefined view axis |
| `embeddings.py` | 144 | Ollama `/api/embed` wrapper (nomic-embed-text), `cosine`, `embed_one`, `embed_texts` |
| `episode_embeddings.py` | 174 | `EpisodeEmbeddingStore` — SQLite sidecar for episode vectors (ADR-0019) |
| `episode_log.py` | ~100 | `EpisodeLog` (append-only JSONL, `read_range` with `record_type` filter) |
| `knowledge_store.py` | 335 | `KnowledgeStore` — patterns JSON + provenance/trust/bitemporal fields (ADR-0021; forgetting/feedback retired by ADR-0028, `provenance.sanitized` retired by ADR-0029) + view telemetry (ADR-0020); `get_live_patterns()` / `get_live_patterns_since()` apply `is_live` filter at the API boundary so readers (insight, retrieval) do not import `forgetting` directly |
| `memory.py` | 499 | `MemoryStore` facade, `Interaction`/`PostRecord`/`Insight` dataclasses, query helpers |
| `views.py` | 309 | `ViewRegistry` — seed-text views with `seed_from` + `${VAR}` substitution, lazy centroid cache, embedding cosine ranking (BM25 hybrid retrieval was withdrawn by ADR-0034) |
| `snapshot.py` | 160 | `write_snapshot()` + `collect_thresholds()` — pivot snapshots per ADR-0020. Reads thresholds from `core/thresholds.py` registry |
| `forgetting.py` | 33 | Retrieval gate (ADR-0021 IV-2/IV-7 + ADR-0028 retirement): `TRUST_FLOOR`, `is_live(pattern)` — bitemporal + trust floor only. Ebbinghaus strength and mark_accessed were retired by ADR-0028. |
| `scheduler.py` | 165 | Rate limit state, `has_read_budget`/`has_write_budget`, persistence |
| `constitution.py` | 130 | `amend_constitution()` → `AmendmentResult`. ADR-0033 layer-separation framing applied to amendment prompt (constitutional values stay above operational specifics) |
| `distill.py` | 823 | `distill()` w/ embedding centroid classify (ADR-0019) + provenance/trust/bitemporal write (ADR-0021); `distill_identity()` reads/writes identity.md as a single text blob (legacy whole-file path restored by ADR-0030). `memory_evolution` pass (ADR-0022) was removed by ADR-0034 |
| `insight.py` | 282 | `extract_insight()` → `InsightResult`; view-driven batch building. Pulls live-only patterns via `KnowledgeStore.get_live_patterns` and ranks batches by `effective_importance` (importance × trust × 0.95^days; strength factor retired by ADR-0028). Uses `text_utils` + `artifact_extraction` helpers (ADR-0035 PR2/PR3) |
| `rules_distill.py` | 348 | `distill_rules()` → `RulesDistillResult`; Practice/Rationale B-layer format. Uses `text_utils` + `artifact_extraction` helpers (ADR-0035 PR2/PR3) |
| `stocktake.py` | 368 | Skill/rule audit: embedding-only clustering at `SIM_CLUSTER_THRESHOLD=0.80`, `merge_group()` with `CANNOT_MERGE` reject. Uses `text_utils._strip_frontmatter` (broken `stocktake → rules_distill` import edge by ADR-0035 PR2) |
| `report.py` | 256 | `generate_report()` JSONL → Markdown activity summary |
| `metrics.py` | 160 | Session metrics aggregation (actions, topics, engagement) |
| `text_utils.py` | 60 | **NEW (ADR-0035 PR2)**: shared Markdown helpers (`slugify`, `extract_title`, `_strip_frontmatter`) — promoted from insight/rules_distill to break the stocktake → rules_distill edge |
| `thresholds.py` | 90 | **NEW (ADR-0035 PR2)**: centralized retrieval/classification thresholds (`NOISE_THRESHOLD`, `SIM_DUPLICATE`, `SIM_UPDATE`, `DEDUP_IMPORTANCE_FLOOR`, etc.) with ADR / calibration date / unit annotations. `snapshot.collect_thresholds` reads from here so new values appear in pivot snapshots automatically |
| `artifact_extraction.py` | 69 | **NEW (ADR-0035 PR3a)**: shared `extract_title → slugify → path-escape guard` chain for insight/rules-distill LLM artifact bodies. Tightly scoped — does not become a base class for the broader extract→validate→stage loop (ADR-0024/0025 was withdrawn by ADR-0030) |

**Total: ~5660 LOC (25 modules) — adapters / cli account for the remaining ~5730 LOC**

## Key Dataclasses

All frozen (immutable) with type hints.

**core/memory.py** — Domain models:
```python
Interaction(timestamp, agent_id, agent_name, type, direction)
PostRecord(timestamp, post_id, title, topic)
Insight(timestamp, observation, insight_type)
```

**ADR-0012 Result types** — core 関数が返す生成結果。ファイル書き込みは cli.py が承認後に実行:
```python
AmendmentResult(text, target_path, marker_dir)           # constitution.py
IdentityResult(text, target_path)                        # distill.py (whole-file, restored by ADR-0030)
SkillResult(text, filename, target_path)                 # insight.py
InsightResult(skills, dropped_count, skills_dir)
RuleResult(text, filename, target_path)                  # rules_distill.py
RulesDistillResult(rules, dropped_count, rules_dir)
```

## EpisodeLog Schema (JSONL)

Daily log at `logs/YYYY-MM-DD.jsonl`. Each record:
```json
{"type": "post|comment|interaction|action|insight|session", "ts": "...", ...}
```
`record_type` filter: `EpisodeLog.read_range(days=3, record_type="interaction")`.

Embedding sidecar (`embeddings.sqlite`, ADR-0019) indexes episode summaries for view queries.

## KnowledgeStore Schema (JSON)

File: `~/.config/moltbook/knowledge.json`. Each pattern (post-ADR-0021):
```json
{
  "pattern": "…",
  "distilled": "2026-04-16T…",
  "importance": 0.7,
  "embedding": [..768 floats..],
  "gated": false,
  "last_classified_at": "2026-04-16T02:15:33Z",
  "last_view_matches": {"constitutional": 0.72, "noise": 0.12, …},

  "provenance": {"source_type": "self_reflection|external_reply|mixed|unknown",
                 "source_episode_ids": ["..."],
                 "pipeline_version": "distill@0.26"},
  "trust_score": 0.9,
  "trust_updated_at": "2026-04-16T…",
  "valid_from": "2026-04-16T…",
  "valid_until": null
}
```
**Invariants**:
- Patterns only; agents/topics/insights live in JSONL.
- `gated` is behavioural (skipped in distill dedup); `last_view_matches` is read-only telemetry (ADR-0020 — never branch on it).
- `valid_until=None` means live; superseded rows keep the timestamp (bitemporal soft-invalidate, ADR-0021). Retrieval must filter via `forgetting.is_live(p)`.
- `effective_importance = importance × trust_score × 0.95^days_since_distilled` — see `knowledge_store.effective_importance` (ADR-0021 + ADR-0028 strength-factor retirement).
- `last_accessed_at` / `access_count` / `success_count` / `failure_count` fields retired by ADR-0028.
- `provenance.sanitized` flag + `source_type=user_input|external_post` retired by ADR-0029 (dormant at landing; MINJA defense is structurally quarantine at `summarize_record`, not trust-weighting).
- `category` field removed by ADR-0026. Legacy `category` keys are silently dropped on the next save; the `migrate-categories` rewrite command was retired (ADR-0035) once active deployments finished migrating. Legacy `category == "noise"` is preserved as `gated = True` only for stores that already ran the migration on a v2.0.x release tag.

## LLM Functions (core/llm.py)

**Configuration** via `configure(...)`:
```python
configure(identity_path=..., ollama_url="http://localhost:11434",
          axiom_prompt="<constitutional_clauses>", model="qwen3.5:9b",
          backend=None)        # default: built-in Ollama HTTP
```

**Pluggable backend** (`LLMBackend` Protocol, `runtime_checkable`):
```python
class LLMBackend(Protocol):
    def generate(self, prompt: str, system: str, num_predict: int,
                 format: Optional[Dict], ...) -> str: ...
```
When `_backend` is set via `configure(backend=...)`, `generate()` delegates to
the backend; sanitization, circuit breaker, and `wrap_untrusted_content` stay
in this module and apply uniformly. Used by the
`contemplative-agent-cloud` add-on to route generation through a managed LLM.

**Circuit breaker**: 5 consecutive failures → open for 120s.

Reused surface exposed to adapters via `llm_functions.py`: `score_relevance`, `generate_comment`, `generate_reply`, `generate_cooperation_post` (post-ADR-0043 takes `feed_seeds: list[dict]`), `format_feed_seeds`, `generate_post_title`, `summarize_post_topic`, `select_submolt`, `generate_session_insight`, plus the generic `generate(prompt, system_prompt, …)` used by distill / insight / rules / constitution / stocktake. `extract_topics` and `check_topic_novelty` remain exported as orphaned helpers since ADR-0043 retired the self-post summary path.

All output passes `_sanitize_output()`. All external inputs → `wrap_untrusted_content()`.

## Views Mechanism (ADR-0019)

`ViewRegistry` replaces the former `category`/`subcategory` string fields. Each view is a Markdown file under `~/.config/moltbook/views/` (user) or `config/views/` (packaged fallback) with YAML frontmatter:

```
---
threshold: 0.55
top_k: 50
seed_from: ${CONSTITUTION_DIR}/*.md
---
Fallback body (used when seed_from resolves to nothing).
```

- **`seed_from`** resolves glob patterns; `${VAR}` substitutes from `path_vars` passed to the registry (currently only `CONSTITUTION_DIR`). Honours `--constitution-dir` override.
- **Centroids** lazily computed on first `get_centroid(name)` call and cached per instance.
- **Seed views** ship in `config/views/`: `communication`, `constitutional`, `noise`, `reasoning`, `self_reflection`, `social`, `technical`.

## Distill Pipeline (core/distill.py)

### Knowledge Distill (`distill()`)

```
Step 0 — Embedding gate (ADR-0019/ADR-0026, no LLM):
  embed all episode summaries → cosine against the noise view centroid
  → gated (sim ≥ 0.55, excluded from distill) | kept (otherwise)
  Constitutional / uncategorized routing collapsed into a single "kept"
  bucket — topic routing happens at query time via views.

Step 1 — Extract (batch_size=30):
  kept → LLM(DISTILL_PROMPT) → repeated-fact patterns

Step 2 — Refine:
  → LLM(DISTILL_REFINE_PROMPT) → JSON {"patterns": [...]}
  → _is_valid_pattern() filter

Step 3 — Score and persist:
  → LLM(DISTILL_IMPORTANCE_PROMPT) → {"scores": [...]}
  → _dedup_patterns() uses embedding cosine (SIM_DUPLICATE=0.90, SIM_UPDATE=0.80)
  → KnowledgeStore.add_learned_pattern(..., embedding=..., gated=...)
```

**Thresholds** (canonical list in `snapshot.collect_thresholds()`):
`NOISE_THRESHOLD=0.55`, `SIM_DUPLICATE=0.90`, `SIM_UPDATE=0.80`, `DEDUP_IMPORTANCE_FLOOR=0.05`.

### Identity Distill (`distill_identity() → IdentityResult`)

Input: patterns matching the `self_reflection` view (top 50 by importance), not raw subcategory strings. Behavioural rules route to `insight`; identity stays observational.

```
Stage 1: LLM(IDENTITY_DISTILL_PROMPT) → free-form analysis
Stage 2: LLM(IDENTITY_REFINE_PROMPT) → concise persona
→ validate_identity_content() → IdentityResult (write gated by cli.py approval)
```

## Insight Pipeline (core/insight.py)

`extract_insight() → InsightResult`

View-driven batching (ADR-0019):

1. `KnowledgeStore` patterns (non-gated).
2. Exclude patterns matching the `self_reflection` view (routed to `distill_identity`).
3. `_build_view_batches()` — for each loaded view (except `noise` and `self_reflection`; ADR-0026 restored `constitutional` to the skill-extraction path), rank patterns by cosine and keep top 10 by importance.
4. `_extract_skill()` — one LLM call per batch → one skill Markdown.
5. `validate` + slugify → `SkillResult` list.
6. Writes gated by cli.py per-file approval.

Cross-view merge / dedup is delegated to `skill-stocktake` (insight = narrow generator, stocktake = broad consolidator; ADR-0016).

## Rules Distill Pipeline (core/rules_distill.py)

`distill_rules(skills_dir) → RulesDistillResult`

Reads `skills/*.md`, strips YAML frontmatter, emits Practice/Rationale B-layer rules (not When/Do/Why — see rules layer redesign in `project_rules_b_layer`). 2-stage LLM (extract → structured Markdown). `MIN_SKILLS_REQUIRED=3`, `BATCH_SIZE=10`.

## Constitution Amendment (core/constitution.py)

`amend_constitution() → AmendmentResult`. Once ≥3 patterns match the `constitutional` view, generate an amendment proposal from current constitution + patterns.

## Migration (retired — ADR-0035)

`core/migration.py` and the three CLI subcommands `embed-backfill`,
`migrate-patterns`, `migrate-categories` were retired in ADR-0035 once
active deployments finished migrating (2026-04-15). Recovery for a
v1.x store: checkout a v2.0.x release tag and run the migration
commands there before pulling main.

## Snapshot (core/snapshot.py, ADR-0020)

`write_snapshot(command, views_dir, constitution_dir, snapshots_dir, view_registry, knowledge_store, *, prompts_dir=None, skills_dir=None, rules_dir=None, identity_path=None)`:
- Writes `snapshots/{command}_{UTC-ts}/` containing `manifest.json` plus a full copy of the runtime context: `views/*.md`, `constitution/*.md`, `prompts/*.md`, `skills/*.md`, `rules/*.md`, `identity.md`, and `centroids.npz`.
- If `knowledge_store` is passed, also calls `KnowledgeStore.update_view_telemetry()` to stamp every pattern with `last_classified_at` + `last_view_matches` (read-only observational data).
- Never raises — snapshots are observability.

Called from `_handle_distill`, `_handle_distill_identity`, `_handle_insight`, `_handle_rules_distill`, `_handle_amend_constitution`. `--dry-run` skips snapshots. The full-context bundle makes every behaviour-producing run exactly replayable.

## Report Generation (core/report.py)

`generate_report(date)` → Markdown summary from JSONL entries.

## Security Model

1. **Input wrapping**: `wrap_untrusted_content(text)` tags external data.
2. **Output sanitization**: `_sanitize_output(text)` removes `FORBIDDEN_SUBSTRING_PATTERNS`.
3. **Pattern validation**: Config files checked on load.
4. **Identity validation**: `validate_identity_content()` before system-prompt use.
5. **Archive**: `archive_before_write()` preserves identity history.
6. **Audit**: `audit.jsonl` records approval decisions + `snapshot_path` (ADR-0020) for behaviour-producing commands.

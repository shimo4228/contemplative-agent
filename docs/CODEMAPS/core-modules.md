<!-- Generated: 2026-06-05 | Files scanned: 24 core modules | Token estimate: ~2053 -->
# Core Modules Codemap

Platform-independent foundation (no Moltbook dependencies). All imports flow: adapters → core.

## Module Overview

| Module | LOC | Purpose |
|--------|-----|---------|
| `_io.py` | 46 | `write_restricted`, `truncate`, `archive_before_write` |
| `config.py` | 28 | `FORBIDDEN_SUBSTRING_PATTERNS`, `VALID_ID_PATTERN`, `MAX_COMMENT_LENGTH` |
| `domain.py` | 362 | `DomainConfig`, `PromptTemplates` (reads `MOLTBOOK_HOME/prompts/` overrides with packaged fallback), constitution loader |
| `prompts.py` | ~70 | Lazy-load proxy to `config/prompts/*.md` + placeholder resolution |
| `llm.py` | 553 | Ollama interface + `LLMBackend` Protocol (pluggable), circuit breaker, sanitization; `_build_system_prompt` reads identity.md as single blob (ADR-0030) |
| `clustering.py` | ~115 | Average-linkage cosine agglomerative clustering (numpy-only). Used by `insight` and `rules_distill` |
| `embeddings.py` | 92 | Ollama `/api/embed` wrapper (nomic-embed-text), `cosine`, `embed_one`, `embed_texts` |
| `episode_embeddings.py` | 162 | `EpisodeEmbeddingStore` — SQLite sidecar for episode vectors (ADR-0019) |
| `episode_log.py` | ~100 | `EpisodeLog` (append-only JSONL, `read_range` with `record_type` filter) |
| `knowledge_store.py` | 337 | `KnowledgeStore` — patterns JSON + provenance/bitemporal (ADR-0021); `is_live()` (bitemporal-only, `valid_until is None`; trust floor retired ADR-0051); `effective_importance()` (pure time decay `0.95^days`, LLM rating retired ADR-0056), `pattern_id()`, `epistemic_kind_for()`, `epistemic_counts_for()` (ADR-0050); `get_live_patterns()` / `get_live_patterns_since()` / `get_raw_patterns()` |
| `memory.py` | 498 | `MemoryStore` facade, `Interaction`/`PostRecord` dataclasses (`Insight` retired, ADR-0052) |
| `views.py` | 298 | `ViewRegistry` — seed-text views with `seed_from` + `${VAR}` substitution, lazy centroid cache; `find_by_view` = pure cosine rank + threshold + top_k (no importance weight, no trust, ADR-0051) |
| `snapshot.py` | 160 | `write_snapshot()` + `collect_thresholds()` — pivot snapshots (ADR-0020) |
| `scheduler.py` | 165 | Rate limit state, `has_read_budget`/`has_write_budget`, persistence |
| `constitution.py` | 130 | `amend_constitution() → AmendmentResult`. ADR-0033 layer-separation framing. ADR-0050 lineage fields. |
| `distill.py` | 844 | `distill()` (binary noise gate + 2-step + embedding dedup; importance-scoring step retired ADR-0056); `distill_identity()` (single-stage, self_reflection view, whole-file write, ADR-0030). ADR-0050 lineage fields on all result types. |
| `insight.py` | 318 | `extract_insight() → InsightResult`; global embedding clustering, no view batching (ADR-0050) |
| `rules_distill.py` | 348 | `distill_rules() → RulesDistillResult`; Practice/Rationale B-layer format (ADR-0048) |
| `stocktake.py` | 415 | Skill/rule audit: single-call LLM grouping (ADR-0046), `merge_group()` union-of-patterns, `CANNOT_MERGE` reject, singleton trigger-altitude clean (ADR-0048) |
| `report.py` | 256 | `generate_report()` JSONL → Markdown activity summary |
| `metrics.py` | 160 | Session metrics aggregation |
| `text_utils.py` | 60 | Shared Markdown helpers (`slugify`, `extract_title`, `strip_frontmatter`, `synthesize_frontmatter`) — ADR-0035 PR2, ADR-0048 |
| `thresholds.py` | 90 | Centralized thresholds with ADR/calibration annotations. `snapshot.collect_thresholds` reads from here. |
| `artifact_extraction.py` | 69 | Shared `extract_title → slugify → path-escape guard` chain (ADR-0035 PR3a) |

**Note**: `forgetting.py` was deleted (ADR-0051); `is_live` moved to `knowledge_store.py`.

**Total: ~6006 LOC (24 modules)**

## Key Dataclasses

All frozen (immutable) with type hints.

**core/memory.py** — Domain models:
```python
Interaction(timestamp, agent_id, agent_name, type, direction)
PostRecord(timestamp, post_id, title, topic)
```

**ADR-0012 Result types** — generated results; file writing done by cli.py after approval:
```python
AmendmentResult(text, target_path, marker_dir, pattern_ids, epistemic_counts)  # constitution.py
IdentityResult(text, target_path, pattern_ids, epistemic_counts)               # distill.py
SkillResult(text, filename, target_path, pattern_ids, epistemic_counts)         # insight.py
InsightResult(skills, dropped_count)
RuleResult(text, filename, target_path, source_ids)                            # rules_distill.py
RulesDistillResult(rules, dropped_count)
```

ADR-0050: `pattern_ids` = content-hash ids of input patterns; `epistemic_counts` = `{observed, generated}` tally derived from `provenance.source_type` (never persisted); `source_ids` (RuleResult) = skill filenames of the batch.

## EpisodeLog Schema (JSONL)

Daily log at `logs/YYYY-MM-DD.jsonl`. Each record:
```json
{"type": "post|comment|interaction|action|insight|session", "ts": "...", ...}
```
`record_type` filter: `EpisodeLog.read_range(days=3, record_type="interaction")`.
Embedding sidecar (`embeddings.sqlite`, ADR-0019) indexes episode summaries.

## KnowledgeStore Schema (JSON)

File: `~/.config/moltbook/knowledge.json`. Each pattern (post-ADR-0056):
```json
{
  "pattern": "…",
  "distilled": "2026-04-16T…",
  "embedding": [..768 floats..],
  "gated": false,
  "last_classified_at": "2026-04-16T02:15:33Z",
  "last_view_matches": {"constitutional": 0.72, "noise": 0.12, …},
  "provenance": {"source_type": "self_reflection|external_reply|mixed|unknown",
                 "source_episode_ids": ["..."],
                 "pipeline_version": "distill@0.26"},
  "valid_from": "2026-04-16T…",
  "valid_until": null
}
```

**Invariants**:
- `valid_until=null` means live; superseded rows keep their timestamp (bitemporal soft-invalidate).
- `effective_importance = importance × 0.95^days_since_distilled` — nothing else (ADR-0051).
- `gated` is behavioural (excluded from distill batching); `last_view_matches` is read-only telemetry.
- `trust_score` / `trust_updated_at` retired by ADR-0051 (legacy rows shed fields on next save).
- `category` field removed by ADR-0026.

## Thresholds (canonical: `core/thresholds.py`)

| Constant | Value | Used by | ADR |
|----------|-------|---------|-----|
| `NOISE_THRESHOLD` | 0.55 | distill Step 0 | ADR-0026 |
| `SIM_DUPLICATE` | 0.90 | distill dedup SKIP | ADR-0019 |
| `SIM_UPDATE` | 0.80 | distill dedup UPDATE | ADR-0019 |
| `DEDUP_IMPORTANCE_FLOOR` | 0.05 | distill dedup skip-low | ADR-0019 |
| `CLUSTER_THRESHOLD_INSIGHT` | 0.70 | insight clustering | ADR-0009 |
| `CLUSTER_THRESHOLD_RULES` | 0.65 | rules-distill clustering | ADR-0009 |
| `MAX_BATCH` | 10 | insight + rules-distill per-batch cap | — |

## LLM Functions (core/llm.py)

**Configuration**: `configure(identity_path, ollama_url, axiom_prompt, model, backend=None)`

**LLMBackend Protocol** (`runtime_checkable`):
```python
class LLMBackend(Protocol):
    def generate(self, prompt: str, system: str, num_predict: int,
                 format: Optional[Dict], ...) -> str: ...
```

**Circuit breaker**: 5 consecutive failures → open for 120s.

All output passes `_sanitize_output()`. All external inputs → `wrap_untrusted_content()`.

## Views Mechanism (ADR-0019)

`ViewRegistry` seed files under `~/.config/moltbook/views/` (user) or `config/views/` (packaged fallback):
```
---
threshold: 0.55
top_k: 50
seed_from: ${CONSTITUTION_DIR}/*.md
---
Fallback seed body.
```

`find_by_view(name, candidates)` = embed seed → cosine rank → threshold filter → top_k slice. Pure cosine only (no importance weight, no trust; ADR-0051).

Seed views: `communication`, `constitutional`, `noise`, `reasoning`, `self_reflection`, `social`, `technical`.

## Security Model

1. **Input wrapping**: `wrap_untrusted_content(text)` tags external data.
2. **Output sanitization**: `_sanitize_output(text)` removes `FORBIDDEN_SUBSTRING_PATTERNS`.
3. **Pattern validation**: config files checked on load.
4. **Identity validation**: `validate_identity_content()` before system-prompt use.
5. **Archive**: `archive_before_write()` preserves identity history.
6. **Audit**: `audit.jsonl` records approval decisions + `snapshot_path` + `source_ids` + `epistemic_counts` (ADR-0020/0050).

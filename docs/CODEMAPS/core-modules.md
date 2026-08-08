<!-- Generated: 2026-08-01 | Files scanned: 31 core modules | Token estimate: ~3596 -->
# Core Modules Codemap

Platform-independent foundation (no Moltbook dependencies). All imports flow: adapters → core.

## Module Overview

| Module | LOC | Purpose |
|--------|-----|---------|
| `_io.py` | 285 | `write_restricted`, `truncate`, `archive_before_write` |
| `run_context.py` | 35 | ADR-0078: mints process-wide `run_id` (uuid4) at import; `set_session_id`/`clear` for the active `run` session; read by `core/_io.py`'s `append_jsonl_restricted` to stamp every JSONL record |
| `config.py` | 47 | `FORBIDDEN_SUBSTRING_PATTERNS`, `VALID_ID_PATTERN`, `MAX_COMMENT_LENGTH` |
| `domain.py` | 403 | `DomainConfig`, `PromptTemplates` (reads `MOLTBOOK_HOME/prompts/` overrides with packaged fallback), constitution loader |
| `prompts.py` | 74 | Lazy-load proxy to `config/prompts/*.md` + placeholder resolution |
| `llm/` (package, ADR-0079) | 1677 | Ollama interface behind a **permanent facade** (`llm/__init__.py` — the public `core.llm` import path is API for siblings; transport + generation + `configure`/`reset_llm_config` live here). Submodules: `llm/backend.py` — `LLMBackend` Protocol (pluggable, returns `BackendResult`, keyword `temperature`/`think`, `model`/`context_window` properties) + circuit breaker + `circuit_shield()` context-manager isolation (ADR-0076: a failing observer can never trip the breaker for the generation it watches); `llm/prompting.py` — system-prompt assembly, sole owner of prompt-side mutable state, `system_prompt_budget_reading()` window-share instrument at adopt gate, `_build_system_prompt` reads identity.md as single blob (ADR-0030); `llm/guard.py` — sanitization, `validate_trusted_url` SSRF guard, `wrap_untrusted_content`. Generation keeps the `drop_truncated` gate, per-call `think` flag + reasoning-trace capture (`generate_for_api` returns `GenerationOutput(text, thinking)`); `llm/request.py` — frozen `GenerationRequest` (what the caller asked for) / `ResolvedRequest` (system prompt built + output budget clamped), so the resolution boundary is a type rather than a renamed positional argument, backend-aware context-budget pre-flight (audit C2, ADR-0066) |
| `clustering.py` | 139 | Average-linkage cosine agglomerative clustering via exact Lance-Williams merge (ADR-0074 perf rewrite, same partitions as the retired naive version), numpy-only. Used by `insight` and `rules_distill` |
| `embeddings.py` | 148 | Ollama `/api/embed` wrapper (nomic-embed-text), `cosine`, `embed_one`, `embed_texts` |
| `episode_embeddings.py` | 162 | `EpisodeEmbeddingStore` — SQLite sidecar for episode vectors (ADR-0019) |
| `episode_log.py` | 91 | `EpisodeLog` (append-only JSONL, `read_range` with `record_type` filter) |
| `knowledge_store.py` | 399 | `KnowledgeStore` — patterns JSON + provenance/bitemporal (ADR-0021); `is_live()` (bitemporal-only, `valid_until is None`; trust floor retired ADR-0051); `effective_importance()` (pure time decay `0.95^days`, LLM rating retired ADR-0056), `pattern_id()`, `epistemic_kind_for()`, `epistemic_counts_for()` (ADR-0050); `get_live_patterns()` / `get_live_patterns_since()` / `get_raw_patterns()` |
| `memory.py` | 290 | `MemoryStore` facade (delegates to `memory_repos.py`), `Interaction`/`PostRecord` dataclasses (`Insight` retired, ADR-0052) |
| `memory_repos.py` | 427 | The four stores behind the facade — `InteractionIndex` (episode-log-backed agent graph), `FollowState` (`agents.json` + forbidden-pattern trust boundary), `PostHistory` (bounded self-post tail + 7d rate), `CommentLedger` (`commented_cache.json` + per-author windows). Split out so each storage surface and retention policy has one owner |
| `views.py` | 344 | `ViewRegistry` — seed-text views with `seed_from` + `${VAR}` substitution, lazy centroid cache; `find_by_view` = pure cosine rank + threshold + top_k (no importance weight, no trust, ADR-0051) |
| `view_metrics.py` | 387 | Read-only pattern-composition instruments: consumed-view supply, seed-independent diversity (pairwise cosine + cluster structure), `nearest_view` singleton visibility (grounding composition removed — constant under per-episode mapping, ADR-0072). Observability only — never wired into gates/ranking (AKC ADR-0015 shape) |
| `snapshot.py` | 218 | `write_snapshot()` + `collect_thresholds()` — pivot snapshots (ADR-0020) |
| `scheduler.py` | 210 | Rate limit state, `has_read_budget`/`has_write_budget`, persistence |
| `constitution.py` | 152 | `amend_constitution() → AmendmentResult`. ADR-0033 layer-separation framing. ADR-0050 lineage fields. |
| `distill.py` | 931 | `distill()` (per-episode grounded distill: activity-only scope via `episode_render._is_rich_episode`, one LLM call per episode, no noise gate; ADR-0060, importance-scoring step retired ADR-0056); `_postgate()` durability postgate (ADR-0084); `_is_valid_pattern` validity gate (length floor + extraction-failure meta-statement phrase filter, ADR-0072); `distill_identity()` (single-stage, self_reflection view, whole-file write, ADR-0030). ADR-0050 lineage fields on all result types. Re-exports `render_episode` / `summarize_record` from `episode_render.py` (public names; ADR-0079 Phase 3b). |
| `pattern_dedup.py` | 165 | Embedding-cosine dedup decisions for distilled patterns (add / update / skip / skip-new against live pool + current batch; ADR-0019/0021/0056). Extracted from distill.py (ADR-0079 Phase 3b); does not import distill. |
| `episode_render.py` | 182 | Episode→prompt-text projection for distillation (`render_episode`, `summarize_record`, rich-episode scope, source-type derivation). Extracted from distill.py (ADR-0079 Phase 3b); does not import distill. |
| `insight.py` | 609 | `extract_insight() → InsightResult`; global embedding clustering, no view batching (ADR-0050); ADR-0074 weekly-staged flow: `.last_insight` marker guard refuses an implicit full recluster, novelty gate delegated to `insight_novelty.py`, `--stage` writes a pending-review ledger consumed by `adopt-staged`. Re-exports `skill_theme` (public name; ADR-0079 Phase 3a). |
| `insight_novelty.py` | 456 | ADR-0074 LLM novelty gate for staged insight: known-theme loading, token-budget chunk packing, covered-id parsing, novelty audit log (`skipped_known`). Extracted from insight.py (ADR-0079 Phase 3a); does not import insight. Namespace note: distinct from `adapters/moltbook/novelty.py` (feed novelty). |
| `skill_selection.py` | 821 | ADR-0076 shadow instrument: `select_applicable_skills()` pass-1 LLM pick over the skill catalog (name+description only, identity-only system prompt — no learned vocabulary fed back to the judge), `shadow_observe_skill_selection()` select-record-and-enforce wrapper under `circuit_shield()` (a failing selector can never trip the breaker for the generation it precedes), audit → `logs/skill-selection-YYYY-MM-DD.jsonl`; `read_skill_selection_log()` / `format_skill_selection_report()` back `report --skill-selection` (window aggregates + `SkillSelectionDay` per-day breakdown + `enforced_records` + per-name `never_selected_exposure`, the last three added 2026-08-08 because window-wide aggregates hide regime changes). ADR-0081 enforcement (implemented 2026-07-24, same day as the deciding first reading; **unconditional since the 2026-08-08 amendment retired `MOLTBOOK_SKILL_SELECTION_ENFORCE`**): `shadow_observe_skill_selection()` returns the selected names (empty tuple = inject nothing) on a judged verdict, else `None` = full injection (fail-open, kill switch); every record carries `enforced`; `selected_skills_block()` builds the pass-2 bodies (skill_theme identity match + frontmatter strip + forbidden-pattern validation) consumed by `llm.build_system_prompt_with_skills()`. `configured_injection_regime()` (2026-08-08, ADR-0089 amendment) names what may reach `<learned_skills>` — `full_corpus` (kill switch: `audit_dir` unset) / `two_pass_selected` (selector configured) — derived from live module state in the same short-circuit order as `shadow_observe_skill_selection`; the third literal `full_corpus_shadow_observed` is unreachable after the flag retirement but survives for baselines that recorded it. It reports a **ceiling, not an outcome**: four further conditions (`empty_catalog`, `no_template`, `fail_open_llm`, `fail_open_parse`) still route an individual call back to full-corpus injection. `selection_preconditions_unmet()` covers the two deterministic ones for a preflight; `observed_injection_outcomes(audit_dir)` counts what calls actually did (`records` / `enforced` / `fell_back` / verdict tally, counts only — never the untrusted situation strings). Both consumed by the eval, which records the ceiling as `manifest.injection_regime` and the outcome as `injection_observed` |
| `rules_distill.py` | 404 | `distill_rules() → RulesDistillResult`; Practice/Rationale B-layer format (ADR-0048) |
| `stocktake.py` | 631 | Skill/rule audit: single-call LLM grouping (ADR-0046), `merge_group()` union-of-patterns, `CANNOT_MERGE` reject, singleton trigger-altitude clean (ADR-0048), `audit_skill_description()` usage/description audit (ADR-0081) |
| `report.py` | 321 | `generate_report()` JSONL → Markdown activity summary |
| `metrics.py` | 189 | Session metrics aggregation |
| `text_utils.py` | 169 | Shared Markdown helpers (`slugify`, `extract_title`, `strip_frontmatter`, `synthesize_frontmatter`) — ADR-0035 PR2, ADR-0048 |
| `thresholds.py` | 84 | Centralized thresholds with ADR/calibration annotations. `snapshot.collect_thresholds` reads from here. |
| `artifact_extraction.py` | 103 | Shared `extract_title → slugify → path-escape guard` chain (ADR-0035 PR3a) |

**Note**: `forgetting.py` was deleted (ADR-0051); `is_live` moved to `knowledge_store.py`. Aggregate counts: [INDEX.md § Statistics](INDEX.md#statistics).

## Key Dataclasses

All frozen (immutable) with type hints.

**core/memory.py** — Domain models:

```python
Interaction(timestamp, agent_id, agent_name, type, direction)
PostRecord(timestamp, post_id, title, topic)
```

**ADR-0012 Result types** — generated results; file writing done by cli/ (approval.py / adopt.py) after approval:

```python
AmendmentResult(text, target_path, marker_dir, pattern_ids, epistemic_counts)  # constitution.py
IdentityResult(text, target_path, pattern_ids, epistemic_counts)  # distill.py
SkillResult(text, filename, target_path, pattern_ids, epistemic_counts)  # insight.py
InsightResult(skills, dropped_count, skipped_known)  # skipped_known: ADR-0074 novelty gate
RuleResult(text, filename, target_path, source_ids)  # rules_distill.py
RulesDistillResult(rules, dropped_count)
```

ADR-0050: `pattern_ids` = content-hash ids of input patterns; `epistemic_counts` = `{generated, unknown}` tally derived from `provenance.source_type` (never persisted; ADR-0082 retired the third `observed` key); `source_ids` (RuleResult) = skill filenames of the batch.

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
  "provenance": {"source_type": "self_reflection|external_reply|mixed|unknown",
                 "source_episode_ids": ["..."],
                 "pipeline_version": "distill@0.60"},
  "valid_from": "2026-04-16T…",
  "valid_until": null
}
```

**Invariants**:

- `valid_until=null` means live; superseded rows keep their timestamp (bitemporal soft-invalidate).
- `effective_importance = 0.95^days_since_distilled` (or `0.1` for an unknown timestamp) — pure time decay; the distill-time LLM `importance` rating was retired by ADR-0056, so the stored base is no longer read.
- `gated` is behavioural (insight clustering skips gated rows); no per-pattern view telemetry is persisted (`last_classified_at` / `last_view_matches` never existed in code — removed from this doc 2026-07-03).
- `trust_score` / `trust_updated_at` retired by ADR-0051; `importance` retired by ADR-0056 (legacy rows shed all three fields on next save).
- `category` field removed by ADR-0026.
- `provenance.source_type` is stamped at distill time (ADR-0050/0060). The enum values are valid in type space, but post-ADR-0060 per-episode distill new patterns are stamped `self_reflection` / `external_reply`; the `observed` epistemic kind was structurally absent for new patterns (interaction records are filtered out before distill), so ADR-0082 retired the kind and its `external_reply` arm — `epistemic_counts` is now a `{generated, unknown}` split, and an `external_reply` row tallies as `unknown`. The `external_reply` **source_type** itself is kept: it is a provenance record, a separate layer from the epistemic tally.

## Thresholds (canonical: `core/thresholds.py`)

| Constant | Value | Used by | ADR |
|----------|-------|---------|-----|
| `SIM_DUPLICATE` | 0.90 | distill dedup SKIP | ADR-0019 |
| `SIM_UPDATE` | 0.80 | distill dedup UPDATE | ADR-0019 |
| `DEDUP_IMPORTANCE_FLOOR` | 0.05 | distill dedup skip-low (`effective_importance` = pure time decay) | ADR-0019, ADR-0056 |
| `CLUSTER_THRESHOLD_INSIGHT` | 0.70 | insight clustering | ADR-0019 |
| `CLUSTER_THRESHOLD_RULES` | 0.65 | rules-distill clustering | ADR-0019 |
| `MAX_BATCH` | 10 | insight + rules-distill per-batch cap | — |

## LLM Functions (core/llm/ package)

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

```yaml
---
threshold: 0.55
top_k: 50
seed_from: ${CONSTITUTION_DIR}/*.md
---
Fallback seed body.
```

`find_by_view(name, candidates)` = embed seed → cosine rank → threshold filter → top_k slice. Pure cosine only (no importance weight, no trust; ADR-0051).

Seed views: `constitutional` (amend-constitution) and `self_reflection` (distill-identity) — both have a live consumer. The five orphaned seeds (`communication`, `noise`, `reasoning`, `social`, `technical` — former insight batch axes / noise gate, dead since ADR-0050/0060) were pruned in ADR-0073: a consumer-less view is dead by definition, and future views are grown from stable corpus clusters together with their consumer wiring, not pre-authored. `view_metrics.py` instruments measure only consumed views.

## Security Model

1. **Input wrapping**: `wrap_untrusted_content(text)` tags external data.
2. **Output sanitization**: `_sanitize_output(text)` removes `FORBIDDEN_SUBSTRING_PATTERNS`.
3. **Pattern validation**: config files checked on load.
4. **Identity validation**: `validate_identity_content()` before system-prompt use.
5. **Archive**: `archive_before_write()` preserves identity history.
6. **Audit**: `audit.jsonl` records approval decisions + `snapshot_path` + `source_ids` + `epistemic_counts` (ADR-0020/0050).

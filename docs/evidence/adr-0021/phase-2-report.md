# Phase 2 Report — ADR-0022 Memory Evolution + Hybrid Retrieval

Date: 2026-04-16
Status: Implementation complete, tests green. Opt-in automatically via existing `distill` and `find_by_view` code paths (no migration step required).

## Scope

Implemented improvement vectors IV-4 (Memory Evolution, A-Mem bidirectional update) and IV-5 (Hybrid Retrieval via BM25 augmentation). Builds directly on ADR-0021's bitemporal soft-invalidation contract and trust × strength scoring.

## Artifacts

### New files

| File | Purpose |
|---|---|
| `src/contemplative_agent/core/memory_evolution.py` | `find_neighbors` / `revise_neighbor` / `apply_revision` / `evolve_patterns` — A-Mem-style bidirectional update. Bitemporal-coherent (soft-invalidates old, appends revised row). |
| `config/prompts/memory_evolution.md` | LLM prompt template for revising a neighbor pattern in light of a newly arrived related pattern. Emits `NO_CHANGE` marker when no revision is warranted. |
| `docs/decision-history/0022-memory-evolution-and-hybrid-retrieval.md` | ADR-0022 rationale, decision, alternatives (RRF / re-embedding / merging evolution into dedup all rejected). |
| `tests/test_memory_evolution.py` | 22 new cases covering evolution unit paths + hybrid BM25 `_rank` behavior + frontmatter parsing. |

### Modified files

| File | Change |
|---|---|
| `pyproject.toml` | Added `rank-bm25>=0.2.2` (MIT, ~1 KB pure Python). |
| `src/contemplative_agent/core/views.py` | `View` gains `bm25_weight` (default 0.3). `_rank` accepts optional `bm25_scores`, `alpha`, `beta`; score now `(α·cosine + β·bm25_norm) × trust × strength`. `find_by_view` / `find_by_seed_text` build a per-query BM25 index via new `_compute_bm25_scores`. Frontmatter parser handles `bm25_weight:` key. |
| `src/contemplative_agent/core/distill.py` | After `_distill_category` commits added patterns, a memory-evolution pass revises in-band (EVOLUTION_MIN=0.65 ≤ sim < SIM_UPDATE=0.80) same-category live neighbors. Revised rows appended in-place to `_learned_patterns`. |
| `src/contemplative_agent/core/domain.py` | `PromptTemplates` gains `memory_evolution` field; `load_prompt_templates` loads `config/prompts/memory_evolution.md`. |
| `src/contemplative_agent/core/prompts.py` | `_ATTR_MAP` registers `MEMORY_EVOLUTION_PROMPT`. |
| `docs/decision-history/README.md` | ADR-0022 index entry. |

## Test results

| Suite | Count | Status |
|---|---|---|
| test_memory_evolution.py (new) | 22 | PASS |
| test_views.py | 34 | PASS |
| test_knowledge_store.py | 23 | PASS |
| test_distill.py | 43 | PASS |
| test_memory.py | 85 | PASS |
| test_migration.py | 13 | PASS |
| test_insight / test_rules_distill / test_snapshot | 75 | PASS |
| test_cli / test_agent / test_scheduler / test_verification / test_content / test_stocktake / test_metrics / test_domain / test_constitution | 390 | PASS |
| **Total touched** | **~685** | **PASS** |

## Smoke verification (no LLM call required)

- `_compute_bm25_scores` on a 4-pattern corpus correctly scores the `axiom`-bearing pattern first for the query `"axiom"`.
- All 7 packaged views load with `bm25_weight=0.3` (default).
- `evolve_patterns` end-to-end test with mocked `generate_fn`: neighbor in 0.65-0.80 sim band gets soft-invalidated, revised row appended with `provenance.source_type="mixed"`, unrelated patterns untouched.

## Behavior changes now live (no migration required)

**Retrieval**:
- Every `find_by_view(name, candidates)` call now blends BM25 lexical scoring (weight 0.3 default) with cosine (weight 0.7). Views can override via `bm25_weight:` frontmatter key. Set to 0.0 for pure cosine on views where lexical noise would hurt (e.g. potentially `self_reflection` if tuning shows drift).
- Threshold gate continues to apply to raw cosine, so tuning stays semantic.

**Write path (distill)**:
- After Step 3b dedup commits new patterns, each new pattern triggers up to `EVOLUTION_K=3` LLM calls to refresh topically-related neighbors' `distilled` text.
- Each revision: old row gets `valid_until=now`, a new row is appended with the revised text, embedding/importance/category preserved, `provenance.source_type="mixed"`, `evolution_similarity` recorded in provenance.
- `NO_CHANGE` marker from the LLM is a no-op.
- Cost budget: K × new_patterns × ~3-5s latency per call on qwen3.5:9b. With typical 5-20 new patterns per distill, worst case ~5 min added to the nightly pipeline.

## Known caveats / follow-ups

- **Prompt discipline** (prompt-model-match memory): the memory_evolution.md template was drafted by Opus. Recommended follow-up: sample 5-10 (new, neighbor) pairs from actual distill runs and have qwen3.5:9b revise the prompt for its own thought space. Acceptable as a separate iteration.
- **Evolution observability**: no dedicated log file yet. `logger.info` logs each revision; a future `inspect-pattern` CLI could surface evolution history for any pattern.
- **BM25 tuning**: default α=0.7, β=0.3 is unvalidated. If observation shows lexical dominance or blindness, adjust per view.
- **Evolution threshold tuning**: `[0.65, 0.80)` is a guess. Post-migration distill runs will reveal whether the band catches too much (evolution noise) or too little (misses opportunities).
- **RRF upgrade**: if linear α+β misbehaves, reciprocal rank fusion is the next stop. Deferred.

## Next step

Phase 3 (ADR-0023): Skill-as-Memory loop (IV-9) — skill router + reflective write + usage log. Uses `feedback.py` (stubbed in Phase 1) for attribution.

Launch with: `./scripts/launch-phase.sh 3` (or continue in this session if terminal login is unavailable).

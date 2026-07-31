# ADR-0022: Memory Evolution + Hybrid Retrieval

## Status

withdrawn (by [ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.md) on 2026-05-05)

## Date

2026-04-16

## Context

Phase 1 (ADR-0021) gave each pattern provenance, bitemporal validity, strength, and feedback counters, but wrote patterns as isolated atoms. Two downstream gaps remain:

1. **Patterns don't reinterpret each other.** When a new pattern lands near an existing pattern in embedding space but *below* the `SIM_UPDATE=0.80` dedup threshold, the existing pattern stays frozen. A-Mem (arXiv:2502.12110) — and the Zettelkasten tradition it draws from — treats the arrival of a related-but-distinct observation as an occasion to revise the earlier note's contextual description. Without this loop, the knowledge store accumulates history linearly; it never *rethinks*. Related observations sit next to each other without cross-referencing.

2. **Retrieval is embedding-only.** `views.py _rank` filters by cosine similarity to the view seed. This is good for semantic topicality but poor for: named entities (a specific agent name), stable technical terms (a class name, a concept label), and queries that want an exact keyword even when paraphrased forms also match. Zep / Graphiti, Cognee, and Mem0 all land on *hybrid* retrieval — vector + lexical — because neither channel alone is sufficient. BM25 is the simplest lexical channel, is O(log N) per query after index build, has zero LLM calls, and composes multiplicatively with cosine.

Both gaps are local, bounded changes that do not touch the pattern schema. Phase 1's contract (dict-based, additive fields) holds.

## Decision

### IV-4: Memory Evolution

After `_dedup_patterns` produces the final add-list, a new step runs for each added pattern:

1. Compute cosine against all *live* existing patterns (`valid_until is None`) with embeddings.
2. Collect those with `EVOLUTION_MIN ≤ sim < SIM_UPDATE` (default range `[0.65, 0.80)`). This is the "topically related but distinct" zone. Above `SIM_UPDATE` the ADR-0021 dedup path already handles it; below `EVOLUTION_MIN` the patterns are too distant to meaningfully reinterpret.
3. Cap the count at `EVOLUTION_K=3` neighbors per new pattern (highest cosine first). Evolution is cheap per call (one LLM invocation per (new, neighbor) pair) but cost grows with K × new_count — the cap keeps worst case bounded.
4. For each (new, neighbor) pair, call the LLM with prompt `memory_evolution.md`. Input: the neighbor's current `distilled` text plus the new pattern. Output: a refreshed `distilled` that *incorporates* what the new pattern reveals about the neighbor's meaning. If the LLM signals no meaningful revision (empty or marker `NO_CHANGE`), the neighbor is left alone.
5. If a revision is produced: soft-invalidate the neighbor (`valid_until = now`), and *add* a new pattern copying the neighbor's identity (same embedding, importance, category, provenance.source_episode_ids) but with the new `distilled` text. The new row gets `provenance.source_type = "mixed"` (blend of original source + new context), `valid_from = now`, and inherits the old pattern's access counters reset to zero (a revised interpretation has no retrieval history of its own).

Rationale for reusing the embedding: the neighbor was about the same thing; that doesn't change. Only the *interpretation* changes. Re-embedding the new distilled text is possible but costs an Ollama call per evolution and adds drift risk if the new text uses different words for the same concept.

### IV-5: Hybrid Retrieval (BM25 augmentation)

`views.py _rank` is extended with a lexical channel:

- Add `rank_bm25` (MIT, ~1 KB pure-Python) to `pyproject.toml`.
- On first query, `ViewRegistry` lazily builds a `BM25Okapi` index from `(pattern + distilled)` text of all live patterns. The index is cached per-registry and invalidated when the registry's pattern set changes (via a generation counter on `KnowledgeStore`).
- Combined score: `α × cosine + β × bm25_norm`, where `bm25_norm` is min-max normalized per query (BM25 raw scores are unbounded), defaults `α=0.7, β=0.3`.
- Tuning: per-view frontmatter can override α / β. Views that want to stay purely semantic (e.g. `self_reflection`) can set `bm25_weight: 0.0`.
- Filters unchanged: `threshold` still applies to raw cosine (lexical noise shouldn't let a low-similarity pattern sneak in); `is_live` still gates by trust + strength + bitemporal.

Why BM25 over alternatives: TF-IDF is a degenerate case of BM25; dense-dense rerankers (ColBERT, etc.) add an embedding call per query; graph traversal requires an entity-relation store we don't have. BM25 is the least-invasive, highest-ROI hybrid step.

### Shared constants

New module `src/contemplative_agent/core/evolution.py` holds `EVOLUTION_MIN`, `EVOLUTION_K`, hybrid scoring weights, and the small orchestration logic. Evolution itself lives separately from `distill.py` so it can be unit-tested without the distill pipeline.

## Alternatives Considered

1. **Re-embed the revised distilled text.** Keeps the embedding consistent with the displayed text. Rejected: (a) one Ollama call per evolution × K neighbors × N new patterns is expensive; (b) the neighbor's *topic* hasn't changed, only its *interpretation*, so the old embedding is still a correct coordinate. Revisit if retrieval drift is observed.

2. **Evolution threshold = SIM_UPDATE (merge evolution into dedup).** Simpler code path. Rejected: conflates two different operations. Dedup at 0.80+ says "these are the same thing, pick one"; evolution at 0.65-0.80 says "these are related, make the older one aware of the newer one". Collapsing them either misses evolution (if we use 0.80 as the floor) or over-dedups (if we use 0.65).

3. **LLM judge on every retrieval.** Could replace both cosine ranking and BM25 with an LLM that judges relevance. Rejected at this scope — blows the retrieval latency budget and adds a stochastic failure mode to a read-path that currently works. Skill router (ADR-0023, Phase 3) will introduce LLM-in-the-loop selection for skills specifically.

4. **Per-pattern BM25 weight stored as state.** Considered for fine-grained tuning. Rejected — keeps BM25 a pure query concern, same reasoning as ADR-0019's embedding+views move (classification as query not state).

5. **Full hybrid with reciprocal rank fusion (RRF).** More principled than linear combination. Considered. Deferred — RRF tends to flatten score differences (wants ranks not scores), losing the calibration `trust_score × strength` provides. If observation shows linear α+β weighting misbehaves, revisit.

6. **Skip IV-5 for now, BM25 is optional.** The original plan lists IV-5 at rank 6 of 8. Considered skipping. Rejected: BM25 is the cheapest win in the survey; lexical blindness bites most on view queries that mention specific proper nouns (e.g. a view seeded with "contemplative axioms" should find the patterns that literally contain "contemplative" or "axiom"). Delay adds no information.

## Consequences

- **Evolution cost**: bounded by `K * new_patterns * avg_llm_latency`. With `K=3`, typical new_patterns=5-20 per distill run, avg latency ~3-5s on qwen3.5:9b, that's 45s - 5min per distill. Acceptable in the nightly pipeline; noticeable in interactive. Can be disabled via config if observation shows drift / low value.
- **Evolution audit trail**: every revision leaves a soft-invalidated old row + a new row. The pair reconstructs "X was reinterpreted when Y arrived at time T". `.reports` or a future `inspect-pattern` CLI can surface this. No new log file is introduced.
- **BM25 index memory**: O(total tokens) per pattern. For 585 patterns at ~30 tokens average, index is ~20 KB. Negligible.
- **BM25 index rebuild**: triggered when KnowledgeStore generation counter changes. Cost is O(N × avg_tokens) — measured ~20 ms for 585 patterns in benchmark, well below the per-query Ollama latency floor.
- **Backward compatibility**: patterns added pre-Phase 2 participate in evolution as neighbors (as long as they have embeddings) and in BM25 retrieval (as long as their `pattern + distilled` text is non-empty). No migration needed.
- **Prompt discipline**: `memory_evolution.md` is drafted by Opus here; it should be reviewed by running it through qwen3.5:9b against a sample neighbor pair and iterating on the phrasing. The `prompt-model-match` feedback memory applies.
- **Tests**: new `tests/test_memory_evolution.py`, new `TestHybridRankBM25` in `tests/test_views.py`, adjustments to `test_distill.py` for the evolution hook. Mock the LLM and BM25 where possible.

## Key Insight

ADR-0019 said "classification is a query, not state". ADR-0021 said "epistemic axes should be explicit fields". ADR-0022 says: "patterns are not static atoms; their meaning is a function of what's arrived since". Evolution makes that explicit in the write path; hybrid retrieval makes it explicit in the read path. Together they move the store from a list-of-observations toward something closer to a Zettelkasten — where adding a note changes nearby notes and where finding a note uses both what it's *about* (cosine) and what it *says* (lexical).

## Withdrawal Note (2026-05-05)

[ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.md) withdraws this ADR in full. Both IV-4 (memory evolution) and IV-5 (BM25 hybrid retrieval) were removed after empirical evaluation showed:

- 78% of memory_evolution revisions fell in the `[0.75, 0.80)` band, where the LLM produced rephrasings rather than reinterpretations
- BM25 had no effect because view seeds (abstract themes) and pattern text (concrete log observations) shared no vocabulary
- The `distilled` field was used for two incompatible purposes (ISO timestamp by ADR-0021 callers, prose by ADR-0022's revision path), which produced 39.6% schema-broken rows

The bibliography references (A-Mem, Zep / Graphiti / Cognee / Mem0) are kept as starting points for any future ADR that revisits these questions with a different mechanism. See [ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.md) for the empirical record and the lesson recorded.

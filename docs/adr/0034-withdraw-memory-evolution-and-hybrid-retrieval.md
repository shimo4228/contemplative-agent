# ADR-0034: Withdraw Memory Evolution and BM25 Hybrid Retrieval — Cost Without Benefit

## Status

accepted — supersedes ADR-0022

## Date

2026-05-05

## Context

ADR-0022 introduced two related capabilities:

- **IV-4 Memory Evolution** — when a new pattern arrives in the cosine `[0.65, 0.80)` band of an existing pattern, an LLM rewrites the older pattern's `distilled` text in light of the new arrival; the old row is soft-invalidated and a revised row is appended (A-Mem-style bidirectional update).
- **IV-5 BM25 Hybrid Retrieval** — `views.py _rank` blends a lexical channel (`rank-bm25` over `pattern + distilled`) with cosine similarity at α/β weights so that view queries containing literal proper nouns (e.g. "contemplative axioms") can find patterns that lexically contain those terms.

After two and a half weeks of running both in production and inspecting the resulting `knowledge.json`, the empirical record argues against keeping either feature. This ADR records that decision and the evidence behind it, so the bibliography reference (A-Mem, Zep/Graphiti, Cognee, Mem0) survives even though the implementation does not.

### 1. Memory evolution produced low-quality revisions across the entire band

A direct read of revised rows in the pre-migration backup `knowledge.json.bak.20260504T132510` (475 revised rows with `provenance.evolution_similarity` recorded) shows three recurring failure modes, partitioned by cosine band:

| Band | Count | Share | Observed pattern |
|---|---|---|---|
| `[0.65, 0.70)` | 17 | 3.6% | Replaces the neighbor's *general* observation with a *specific* timestamp / user-id log entry from the new pattern's source. The revision narrows scope rather than reinterpreting meaning |
| `[0.70, 0.75)` | 70 | 14.7% | Rewrites the neighbor with a different topic from the new pattern. Functionally a topic swap, not a revision |
| `[0.75, 0.80)` | 372 | **78.3%** | Rephrases the neighbor's text in near-identical content with vocabulary additions (`dynamically`, `trembling`, `rhythm`, `anchor`, `dissolve`). Adds no information |

The mean evolution_similarity is **0.773**; the distribution is heavily skewed toward the upper edge of the evolution band, exactly the regime where the revision degenerates into stylistic rephrasing of an already-redundant pattern.

The original ADR-0022 hypothesis — "neighbors are about the same thing; only the interpretation changes" — does not survive contact with the qwen3.5:9b prompt response. The LLM does not reinterpret; it either substitutes a more specific log entry or rephrases the neighbor in fluent prose. Adjusting the threshold band does not help: the high-similarity tail has worse revisions than the low-similarity head.

### 2. Memory evolution drove a runaway append rate

Every revision keeps the old row (soft-invalidated) and adds the new row, by design (audit trail). With `K=3` neighbors per new pattern and 5–20 new patterns per distill run, each daily distill expanded `knowledge.json` by 15–60 rows from evolution alone, on top of the normal additions. The weekly delta climbed +24 → +90 → +199 → +256 patterns/week through April. After the prompt was disabled by renaming `config/prompts/memory_evolution.md` to `.md.disabled` on 2026-05-04, the daily delta dropped to 5–10 — the level of the underlying distill itself.

The append rate was the symptom that triggered the investigation. The diagnosis turned out to be: the feature was working as designed, but the design's value premise (revisions are worth their row cost) was not satisfied by the actual revisions produced.

### 3. BM25 had no effect to lose

BM25 hybrid retrieval was added so that view queries with specific lexical tokens could find patterns containing those tokens literally. In practice the seven `~/.config/moltbook/views/*.md` files describe abstract themes — "Patterns about dialogue, reply strategies, conversational rhythm" (`communication.md`), "Patterns about analysis, inference, decision-making" (`reasoning.md`), and so on — while the patterns being indexed are concrete log observations: "Multiple upvoting activities occur in rapid succession", "The system consistently initiates an 'activity: reply'…". The view-side and pattern-side vocabularies do not overlap, so the lexical channel produces near-zero boost regardless of weight.

The feature works as specified. It just has no patterns to act on, given the current pattern-content distribution. The 30% weight that the linear blend assigns to BM25 effectively dilutes the cosine signal with noise.

### 4. Schema bug as a downstream consequence

`memory_evolution.apply_revision` writes the LLM-generated text into the `distilled` field, while every ADR-0021 caller (`add_learned_pattern`, `effective_importance`, `_filter_since`, `valid_from` inheritance) treats `distilled` as an ISO timestamp. The consequence: 39.6% of `knowledge.json` rows had `distilled` containing prose instead of an ISO datetime, which made `effective_importance` apply a 10× retrieval penalty to those rows (`base * 0.1`) and broke `_filter_since`. The 2026-05-04 migration removed the broken rows along with the corresponding soft-invalidated original neighbors, so the data side is now consistent — but the code path that produced the bug is still present.

### 5. Costs of leaving the scaffold in place

- ~250 LOC in `core/memory_evolution.py` plus tests
- ~100 LOC of BM25-specific code in `core/views.py` (`_compute_bm25_scores`, `_tokenize`, `bm25_weight` parser, `_rank` α/β blend)
- One external dependency (`rank-bm25 ≥ 0.2.2`)
- One prompt file (`config/prompts/memory_evolution.md`) that is currently disabled by rename, plus its `domain.py` plumbing and `prompts.py` mapping
- Continued risk that someone re-enables the prompt by undoing the rename without re-running the empirical evaluation

## Decision

Withdraw ADR-0022 in full. Both IV-4 (memory evolution) and IV-5 (BM25 hybrid retrieval) are removed.

Specifically:

1. Delete `src/contemplative_agent/core/memory_evolution.py` and `tests/test_memory_evolution.py`
2. Delete `config/prompts/memory_evolution.md.disabled`
3. Remove the memory_evolution import + invocation block from `core/distill.py`
4. Remove `KnowledgeStore.add_revised_patterns` from `core/knowledge_store.py`
5. Remove the `MEMORY_EVOLUTION_PROMPT` mapping from `core/prompts.py`
6. Remove the `memory_evolution` field and reader from `core/domain.py`
7. Remove BM25 from `core/views.py`: `HYBRID_BETA_DEFAULT`, `_TOKEN_RE`, `_tokenize`, `ViewDef.bm25_weight`, the frontmatter parser branch, the BM25 paths in `find_by_view` and `find_by_seed_text`, the `bm25_scores`/`alpha`/`beta` arguments in `_rank`, and `_compute_bm25_scores` itself. `_rank` returns to `cosine × trust`
8. Remove `rank-bm25` from `pyproject.toml` dependencies
9. Mark ADR-0022 as `withdrawn (by ADR-0034 on 2026-05-05)`. Keep its body intact so future readers can reconstruct the reasoning and see explicitly that the A-Mem-style approach and BM25 hybrid retrieval were tried and withdrawn

The on-disk `~/.config/moltbook/knowledge.json` stays as it is (497 rows after the 2026-05-04 migration removed broken revised rows and their corresponding soft-invalidated original neighbors). The remaining `provenance.source_type = "mixed"` rows are produced by the regular distill pipeline when an extract spans episodes from multiple sources, and are unrelated to memory evolution.

## Consequences

**Positive**:

- ~350 LOC removed (memory_evolution module + tests + BM25 paths in views.py)
- One external dependency (`rank-bm25`) removed
- The `distilled` field's contract is unambiguous again: ISO timestamp, always. `effective_importance` and `_filter_since` are no longer susceptible to the schema bug
- `views._rank` is a pure cosine ranker again. Score interpretation is straightforward (no α/β blend to reason about)
- The `prompt-model-match` constraint (memory) no longer has to keep a `memory_evolution.md` prompt aligned with qwen3.5:9b's actual behavior
- Daily distill runs add 5–10 patterns/day instead of 30–80, so the natural saturation curve of the knowledge store becomes visible without evolution-driven amplification

**Negative**:

- The two referenced systems that motivated ADR-0022 (A-Mem for evolution, Zep / Graphiti / Cognee / Mem0 for hybrid retrieval) remain in the bibliography even after withdrawal. They are kept as references because the questions they address (do related patterns reinterpret each other? does literal-token search complement vector search?) are real, even though the answers proposed by ADR-0022 did not work in this code base. A future ADR may revisit either question with a different mechanism (re-embedding rather than text revision; a different lexical channel; or a different pattern-content profile that makes BM25 productive)
- If someone later wants to test "would memory evolution work with a re-embedding step?" or "would BM25 work if pattern text described topics rather than logged events?", they will need to rebuild the scaffolding rather than toggle a flag. The plain-text revisions seen in the 475-row sample suggest the answer to both questions is "still no without further changes," so the cost of rebuild is acceptable

**Neutral**:

- ADR-0019 (embedding + views) is untouched. Views continue to route patterns by cosine to view seeds. The only change is that `_rank` no longer mixes in a lexical signal
- ADR-0021 (pattern schema, trust, bitemporal) is untouched. `effective_importance` keeps using `distilled` as an ISO timestamp, which is now consistent across the entire store
- ADR-0023 (skill-as-memory loop) and ADR-0028 (retire pattern-level forgetting) had no functional dependency on memory evolution and are not affected
- `provenance.source_type = "mixed"` survives as a label that the regular distill pipeline still emits when bundling episodes from multiple sources. It no longer implies "produced by memory evolution"

## Lesson recorded

ADR-0030 produced one heuristic ("one artifact, one responsibility"). ADR-0034 produces a complementary one, recorded in memory as `feedback_validate-mechanism-against-actual-llm-output.md`:

**Validate a mechanism against actual LLM output before generalizing it.** ADR-0022's evidence was theoretical (A-Mem paper, Zep/Cognee/Mem0 surveys) and analytical (the `[0.65, 0.80)` band is "topically related but distinct"). The empirical evaluation against qwen3.5:9b on real distilled patterns was deferred to "observation in nightly runs". When the observation arrived, the band's actual content was not "topically related but distinct" — it was "almost-duplicates that the LLM rephrases" — and the mechanism never produced the claimed value.

Concrete check, applied to future memory / retrieval ADRs:

1. Before committing a new mechanism that calls an LLM per row, run the prompt against 20–50 real samples and read the output yourself
2. Categorize the output by what the mechanism *claimed* it would produce vs what it *actually* produced
3. If those categories don't match, the mechanism is mis-specified — either change the prompt, change the trigger condition, or drop the mechanism
4. Only then commit to the audit-trail / row-rate consequences of running the mechanism at scale

The cost of this check is one afternoon of reading prompt outputs. The cost of skipping it was 475 low-value revised rows and the schema bug they masked.

## References

- [ADR-0022](0022-memory-evolution-and-hybrid-retrieval.md) — withdrawn
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — embedding + views, retained
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — pattern schema, retained
- [ADR-0030](0030-withdraw-identity-blocks.md) — first withdrawal ADR; precedent for keeping the withdrawn ADR's body intact
- A-Mem (Xu et al., 2025, arXiv:2502.12110) — bibliography, no longer implemented
- Zep / Graphiti / Cognee / Mem0 — bibliography, BM25 hybrid retrieval no longer implemented

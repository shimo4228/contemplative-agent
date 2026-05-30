# ADR-0046: Stocktake Duplicate Detection — LLM Grouping over Embedding Clustering

## Status

accepted

## Date

2026-05-30

## Context

`skill-stocktake` (and its counterpart `rules-stocktake`) detect redundant skills and rules, then merge each redundant group. Commit `316719f` (2026-04-15) replaced an earlier LLM-based duplicate-detection step with embedding-cosine + single-linkage union-find clustering, motivated purely by performance: `core/llm.generate()` had hardcoded `num_predict=8192`, causing the prior approach to hang on the M1 dev machine.

Embedding-only clustering over-merges in this codebase. Auto-extracted skills share heavy boilerplate vocabulary — "emptiness pruning", "trembling texture", friction-to-insight framing — so genuinely distinct concrete patterns score 0.90+ cosine similarity against one another. Transitive single-linkage union-find then chains the entire set into a single component. This was observed live: 18 skills collapsed into one merge group.

The per-group `CANNOT_MERGE` safety net — which allows the merge LLM to reject a spurious group — cannot split an already-chained blob. It is all-or-nothing per group. Once embedding clustering chains N skills into one component, the merge step must either accept or reject the entire set; it has no mechanism to recover the structure that single-linkage destroyed.

A second failure was found in the merge prompt itself. It instructed the LLM to "identify the core behavior they share and produce ONE comprehensive skill", which reduced N skills to their lowest-common-denominator abstraction. Distinct concrete trigger→action patterns were dropped in this flattening — for example, an "upvote-burst → create a post" policy was lost.

The performance motivation behind `316719f` is now moot. Every `generate()` caller was subsequently updated to pass an explicit `num_predict`; the hang cannot recur.

## Decision

Adopt two coordinated changes to duplicate detection and merge behavior.

1. **Revert duplicate detection to a single LLM grouping call.** All candidate skill bodies are submitted in one `generate()` request, which returns `{"groups": [{files, reason}]}`, parsed by `_parse_groups`. Because the LLM reads full skill bodies, it discriminates on concrete behavior: skills that share vocabulary or framing but prescribe distinct actions are left in separate groups or left ungrouped entirely. The grouping prompts (`config/prompts/stocktake_skills.md`, `stocktake_rules.md`) explicitly instruct: shared vocabulary but distinct concrete behavior ⇒ do NOT group; prefer several small coherent groups over one catch-all.

2. **Invert the merge prompt from synthesis to union.** Replace "identify the core behavior they share" with: produce the UNION of every distinct concrete pattern; dedup only verbatim boilerplate; a behavior present in only one input must survive; never collapse two distinct concrete actions into one generic one. `merge_group`'s `num_predict` scales with group size: `min(8192, max(3000, 500 × n))`.

Remove the dead `SIM_CLUSTER_THRESHOLD` constant from `core/thresholds.py` and `core/snapshot.py`.

These changes are implemented in commits `7224b30` (merge prompt inversion) and `0f05ecf` (grouping revert).

## Alternatives Considered

### Raise `SIM_CLUSTER_THRESHOLD` from 0.80 to 0.90

Tighten the cosine threshold to reduce over-grouping. Rejected — the boilerplate vocabulary dominates cosine space across this codebase's auto-extracted skills; even genuinely distinct skills score above 0.90. A threshold knob cannot separate patterns that the embedding cannot see.

### Average-linkage instead of single-linkage union-find

Replace single-linkage with average-linkage to reduce chaining. Rejected — the 18 skills form a near-complete graph at ≥0.80 cosine, so average-linkage at that threshold still merges them. Concrete-pattern differences do not move the embedding enough to avoid the blob at any reasonable threshold.

### Strip shared boilerplate from the similarity metric before scoring

Pre-process skill bodies to remove shared vocabulary before computing cosine similarity. Rejected — defining "what is boilerplate" requires precisely the kind of judgment the embedding cannot make. Brittle heuristics would need to be maintained and would fail on new domain vocabulary.

### Keep embedding clustering and only fix the merge prompt

Leave grouping as-is and fix only the synthesis-to-union inversion in the merge prompt. Rejected — the inverted merge prompt addresses within-group flattening but not over-grouping. The blob still forms; the merge step still receives one undifferentiated component.

### Right-size `num_ctx` per caller to address the original performance hang

Fix the M1 hang by capping `num_ctx` per caller rather than switching the grouping algorithm. Deferred as a separate concern. The real slowness on M1 16 GB is the generation model (qwen3.5:9b) swapping during inference; that is a model-selection question, not a stocktake-algorithm one, and is out of scope here.

## Consequences

### Positive

- Duplicate detection discriminates on concrete behavior again. Live result: 18 skills → 5 small groups + 8 standalones; the merge gate rejected 2 groups via `CANNOT_MERGE` and merged 3, producing a sensible 18→16 consolidation with no blob.
- The union-oriented merge prompt preserves distinct concrete patterns. Of the 5 patterns that the synthesis-merge had dropped, 2 were fully recovered and 2 were partially recovered.
- One LLM grouping call replaces O(N²) pairwise calls, keeping the operation fast while eliminating the original hang. The `SIM_CLUSTER_THRESHOLD` constant and its two call sites are removed entirely.

### Negative

- LLM grouping is not exhaustive; it can still miss an obvious near-duplicate pair. Observed in the same live run: `fluid-administrative-content-coupling-with-frictio` was left standalone despite being a near-verbatim twin of `fluid-engagement-coupling-and-reformation`.
- Merging already-broad inputs can yield an over-broad merged skill. One result from the live run carried 10 triggers, which is below the selectivity threshold that makes a skill reliably actionable.
- The single grouping call is bounded by `num_ctx` for very large skill stores. This is not currently a constraint but becomes one as the store grows.
- The deepest ceiling — auto-extracted skills being jargon-dominated with shared contemplative-AI boilerplate — is upstream in the insight extraction prompt. That problem is consciously out of scope for this ADR and is accepted as the agent's current extraction limit.

### Neutral / Follow-ups

- The embedding-clustering approach this supersedes was introduced in commit `316719f` (2026-04-15) and was never recorded in its own ADR. The removal is recorded here.
- If the skill store grows to the point where a single grouping call exceeds `num_ctx`, a candidate approach is two-pass grouping: lightweight embedding pre-filtering to produce candidate pairs, followed by LLM judgment on those pairs only.

## Related

- [ADR-0016](./0016-insight-narrow-stocktake-broad.md) — Insight as Narrow Generator, Stocktake as Broad Consolidator; this ADR refines the stocktake consolidator's duplicate-detection mechanism.
- The embedding-clustering approach this supersedes was introduced in commit `316719f`, not its own ADR.

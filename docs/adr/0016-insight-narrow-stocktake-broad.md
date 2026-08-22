# ADR-0016: Insight as Narrow Generator, Stocktake as Broad Consolidator

## Status

partially-superseded-by ADR-0097 (the stocktake-as-broad-consolidator half retired 2026-08-22 — consolidation moved to the Saturday gate; insight-as-narrow-generator, the BATCH_SIZE=10 cap, the self-reflection routing and the rarity removal remain in effect)

## Date

2026-04-11

## Context

The insight pipeline had accumulated three tightly-coupled mechanisms that each tried to solve a different quality problem:

1. **Subcategory batching** (`_build_subcategory_batches`) to give the LLM thematically coherent input per batch.
2. **Two-stage clustering** (`_group_patterns`, introduced in `2ced140`): within each subcategory batch, a second LLM call split the top-30 patterns into themes, producing multiple skills per batch.
3. **Rarity scoring** (`_score_rarity_existing`, `_score_rarity_batch`, `DISTILL_RARITY_PROMPT`): an LLM-scored novelty value used only as a tiebreaker in `importance * rarity` sorting.

Empirical result (2026-04-11 run, 214 patterns):

- 7 subcategory batches → 22 extracted skills
- User manual selection kept 6/22 (27% retention)
- Selection feedback: "22 skills were nearly identical" — the Emptiness axiom dissolves specificity when 30 patterns collapse into 1 skill.

Separately, two latent defects surfaced:

- **rarity scoring stuck at 1.0**: `_score_rarity_existing` filters comparison baseline to `rarity is not None`, so initial runs have empty baseline → all patterns get `1.0`, and the code never re-scores them because the main loop only touches `rarity is None`.
- **identity distillation input was ambiguous**: `distill_identity` pulled from the top-50 importance-sorted patterns across all subcategories, mixing behavioral norms with self-observations. Self-reflection patterns (the natural identity material) competed with technical/communication patterns for slot space.

The homogenization problem cannot be solved by sort-key tweaks because the root cause is the Emptiness constitutional axiom, which operates *during* LLM synthesis. No amount of pre-sort reshuffling changes what the model dissolves downstream.

## Decision

Establish an explicit role separation between insight and skill-stocktake, then simplify insight to match:

**Insight = narrow generator.** One skill per subcategory per run, fed the top-N most important patterns from that subcategory. No cross-subcategory synthesis, no within-batch clustering.

**Skill-stocktake = broad consolidator.** Cross-subcategory merging, duplicate detection, cross-cutting theme discovery. Operates on the skill file space, not the pattern space.

Concrete changes:

1. **Drop rarity scoring entirely.** Remove `_score_rarity_existing`, `_score_rarity_batch`, `DISTILL_RARITY_PROMPT`, `config/prompts/distill_rarity.md`, the `rarity` field on `KnowledgeStore.add_learned_pattern`, and `_FALLBACK_RARITY` in insight. Insight sort key becomes `importance` alone.

2. **Drop `_group_patterns` (two-stage clustering).** The second-stage LLM clustering was redundant with subcategory grouping and compounded Emptiness dissolution by collapsing more patterns per skill.

3. **Narrow `BATCH_SIZE` from 30 → 10** in insight. Smaller input preserves specificity and keeps per-run LLM call count bounded as knowledge grows.

4. **Route `self-reflection` subcategory to `distill_identity`.** Exclude it from insight entirely. `distill_identity` now reads only `self-reflection` patterns via `KnowledgeStore.get_context_string(category="uncategorized", subcategory="self-reflection", limit=50)`. A new `subcategory` parameter is added to `get_context_string`.

5. **Do not attempt to solve homogenization at the insight layer.** Acknowledge it as a constitutional effect (Emptiness axiom) and rely on skill-stocktake + user selection for quality control.

## Alternatives Considered

- **Fix rarity instead of removing it.** Possible fix: track `id(p)` to exclude the current batch from the baseline. Rejected because importance and rarity overlap conceptually (a novel-but-important pattern already scores high on importance), rarity was only used as a sort tiebreaker, and subcategory batching already provides the diversity that rarity was meant to add.

- **Keep the 30-pattern cap.** Rejected because the checkpoint showed a 27% user selection rate at cap=30, and smaller caps directly reduce the "patterns-per-skill" ratio that drives Emptiness dissolution. Cap=10 also skips below the `_GROUP_SKIP_THRESHOLD=10`, which made the two-stage clustering redundant anyway.

- **Keep `_group_patterns` for "future scale".** Rejected as speculative dead code. If a future use case needs cross-cluster thematic splits, skill-stocktake is the correct place — it has a global view of skills across runs, not a local view within one batch.

- **Flatten everything: drop subcategory batching, use global top-N importance.** Rejected because subcategory serves a legitimate purpose: it gives the extraction prompt a thematic label to frame the skill. Without it, the LLM must infer theme from content alone, and identity/behavior routing becomes impossible.

- **Route self-reflection through a side channel without changing insight.** Rejected because letting self-reflection leak into both insight and identity creates duplicate outputs and blurs the "internal state vs. external behavior" distinction that motivates the routing.

## Consequences

- **Fewer, more focused skills per run.** Max 6 skills per run (7 subcategories − self-reflection), each summarizing ≤10 patterns. LLM calls per insight run drop from ~28 (grouping × 7 + extraction × 22) to ~6 (extraction only).

- **Identity distillation has a cleaner input.** Self-reflection patterns feed identity; behavioral patterns feed skills. The feedback loop (identity shapes patterns, patterns update identity) is confined to self-observation data, reducing drift from behavioral norms.

- **Stocktake becomes load-bearing.** Because insight emits subcategory-aligned skills, cross-cutting themes only emerge through stocktake. If stocktake is not run regularly, the skill space will grow flat (6 buckets × N runs). This is acceptable given that `skill-stocktake` is already a standard operation with `--stage`/`adopt-staged` workflow.

- **Rarity is gone from the knowledge schema.** Existing `knowledge.json` entries with a `rarity` field are tolerated (the field is ignored on load) and will be stripped on the next write cycle. No migration script needed.

- **Homogenization is explicitly unsolved.** Future work on constitutional presets (non-Emptiness axioms) or identity-distill prompt refinement is the path to address it — not sort-key engineering.

- **Aligns with `feedback_simplicity`**: the change reduces ~130 lines of code, one LLM pipeline pass, and one prompt template file, while making the design principle explicit for future readers.

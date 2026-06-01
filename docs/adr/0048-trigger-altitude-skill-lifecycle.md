# ADR-0048: Trigger-Altitude for Skill Lifecycle

## Status

accepted

## Date

2026-06-02

## Context

Auto-extracted skills carry episode-derived "When to Use" triggers that are studded with transient surface identifiers — specific usernames, post or topic IDs, saturated relevance scores (e.g. `>0.92`), and timestamp or duration windows. Such triggers match only the exact past episode that produced them; they do not fire on future analogous situations, which defeats the purpose of a reusable skill.

This is a lifecycle problem that spans three stages. (1) **Generation** — `insight` extraction emits the transient triggers verbatim. (2) **Consolidation-merge** — `stocktake` detects redundant skill groups and produces a merged skill, but the merge prompt did not generalize triggers; surface identifiers passed through unchanged. (3) **Consolidation-clean** — skills with no merge twin keep their raw episode-derived triggers forever; there was no pass at all for un-merged singletons.

Commit `c20ec5f` ("require recurring structural triggers in skill extraction") tightened stage 1 retroactively, but stages 2 and 3 remained untreated. Every outward generation (`generate_comment` / `generate_reply` / `generate_cooperation_post`) injects all skill bodies into the system prompt, so an oversized corpus of narrowly-triggering skills contributes both mis-fires and unnecessary token bloat.

A frontmatter regression surfaced while implementing the clean phase. The merge prompt (`config/prompts/stocktake_merge.md`) emitted no YAML frontmatter, so merged skills lacked `name`, `description`, and `origin`. The clean phase (`core/stocktake.py`) rewrote a frontmatter-stripped body and wrote it back to the original filename, silently dropping the source file's frontmatter — including reflection bookkeeping fields (`last_reflected_at`, `success_count`, `failure_count`) and `origin`.

## Decision

Apply trigger-altitude generalization at all three lifecycle stages and fix frontmatter handling throughout.

1. **Stage 1 — Insight generation** (`config/prompts/insight_extraction.md`): require recurring structural triggers; generalize transient identifiers. Retroactive, implemented in commit `c20ec5f`.

2. **Stage 2 — Stocktake merge** (`config/prompts/stocktake_merge.md`): generalize transient surface identifiers in triggers to structural altitude. Drop a saturated relevance score's numeric value entirely (write "high relevance", never "high relevance (>0.92)"); retain genuine recurring thresholds (e.g. "more than 3 times in 7 days"). Collapse triggers that become structurally identical after generalization. The merge prompt now emits a YAML frontmatter block (`name` / `description` / `origin: auto-extracted`), mirroring `config/prompts/insight_extraction.md`.

3. **Stage 3 — Stocktake clean** (`core/stocktake.py` `clean_skill_triggers` + `config/prompts/stocktake_clean.md`): a new phase. A singleton with no merge twin has its "When to Use" triggers rewritten at structural altitude directly. A `CLEAN_NOOP` sentinel makes the pass idempotent across runs.

4. **Grouping** (`config/prompts/stocktake_skills.md`): judges trigger sameness at structural altitude, not at surface-identifier level.

5. **Frontmatter handling**: the clean phase preserves the original file's frontmatter verbatim by re-attaching it to the rewritten body via `text_utils.split_frontmatter`. For legacy skills that predate frontmatter emission, `text_utils.synthesize_frontmatter` produces a minimal block. This fixes the clean frontmatter-loss regression and keeps reflection bookkeeping intact.

## Alternatives Considered

### Verbatim triggers (status quo)

Keep episode-derived specifics unmodified. Rejected — triggers fire only on the exact past episode; saturated scores and usernames never generalize, so skills do not transfer to analogous future situations.

### Numeric cap on skill count

Cap the corpus at N skills and drop the remainder. Rejected — a numeric quality filter on LLM output is an anti-pattern (`no-numeric-caps` rule); it would remove skills by count rather than by redundancy, discarding valid skills once the cap is hit.

### Embedding clustering for consolidation

Revive cosine-based grouping to identify near-duplicate skills for trigger normalization. Rejected — already rejected in [ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.md) on the grounds that embedding-cosine over-merges on shared contemplative-AI boilerplate vocabulary. Trigger-altitude operates inside the LLM grouping and merge path, not via a revived embedding clusterer.

### Skip frontmatter emission entirely

In all-injected single-shot generation a frontmatter `description` is dead-weight the LLM reads as part of each skill body. Rejected by the maintainer in favor of frontmatter hygiene and as a latent input for a possible future deterministic metadata view; preservation additionally fixes the frontmatter-loss regression.

### LLM-synthesized frontmatter on every clean

Regenerate frontmatter from scratch on each clean pass rather than preserving the original. Rejected — regenerating frontmatter would lose reflection bookkeeping (`success_count` / `failure_count`) and could alter `origin` and `name`. Preservation is chosen; synthesis is used only for frontmatter-less legacy inputs.

## Consequences

### Positive

- Surviving skills carry reusable, structurally-general triggers. A live run consolidated 16 skills to 6 (3 merges consuming 13 source files + 3 cleaned singletons), substantially cutting skill-corpus token bloat.
- Frontmatter is now emitted on merges and preserved on cleans, with reflection bookkeeping (`success_count` / `failure_count` / `last_reflected_at`) intact.
- `CLEAN_NOOP` keeps the clean phase idempotent; re-running stocktake on an already-cleaned corpus produces no churn.

### Negative

- Altitude generalization in the merge phase is stochastic: `qwen3.5:9b` occasionally retains a saturated relevance score in a trigger (one occurrence in the live run, hand-corrected before `adopt`).
- Aggressive consolidation can yield over-broad merged skills. One 7-to-1 merge in the live run produced a 10-trigger skill, below the selectivity threshold noted in [ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.md).
- A merged skill's frontmatter `name` may not match its filename slug, mirroring existing behavior in insight extraction.

### Neutral / Follow-ups

- The clean phase only generalizes "When to Use" triggers. A saturated score embedded in a skill's Solution body is preserved verbatim; that case is out of scope.
- The deeper monotonic-growth pressure — insight keeps generating skills; [ADR-0036](./0036-sunset-skill-as-memory-loop.md) retired the embedding usage-log retirement signal — leaves stocktake as the only counter-pressure. A periodic stocktake cadence or a future deterministic retirement signal is separate ADR territory.

## Related

- [ADR-0016](./0016-insight-narrow-stocktake-broad.md) — Insight as Narrow Generator, Stocktake as Broad Consolidator; this ADR extends the clean and merge stages of that pipeline.
- [ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.md) — Stocktake Duplicate Detection — LLM Grouping over Embedding Clustering; trigger-altitude operates within the LLM grouping and merge path established there.
- [ADR-0036](./0036-sunset-skill-as-memory-loop.md) — Sunset Skill-as-Memory Loop; retirement of the embedding usage-log signal that leaves stocktake as sole counter-pressure to skill-corpus growth.

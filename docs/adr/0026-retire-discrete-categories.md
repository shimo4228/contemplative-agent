# ADR-0026: Retire Discrete Categories (Phase-3 Completion of ADR-0019)

## Status

accepted

## Date

2026-04-16

## Context

ADR-0019 replaced the LLM classify / subcategorize calls with two structurally distinct mechanisms: a per-pattern `embedding` (semantic coordinate) and a `views/` directory whose Markdown seed files materialise analytical axes at query time. Two residues from the old schema survived that transition:

1. **`category: "constitutional" | "uncategorized" | "noise"`** — a discrete label still written onto every pattern, now produced by embedding-centroid classification rather than an LLM call, but still a state field on the pattern row.
2. **`_INSIGHT_EXCLUDED_VIEWS = {"self_reflection", "noise", "constitutional"}`** — a hard-coded exclusion set inside `core/insight.py` that prevents skill extraction from running over the `constitutional` view.

The combination produces three compounding issues:

1. **The `constitutional` view is dead from the insight path.** `extract_insight` filters `raw_patterns` to `category == "uncategorized"` before ever calling `view_registry.find_by_view(...)`, and then the build-batches step further excludes the `constitutional` view. Any pattern that the classifier tagged as `constitutional` is therefore unreachable from skill extraction by construction, even though the `constitutional` view exists and `amend_constitution` uses it.
2. **Two axes encode the same decision.** "Should this pattern participate in constitutional amendment?" is asked both by `category == "constitutional"` (a row field set once at distill time) and by `view_registry.find_by_view("constitutional", ...)` (a query-time cosine match). When the two disagree — new view seeds, drifted centroids — the row field wins because it gates access.
3. **The schema-vs-Emptiness friction ADR-0019 opened is still partly unresolved.** ADR-0019 argued that "classification is a query, not state — store the coordinate, materialise the cut at query time." The `category` field is exactly the kind of frozen analytical axis that argument pushed out — we removed `subcategory` but kept a narrower version of the same problem.

The situation is stable (the agent works), but the pipeline quietly diverges from the architectural claim ADR-0019 made. This ADR finishes the migration.

A separate but complementary question — whether `noise` judgment itself should remain a gating decision at all, or whether noise episodes should be preserved as "seeds" for later re-classification — is intentionally out of scope here. That belongs in ADR-0027 (proposed: "Noise as Seed").

## Decision

Retire the pattern-level `category` field in three ordered phases. Each phase is independently testable, independently revertable, and leaves the system in a working state.

### Phase 1 — Remove `category` gating from the insight read path

`core/insight.py`:

- Drop `"constitutional"` from `_INSIGHT_EXCLUDED_VIEWS`. Keep `"self_reflection"` (routed to `distill_identity`) and `"noise"` (gate decision) in place.
- Change `knowledge_store.get_live_patterns(category="uncategorized")` and `get_live_patterns_since(..., category="uncategorized")` (three call sites on lines 213 / 217 / 220) to drop the `category` argument. The insight path now reads all live patterns and lets views do the routing.

Expected effect: constitutional-tagged patterns become reachable from `extract_insight`, matched against whichever view's centroid they actually land near. If a pattern was tagged constitutional because its noise/const embedding similarities went that way, it will still match the constitutional view in `_build_view_batches` — the view is no longer unreachable.

No schema change. Both `category` and `views` keep writing/being-read — only the hard exclusion disappears.

### Phase 2 — Replace three-way classification with a binary `gated` flag

`core/distill.py`:

- Replace the three-tuple `_ClassifiedRecords(constitutional, noise, uncategorized)` with a two-tuple `_ClassifiedRecords(kept, gated)`. Noise episodes go to `gated`; constitutional and uncategorized merge into `kept`.
- Rewrite `_classify_episodes` to compute only `noise_sim` and set `gated = noise_sim >= NOISE_THRESHOLD`. The `CONSTITUTIONAL_THRESHOLD` constant remains in the codebase (Phase 3 deletes it) but is no longer read here.
- Remove the `for category, cat_records in [("uncategorized", ...), ("constitutional", ...)]` loop in `distill`; call `_distill_category` once with `kept` and a single placeholder category string (temporarily `"uncategorized"` for schema compatibility — Phase 3 drops the argument).
- `_distill_category`'s dedup scope still filters `existing_same_cat` by `category == "uncategorized"` — this becomes a no-op post-migration (all rows get that value), and Phase 3 removes the filter.

`core/constitution.py`:

- Replace `knowledge.get_learned_patterns(category="constitutional")` and `knowledge.get_context_string(category="constitutional")` with view-based retrieval. Concretely: load the agent's `ViewRegistry`, call `view_registry.find_by_view("constitutional", knowledge.get_live_patterns())`, and format the matched pattern bodies into the prompt. `amend_constitution` needs a `view_registry` argument added (same shape as `distill_identity`); the CLI's `_handle_amend_constitution` passes it in.

Expected effect: new patterns still end up in `knowledge.json` with `category = "uncategorized"` (schema-preserved), the noise gate still works, and `amend_constitution` reads via views instead of the row field. The `category` field becomes a vestigial constant for every new row.

Test impact: `tests/test_distill.py` `_ClassifiedRecords` assertions (4 cases), `tests/test_constitution.py` (2 cases).

### Phase 3 — Drop the `category` field and ship a migration

`core/knowledge_store.py`:

- Remove the `category` parameter from `add_learned_pattern`. Stop writing the field in `_parse_json` / `save`.
- Delete `_filtered_pool`'s `category` branch. `get_raw_patterns(category=...)`, `get_learned_patterns(category=...)`, `get_context_string(category=...)`, `get_live_patterns(category=...)`, `get_live_patterns_since(since, category=...)`, and `get_raw_patterns_since(since, category=...)` lose their `category` parameter. Callers have already moved off it by Phase 2 — this is sweep-up.

`core/distill.py`:

- Drop the `category` argument from `_distill_category` and `add_learned_pattern(..., category=...)`.
- Dedup scope becomes "all live patterns" (no per-category split). Cross-axis duplicates were already deduplicatable via views; the row-level split was artificial.
- `_distill_category`'s `MEMORY_EVOLUTION_PROMPT` branch drops its `category == category` predicate on `live_same_cat`.

`core/migration.py`:

- Add `drop_category_field(knowledge: KnowledgeStore, *, dry_run: bool = False) -> MigrationStats`. Follows the `backfill_pattern_embeddings` shape: in-place mutate (or count in dry-run), caller saves. Handles legacy `category == "noise"` by preserving it as `gated = True` (a binary flag separate from the retired ternary label).
- CLI: add `_handle_migrate_categories` next to `_handle_migrate_patterns`. Same ergonomics — `--dry-run`, summary output, `_log_approval("migrate-categories", ...)` entry.

Test impact: `tests/test_migration.py` gets 2–3 new cases for `drop_category_field`; `tests/test_knowledge_store.py` loses its `category`-filter assertion; `tests/test_memory_evolution.py` loses its `category`-preserve check.

## Alternatives Considered

1. **Big-bang removal in a single commit.** Considered and rejected: the cross-file surface is 8 modules (`insight.py`, `distill.py`, `constitution.py`, `knowledge_store.py`, `memory_evolution.py`, `migration.py`, `views.py`, plus tests). A single-commit removal passes tests but is hard to bisect if post-merge behaviour drifts. Three-phase keeps each step under ~60 LOC net.
2. **Keep `constitutional` as a distinct row-level namespace, just remove insight's hard exclusion.** Smaller change, but it leaves the schema/query duplication unresolved. The `constitutional` view would become reachable from insight, but the `category == "constitutional"` branch in `distill` and `amend_constitution` would continue encoding the same decision twice. That's the worst-of-both-worlds state the ADR-0019 author explicitly argued against ("partial migrations rot").
3. **Derive `gated` at query time rather than persisting it.** Same argument ADR-0019 made and rejected for the same reason: noise classification gates pipeline steps, making it derived would force re-embedding every episode every distill run. Persist the gate decision, query the semantic axis.
4. **Collapse noise gating too (the "radical" option).** Deferred to ADR-0027. The motivation for that change is a different axis (is the noise judgment itself appropriate?) and the implementation risks are different (LLM prompt volume, `num_ctx` truncation, forgetting-dependent cleanup). Keeping the scopes separate keeps rollback surfaces small.
5. **Rename `category` → `namespace` instead of removing it.** Doesn't resolve the state-vs-query friction. Rejected.

## Consequences

**Positive**:

- `amend_constitution` and `extract_insight` read through the same mechanism (`ViewRegistry`), closing the divergence where the same conceptual question ("which patterns are constitutional?") had two answers that could disagree.
- Adding a new analytical axis (say, an `aesthetic` view) no longer requires rerunning a classifier over existing patterns — you write a seed Markdown file and the view materialises at query time. This is the full payoff of ADR-0019's central claim.
- Migration is one-shot and reversible: `knowledge.json.bak.{timestamp}` is auto-saved before mutation, and rolling back is `cp` + deleting the post-migration file.
- Test suite shrinks (estimated net removal ~80 LOC once Phase 3 lands).

**Negative / risks**:

- Phase 2 changes the signature of `amend_constitution` (adds a required `view_registry` argument). The single CLI caller is updated in lockstep; the risk is limited to that site.
- `NOISE_THRESHOLD = 0.55` is now the only knob controlling what enters distillation. Mis-tuning it after this ADR lands has a wider blast radius than before (previously a pattern could survive as "constitutional" even if it looked noise-ish). Mitigation: dry-run on a 14-day window before shipping the Phase-2 thresholds change; no threshold change is landing with this ADR.
- Legacy `knowledge.json` files that were tagged `category: "noise"` via the pre-0019 LLM classifier (unlikely to exist in this codebase, but possible in cloned research data) need the migration to preserve them as `gated: True` rather than silently dropping the signal. The migration handles this explicitly.
- The `category`-indexed dedup scope (`distill._distill_category`) becomes cross-namespace after Phase 3. Some constitutional-ish patterns may now deduplicate against uncategorized-ish patterns they wouldn't have previously collided with. Acceptable — the Emptiness axiom argues against keeping separate namespaces for what is ultimately the same semantic coordinate.

**Explicitly not addressed** (next ADR territory):

- Whether the `noise` gate itself should persist (ADR-0027 candidate).
- Any reshaping of the per-view thresholds (per-view tuning is already in `views/*.md` frontmatter).
- Runtime retrieval re-evaluation of past patterns when view centroids shift (ADR-0027 territory).

## Rollback Plan

Each phase is independently revertable:

- **Phase 1**: restore the three insight.py lines. The schema hasn't changed, so no data work needed.
- **Phase 2**: restore the three-tuple `_ClassifiedRecords`, the two-category loop in `distill()`, and the `category="constitutional"` reads in `constitution.py`. New patterns written under Phase 2 already carry `category = "uncategorized"`, so they survive the revert unchanged.
- **Phase 3**: the migration is in-place but the pre-migration backup `.bak.{timestamp}` is the authoritative rollback artifact. Restore it and re-run distill; any patterns added after the migration will need to have their `category` field set from their `embedding` (rerun classification). Mitigation: don't land Phase 3 on the same day as data-volume operations.

## Migration

`drop_category_field` is idempotent. Running it twice on a legacy file produces the same result. Running it on a Phase-3 file with no `category` fields is a no-op. The CLI reports "already migrated" in that case.

```
contemplative-agent migrate-categories --dry-run   # count only
contemplative-agent migrate-categories             # actually migrate
```

The migration:

1. Loads `knowledge.json` (via `KnowledgeStore`).
2. For each pattern: if `category == "noise"`, set `gated = True` (rare — primarily a defense for legacy research data). Always delete the `category` key.
3. Writes the result via `KnowledgeStore.save()`.

The `audit.jsonl` entry is written by the CLI, same pattern as `migrate-patterns` (ADR-0021) and `migrate-identity` (ADR-0025).

## References

- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — declared the direction; this ADR finishes the `category` half of that direction.
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — the `migrate-patterns` CLI shape that `migrate-categories` mirrors.
- [ADR-0025](0025-identity-history-and-migrate-cli.md) — the deferred-wiring-lands-now discipline this ADR reuses.
- Internal issue tracker (local-only) entry N4 — motivated this ADR.

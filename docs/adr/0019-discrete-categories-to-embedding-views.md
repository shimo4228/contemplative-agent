# ADR-0019: Discrete categories → Embedding + Views

## Status
accepted

## Date
2026-04-15

## Context

The original Knowledge layer (ADR-0004) shipped two discrete-label fields on each pattern:

- **`category`** — `constitutional` / `noise` / `uncategorized` (set by Step 0 LLM classify, one call per episode)
- **`subcategory`** — `communication` / `reasoning` / `social` / `content` / `self-reflection` / `technical` / `other` (set by `_subcategorize_patterns`, one LLM call per pattern)

Three problems compounded:

1. **Operational cost.** With ~500 episodes/day, Step 0 alone burned ~17 minutes of LLM time daily; subcategorize added another LLM call per new pattern; and `_dedup_patterns` used `SequenceMatcher` (language-surface similarity, blind to paraphrase) backed by an `_llm_quality_gate` that fired one extra LLM call per uncertain pair.
2. **Architectural friction with the Emptiness axiom.** The constitution explicitly rejects "rigidly reifying any single objective as final", yet the schema baked a fixed taxonomy into pattern state. Identity is allowed to drift through distillation, but the analytical axes that rank and route those patterns were frozen at design time.
3. **State / query confusion.** Subcategory is fundamentally a *query* ("which patterns are about communication?") that was being persisted as *state*. Adding a new analytical axis (e.g. a self-reflection sub-flavour) required re-labelling every existing pattern.

`core/embeddings.py` had already been introduced (commit `316719f`) for the stocktake clustering use case, which made cosine similarity available without standing up new infrastructure.

## Decision

Replace both discrete-label fields with two structurally distinct mechanisms:

1. **Embedding state.** Every pattern carries an `embedding: List[float]` (1024-dim from `nomic-embed-text`). It is the single semantic coordinate.
2. **Views as queries.** A `views/` directory of seed-text Markdown files defines analytical axes at query time. `ViewRegistry.find_by_view(name, candidates)` embeds the seed and ranks candidates by cosine, applying per-view threshold and top_k.

A small **binary `gated`** flag survives — but only because it represents a *gate decision* ("should this episode enter distillation?"), not a category. Gated patterns are derived from the `noise` view's centroid distance against an episode embedding.

Concretely:

- `_dedup_patterns` is now embedding cosine: `SIM_DUPLICATE=0.92` → SKIP, `SIM_UPDATE=0.80` → boost importance, else ADD.
- `_subcategorize_patterns` and the `subcategory` field are deleted entirely.
- `_classify_episodes` is embedding centroid argmax against the `noise` and `constitutional` view seeds. Patterns with `noise_sim ≥ NOISE_THRESHOLD` are gated; `constitutional_sim ≥ CONSTITUTIONAL_THRESHOLD` enters the constitutional namespace; otherwise uncategorized.
- `extract_insight` builds one batch per non-excluded view; the `self_reflection` view is excluded (those patterns route to `distill_identity`).
- `distill_identity` selects patterns via `ViewRegistry.find_by_view("self_reflection", ...)` rather than the deleted subcategory filter.
- Internal callers of `generate()` no longer pass `max_length`; the char cap on `_sanitize_output` was an SNS-platform constraint that had been spuriously affecting internal pipelines (rules_distill output was silently truncated mid-rule on 2026-04-11). Only post / comment / reply / title callers retain `max_length`.
- A `embed-backfill` CLI subcommand bulk-embeds existing knowledge.json patterns and the full episode log into a SQLite sidecar (`embeddings.sqlite`), preserving the JSONL append-only contract.

This was prompted by an explicit Architect-agent review that recommended option β (full removal of discrete categories) over option α (keep the field, just produce it via embedding). The review's central argument: *classification is a query, not state — store the coordinate, materialise the cut at query time.*

## Alternatives Considered

1. **α: Keep `subcategory` field, replace only the LLM call.** Smallest delta (just swap the producer), but doesn't fix the schema-vs-Emptiness friction or the migration-on-axis-addition problem. Rejected — leaves the structural issue intact.
2. **γ: Hybrid — keep field but optional, new routing via embedding.** Postpones the full migration but creates a parallel-axis period that's worse than either endpoint. Rejected — partial migrations rot.
3. **`gated` derived per-query rather than persisted.** Considered, but episode classification is a one-shot decision that gates downstream pipeline steps; making it derived would force every distill run to re-embed every episode. Persistent `gated` is a binary cache of a gate decision, not a category.
4. **Custom JSON schema for views (rules + threshold + weights).** Considered for richer view definitions. Rejected for now — the seed-text Markdown is enough; YAML frontmatter handles `threshold` and `top_k`. Add complexity only if a real use case appears.

## Consequences

- LLM cost reduction: classify (~17 min/day) + subcategorize + dedup gate are gone. Net daily LLM time drops by ~20 minutes for typical episode volumes.
- Migration is one-shot via `embed-backfill`. `~/.config/moltbook/` is git-untracked, so the command auto-saves `knowledge.json.bak.{timestamp}` before mutating; rollback is `cp` + delete sidecar.
- Storage: each pattern grows ~3 KB (1024 float32 + JSON encoding); 100 patterns ≈ 0.4 MB. Episode SQLite ~80 MB / month.
- `embed_texts` is now load-bearing for distill. Its failure mode is reduced functionality (patterns ADD without dedup), not pipeline failure.
- A new `nomic-embed-text` model dependency joins `qwen3.5:9b` in Ollama. M1 16 GB confirmed adequate.
- Threshold tuning is the new operational concern (`SIM_DUPLICATE`, `SIM_UPDATE`, `NOISE_THRESHOLD`, `CONSTITUTIONAL_THRESHOLD`, per-view thresholds). Defaults shipped from initial calibration; expected adjustment based on dry-run observation.
- The `noise` view is the only place the gate decision lives. Tuning it changes what enters distillation; document changes via `docs/adr/` if non-trivial.
- Test suite shrinks: `_llm_quality_gate`, `_subcategorize_patterns`, truncation guards, and their tests are deleted (~500 lines net removal).

## Key Insight

The mistake the original schema made was treating "what kind of pattern is this?" as a property of the pattern. It is not — it is a property of the question we want to ask of the pattern. Embeddings store the answer-shape; views store the questions; binding them happens at query time. The Emptiness axiom isn't a literary flourish — it has a structural reading, and this ADR is what acting on that reading looks like.

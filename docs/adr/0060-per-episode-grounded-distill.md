# ADR-0060: Per-Episode Grounded Distill — Replace Batch Extract + Noise Gate with One Grounded LLM Call per Engagement Episode

## Status

accepted

## Date

2026-06-23

## Context

Since the project's first day the distill pipeline never read the full text of the agent's posts
or comments. Its learning material was `summarize_record`'s digest: `internal_note` (full) +
`content_summary[:80]` (raw 80 characters) + `title` + an action label. Each activity record
also carries `original_post`, the other agent's comment (`their_comment`, replies), and the
agent's own output (`content`) — all discarded before the LLM ever saw them. The consequence is
structural: knowledge, identity, skills, and rules were built mainly from the agent's *introspection
about the world* (`internal_note`), not the world itself. This is the root of the self-referential
register collapse and echo-chamber behaviour that the weekly diagnosis kept chasing. Of the
approximately 2,946 characters available per episode in the activity store, only approximately 120
were consumed — a 24× idle budget.

The batch-extract step compounded the thinness problem. Thirty episodes were collapsed into a
single "extract patterns" LLM call followed by a refine call. Averaging 30 episodes in one context
window suppresses sharp one-offs and pulls the output toward a modal thematic register — a
flattening engine. The subsequent noise gate (introduced by [ADR-0026](./0026-retire-discrete-categories.md)
Step 0 and extended in [ADR-0027](./0027-noise-as-seed.md) Phase 1) embeds episode summaries,
computes cosine against a noise centroid, and gates at `NOISE_THRESHOLD 0.55`. This ingest-time
classification is redundant: downstream consumers — identity, constitution — reach patterns only
through fixed-seed view centroids at query time ([ADR-0031](./0031-classification-as-query.md)
"classification as query"), so noise patterns are simply never retrieved; `insight` has its own
`min-cluster-size` plus an LLM acceptance step as independent defenses.

Before committing to the redesign, a read-only measurement prototype was run against the production
store and episode log (`scripts/proto_grounded_distill.py`, results in
`docs/evidence/adr-0060/measurement-2026-06-22.md`) over a 3-day window. Four findings determined
the decision:

1. **Reinforce cannot fire cross-modal.** The locked design's reinforce branch was intended to
   skip the LLM when an incoming episode already resembled stored patterns (cosine ≥ 0.80). In
   practice, episode-vs-pattern cosine maxed at 0.765 — short of the threshold — because episodes
   are instances and patterns are generalizations: cross-modal comparison collapses similarity.
2. **Genuine episode-level near-duplication is rare.** At cosine 0.90, only approximately 3.4%
   of episodes in the window were near-duplicates of each other. Clustering saves approximately
   4 LLM calls per 3-day window, which is not a meaningful latency budget.
3. **Loose clustering flattens.** A 10-episode cluster at threshold 0.70 collapsed into thematic
   abstractions ("Complexity as a liability") — reproducing the exact register collapse the
   redesign was meant to cure. Clustering is the one component that demonstrably degrades quality.
4. **Singletons are grounded and selective.** One episode → one LLM call produced specific,
   world-facing patterns and correctly returned `[]` on routine episodes, preserving the intent
   of the noise gate without the dedicated gate machinery.

Latency is acceptable: a per-episode call on `qwen3.5:9b` with the small per-episode context runs
approximately 17 seconds (no swap); approximately 115 calls per 3-day window amounts to
approximately 12 minutes per day for a daily batch.

This ADR supersedes the clustering-based design briefly locked in a planning handoff (D3), the
ingest-time noise gate of [ADR-0026](./0026-retire-discrete-categories.md) Step 0, and the
noise-log writer of [ADR-0027](./0027-noise-as-seed.md) Phase 1.

## Decision

Distill each substantive engagement episode individually through a single grounded LLM call.

1. **Scope filter (`_is_rich_episode`).** Distill only activity records for `RICH_ACTIONS =
   {comment, reply, post}`. Drop the short paired interaction/post-type records (each engagement
   writes both a rich record and a short paired record) and the template sparse actions
   (`upvote`, `follow`, `unfollow`) that carry no engagement content. The insight-record read
   exclusion established by [ADR-0052](./0052-retire-session-insight.md) is unchanged.

2. **Remove the noise gate entirely.** Delete `_classify_episodes`, `_ClassifiedRecords`,
   `_view_centroids_hash`, `_write_noise_log`, the `noise-*.jsonl` writer, the
   `NOISE_THRESHOLD` import, and the `view_registry`/`log_dir` parameters of `distill()`.
   Keeping noise out of retrieval is the view centroids' job at query time per [ADR-0031](./0031-classification-as-query.md).

3. **Render each episode richly (`render_episode`).** Produce a header followed by:
   `original_post`, `their_comment` (replies), the agent's own `content` and `title` (for posts),
   and `internal_note` in full. Each external field is excerpted by a new `truncate_boundary`
   helper (sentence → word → character, with a marker) at `EXCERPT_CAP` values set to the
   platform field limits (`original_post`/`content` = `MAX_POST_LENGTH` 40000, `their_comment` =
   `MAX_COMMENT_LENGTH` 10000), so realistic content is never cut: one episode per LLM call fits
   inside `NUM_CTX` (32768) with margin even at platform max — the worst-case reply estimates
   ≈21.6k input tokens for ASCII content (`llm._estimate_tokens`, ~3 chars/token) against a
   ~29k input budget after `num_predict`. `truncate_boundary` remains a structural guard for
   out-of-spec data; a pathological all-CJK render at platform max would be skipped (logged, not
   corrupted) by the existing `NUM_CTX` over-budget guard in `generate()`. `internal_note` is
   never capped. The measured field-length distribution (p90 ≈ original_post 4700 / content 4700 /
   their_comment 1500, max ≈ 7400; `docs/evidence/adr-0060/`) sits well within these caps, so no
   real episode is truncated — an earlier ~p90 cap choice was over-conservative given the NUM_CTX
   headroom.

4. **One LLM call per episode (`_distill_one`) with structured output.** Use the new
   `config/prompts/distill_episode.md` prompt constrained by an Ollama structured-output schema
   (`_PATTERNS_SCHEMA`, `{"patterns":[...]}`). This removes the malformed-JSON the old 2-step
   bullet fallback used to absorb (the prototype observed 2 of 5 malformed responses). Replaces
   the 2-step `_distill_batch` (extract → refine) and the fixed `BATCH_SIZE=30` batching
   (`_distill_category` → `_distill_episodes`).

5. **Per-episode provenance.** Each extracted pattern carries the single source episode's
   `source_type` and timestamp.

6. **Embed → cosine dedup → store tail is unchanged.** `_dedup_patterns` with
   `SIM_DUPLICATE 0.90` / `SIM_UPDATE 0.80` and `_store_new_patterns` remain. Pattern-level
   dedup is what prevents accumulation of duplicate patterns; a recurring episode's pattern is
   caught here (SKIP or UPDATE) without any episode pre-clustering. `DISTILL_PROMPT` and
   `DISTILL_REFINE_PROMPT` are kept in place, as they continue to serve `rules_distill`.

## Alternatives Considered

### Clustering-based design (reinforce / cluster / singleton routing on episode embeddings)

The design briefly locked in a planning handoff routed episodes through three branches on the
basis of embedding similarity: reinforce (skip LLM, update existing pattern) for episodes close
to stored patterns, cluster (one call per group) for near-duplicate episodes, singleton (one call
per episode) for distinct episodes. Rejected on prototype evidence: reinforce cannot fire because
episode-vs-pattern cosine is cross-modal (instance vs. generalization), peaking at 0.765 against
a 0.80 threshold; genuine near-duplication is approximately 3.4%, so clustering saves approximately
4 calls per 3-day window; and loose clustering was the one component that demonstrably produced
the register flattening being repaired. Recurrence of an episode's content belongs to `insight`
(pattern → skill), not `distill` (episode → pattern); routing episode pre-clustering through
`distill` also creates a two-stage-clustering coherence problem that disappears when clustering
is removed from this stage entirely.

### Keep the noise gate

Retain `_classify_episodes` and its ingest-time embedding classification. Rejected as redundant
with [ADR-0031](./0031-classification-as-query.md) query-time view centroids and `insight`'s own
`min-cluster-size` plus LLM acceptance defense. The gate is coarse, uncertain, and contradicts the
"classification as query" principle by making an admission decision at ingest rather than at
retrieval. Noise patterns that survive the gate are simply never retrieved by any downstream view.

### Enrich the digest but keep batch-extract

Widen `content_summary` and add external fields to the existing digest while preserving the 30-episode
batch call. Rejected because the averaging machine remains intact: the flattening is in the batching,
not only in the thin input. Register collapse is not cured by richer input if it is still pooled
across 30 episodes before the LLM sees it.

### Lower the reinforce threshold to make reinforce fire

Drop the reinforce cosine threshold from 0.80 to approximately 0.72 to capture the observed
episode-vs-pattern cosine range. Rejected: at that threshold, half the episode pool is marked
as "already known" against old-register patterns, suppressing new observations. The recency
benefit reinforce promised — refreshing a decaying pattern's timestamp — is already delivered by
the `SIM_UPDATE` branch of the unchanged pattern-level dedup step.

## Consequences

### Positive

- Patterns are grounded in the world — the other agent's post, their comment, the agent's own
  output — instead of only the agent's introspection (`internal_note`), directly addressing the
  structural root of the echo-chamber and register collapse.
- No batch averaging: each pattern derives from one coherent episode, preserving specificity and
  sharp one-offs. The LLM returns `[]` rather than fabricating a pattern from a routine episode.
- Structured output schema (`_PATTERNS_SCHEMA`) removes the malformed-JSON surface the old
  2-step bullet fallback existed to absorb.
- Net code removal: the noise gate, the 2-step extract-refine pipeline (`_distill_batch`,
  `_render_episode_lines`), and the fixed-size `BATCH_SIZE=30` routing are all deleted
  (`_distill_category` becomes the per-episode `_distill_episodes`).
- Consistent with the "observation should be faithful, not re-steered" trajectory established by
  [ADR-0058](./0058-value-injection-at-action-time.md) — feeding the external content is the
  natural completion of the same intent.

### Negative

- Approximately 14× more LLM calls per run (approximately 115 per 3-day window vs. approximately
  8 previously), yielding approximately 12 minutes per day on `qwen3.5:9b`. This is the honest
  price of per-episode grounding and is accepted as feasible for a daily batch.
- Knowledge grows faster and more granularly (approximately one pattern per distilled episode).
  Daily `insight` is bounded by `get_live_patterns_since` (inter-run window only, not the total
  store); pattern-level dedup (SIM_DUPLICATE 0.90 / SIM_UPDATE 0.80) throttles accumulation of
  duplicates; decay ranking (`0.95^days`) keeps the working set recent; and the no-delete policy
  retains patterns as research data. These mitigations are pre-existing.
- `insight --full` re-clusters the entire live pattern pool O(N²) and will slow as the pool grows
  faster. This is a pre-existing issue that faster pattern growth surfaces sooner. Mitigation, if
  the cost bites, is filtering `--full` candidates by the existing decay floor (approximately 58
  days).
- `epistemic_counts` shifts structurally: every distilled episode is an activity record
  (`_episode_source_kind=self` → `self_reflection` → `generated`), so the `observed` provenance
  kind is now structurally zero. External world content enters as grounding text within the
  episode render, not as a separate provenance kind. This is a documentation and monitoring
  concern, not a data-loss concern.

### Neutral / Follow-ups

- The throwaway measurement script (`scripts/proto_grounded_distill.py`) was removed once the
  per-episode design settled in production; its read-only measurement output is preserved in
  `docs/evidence/adr-0060/measurement-2026-06-22.md`.
- `docs/CODEMAPS/architecture.md` Data Flow section requires one update: the distill step is now
  one grounded LLM call per rich episode, not a 2-step batch call per 30 episodes, and the noise
  gate is absent — per the CLAUDE.md freshness rule, update in the same PR.
- `graph.jsonld` gains an ADR-0060 node (`supersedes` ADR-0026 Step 0 and ADR-0027 Phase 1;
  `alignsWith` ADR-0031, ADR-0058, ADR-0019) — deferred to the dual-update at release.
- This ADR supersedes ADR-0026 Step 0 (binary ingest-time noise gate) and ADR-0027 Phase 1
  (noise-log writer).

## References

- [ADR-0026](./0026-retire-discrete-categories.md) — binary noise gate at ingest; this ADR
  supersedes its Step 0.
- [ADR-0027](./0027-noise-as-seed.md) — noise-as-seed and noise-log writer; this ADR supersedes
  its Phase 1 noise-log writer.
- [ADR-0031](./0031-classification-as-query.md) — "classification as query"; the principle that
  makes ingest-time noise gating redundant — noise patterns are never retrieved by any view centroid.
- [ADR-0056](./0056-retire-importance-llm-scoring.md) — retired the importance LLM rating, making
  distill 2-step (extract → refine); this ADR takes distill from 2-step batch to one call per
  episode.
- [ADR-0058](./0058-value-injection-at-action-time.md) — axiom-free distillation; this distill
  remains base-only per that decision. The per-episode grounding extends the same "extract the
  external observation faithfully" intent by actually feeding the external content.
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — embedding handles structure,
  LLM handles value; embedding continues to do pattern-level dedup (structure), and the new LLM
  call does per-episode grounding (generation).
- [ADR-0045](./0045-pre-action-internal-note.md) — pre-action internal note; `render_episode`
  now pairs the `internal_note` this ADR introduced with the full world content the agent was
  responding to.
- [ADR-0052](./0052-retire-session-insight.md) — insight-record read exclusion; unchanged by
  this ADR.

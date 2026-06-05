# ADR-0021: Pattern Schema Extension — Provenance / Bitemporal / Forgetting / Feedback

## Status
partially-superseded-by ADR-0028 (Forgetting IV-3 + Feedback IV-10 retired 2026-04-18), ADR-0029 (dormant Provenance elements `user_input` / `external_post` / `sanitized` retired 2026-04-18), and ADR-0051 (trust weighting — `trust_score` / `TRUST_BASE_BY_SOURCE` / `TRUST_FLOOR` — retired 2026-06-05). Bitemporal (IV-2) and the `source_type` provenance surface remain in effect.

## Date
2026-04-16

## Context

After ADR-0019 (embedding + views) and ADR-0020 (pivot snapshots), the Layer 2 knowledge store has three structural gaps that a comparative survey of mature agent memory systems (Mem0, Letta, Zep/Graphiti, A-Mem, Memento-Skills, Cognee, MemoryBank) makes visible:

1. **Trust is lost at the episode → pattern boundary.** `EpisodeLog` records are untrusted (wrapped via `wrap_untrusted_content()`). After distillation, patterns enter `knowledge.json` with no source attribution and no trust score. They are then injected into system prompts indiscriminately. The 2025 MINJA attack (memory injection, 95%+ success rate against production agents) and the follow-up MemoryGraft (arXiv:2512.16962) demonstrate this is the critical vector — a single crafted external post can permanently shape the agent's behavior, and there is no structural means to detect or down-weight it.

2. **"Updating" a pattern silently destroys the previous truth.** `_dedup_patterns` with `SIM_UPDATE=0.80` mutates the existing pattern's `importance` and `distilled` timestamp in place. Replayability (ADR-0020) is preserved at the snapshot level but not at the pattern level: an individual pattern has no history of "what it used to say before last Tuesday's distill". Graphiti's bitemporal design (arXiv:2501.13956) addresses exactly this by keeping `valid_from` / `valid_until` on every edge.

3. **Forgetting is retrieval-blind.** `effective_importance = importance × 0.95^days_elapsed` decays with wall-clock time since distillation, but ignores whether a pattern is ever actually retrieved. Patterns that no view ever matches persist at full weight as long as they are fresh; patterns that carry the agent's daily work drop in weight just as fast as stale ones. MemoryBank (arXiv:2305.10250) uses the Ebbinghaus form `strength = e^(−t/S)` where `S` is reinforced by access.

4. **Patterns carry no signal of whether they helped.** There is no loop from action outcome back to the pattern that informed it. Cognee's memify layer demonstrates that even a crude `success_count` / `failure_count` on edges produces a useful self-correction gradient.

These four gaps share a property: all four require additions to the same dict schema, and all four are cheaper to add in one migration than four. Running four schema migrations against `knowledge.json` would each require a backup, a replay, and per-field tests. One migration covers them all.

## Decision

Extend the pattern dict in `knowledge.json` with nine optional fields, grouped by concern:

### Provenance (IV-7)

```
provenance: {
    source_type: "self_reflection" | "external_reply" | "mixed" | "unknown"
    source_episode_ids: List[str]   # up to K most representative
    pipeline_version: str            # e.g. "distill@0.21"
}
trust_score: float                   # 0.0 - 1.0
trust_updated_at: str                # ISO8601
```

> **ADR-0029 (2026-04-18)**: `user_input` / `external_post` `source_type` values and the `sanitized` provenance flag were retired (dormant since landing — no producer / no consumer in production). The original six-value enum and `sanitized: bool` field are preserved here for historical accuracy; `SOURCE_TYPES` in `knowledge_store.py` reflects the current four values.

Initial `trust_score` at distill time is derived from `source_type` with a fixed table:

| source_type | base trust |
|---|---|
| self_reflection | 0.9 |
| external_reply  | 0.55 |
| mixed           | min of inputs |
| unknown         | 0.6 |

> **ADR-0029 (2026-04-18)**: `external_post` (0.5) and `user_input` (0.7) rows were retired — neither had a producer in production.

The score is adjusted by: `+0.05` when a downstream approval gate (identity / skill / rule / constitution) accepts the pattern, `−0.1` when the pattern is invalidated by a contradicting newer pattern (see IV-4 in ADR-0022). A future `contemplative-agent flag-pattern <id>` CLI subtracts `0.3` on user flag.

> **ADR-0029 (2026-04-18)**: the `−0.2 if sanitized flag is false` adjustment was retired — the flag was always written true in production and had no consumer. Upstream sanitization already happens in `llm._sanitize_output`.

### Bitemporal (IV-2)

```
valid_from: str                      # ISO8601; initial = distilled timestamp
valid_until: str | None              # None = current truth; ISO8601 when superseded
```

`_dedup_patterns` is modified so that when a new pattern triggers `SIM_UPDATE` against an existing one, the existing pattern is not mutated in place. Instead it receives `valid_until = now` and a new pattern is added with `valid_from = now`, `valid_until = None`. Retrieval filters on `valid_until is None`.

### Forgetting (IV-3)

```
last_accessed_at: str                # ISO8601
access_count: int                    # retrievals that selected this pattern
strength: float                      # e^(−Δt / S), S = f(importance, access_count)
```

`strength` is computed lazily on retrieval using MemoryBank's formula:

```
Δt = hours since last_accessed_at
S  = BASE_S * (1 + log1p(access_count)) * (0.5 + importance)
strength = exp(−Δt / S)
```

`BASE_S = 240` (10 days) is the half-life anchor for a mid-importance, never-accessed pattern. Constants live in a new `forgetting.py` module.

Retrieval excludes patterns with `strength < STRENGTH_FLOOR (0.05)` — soft-archive without physical delete.

### Feedback (IV-10)

```
success_count: int                   # post-action signals of "this helped"
failure_count: int                   # "this caused a regression"
```

Populated asynchronously by a new `feedback.py` post-action updater that reads episode logs and attributes outcomes to patterns that were in the retrieval set for that action (attribution requires ADR-0023 skill router log, so updater is stub-only in this ADR).

### Retrieval scoring

`views.py` `_rank` is extended:

```
score = cosine_sim(seed_emb, pattern_emb)
      * trust_score
      * strength
```

with a hard filter `valid_until is None and trust_score >= TRUST_FLOOR (0.3) and strength >= STRENGTH_FLOOR (0.05)`.

Side effects on retrieval: increment `access_count`, set `last_accessed_at = now`. This is a mutation on read — acceptable here because the knowledge file is single-writer and retrieval is I/O bound elsewhere.

### Migration

One-shot `contemplative-agent migrate-patterns` CLI:

- Backup `knowledge.json.bak.pre-adr0021-{timestamp}`
- Fill defaults: `provenance.source_type = "unknown"`, `trust_score = 0.6`, `trust_updated_at = now`, `valid_from = distilled_timestamp or now`, `valid_until = None`, `last_accessed_at = last_accessed_from_legacy or now`, `access_count = 0`, `strength` is computed lazily (not stored), `success_count = 0`, `failure_count = 0`
- Idempotent: running a second time is a no-op
- No backfill of `source_episode_ids`; unknown patterns stay unknown

Persistence stays dict-based (not frozen dataclass) to minimize blast radius. Helper getters with defaults live on `KnowledgeStore`.

## Alternatives Considered

1. **Separate ADRs and migrations per field.** Technically cleaner. Rejected: four migrations against the same file multiply operational cost without reducing risk; the fields are logically independent but schematically coupled.

2. **Frozen dataclass for Pattern.** Aligns with the project-wide immutability rule. Rejected for this ADR — the existing code treats patterns as dicts throughout (`get_raw_patterns`, `_filtered_pool`, `add_learned_pattern` append to a list of dicts). Converting to a dataclass is a larger refactor that deserves its own ADR and its own risk budget. Current helper functions on `KnowledgeStore` already encapsulate most access; adding typed accessors is the lighter-weight step.

3. **Adopt Mem0 wholesale.** Covers ~2 of 4 gaps (atomic fact + partial UPDATE/DELETE semantics) but not IV-7 (trust) nor IV-3 (forgetting) nor the bitemporal contract. Also brings an external vector DB dependency, violating ADR-0015 (one external adapter per agent) and bypassing the approval-gate design. Rejected — mechanism is a commodity, but the commodity this project needs is not what Mem0 provides.

4. **Physical delete on invalidation.** Simpler. Rejected — violates the `no-delete-episodes` principle's spirit at a layer above episodes. Soft invalidation preserves the audit trail and enables retroactive analysis.

5. **LLM-driven trust scoring (judge pattern at write time).** Considered for richer trust signal. Rejected for now — introduces a new stochastic failure mode to a security-critical path. Start rule-based; promote to LLM only after observing a concrete failure the rules miss.

6. **Per-view trust floor.** Considered (constitution view strict, exploration view lenient). Deferred — constant floor first, per-view override via frontmatter can be added without a new ADR if observation warrants.

## Consequences

- **Security**: External content is structurally quarantined at the distill summary boundary (`summarize_record` excludes raw post text from LLM prompts for `activity` episodes). For the one external path that does reach distill (`interaction` with `direction=received`, i.e., replies/mentions to the agent), `source_type=external_reply` sets base trust `0.55`, which down-weights such patterns in retrieval and excludes them below `TRUST_FLOOR`. The trust-weighting mechanism is secondary defense; structural absence is primary. (This paragraph reflects the post-ADR-0029 design; earlier revisions cited `source_type=external_post` as the primary signal, but that enum was retired with zero production producers — the actual defense was always Model B quarantine.)
- **Retrieval quality**: cosine × trust × strength multiplicative scoring means stale or low-trust patterns lose weight *and* low-similarity patterns still gate out. Expected behavior: top-K results become more recent and more trusted at constant similarity.
- **Replayability**: snapshots (ADR-0020) already capture the view lens. Adding `valid_from`/`valid_until` to patterns means any past snapshot can be fully reconstructed — including "what did pattern X say on date D" — by filtering patterns whose interval covers D.
- **Storage**: ~200 bytes/pattern added (small vs. the existing 3 KB embedding). Negligible.
- **Migration exposure**: existing 289 patterns get `trust_score = 0.6` by default, which is the "unknown" default and is intentionally not high. This means existing patterns lose a small amount of retrieval weight relative to post-migration patterns of known good provenance. Expected and desired — the migration should not retroactively mark old patterns as trusted.
- **Backward compatibility**: load path reads legacy patterns without these fields and treats them as defaults. Save path always writes them. Rollback is `cp knowledge.json.bak.pre-adr0021-* knowledge.json`.
- **New modules**: `forgetting.py` (Ebbinghaus math + floors), `feedback.py` (post-action updater stub). Both small.
- **Test surface**: ~15 new test cases across `test_knowledge_store`, `test_distill`, `test_views`, new `test_forgetting`, new `test_feedback`, new `test_migration` cases.
- **Follow-up dependencies**: ADR-0022 (Memory Evolution + Hybrid Retrieval) assumed `valid_from`/`valid_until` (later withdrawn by ADR-0034). ADR-0023 (Skill router) assumes `source_episode_ids` for attribution.

## Key Insight

ADR-0019 moved *analytical axes* from state to query — classification is a question, not a property. This ADR moves *epistemic axes* from implicit to explicit — trust, validity time, freshness, and outcome attribution were already shaping behavior (via `effective_importance` and dedup), but as hidden, non-introspectable decisions. Making them explicit fields is the same move applied to the meta-layer: if the axis matters enough to affect retrieval, it matters enough to be observable, debuggable, and per-pattern tunable.

The Boundless Care axiom maps to IV-7 (don't propagate untrusted knowledge to downstream others), Mindfulness to IV-2 and IV-3 (keep past selves and access patterns observable), and Non-Duality to IV-10 (feedback closes the loop between agent action and agent memory — self and other learn together).

# ADR-0028: Retire Pattern-Level Forgetting and Feedback — Memory Dynamics Belong to the Skill Layer

## Status

accepted

## Date

2026-04-18

## Context

ADR-0021 (2026-04-16) added four fields to each pattern in `knowledge.json` for a memory-dynamics layer modelled on per-turn retrieval agents (Mem0, Letta, Zep, A-Mem, MemoryBank, Memento-Skills):

- `last_accessed_at` / `access_count` / `strength` (lazy) — Ebbinghaus forgetting (IV-3)
- `success_count` / `failure_count` — post-action feedback counters (IV-10)

Post-landing audit ([evidence/adr-0021/implementation-audit-20260418.md](../evidence/adr-0021/implementation-audit-20260418.md)) showed these mechanisms never fired in production:

- `access_count = 0` for **377/377 patterns (100%)**
- `last_accessed_at == trust_updated_at` for **377/377 patterns** — never updated post-creation
- `success_count = 0` and `failure_count = 0` for **377/377 patterns (100%)**

Investigation revealed two overlapping reasons:

### 1. The retrieval model the design assumes does not exist in this agent

ADR-0021's forgetting/feedback loop assumes patterns are retrieved on every action turn, so access counts and outcome attribution can accumulate. In contemplative-moltbook, patterns are only touched in **batch pipelines** (`distill`, `insight`, `amend-constitution`, `distill-identity`) — not in the agent's hot path. The reply/post live loop reads from `memory.episodes` and `constitution`, not from `knowledge.json` patterns. Only two call sites of `ViewRegistry.find_by_view` exist in the entire codebase (`distill.py:226` inside `distill_identity`; `constitution.py:75` inside `amend_constitution`), both gated behind rarely-run CLI subcommands.

Since retrieval frequency is the unit of forgetting and action attribution is the unit of feedback, **this agent has neither in the pattern layer**.

### 2. The correct layer for memory dynamics is already armed by ADR-0023

ADR-0023 (Skill-as-Memory Loop) landed on 2026-04-16 alongside ADR-0021. The skill layer — where `skill_router` selects a skill per action and logs outcomes to `skill-usage-YYYY-MM-DD.jsonl` — is exactly the **per-turn retrieval loop** that ADR-0021's design assumed. Skills are the live memory unit; patterns are upstream raw material distilled from episodes.

| Concern | ADR-0021 (pattern layer) | ADR-0023 (skill layer) |
|---|---|---|
| Usage tracking | `access_count` (dead) | `skill-usage-*.jsonl` (live) |
| Outcome feedback | `success_count` / `failure_count` (dead) | `skill_router.record_outcome` (live) |
| Revision / pruning | `strength` decay (no effect) | `skill-reflect` revises skills by failure rate |

The pattern-layer and skill-layer fields duplicate the same concept. The pattern layer's implementation is dormant; the skill layer's is live. Keeping both invites drift and misleads maintainers.

### 3. ADR-0021 itself admitted this dependency but never closed the loop

ADR-0021 L90 notes: *"Populated asynchronously by a new feedback.py post-action updater... attribution requires ADR-0023 skill router log, so updater is stub-only in this ADR."* ADR-0023 shipped skill-level feedback, not pattern-level attribution. The step that would have linked outcome → skill → pattern(s) — tracking which patterns generated which skills inside `insight` — was never built. The gap between stub and live has remained.

## Decision

Retire pattern-level forgetting and feedback. Specifically:

### Fields removed from pattern schema

- `last_accessed_at`
- `access_count`
- `success_count`
- `failure_count`

`strength` (lazy, never persisted) is no longer computed.

### Modules removed

- `src/contemplative_agent/core/feedback.py` (record_outcome, record_outcome_batch, trust-delta constants)

### Functions removed from `forgetting.py`

- `time_constant`
- `compute_strength`
- `mark_accessed`
- `STRENGTH_FLOOR` constant

### `forgetting.is_live` scope narrowed

`is_live` now gates only on `valid_until is None` and `trust_score >= TRUST_FLOOR`. The strength floor is gone. The module is renamed conceptually from "Ebbinghaus forgetting" to "retrieval gate"; the file name stays for git-history continuity.

### `views._rank` scoring simplified

Retrieval score becomes `(α·cosine + β·bm25_norm) × trust_score`. The strength factor is gone. The `mark_access` parameter is removed — `_rank` is a pure read. (Note: ADR-0034 later removed the BM25 channel; the score is now `cosine × trust_score`.)

### Field initialization removed from producers

- `knowledge_store.add_learned_pattern`
- `memory_evolution.apply_revision` (later removed by ADR-0034)
- `rules_distill._build_skill_dicts` (rank adapter dicts)

### Load-path field preservation removed

`knowledge_store._parse_json` no longer preserves the retired fields on read. On next save after this ADR lands, fresh writes naturally omit them; legacy files on disk will be strip-rewritten transparently the next time distill or migration saves.

### ADR-0021 partial supersede

ADR-0021's *IV-3 (Forgetting)* and *IV-10 (Feedback)* sections are superseded by this ADR. The provenance/trust (IV-7) and bitemporal (IV-2) sections remain in effect. ADR-0021 status updated to `partially-superseded-by ADR-0028`.

## Alternatives Considered

1. **Wire pattern-layer feedback via insight attribution.** Build a `skill → [patterns]` attribution map in `insight` so that `skill_router.record_outcome` can fan-out to the contributing patterns. Rejected: doubles storage, adds attribution noise (many-to-many), duplicates the skill-layer loop without clearly-better signal. ADR-0023 already exposes outcomes at the layer where decisions are made.

2. **Make `find_by_view` fire in the hot path.** Refactor the reply/post live loop to retrieve patterns via `find_by_view` so `mark_accessed` accrues usage. Rejected: the agent's cognitive architecture does not actually want per-turn pattern retrieval — episodes + constitution already carry the right context. A retrieval refactor solves a forgetting problem the agent does not have.

3. **Keep the fields dormant and document the gap.** Leave the schema as-is with a note that the fields are currently dormant. Rejected: dormant fields rot (we discovered the gap by accident in a code-reading session); future contributors will mistake dead zeros for meaningful data.

4. **Remove only feedback; keep forgetting for future retrieval.** Partial retirement. Rejected: same logic for both — forgetting also presupposes a retrieval-heavy hot path this agent does not have. Asymmetric removal leaves an inconsistent schema.

## Consequences

- **Schema cleanup.** Pattern size drops by 4 numeric/string fields (~40 bytes each per pattern). On 377 patterns, ~15 KB reclaimed.
- **Retrieval simpler and more predictable.** Score = cosine × trust. (Originally allowed an optional BM25 blend; the BM25 channel was later removed by ADR-0034.) No hidden time-decay factor; no hidden access-count bonus. Easier to reason about and tune.
- **`is_live` fires on trust + bitemporal only.** The strength floor was never below threshold in production data (all strengths were dominated by creation-date decay at identical access_count = 0), so removing it has no observable effect.
- **Security posture unchanged.** MINJA defense was already structurally achieved via `summarize_record` quarantine + `external_reply` trust 0.55. Forgetting/feedback were never armed as secondary defense in production.
- **Backward-compatible load.** Legacy files containing the retired fields load cleanly; the fields are silently dropped, and the next save rewrites without them.
- **Test surface reduced.** `TestForgetting`, `TestFeedback`, and the `test_rank_marks_access*` cases are removed. `TestRankADR0021` shrinks from 5 to 3 cases, all of which remain meaningful (invalidated skip, low-trust skip, combined-score ordering).
- **ADR-0023 unaffected.** Skill-layer success/failure counters, `skill_router.record_outcome`, and `skill-reflect` continue as the live memory-dynamics loop.
- **`.ja.md` translation.** Added alongside per CLAUDE.md documentation policy.

## Migration

No explicit migration CLI is needed. The load-then-save path in every existing writer (`distill`, `insight`, `amend-constitution`, `migrate-patterns`, `migrate-categories`) already rewrites the full pattern list on each save. Because `_parse_json` no longer preserves the retired fields and producers no longer initialize them, the **next save** after deploying this change transparently strips them from `knowledge.json`.

Operators wishing to strip immediately can run any write-side command (e.g., `contemplative-agent distill --days 0` dry-run is not a write; `contemplative-agent migrate-patterns` is). A backup is automatically produced by `migrate-patterns`.

## Key Insight

ADR-0019 moved *analytical axes* from state to query. ADR-0021 tried to move *epistemic axes* (trust, validity, freshness, outcome) from implicit to explicit fields. Two of those four axes (trust, validity) fit the agent's actual memory layer. The other two (freshness-via-retrieval, outcome-via-attribution) assumed a retrieval model this agent does not use. ADR-0023 landed the real memory-dynamics loop at the skill layer the same week.

The lesson is not about this ADR specifically but about landing borrowed concepts: **a schema that aggregates ideas from surveyed systems can outrun the agent's actual cognitive architecture**. The fix is not to build the missing infrastructure to justify the schema, but to prune the schema to the architecture that exists.

## References

- Audit report: [evidence/adr-0021/implementation-audit-20260418.md](../evidence/adr-0021/implementation-audit-20260418.md)
- Superseded sections: ADR-0021 IV-3 (Forgetting), IV-10 (Feedback)
- Related live mechanism: ADR-0023 (Skill-as-Memory Loop)

# Phase 3 Report — ADR-0023 Skill-as-Memory Loop

Date: 2026-04-16
Status: Implementation complete, tests green. Router, frontmatter, and usage-log API available; adapter wiring into `agent.run_session` / `agent.do_solve` deferred to a follow-up (isolated behavior-risk change).

## Scope

Implemented improvement vector IV-9 (Skill-as-Memory loop): context-conditioned skill router, YAML frontmatter on skill files, JSONL usage log (selection + outcome), and the `skill-reflect` prompt template used to revise failing skills. Builds on ADR-0021's feedback stub and ADR-0022's embedding infrastructure.

## Artifacts

### New files

| File | Purpose |
|---|---|
| `src/contemplative_agent/core/skill_frontmatter.py` | Tiny stdlib-only YAML subset parser/renderer for skill-file metadata (`last_reflected_at`, `success_count`, `failure_count`, plus arbitrary string extras). Safely quotes values containing `:`, `#`, or leading/trailing whitespace; falls back to defaults on malformed frontmatter rather than raising. |
| `src/contemplative_agent/core/skill_router.py` | `SkillRouter.select(context, top_k, threshold)` — cosine top-K over `(title + body)` embeddings, `(path, mtime)` cache key, below-threshold → empty list (no-inject fallback), tie-break by `success_count − failure_count`. `record_outcome(action_id, outcome, note)`, `load_usage(window_days)`, `aggregate_usage(records)`, `needs_reflection(stats)`. |
| `config/prompts/skill_reflect.md` | LLM prompt template for revising a skill given failure contexts; emits `NO_CHANGE` marker when failures don't indicate a real problem. Preserves `# Title` line, forbids changelog / meta-commentary / user-identifying detail. |
| `docs/decision-history/0023-skill-as-memory-loop.md` | ADR-0023 rationale, decision, alternatives (treating skills as patterns / outcome-only log / classifier router all rejected). |
| `tests/test_skill_frontmatter.py` | 15 cases covering parse/render round-trip, null coercion, extras preservation, malformed-fallback, and `update_meta` helper. |
| `tests/test_skill_router.py` | 23 cases covering select (top-K, threshold, tie-break, cache invalidation, empty-context short-circuit, embed-failure resilience), record_outcome, load_usage (corrupt-line tolerance), aggregate_usage, and needs_reflection gating. |

### Modified files

| File | Change |
|---|---|
| `src/contemplative_agent/core/domain.py` | `PromptTemplates` gains `skill_reflect` field; `load_prompt_templates` loads `config/prompts/skill_reflect.md`. |
| `src/contemplative_agent/core/prompts.py` | `_ATTR_MAP` registers `SKILL_REFLECT_PROMPT`. |
| `docs/decision-history/README.md` | ADR-0023 index entry. |

## Test results

| Suite | Count | Status |
|---|---|---|
| test_skill_frontmatter.py (new) | 15 | PASS |
| test_skill_router.py (new) | 23 | PASS |
| test_domain.py | 31 | PASS |
| test_insight.py / test_rules_distill.py | 61 | PASS |
| **Total touched** | **130** | **PASS** |

Full suite not run — changes are isolated additions (new core modules + additive frontmatter/prompt field). No existing skill-writing path was touched, so insight and rules-distill outputs are unchanged; regression surface verified via those 61 tests.

## Smoke verification (no LLM call required)

- `SkillRouter.select` on a 3-skill fixture with a matched-context query returns the topically closest skill first; cosine scores above threshold (0.45) as expected.
- Below-threshold queries return `[]` and still log a `selection` record (so usage stats can see "we looked and found nothing" gaps).
- `(path, mtime)` cache correctly re-embeds after a file write (mtime bump triggers cache invalidation).
- `record_outcome` → `aggregate_usage` round-trip: selection records join to outcome records by `action_id`; `needs_reflection` fires only at ≥2 failures AND ≥30% failure rate (both gates, per ADR-0023).
- Frontmatter round-trip preserves ISO timestamps (quoting is applied for safety when value contains `:`, but parse restores the original string).

## Behavior changes now live

**Skill files**:
- New and existing skills may carry an optional YAML frontmatter block. Skills without frontmatter continue to work — parser returns `SkillMeta()` defaults and the body unchanged. No migration step required; writers (insight / rules-distill) can opt in later.

**Usage log**:
- Nothing writes to `MOLTBOOK_HOME/logs/skill-usage-YYYY-MM-DD.jsonl` yet (router is not wired into the live loop). Once wired, each `select` adds one `selection` record (with a ≤500-char `context_excerpt`, treated as untrusted per ADR-0007); outcome records carry no context, only the join key and label.

**Retrieval**:
- No live retrieval change yet. The router is constructed and tested; integration into `agent.run_session` / `agent.do_solve` is a follow-up so behavior risk lands in its own PR (Phase 2 cadence).

## Known caveats / follow-ups

- **Not yet wired**: `agent.run_session` and `agent.do_solve` still assemble the system prompt the same way. Wiring is one injection point + one outcome-recording hook; deferred to keep this ADR small.
- **Prompt discipline** (prompt-model-match memory): `skill_reflect.md` was drafted by Opus. Sample 5–10 real failure-context batches from live usage and have qwen3.5:9b rewrite the template in its own thought space before relying on reflect output.
- **Threshold tuning**: `0.45` cosine and `needs_reflection` gates (≥2 failures, ≥30% rate) are guesses. First two weeks of real selection logs will reveal whether they're tight or loose.
- **Outcome attribution**: adapters have to choose what counts as success / failure for a given action. For Moltbook: `post` posted without being flagged → success, API error or rate-limit block → failure. For `do_solve`: answer matches expected format → success. The router takes outcome labels as-is; philosophy lives in the caller.
- **Reflection CLI**: a `contemplative-agent reflect-skills` command (approval-gated, staging-dir output like `insight --stage`) is the natural consumer of `needs_reflection`; not built here — it's the ADR's "next ADR" scope.
- **no-delete-episodes compliance**: the usage log is additive-only; nothing rotates or deletes records. Aggregation windows are filter-at-read, not truncate-on-write, so ADR-0021's bitemporal discipline extends cleanly.

## Next step

Phase 4 (closing ADR / wiring): stitch `SkillRouter` into `agent.run_session` / `agent.do_solve`, add `reflect-skills` approval-gated CLI, and run a prototype-before-scale smoke with 3–5 real contexts before turning reflection loose on the full skill corpus.

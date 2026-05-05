# ADR-0023: Skill-as-Memory Loop — Router, Usage Log, Reflective Write

## Status
superseded by ADR-0036

## Date
2026-04-16

## Context

After ADR-0021 (pattern schema) and ADR-0022 (memory evolution + hybrid retrieval; later withdrawn by ADR-0034), the knowledge store is observable, bitemporal, and (was originally meant to) re-interpret itself. Skills — the third memory layer — still have none of that. Three concrete gaps remain:

1. **Skills are loaded indiscriminately.** `llm._build_system_prompt()` (llm.py:235-240) concatenates *every* `.md` under `SKILLS_DIR` into the system prompt on every generation. A skill learned from one narrow situation shapes every unrelated action. With the current ~dozen skills this is tolerable; it does not scale, and it propagates behavioral drift — an insight about submolt selection will also sit inside a solve challenge prompt.

2. **No feedback loop from outcome to skill.** Episode logs record actions, but nothing records *which skill(s) were in the prompt when the action was taken*, and nothing records whether the action worked. `feedback.py` (ADR-0021) deliberately ships as a stub because there was no attribution source. Without this loop, a skill that causes failures keeps being injected.

3. **Skills never rewrite themselves.** `skill-stocktake` merges duplicates and deletes noise, but does not revise a skill in light of *how it has been used*. Memento-Skills (arXiv:2603.18743) makes this loop the defining feature: a skill is a memory unit — retrieved, applied, and rewritten based on outcome. The retrieve→act gap is zero because the unit is the skill itself.

These three gaps form one loop. Solving them separately would re-introduce the same "where is the attribution source" coupling Phase 1 hit when stubbing `feedback.py`.

## Decision

Ship three pieces that close the loop, all infrastructural — no changes to the live agent run path in this ADR:

### 1. Skill frontmatter (optional, backward-compatible)

Skills gain a YAML frontmatter block:

```yaml
---
last_reflected_at: null       # ISO8601 or null
success_count: 0
failure_count: 0
---
# Title

<body>
```

A skill without frontmatter is read as if the defaults were present — no migration needed, legacy `insight`-emitted skills keep working. The writer (skill-reflect, and future insight) always emits frontmatter after Phase 3 writes.

Parser/renderer live in `core/skill_frontmatter.py`. Parse is permissive: unrecognised keys pass through untouched, malformed YAML falls back to "no frontmatter" rather than raising, on the principle that skills came out of an LLM and the system prompt must never hard-fail on their formatting.

### 2. SkillRouter (`core/skill_router.py`)

Given a context string (a task description, a post excerpt, a session seed), select the top-K skills by cosine similarity against their embedded (title + body).

- Embeddings are computed via the project's `embed_texts` (nomic-embed-text, 768d) and cached in-memory keyed by `(path, mtime)`. A file edit invalidates its cache entry on the next `select()`.
- `select(context, top_k=3, threshold=0.45) -> List[SkillMatch]`. Below the threshold → empty list: the caller injects *nothing extra*, which is always safer than injecting a poorly-matched skill. Tie-break on `success_count − failure_count` (frontmatter), so proven skills win ties.
- Every `select()` call writes a `selection` record to `MOLTBOOK_HOME/logs/skill-usage-YYYY-MM-DD.jsonl`. Each record carries an `action_id` (caller-supplied or auto-generated) plus a short `context_excerpt` (first 500 chars of the context string, truncated) so `skill-reflect` can sample failure contexts later. Context is treated as untrusted on read (`wrap_untrusted_content()`), same boundary model as episodes (ADR-0007).
- `record_outcome(action_id, outcome)` appends a tiny `outcome` record (`"success" | "failure" | "partial"`). Outcome records carry no context — only the action_id, outcome label, and an optional trusted `note` (supplied by the agent itself, not from external input). Joining selection → outcome by action_id reconstructs the full picture at reflect time.

The router is *not* wired into the live `agent.run_session` / `agent.do_solve` path in this ADR. It is constructed, unit-tested, and available; adapter integration is a follow-up. Rationale: the Phase 2 pattern — schema changes in Phase 1, algorithm changes in Phase 2 — keeps behavior risk concentrated in one PR at a time. Wiring into the live loop affects every post / reply / solve and is its own change set.

### 3. `contemplative-agent skill-reflect` CLI

Aggregates usage logs over a window (`--days 14`, default) and, per skill, computes success/failure counts and samples up to N recent failure contexts (by action_id join).

For each skill with `(failures ≥ MIN_FAILURES=2) AND (failure_rate ≥ 0.3)`, the LLM is called with `SKILL_REFLECT_PROMPT` to produce a revised skill body. Revised body preserves the `# Title` line. The LLM may emit the literal marker `NO_CHANGE` to signal no revision warranted.

The revised output goes through the standard approval gate (reuses `_approve_write` and `_log_approval` in cli.py:288-295 / 235-285). `--stage` writes to the staging dir for coding-agent workflows, same pattern as `insight`, `rules-distill`, `distill-identity`. Successful writes update the frontmatter: `last_reflected_at = now`, counters *preserved*, not reset — a recurring failure should still count against the skill until it's solved.

Thresholds and window live in `core/skill_router.py` as named constants; no per-view override for this ADR (can be added without a new ADR if observation warrants).

### Feedback wiring (seed, not full loop)

The usage log is the attribution source that Phase 1's `feedback.py` was waiting for. This ADR produces the log. Reading the log into `feedback.record_outcome_batch()` on retrieved patterns requires knowing which patterns the skill itself relied on — skills don't cleanly map 1:1 to patterns, so that path needs design work (probably: skills record the pattern ids they were distilled from, then outcomes on the skill back-propagate to those patterns). Deferred to a follow-up ADR.

## Alternatives Considered

1. **LLM-judge skill selection.** Could replace cosine ranking with an LLM that picks the most relevant skill. Rejected: adds a stochastic read-path call, same reasoning as ADR-0022's rejection of LLM-judge retrieval. Start with cosine; promote only if rules-based misses a concrete case.

2. **Tag / keyword-based router.** Add `tags:` frontmatter, match on token overlap. Rejected: labor burden on skill authoring (insight doesn't emit tags), and embeddings already capture topical similarity. Keywords would be a strictly weaker signal sitting on top of the same texts.

3. **Re-embed skills on every run.** Simpler cache story. Rejected: with even a dozen skills this is one Ollama call per `select()` start-up. Mtime-keyed cache is ~10 lines of code and removes the cost entirely.

4. **Reset `success_count` / `failure_count` on reflect.** Cleaner semantics per reflection epoch. Rejected: a skill that keeps failing *should* keep accruing evidence. If counts drift too high, `skill-stocktake` can introduce a drop path later. Losing signal is worse than noisy signal.

5. **Make frontmatter mandatory and migrate all existing skills.** More uniform. Rejected: adds a migration step for a purely cosmetic change. The reader-with-defaults pattern is 5 lines and removes the need to touch every skill on disk.

6. **Wire router into `_build_system_prompt()` in this ADR.** Completes the story end-to-end. Rejected for scope: `_build_system_prompt` is called from every LLM path in the adapter (comment, reply, cooperation_post, session_insight, topic_extraction, topic_novelty, post_title, submolt_selection, solve, relevance, generate_report) — wiring is not a trivial change. Does not block shipping the infrastructure; the router is importable and callable today.

7. **Skip usage log, reflect from `knowledge.json` provenance instead.** Patterns record `source_episode_ids`; one could attribute skill success/failure by replaying from episodes. Rejected: episodes are untrusted inputs (ADR-0007); joining action outcomes to specific skill injections requires tracking *which skills were in the prompt*, which episodes do not record. The log is the direct, minimal source of truth.

8. **Store usage log in knowledge.json as a field.** Co-locates with pattern state. Rejected: knowledge.json is per-distill write, usage log is per-action write — different cadences, different writers, different risk profiles. Append-only jsonl is the right shape.

## Consequences

- **Observability**: per-skill retrieval and outcome counts are queryable from the jsonl log. A future `inspect-skill` CLI or simple `jq` pipeline makes this trivial.
- **Prompt shape (when wired)**: with the router enabled, irrelevant skills no longer pollute unrelated prompts. Expected result: lower token count per generation and less cross-domain behavioral drift.
- **Storage**: frontmatter adds ~100 bytes/skill; usage log is ~150 bytes/record. For a working agent doing ~50 actions/day, ~7.5 KB/day, ~2.7 MB/year — negligible vs. episode logs.
- **Backward compat**: existing skills without frontmatter continue to load. `_build_system_prompt()` is unchanged. Zero migration.
- **Approval gate preserved**: reflections never auto-apply; `skill-reflect` emits diffs through the same gate `insight` uses (ADR-0012).
- **Trust boundary**: the log stores only action_id (hash) and labels, no raw input. The skill body, written by the LLM, stays in the existing `validate_identity_content` pipeline.
- **Follow-up work enabled**: router → `_build_system_prompt()` wiring; pattern-level attribution from skill outcomes (ties into `feedback.py`); drop path in `skill-stocktake` for skills that stay high-failure across reflections.
- **Tests**: new `tests/test_skill_frontmatter.py`, new `tests/test_skill_router.py`, new `tests/test_skill_reflect.py`. No changes to existing tests.
- **Prompt discipline**: `config/prompts/skill_reflect.md` is drafted by Opus; `prompt-model-match` says qwen3.5:9b should revise it against a sample of real usage aggregates before production use.

## Key Insight

ADR-0019 made classification a query. ADR-0021 made epistemic axes explicit fields. ADR-0022 made patterns rewrite each other. ADR-0023 makes skills *observable* and *outcome-aware*, which is the precondition for them to rewrite themselves.

Memento-Skills' single-sentence framing — *a skill is a memory unit* — only pays off once the system can answer three questions per skill: "when do I retrieve it?", "what happens when I do?", "should it still say what it says?". This ADR supplies the first two (router + log) and a narrow version of the third (reflect-on-failure). The broader version — skills whose interpretation drifts as the world drifts, the way ADR-0022 does for patterns — is the natural next step once the log has produced real data.

Boundless Care maps here directly: a skill that quietly causes failures is a form of structural harm; making its failure count a retrievable field is how the system can care about the harm without requiring vigilance from the live loop.

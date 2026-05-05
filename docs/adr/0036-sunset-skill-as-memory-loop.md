# ADR-0036: Sunset Skill-as-Memory Loop — Retire Router, Usage Log, and Reflect

## Status
accepted — supersedes ADR-0023

## Date
2026-05-05

## Context

ADR-0023 (2026-04-16) shipped three pieces meant to close a "skill = memory unit" loop after Memento-Skills (arXiv:2603.18743):

1. **`SkillRouter`** — embedding-based context → top-K skill retrieval with a usage log
2. **Skill-usage log** — `selection` + `outcome` records joined by `action_id`, written to `MOLTBOOK_HOME/logs/skill-usage-YYYY-MM-DD.jsonl`
3. **`skill-reflect` CLI** — aggregate the log over a window, revise skills whose recent failure rate exceeds a threshold

Three weeks of running the agent under this scaffold makes the verdict clean: the loop never closed, and the shape was wrong even if it had.

### Implementation observations (proximate)

- **Router matches are discarded.** Both call sites (`post_pipeline.py:86` and `reply_handler.py:230`) call `router.select(context, top_k=3, action_id=...)` and ignore the return value. The matches never reach `_build_system_prompt()` (`core/llm.py:295`), which continues to load *every* skill via `_load_md_files(_skills_dir)` regardless of context. ADR-0023 line 95 explicitly listed `router → _build_system_prompt() wiring` as follow-up — three weeks later it had not landed.
- **`failure` only captures API errors.** Reading the actual log (20 days, 526 records) shows `outcome` distribution `success: 190 / partial: 59 / failure: 14`. The 14 failures are network exceptions (`ConnectionResetError`, HTTP 500s, read timeouts). Real "the agent produced bad output" cases are caught by the deterministic gates (`gated:duplicate`, `gated:test_content`, etc.) and recorded as `partial`. `needs_reflection` only checks `failure_rate`, so 30 days of running yields `eligible=0`.
- **`top_k=3` makes attribution impossible.** Each `select()` writes one record charging *three* skills against the same `action_id`. Even if `partial` were re-labelled as `failure`, the per-skill signal cannot be separated from co-occurring skills selected for the same context.
- **Frontmatter counters are dead path.** `success_count` / `failure_count` exist only as a tie-breaker in `skill_router.py:252` — i.e. inside the same matches that the call sites discard. No external reader, no externally observable effect.
- **Not a MINJA contribution.** ADR-0023 invokes `wrap_untrusted_content` / `validate_identity_content` / `append_jsonl_restricted`, but those primitives belong to ADR-0007 (security boundary model) and `_io.py` (used by audit log, episodes, etc.). MINJA defense is ADR-0021 (trust scores, `source_type=external_reply` down-weighting, `TRUST_FLOOR`). ADR-0023 carries no security work that survives its sunset.

A month of observation is the right length for this kind of scaffolding decision: it lets the loop accumulate enough data that "no eligible skills, ever" is a finding rather than a small-sample artifact.

### Architectural framing (ultimate) — wiring would not have helped

Even if the missing wire had landed and reflect had received a proper `failure` signal, the shape is wrong:

- **Context-aware filtering belongs to views, not routing.** ADR-0019 established that classification is a query (decision is computed at retrieval time over deterministic predicates), and the project's `mechanism-vs-value-split` principle says: similarity / dedup / clustering belongs to mechanism (embedding), but importance / applicability / value judgment belongs to LLM or to a deterministic query over typed metadata. "Which skill applies to this context?" is the second kind of question. Cosine over skill body text is asking similarity to answer applicability — a mismatched mechanism. The right shape, if context-aware skill filtering ever becomes load-bearing, is a view over skill metadata (deterministic, observable, debuggable), not a top-K retrieval pass.
- **Skills are designed to be all-injected with LLM-evaluated triggers.** Each skill body carries its own trigger conditions, and the LLM is what reads the body and decides "does this apply right now?" Inserting a router (cosine) in front duplicates the trigger-evaluation responsibility across two layers — the router pre-filters by similarity, then the LLM still has to decide applicability. This breaks `single-responsibility-per-artifact`: the skill text owns its trigger and the LLM owns the application; nothing else should make the call.

Together the two framings say: this was the wrong place to do filtering, with the wrong mechanism. Repair would mean replacing rather than wiring.

## Decision

Sunset ADR-0023 in full. Concretely:

### Delete

- `src/contemplative_agent/core/skill_router.py` (entire module)
- `src/contemplative_agent/core/skill_reflect.py` (entire module)
- `src/contemplative_agent/core/skill_frontmatter.py` (entire module — created in commit `db5a93c` for ADR-0023, no other consumers)
- `tests/test_skill_router.py`, `tests/test_skill_reflect.py`, `tests/test_skill_frontmatter.py`, `tests/test_session_context.py`
- `config/prompts/skill_reflect.md`
- `docs/evidence/adr-0023/`
- `skill-reflect` CLI (`_handle_skill_reflect`, parser, dispatch entry)
- `prune-skill-usage` CLI (`_handle_prune_skill_usage`, parser, dispatch entry) — generation stops, leaving the cleanup helper as half-finished implementation
- `MIN_FAILURES_FOR_REFLECT`, `FAILURE_RATE_FOR_REFLECT`, `SKILL_ROUTER_DEFAULT` in `core/thresholds.py`
- `SKILL_REFLECT_PROMPT` entry in `core/prompts.py` and the `skill_reflect` field in `DomainConfig`

### Modify

- `adapters/moltbook/post_pipeline.py` and `reply_handler.py`: drop `router.select()` and all `record_outcome()` calls. The deterministic gates (`is_duplicate_title`, body-hash dedup, test-content gate, confirm gate, rate-limit gate) keep their `return` paths intact — they were always doing the load-bearing work.
- `adapters/moltbook/agent.py`: drop `SkillRouter` instantiation
- `adapters/moltbook/session_context.py`: drop `skill_router` field; `SessionContext` now holds memory + per-session bookkeeping only
- `core/insight.py`: simplify the skill-emit step — the LLM body is appended to `SkillResult.text` directly, no frontmatter round-trip

### Preserve

- Existing `~/.config/moltbook/logs/skill-usage-*.jsonl` files stay on disk (20 files, 213 KB). They are observation evidence for this ADR plus design input if a future view-based skill filter is built. Manual cleanup if desired: `rm ~/.config/moltbook/logs/skill-usage-*.jsonl`. No new logs are generated after this PR.
- Existing skill `.md` files in `~/.config/moltbook/skills/` keep their `last_reflected_at` / `success_count` / `failure_count` frontmatter fields. These become unread by the new code path; they are harmless residue, not a migration target.
- General security infrastructure (`wrap_untrusted_content`, `validate_identity_content`, `append_jsonl_restricted`) survives untouched — those belong to ADR-0007 / ADR-0012 / `_io.py`.

## Alternatives Considered

- **Partial sunset (keep router, retire reflect).** Rejected. The router's `select()` matches are discarded today and an end-to-end wire would still face the architectural mismatch above. Keeping the retrieval mechanism without a load-bearing consumer would cement the same scaffolding pattern ADR-0030 had to retract for ADR-0024/0025.
- **Wire the router into `_build_system_prompt()` and keep going.** Rejected on the architectural framing — `mechanism-vs-value-split` says cosine over skill bodies is the wrong tool for "does this apply?". If skill count later outgrows the model context budget, the right next move is a view over skill metadata (deterministic), not a router.
- **Re-label `gated:*` partials as `failure` so reflect fires.** Rejected. Top-K=3 dilution still leaves attribution unsolvable, and gates fire on output similarity, not skill causation; the reflect prompt would receive co-occurrence noise rather than per-skill signal.

## Consequences

- **Surface deletion is large but mechanical.** Roughly 8 files deleted, 15 files edited, 2 ADR files added. Pattern matches ADR-0035's migration-surface sunset in scope.
- **Zero load-bearing surface lost.** `_build_system_prompt()` was always the actual skill-injection path; `select()` matches were never read. The runtime behavior of the agent is unchanged after this PR — the only observable change is that no new `skill-usage-*.jsonl` files are written.
- **Door is left open for views over skills.** If skill count grows beyond what fits in the context budget, ADR-0019's view pattern is the natural extension. That would be a separate ADR with a different shape — typed query predicates over skill frontmatter, not embedding retrieval.

## Notes

This sunset follows the same pattern as ADR-0030 retracting ADR-0024/0025: ship a scaffold, observe for ~1 month, retract when the load-bearing part fails to land. The discipline that matters is the observation period — without it, "this didn't get used yet" is indistinguishable from "this is being adopted slowly."

The 20-day skill-usage corpus (213 unique contexts × 13 skills × 263 actions, 231 KB) stays on disk as evidence and possible future-view design input. It is not deleted with the code.

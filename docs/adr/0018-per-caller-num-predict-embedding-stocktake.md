# ADR-0018: Per-Caller num_predict + Embedding-Only Stocktake

## Status

accepted (amended 2026-05-04 — see Amendment section below)

## Date

2026-04-15

## Context

Two failure modes surfaced on 2026-04-15:

1. `skill-stocktake` hung mid-run on M1 (16 GiB, `free_swap="0 B"`). Individual `/api/generate` calls took 9+ minutes; one agent generate call hung 3.5 hours.
2. The daily `distill` launchd job at 03:00 died before writing a single byte to `distill-launchd.log`.

Investigation traced both to the same root cause: `core/llm.py:generate()` hardcoded `num_predict=8192` for every caller. `max_length` (already a parameter) was used only for post-generation character truncation — it did not propagate to Ollama. On M1 + qwen3.5:9b Q4_K_M at ~10 tok/s, a call whose prompt is a 1KB pair-judge query could still generate up to 14 minutes of tokens before hitting a stop condition. Sequential pair-judge loops (20+ calls per stocktake) compounded this into wall times that routinely exceeded the 600s client read timeout.

Secondary factor: `stocktake.py` ran a hybrid pipeline — embedding cosine triage → LLM pair judge on the uncertain band → union-find clustering. The pair judge existed to disambiguate borderline pairs (0.75-0.92 similarity), but:

- `num_ctx=32768` was allocated regardless of prompt size, so "keep prompts short" bought nothing in KV cache terms (2.2 GiB pre-allocated either way).
- The merge step (`merge_group()`) already receives the full bodies of all cluster members; a separate judgment stage operating on 500-char excerpts was strictly less informed.
- Sequential execution meant a single timed-out pair blocked progress on the rest.

Historical note: prior to this work, `num_ctx` was left at Ollama's VRAM-based default (4096) in committed code. The uncommitted working tree included a change to `num_ctx=32768` that had never been exercised in production. With 13K-token system prompts (identity + constitution + 32K chars of learned skills + rules), the old default meant distill batches were being silently prefix-truncated — a confound that was hiding the true generation cost.

## Decision

Introduce two coupled changes and treat them as one ADR because neither succeeds alone.

### 1. `generate()` accepts an explicit `num_predict` argument

```python
def generate(
    prompt: str,
    system: Optional[str] = None,
    max_length: int = MAX_POST_LENGTH,
    num_predict: Optional[int] = None,
    format: Optional[Dict] = None,
) -> Optional[str]:
```

When `None`, falls back to 8192 (backward compat). `num_ctx` stays at 32768 globally — the system prompt alone forces this, and shrinking it would reintroduce the prefix-truncation confound.

18 call sites across `adapters/moltbook/llm_functions.py`, `adapters/meditation/report.py`, `core/distill.py`, `core/rules_distill.py`, `core/constitution.py`, `core/insight.py`, and `core/stocktake.py` now pass calibrated values ranging from 20 (classify) to 1500 (distill extract, rules extract, identity refine, merge_group). See `core-modules.md` and the plan file for the full table.

### 2. stocktake becomes embedding-only

Deleted: `_triage_pairs`, `_parse_pair_decision`, `_judge_one_pair`, `_llm_pair_judge`, `STOCKTAKE_PAIR_JUDGE_PROMPT` (prompt file left on disk for future removal).

New: single `SIM_CLUSTER_THRESHOLD=0.80`; pairs at or above threshold feed directly into union-find. The calibration band the pair-judge used to arbitrate (0.75-0.92 = "uncertain") is absorbed into the threshold with tolerance for false positives at the low end.

Reject path: the merge prompts (`stocktake_merge.md`, `stocktake_merge_rules.md`) now instruct the LLM to emit `CANNOT_MERGE: <reason>` when candidates are not actually redundant. `stocktake.is_merge_rejected()` detects this with `^\s*CANNOT_MERGE\s*:` (case-insensitive) to tolerate drift. `cli.py` skips rejected groups in both direct-merge and `--stage` flows.

## Alternatives Considered

- **Tune `num_predict` in pair judge only, keep the pipeline.** Rejected because the pair judge was structurally redundant with the merge step. Fixing its runtime cost would not fix the architectural duplication. The merge LLM sees both full bodies and is already making a creative decision; adding "refuse if distinct" to it absorbs pair-judge's entire contract.

- **Shrink `num_ctx` globally to 4096 instead of tuning `num_predict`.** Rejected because the committed baseline was already at 4096 (Ollama default) and was silently truncating 13K-token system prompts — learned skills and rules never reached the model at all. Keeping 32768 is load-bearing for correct behavior; the KV cache cost (2.2 GiB) is tolerable, the per-call generation cost was not.

- **Keep `num_predict=8192` as default, migrate callers opportunistically.** Partially adopted — the signature still defaults to 8192 for safety at any unaudited call site. But 18 sites were migrated in one pass because leaving a subset un-tuned would let the crash symptom reappear on any caller that hits a long-stop-token path.

- **Pure embedding clustering without a reject path.** Rejected because embedding cosine is surface-level; at 0.80-0.86 the pairs can be same-attractor-different-vocabulary *or* related-but-distinct behaviors. A safety net is required, and co-locating it with the merge step (which already loads full bodies) is cheaper than adding a separate judgment stage.

- **JSON-structured merge output with a `"merge": false` field.** Rejected in favor of the `CANNOT_MERGE:` sentinel because merge output is Markdown (not JSON), and switching the output format to carry an optional structural flag would complicate both the prompt and the parser. A leading sentinel string is both unambiguous and orthogonal to Markdown.

- **Lower `BATCH_SIZE` in distill (30 → 10) instead of raising `num_predict`.** Considered for distill specifically, rejected for this ADR. The immediate symptom was `num_predict`, not batch size. Batch tuning is left as a follow-up if distill extract turns out to truncate at `num_predict=1500` (see open risk below).

## Consequences

- `skill-stocktake` on 8 auto-extracted skills completes in 3m42s (previously crashed or timed out). Verified on 2026-04-15 with `SIM_CLUSTER_THRESHOLD=0.80` correctly collapsing 8 skills (28 pairs, max cosine 0.94) into a single merge group, which `merge_group()` then unified without triggering `CANNOT_MERGE`.
- After adopt-staged consolidated the 8 skills into 1, the system prompt shrinks from ~32K chars → ~5K chars. Every subsequent `generate()` call in the agent path pays that much less prefill. This compounds with the `num_predict` fix.
- Memory footprint improves indirectly: the embed→generate→embed→generate ping-pong the pair judge used to induce is gone. Only one model is resident at a time during stocktake, which matters on M1 16 GiB where qwen alone is 9.1 GiB resident.
- Removes ~130 lines from `stocktake.py`. Aligns with `feedback_simplicity`.
- Test suite grew from 869 → 942 tests (pair-judge tests deleted, embedding-clustering + `is_merge_rejected` tests added).

### Open risks

- **distill extract `num_predict=1500` may be tight.** `BATCH_SIZE=30` episodes can yield 5-15 patterns × 100-200 tokens = 500-3000 tokens of output. The upper range exceeds 1500. Logged as a memory and to be verified in the next daily distill run; if truncation is observed, raise to 3000.
- **`CANNOT_MERGE:` is a new string contract between prompt and code.** The regex tolerates whitespace and case drift, but a model that decides to output "not redundant" prose instead of the sentinel will merge anyway. Merge prompts explicitly anchor the sentinel; monitor production outputs for drift.

## Relation to Prior ADRs

- ADR-0016 (Insight narrow, Stocktake broad): this ADR upholds that contract — stocktake remains the broad consolidator, but its machinery is simplified. The narrow/broad role split is unchanged.
- ADR-0012 (Human approval gate): the `CANNOT_MERGE` path adds a fourth outcome to the approval state machine (merged / skipped / LLM failure / rejected-as-distinct). All four route through the same write_restricted + audit log.

## Amendment (2026-05-04)

### Context

API publish callers (self-post / comment / reply / post-title) showed a 67% mid-sentence truncation rate on 2026-05-04 (33 comments, 22 truncated; 5 replies, 3 truncated, including a mid-word break "richer artic"). Verbatim duplicate publications also occurred: Apr 30 self-post #2 was re-published verbatim as May 3 self-post #2, identical including the truncation point.

Root cause analysis showed two issues:

1. The original ADR's per-caller `num_predict` calibration (300 / 600 / 50) targeted M1 hang avoidance, not output-length sufficiency. Token caps were tight relative to char caps, so generation halted mid-sentence well before `max_length` slice would trigger.
2. Three independent length caps had accumulated for API publish callers, violating ADR-0030 "1 artifact 1 責務":
   - `num_predict` (token, Ollama side)
   - `max_length` → `_sanitize_output()` slice (char, Python side)
   - `agent.py:_passes_content_filter()` redundant length re-check
   - `generate_post_title()` post-generate `[:80]` slice (3rd cap)

### Decision

Introduce `core/llm.py::generate_for_api(prompt, max_length)` for API publish callers. `num_predict` is derived inside the wrapper as `max(50, ceil(max_length/3) + 50)` (1 token ≈ 3 chars conservative, +50 token margin, 50 floor for very short caps). Callers specify only `max_length` — one parameter instead of two, eliminating the unbalanced-cap class of bug.

Updated config constants reflect verified Moltbook API limits (skill.md, 2026-05-04):

- `MAX_POST_LENGTH`: 20000 → **40000** (the previous value was half the actual API limit)
- `MAX_POST_TITLE_LENGTH`: new constant **300** (replaces `max_length=100` ad-hoc)
- `MAX_COMMENT_LENGTH`: 10000 retained (API does not specify; conservative cap)

Removed redundant layers:

- `agent.py:_passes_content_filter()` length check — `_sanitize_output()` slice already enforces it
- `generate_post_title()` post-generate `[:80]` slice — was an unrelated 3rd cap with no API or design basis

### Scope of Amendment

**API publish callers** (self-post / comment / reply / post-title): per-caller `num_predict` argument removed; migrated to `generate_for_api(prompt, max_length=...)`.

**Internal callers** (distill / insight / topic / submolt / relevance / topic_novelty / topic_summary / session_insight / etc): unchanged. ADR-0018 per-caller calibration still applies. M1 hang avoidance remains the constraint for these paths; consolidation is out of scope for this amendment.

### Related Change

A body-hash dedup gate is added in `post_pipeline.py` to catch verbatim re-publication that title/topic Jaccard misses. This is independent of the truncation fix (a duplicate body with a slightly different title currently slips through the Jaccard gate). The gate reuses the existing `content_hash` (16-char SHA-256 prefix) on `PostRecord` — no schema change.

### Verification

- 7 new tests in `test_llm.py` and `test_agent.py` validate: derivation formula, each caller using `generate_for_api`, `[:80]` slice removal, redundant length check removal, body-hash gate firing.
- Existing `test_too_long` and `test_at_max_length` removed (length check no longer in `_passes_content_filter`).

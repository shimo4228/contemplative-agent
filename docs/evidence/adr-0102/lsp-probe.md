# LSP probe — Claude Code LSP tool over this repo (pyright), 2026-09-05

Evidence for ADR-0102 Decision 2: file-level structure is answerable per query
from code, so nothing needs to be stored. Both calls were made from a Claude
Code session with the built-in `LSP` tool; the language server is the pyright
already listed in `pyproject.toml`'s dev group. No extra installation.

## workspaceSymbol

Query `distill` (any file in the workspace as anchor):

```
Found 5 symbols in workspace:

src/contemplative_agent/core/distill.py:
  distill (Function) - Line 104
  distill_identity (Function) - Line 230
  _DistillOutcome (Class) - Line 334
  _distill_one (Function) - Line 512
  _distill_episodes (Function) - Line 789
```

## incomingCalls

Anchor `src/contemplative_agent/core/distill.py:104:5` (the `distill` function):

```
Found 17 incoming calls:

src/contemplative_agent/cli/memory_cmds.py:
  _handle_distill (Function) - Line 39 [calls at: 64:18]

tests/benchmark_distill.py:
  run_benchmark (Function) - Line 166 [calls at: 203:9]

tests/test_distill.py:
  test_basic_distillation (Function) - Line 71 [calls at: 125:18]
  test_structured_output_format_is_used (Function) - Line 143 [calls at: 159:9]
  test_dry_run_does_not_write (Function) - Line 166 [calls at: 177:18]
  test_dry_run_logs_instrument_lines (Function) - Line 182 [calls at: 204:13]
  test_dry_run_logs_view_supply_with_registry (Function) - Line 210 [calls at: 239:13]
  test_dry_run_instruments_cover_only_would_be_added (Function) - Line 252 [calls at: 281:13]
  test_empty_episodes (Function) - Line 286 [calls at: 289:18]
  test_no_engagement_episodes (Function) - Line 292 [calls at: 306:18]
  test_llm_failure (Function) - Line 311 [calls at: 314:18]
  test_partial_failure_summary_warning (Function) - Line 320 [calls at: 368:13]
  test_no_summary_warning_when_all_succeed (Function) - Line 375 [calls at: 395:13]
  test_bullet_list_recovered_when_output_is_not_json (Function) - Line 407 [calls at: 421:18]
  test_insight_records_excluded_from_prompts (Function) - Line 506 [calls at: 528:13]
  test_all_insight_log_yields_no_episodes (Function) - Line 533 [calls at: 543:18]
  test_no_noise_log_written (Function) - Line 1298 [calls at: 1308:9]
```

## Reading

The codemap's `core-modules.md` row for `distill.py` and the "who calls
distill" prose in `architecture.md` were a snapshot of exactly this answer,
refreshed by hand in 159 commits since 2026-06-01. The query above is free,
always current, and line-accurate. Import-level structure is likewise
available from `grimp` / import-linter (already enforcing the layer contract).

## Counts behind the ADR

| measure | value | command |
|---|---|---|
| codemap files / bytes | 6 / 205,239 | `wc -c docs/CODEMAPS/*.md` (at `ced10e2`) |
| architecture.md bytes | 118,891 (~30k tokens) | same |
| src commits since 2026-06-01 | 197 | `git log --since=2026-06-01 --format=%h -- src \| wc -l` |
| CODEMAPS commits since 2026-06-01 | 159 | `git log --since=2026-06-01 --format=%h -- docs/CODEMAPS \| wc -l` |
| src files citing an ADR number | 70 (69 distinct ADRs) | `grep -rl 'ADR-0' src/contemplative_agent \| wc -l` |
| codemap path references not on disk | 2 of 68, both documented tombstones | see session log |

# Pre-deletion audit — incident rationale in architecture.md, 2026-09-05

Question (ADR-0102 Decision 3): which "why this guard exists" prose in the
codemap's Data Flow / Untrusted Boundary sections exists **nowhere else** and
must move before deletion? Method: every dated bracket, `T-…` id and rationale
sentence in `docs/CODEMAPS/architecture.md` lines 133–236 and 237–1297 (at
commit `ced10e2`; wiki subsections 682–983 skipped — RFC-0025 retired the
mechanism; pure code-order / reason-code / LOC restatements skipped) was
grepped against `docs/adr/`, `src/`, `scripts/`, `tests/`.

Result: **25 items, 23 COVERED, 1 gap, 1 minor gap.** The codemap was a mirror.

| item | codemap line | disposition |
|---|---|---|
| Nonce delimiter, `_frame_is_sound`, `{body}` regression (T-UNTRUSTED-ESCAPE) | 154–173 | COVERED ADR-0007 Amendment 2026-08-16; `core/llm/guard.py` |
| Fixed-point token strip ("bound is not a policy knob", filter after every transform) | 175–195 | COVERED ADR-0007; `guard.py`; `core/episode_render.py` |
| T-OBS-INJ `guard_alive` heartbeat in the shared tier | 197–217 | COVERED `guard.py`; `cli/runtime.py`; ADR-0007 |
| Audit sink never raises | 219–223 | COVERED `guard.py`; ADR-0007 |
| weekly-analysis nonce frame on prior reports | 228–233 | COVERED `scripts/weekly-analysis.sh` |
| T-REPLY-PACING (6,621 candidates/h, break not backoff) | 249–261 | COVERED `adapters/moltbook/reply_handler.py`; `tests/test_reply_chaos.py`; ADR-0081. Dangling pointer to architecture.md in `reply_handler.py` repointed |
| T-FEED-PACING (breaker read twice, 0.0 sentinel, `should_continue`) | 269–291 | COVERED `feed_manager.py`; `post_pipeline.py`; `feed_seeder.py`; `core/llm/backend.py` |
| `non_dict_verification` reject | 297–302 | COVERED `adapters/moltbook/agent.py` |
| distill `nothing_durable`, postgate fails open, prompt unchanged | 436–490 | COVERED `core/distill.py`; ADR-0084 |
| `safe_peer_name` header token | 430–435 | COVERED `core/episode_render.py` |
| self_reflection seed = READ side of ADR-0072 pair | 533–535 | COVERED `core/views.py`; ADR-0019 |
| insight axioms-only system, surprise mask, no z-normalization | 592–627 | COVERED `core/insight.py`; `core/insight_surprise.py`; ADR-0074 / 0096 |
| `.archive/` inert, archive set from argv only | 665–676 | COVERED `cli/skill_archive.py`; `cli/adopt.py`; ADR-0097 |
| T-GUARD pending guard in handler | 1038–1053 | COVERED `cli/staging.py`; `tests/test_staging_pending_guard.py` |
| `report_missing_parts` structural | 1087 | COVERED `scripts/weekly-pipeline.sh` |
| LEDGER_DELTA_INVALID ordering | 1087, 1136–1141 | COVERED `scripts/weekly-pipeline.sh` |
| Baselines aside, sweep signature keying | 1089–1103 | COVERED `scripts/log_anomaly_sweep.py`; `weekly-analysis.sh` |
| Approval join causes | 1091–1093 | COVERED `scripts/value_layer_approval_join.py` |
| Rejected-name tally withheld | 1105 | COVERED `core/selection_metrics.py` |
| Ledger renderer double boundary | 1105 | COVERED `scripts/observation_ledger.py` |
| Session permission scope | 1160 | COVERED `weekly-pipeline.sh`; two scope-shell tests |
| **Report-artifact discontinuity 2026-08-16** (settings layer → model/style change) | 1194 | **GAP → moved** to ADR-0099 Consequences (dated note); `weekly-analysis.sh` header repointed |
| Watchdog `MIN_FINDINGS_BYTES=512` sizing | 1200 | **minor GAP → moved** to a comment beside the constant in `scripts/pipeline_watchdog.sh` |
| IPD bench not wired, ±0.13 floor, 75-min window | 995–1020 | COVERED ADR-0090; `scripts/ipd-two-arm.sh` |
| Submolt scan keeps empty/403 rows | 1230–1235 | COVERED `adapters/moltbook/submolt_scope.py` |

Discarded as trivia (numbers with no decision attached): "two consecutive
weeks lost" + commit `7c96e0f` in the sweep paragraph; "19 of 20" in the
submolt smoke run; "nothing marks a below-threshold post as seen" sentence in
T-FEED-PACING (the guard and its test carry the behaviour).

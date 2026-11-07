# Phase 1 Report — ADR-0021 Pattern Schema Extension

Date: 2026-04-16
Status: Implementation complete, tests green. Awaiting user-triggered migration on production knowledge.json.

## Scope

Implemented improvement vectors IV-7 (provenance + trust scoring), IV-2 (bitemporal invalidation), IV-3 (Ebbinghaus forgetting), IV-10 (feedback counters) as a single coupled pattern schema extension.

## Artifacts

### New files

| File | Purpose |
|---|---|
| `src/contemplative_agent/core/forgetting.py` | Ebbinghaus strength computation, TRUST_FLOOR / STRENGTH_FLOOR, `is_live()`, `mark_accessed()` |
| `src/contemplative_agent/core/feedback.py` | Post-action outcome recorder, asymmetric trust nudges |
| `docs/decision-history/0021-pattern-schema-trust-temporal-forgetting-feedback.md` | ADR-0021 rationale, decision, alternatives |
| `tests/test_knowledge_store.py` | 23 ADR-0021 tests (schema, forgetting, feedback, migration) |

### Modified files

| File | Change |
|---|---|
| `src/contemplative_agent/core/knowledge_store.py` | Added SOURCE_TYPES, TRUST_BASE_BY_SOURCE, DEFAULT_TRUST. Extended `add_learned_pattern` with provenance/trust/valid_from/valid_until. Extended `_parse_json` round-trip. `effective_importance` now multiplies by trust × strength. `get_context_string` calls `mark_accessed` + `is_live` gate. |
| `src/contemplative_agent/core/distill.py` | Added `_episode_source_kind`, `_derive_source_type`, `_trust_for_source` helpers. `_dedup_patterns` UPDATE path now soft-invalidates (valid_until=now) and ADDs a boosted new row. `_distill_category` threads provenance per pattern into `add_learned_pattern`. `return_indices` opt-in for caller projection. |
| `src/contemplative_agent/core/views.py` | `_rank` applies cosine × trust_score × strength, filters via `is_live`, calls `mark_accessed` on results (opt-out via `mark_access=False`). |
| `src/contemplative_agent/core/migration.py` | Added `Adr0021MigrationStats`, `_ensure_adr0021_defaults`, `migrate_patterns_to_adr0021` (idempotent, auto-backup, dry-run aware). |
| `src/contemplative_agent/cli.py` | Added `migrate-patterns` subcommand + `_handle_migrate_patterns`. Registered in Tier 1 (no-LLM) handlers. |
| `docs/decision-history/README.md` | ADR-0021 index entry. |
| `tests/test_distill.py` | Updated `test_similar_triggers_update` for bitemporal semantics; added `TestDeriveSourceTypeADR0021`, `TestDedupSoftInvalidationADR0021`. |
| `tests/test_views.py` | Added `TestRankADR0021` (5 cases). |
| `tests/test_memory.py` | Updated `test_last_accessed_updated_on_get_context` to check `last_accessed_at` + `access_count`. |

## Test results

| Suite | Count | Status |
|---|---|---|
| test_knowledge_store.py (new) | 23 | PASS |
| test_distill.py (incl. new) | 43 | PASS |
| test_views.py (incl. new) | 34 | PASS |
| test_memory.py | 90+ | PASS (after migration fix) |
| test_migration.py | 13 | PASS |
| test_insight, test_rules_distill, test_snapshot, test_cli, test_episode_embeddings | 179 | PASS |
| test_agent, test_scheduler, test_verification, test_content, test_stocktake, test_metrics | 262 | PASS |
| test_llm, test_constitution, test_domain, test_report, test_auth, test_client, test_embeddings, test_meditation_* | 298 | PASS |
| **Total touched** | **~940** | **PASS** |

## Smoke test (real data, dry-run)

```
$ contemplative-agent migrate-patterns --dry-run
=== migrate-patterns summary (ADR-0021) ===
  backup          : (skipped — dry-run)
  patterns total  : 585
  patterns updated: 585
  already migrated: 0
  (dry-run — no file writes performed)
```

All 585 live patterns in `~/.config/moltbook/knowledge.json` would receive defaults as expected. No migration has been committed yet — user must run `contemplative-agent migrate-patterns` without `--dry-run` to commit.

## Behavior changes visible post-migration

- Every pattern gains `provenance.source_type="unknown"`, `trust_score=0.6`, `valid_until=None`, `last_accessed_at=<distilled-or-now>`, `access_count=0`, `success_count=0`, `failure_count=0`.
- Retrieval score is now `cosine × 0.6 × strength` for migrated patterns. Pre-migration baseline was cosine only. Expected consequence: ranking order within a view is preserved (all factors constant) but raw scores drop by ~40%. Thresholds remain semantic (pre-multiplication).
- New patterns added by `distill` after migration get `source_type` derived from their episode types and base trust accordingly (0.9 self, 0.55 external_reply, 0.5 external_post, 0.5 mixed).
- SIM_UPDATE (0.80 ≤ sim < 0.92) during dedup now soft-invalidates the old row (`valid_until=now`) and adds a new boosted row, instead of mutating importance in place. Old rows are retained for audit / replay.

## Known caveats / follow-ups for later phases

- **feedback.py is stub-level for attribution**. The write API (`record_outcome`) is in place but the read-path that identifies *which* patterns contributed to an action depends on the ADR-0023 skill router log — wired there, not here.
- **flag-pattern CLI** (user-driven trust penalty) — deferred, low priority.
- **Per-view trust floor** — deferred, constant TRUST_FLOOR=0.3 for now.
- **source_episode_ids backfill** for existing 585 patterns — not attempted; stays empty on migrated rows. New patterns record up to 5 representative timestamps.

## Next step

Phase 2 (ADR-0022): Memory Evolution (A-Mem style bidirectional update) + Hybrid Retrieval (BM25 augmentation).

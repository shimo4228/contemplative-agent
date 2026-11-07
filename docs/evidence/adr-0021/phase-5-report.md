# Phase 5 Report — ADR-0025 Identity History Log Wiring + migrate-identity CLI

Date: 2026-04-16
Status: All three deferred ADR-0024 follow-ups that were in scope (identity history live write path, adopt-staged history hook, migrate-identity CLI) are wired, tested, and live. The two larger follow-ups (per-block distill routing, runtime agent-edit tool) remain explicitly deferred to separate ADRs.

## Scope

Wired the history helper and migration function that ADR-0024 landed as "schema ready, CLI deferred" into their real entry points:

- Every approved `distill-identity` write now appends one per-block entry to `identity_history.jsonl`.
- Every adoption of a staged `distill-identity` artifact (both interactive and `--yes`) does the same.
- Stage-only and rejected paths **never** append — history is scoped to ground truth on disk.
- Users can upgrade a legacy `identity.md` with a single `contemplative-agent migrate-identity` command; `--dry-run` previews without touching the file.

## Artifacts

### New files

| File | Purpose |
|---|---|
| `docs/decision-history/0025-identity-history-and-migrate-cli.md` | ADR-0025 rationale. Alternatives rejected: proposal-time logging / `DistillMetadata` sidecar / CLI-side re-hashing / `--migrate` flag on `distill-identity` / auto-migrate-on-first-distill. |

### Modified files

| File | Change |
|---|---|
| `src/contemplative_agent/adapters/moltbook/config.py` | `IDENTITY_HISTORY_PATH = MOLTBOOK_DATA_DIR / "logs" / "identity_history.jsonl"`. |
| `src/contemplative_agent/core/distill.py` | `IdentityResult` gains `old_body` / `new_body` / `block_name` / `source` (all defaulted). `distill_identity` populates them from the persona_core body it already extracts. |
| `src/contemplative_agent/cli.py` | Import `identity_blocks` + `IDENTITY_HISTORY_PATH`. New helper `_append_identity_history_for_adoption`. `_handle_distill_identity` direct-write path appends history after `_wr(...)`. `_handle_adopt_staged` captures pre-write text and, for `command == "distill-identity"` on `IDENTITY_PATH`, appends history after `write_restricted(...)`. New handler `_handle_migrate_identity` with `--dry-run`. Subparser registered; handler wired into `no_llm_handlers`. |
| `tests/test_distill.py` | +2 cases: `IdentityResult.old_body` / `new_body` populated correctly for legacy and block-format identities. |
| `tests/test_cli.py` | +11 cases across 3 new test classes: `TestMigrateIdentity` (missing-file / dry-run / full / idempotent / dry-run-on-already-migrated), `TestDistillIdentityHistoryHook` (approved → history / rejected → no history / stage-only → no history), `TestAdoptStagedHistoryHook` (adopt identity → history / adopt non-identity → unchanged / rejected adopt → no history). |
| `docs/decision-history/README.md` | ADR-0025 index entry. |

## Test results

| Suite | Count | Status |
|---|---|---|
| test_identity_blocks.py | 36 | PASS |
| test_distill.py (incl. 2 new ADR-0025 cases) | 45 | PASS |
| test_llm.py | 79 | PASS |
| test_cli.py (incl. 11 new ADR-0025 cases) | 100 | PASS |
| **Total touched** | **260** | **PASS** |

The 11 new cli tests mock `distill_identity` at the import site so the hook behaviour is testable without Ollama or a real ViewRegistry.

## Smoke verification (no LLM, no network)

- `migrate-identity --dry-run` on a legacy file prints the target path + the backup path that *would* be created, makes no writes, leaves no audit or history entries.
- `migrate-identity` (full) on a legacy file writes `identity.md.bak.pre-adr0024`, rewrites `identity.md` with block frontmatter, appends one `audit.jsonl` entry (`command="migrate-identity"`) and one `identity_history.jsonl` entry (`source="migration"`, `old_hash=SHA256("")[:16]`, `new_hash=SHA256(persona_body)[:16]`).
- Running `migrate-identity` a second time is a no-op — prints "already in block format", no backup created, no logs appended.
- `distill-identity` approved run → `identity_history.jsonl` gains one `source="distill-identity"` entry with `old_hash != new_hash`.
- `distill-identity` rejected run → no history entry (audit captures the rejection separately).
- `distill-identity --stage` then `adopt-staged --yes` → history entry appears at adoption time, not at staging time.

## Behaviour changes now live

**Write path side-effects**:
- `~/.config/moltbook/logs/identity_history.jsonl` is created on first distill approval / migration. Each entry is a compact JSON line: `{"block": "persona_core", "ts": "...", "source": "...", "old_hash": "<16 hex>", "new_hash": "<16 hex>"}`. Full-text recovery remains the snapshot subsystem's responsibility (ADR-0020); the history only carries hashes.
- No rotation, no auto-delete. ADR-0021's "memory artefacts are append-only" discipline extends to this file.

**CLI surface**:
- New subcommand `contemplative-agent migrate-identity [--dry-run]` registered alongside `migrate-patterns` in the Tier-1 (no-LLM) dispatch map.
- `distill-identity` and `adopt-staged` user-facing behaviour is unchanged — the history hook is a side-effect only.

**What legacy users see**:
- Nothing, until they opt in by running `migrate-identity`. The 11 packaged templates and any user's existing plain-text `identity.md` continue to work byte-identical.

## Known caveats / follow-ups

- **No history for non-persona block updates yet** — only `persona_core` is refreshed by `distill-identity`. When per-block distill routing lands (next ADR), history threading will need matching `block_name` per route.
- **No inspect CLI** — reading `identity_history.jsonl` requires `cat` / `jq`. A `contemplative-agent inspect-identity-history [--block persona_core]` subcommand is a natural follow-up but explicitly out of scope here.
- **Trust model for `source` field** — currently accepted values are `distill-identity | agent-edit | migration | template | legacy`. The `agent-edit` source will only start appearing when the runtime agent-edit tool (deferred) ships.
- **Still deferred (next ADRs)**:
  - Per-block distill routing (`current_goals` / `recent_themes` distilled from their own views with their own prompts, written in qwen3.5:9b's own thought-space per prompt-model-match memory).
  - Runtime agent-edit tool touching ADR-0013 authorship-problem. Requires its own design discussion.

## Delivery

Single commit on `main`, single ADR. Same cadence as Phases 1–4.

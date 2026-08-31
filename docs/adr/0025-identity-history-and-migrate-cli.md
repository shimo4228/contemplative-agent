# ADR-0025: Identity History Log Wiring + migrate-identity CLI

> **Superseded by [ADR-0030](0030-withdraw-identity-blocks.md) (2026-04-18).** `identity_history.jsonl` was never written to in the live environment; ADR-0020 snapshots + `audit.jsonl` already cover the auditability surface this ADR was intended to close. Body retained for the historical record.

## Status

superseded-by 0030

## Date

2026-04-16

## Context

ADR-0024 landed the identity block schema, a stdlib-only parser/renderer, block-aware distill-identity, and migration-as-a-pure-function. Following the Phase-3 cadence ("schema lands, wiring deferred"), two deliverables were intentionally held back:

1. **`identity_history.jsonl` is never written in the live code path.** `identity_blocks.append_history()` is tested and ready (0600 perms, JSONL, SHA-256 16-hex-prefix hashes of old/new body) but no distill-identity call site invokes it. Every block change therefore leaves a file rewrite on disk with no per-block audit trail beyond the generic `audit.jsonl` approval record.
2. **There is no `migrate-identity` CLI.** The pure function `identity_blocks.migrate_to_blocks(path)` is idempotent, creates `.bak.pre-adr0024`, and is fully tested — but a user who wants to upgrade their legacy `identity.md` to block format has to drop into a Python shell. The 11 packaged templates and any user's existing `identity.md` remain stuck in legacy mode until migration is easy to invoke.

Two deferred-but-deeper tasks from the same follow-up set — per-block distill routing and a runtime agent-edit tool — are **explicitly out of scope** here. Per-block routing needs per-block prompt discipline (each prompt written in qwen3.5:9b's own thought space, not Opus's) and will shape more than one file. The agent-edit tool touches ADR-0013 authorship-problem territory — mid-session self-modification has no precedent in this codebase and warrants its own ADR.

## Decision

### 1. Add an `IDENTITY_HISTORY_PATH` constant

In `src/contemplative_agent/core/config.py`, alongside `IDENTITY_PATH`:

```python
IDENTITY_HISTORY_PATH = MOLTBOOK_DATA_DIR / "logs" / "identity_history.jsonl"
```

Places the history log next to `audit.jsonl` in the existing `logs/` directory. 0600 perms are enforced by `identity_blocks.append_history()` (already tested). The two logs serve distinct purposes:

- `audit.jsonl` — **generic approval record.** "User decided X about path Y at time Z." One entry per approval event, any command.
- `identity_history.jsonl` — **per-block change record.** "Block `persona_core` went from hash A to hash B via source `distill-identity` at time Z." One entry per block change, identity-only. Full-text recovery is the snapshot subsystem's job (ADR-0020); the history keeps only hashes so the log stays small and never re-captures untrusted content.

### 2. Extend `IdentityResult` with history-threading fields

`src/contemplative_agent/core/distill.py`:

```python
@dataclass(frozen=True)
class IdentityResult:
    text: str
    target_path: Path
    # ADR-0025 history threading — defaults keep existing callers working
    old_body: str = ""  # persona_core body *before* distill
    new_body: str = ""  # refined persona body *after* distill
    block_name: str = "persona_core"
    source: str = "distill-identity"
```

Defaults are the key property: any caller that still constructs `IdentityResult(text=..., target_path=...)` keeps working, and any consumer that reads only `.text` / `.target_path` is byte-identical. No tests construct it directly (verified), so the change is non-breaking by construction.

`distill.distill_identity` populates the new fields from what it already has — `current_identity` (the persona_core body pulled out of the parsed document) becomes `old_body`; the validated, cleaned `new_persona_body` becomes `new_body`.

### 3. Wire the history hook into three CLI write sites

| Site | When | Source label |
|---|---|---|
| `_handle_distill_identity` direct write | After `_wr(...)` succeeds | `"distill-identity"` |
| `_handle_adopt_staged` for `command == "distill-identity"` | After `write_restricted(...)` succeeds | `"distill-identity"` |
| `_handle_distill_identity --stage` path | **Never appends** — staging is pre-approval | — |
| `_handle_migrate_identity` | After `migrate_to_blocks()` succeeds | `"migration"` |

All append calls are wrapped in `try/except OSError` so a log-write failure never blocks a successful file write — same defensive pattern as `_log_approval` (cli.py:284–285).

For the `adopt-staged` branch, the current file is read **before** `write_restricted(...)` so we can hash the pre-write body. Without the read-before-write, the old content is gone by the time we notice it was an identity file. The read is free for non-identity staged items (they don't enter the identity branch) and cheap for identity.md (one small file).

### 4. `migrate-identity` CLI subcommand

Patterned after `_handle_migrate_patterns` (ADR-0021):

```bash
contemplative-agent migrate-identity              # run migration
contemplative-agent migrate-identity --dry-run    # preview only
```

- **Already in block format** → prints `already in block format (no-op)` and exits 0.
- **Missing file** → prints `No identity file found at ...` and exits 0 (not an error).
- **Dry-run** → prints the source path, backup path that *would* be created, target block name; no file writes.
- **Full run** → delegates to `identity_blocks.migrate_to_blocks()`, which writes `identity.md.bak.pre-adr0024` then rewrites `identity.md` with the frontmatter schema. Afterwards, one `_log_approval("migrate-identity", ...)` entry lands in `audit.jsonl`, and one `source="migration"` entry lands in `identity_history.jsonl` marking the initial persona_core body.

Registered in the Tier-1 `no_llm_handlers` dispatch map — pure function, no LLM, no network. Same spot as `migrate-patterns`.

### 5. No changes to `identity_blocks.py` or `llm.py`

Both modules already expose everything needed. `append_history`, `parse`, `.get`, `migrate_to_blocks` all ship with ADR-0024 tests. `llm._build_system_prompt` already routes through the block parser.

## Consequences

**Positive**:

- Every `distill-identity` approved write leaves a per-block audit trail. Future tooling (`contemplative-agent inspect-identity-history`, the next ADR's per-block routing) can build on top of that trail without further schema work.
- Users get a one-command upgrade path from legacy plain-text `identity.md` to block format. The existing 11 packaged templates remain legacy-compatible; migration is opt-in.
- Consistent ergonomics with `migrate-patterns` (ADR-0021) — same `--dry-run`, same summary block, same audit log integration.
- Staging-deferred writes (`distill-identity --stage`) produce history only on actual adoption, not on staging. The history log therefore reflects ground truth: what's on disk right now.

**Negative / risks**:

- `IdentityResult`'s field count doubles (2 → 6). Mitigated by defaults; constructors with positional args don't exist in the codebase, so no call site breaks.
- `_handle_adopt_staged` gains an identity-specific branch. Acceptable because `distill-identity` is the only command today that produces identity artifacts; future commands (agent-edit in a later ADR) will slot into the same branch.
- `identity_history.jsonl` grows without bound. Each entry is ~250 bytes, one per distill approval / migration, so growth is bounded by user activity. ADR-0021 already committed us to no-delete on memory artifacts; same discipline applies here.

**Explicitly not addressed** (next ADR territory):

- Per-block distill routing (`current_goals`, `recent_themes`, etc., each from their own view with their own prompt).
- Runtime agent-edit tool for individual blocks during a live session.
- Any automatic pruning, rotation, or compaction of `identity_history.jsonl`.

## Alternatives considered

1. **History append on every *proposal* (including rejected)** — would give visibility into what the LLM tried to write even if the user said no. Rejected because approval events are already in `audit.jsonl`, and duplicating the "proposed but rejected" signal in `identity_history.jsonl` turns the history into a noisy superset of the audit log. History is scoped to ground-truth on-disk changes.
2. **Embed history threading fields in a dedicated `DistillMetadata` sidecar rather than `IdentityResult`** — cleaner type hierarchy, but adds a new dataclass nobody asked for and forces CLI to juggle two objects. Rejected as over-engineering for four optional fields with sensible defaults.
3. **CLI re-hashes the before/after body itself, skipping `IdentityResult` extension** — keeps `IdentityResult` small, but duplicates the parse-and-extract logic already running in `distill.distill_identity`. The current function has already parsed the document to extract `current_identity`; making the CLI do the same work twice is waste. Rejected.
4. **Ship migrate-identity as a flag on another command** (e.g. `distill-identity --migrate`) — couples two orthogonal operations. Users who want to migrate without running a full LLM distill shouldn't have to. Rejected: follow `migrate-patterns` precedent and make it its own subcommand.
5. **Make migration happen automatically on first block-format write from `distill-identity`** — surprises users with in-place format change. Rejected for the same reason ADR-0024 rejected auto-migration: the 11 packaged templates are deliberately plain text, and any automatic format upgrade will surprise someone comparing their running file to the template.

## References

- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — snapshots remain the full-text recovery mechanism; this ADR's history log stores hashes only.
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — the `migrate-patterns` CLI that `migrate-identity` mirrors.
- [ADR-0023](0023-skill-as-memory-loop.md) — sibling ADR that introduced the "tiny stdlib-only frontmatter + history log + deferred CLI wiring" discipline this ADR completes for identity.
- [ADR-0024](0024-identity-block-separation.md) — this ADR completes the deferred wiring from Phase 4 follow-ups.

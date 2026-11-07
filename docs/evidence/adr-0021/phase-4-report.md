# Phase 4 Report — ADR-0024 Identity Block Separation

Date: 2026-04-16
Status: Schema + runtime-read + distill-write changes landed. Tests green. Migration is available as a pure function; the `migrate-identity` CLI subcommand and per-block distill routing are deferred to a follow-up (same cadence as Phase 3, where behaviour-change risk is split from the schema landing).

## Scope

Implemented improvement vector IV-6 (Identity Block Separation). `~/.config/moltbook/identity.md` now supports a YAML-frontmatter block list; files without frontmatter continue to work unchanged as a single `persona_core` block. `distill-identity` refreshes only the `persona_core` body, leaving any other blocks byte-stable. The `llm` system-prompt builder reads through the block parser so frontmatter never leaks into the prompt.

## Artifacts

### New files

| File | Purpose |
|---|---|
| `src/contemplative_agent/core/identity_blocks.py` | Stdlib-only parser/renderer for the frontmatter-block schema. `parse`, `render`, `update_block`, `load_for_prompt`, `migrate_to_blocks`, `append_history`, `body_hash`. Malformed frontmatter degrades to legacy whole-file mode rather than raising. |
| `docs/decision-history/0024-identity-block-separation.md` | ADR-0024 rationale, decision, alternatives (PyYAML dep / separate files per block / store inside knowledge.json / auto-migrate on first distill / per-block LLM distill this phase — all rejected). |
| `tests/test_identity_blocks.py` | 36 cases: parse (legacy + blocks + malformed), render (legacy + blocks + round-trip + extras), update_block (existing / append / legacy / unknown source), load_for_prompt, migrate_to_blocks (forward + idempotent + missing file), body_hash, append_history. |

### Modified files

| File | Change |
|---|---|
| `src/contemplative_agent/core/llm.py` | `_build_system_prompt` reads identity via `identity_blocks.load_for_prompt()` instead of `path.read_text()`. Legacy files still splice verbatim; block files splice the concatenated block bodies, with frontmatter stripped. |
| `src/contemplative_agent/core/distill.py` | `distill_identity` parses the existing file, feeds only the `persona_core` body into the LLM refine, and writes back via `update_block(..., source="distill-identity")`. Legacy files stay legacy on disk; block files stay block-format and non-persona blocks are left byte-identical. Returned `IdentityResult.text` now carries the full rendered file (still works with the existing CLI write path). |
| `tests/test_distill.py` | Added `TestDistillIdentity::test_legacy_file_stays_legacy` and `test_block_format_preserves_non_persona_blocks` to pin the block-aware behaviour. |
| `docs/decision-history/README.md` | ADR-0024 index entry. |

## Test results

| Suite | Count | Status |
|---|---|---|
| test_identity_blocks.py (new) | 36 | PASS |
| test_distill.py (incl. 2 new block cases) | 43 | PASS |
| test_llm.py | 79 | PASS |
| test_memory.py / test_snapshot.py / test_migration.py | 112 | PASS |
| test_agent.py / test_cli.py | 229 | PASS |
| **Total touched** | **499** | **PASS** |

Full suite not run — the changes are surgical (one new core module plus two small insertion points). Regression surface is covered by the 499 tests above, which exercise every touched call path.

## Smoke verification (no LLM call required)

- `parse()` on the checked-in `config/templates/contemplative/identity.md` (plain text) returns `is_legacy=True` with the full file as `persona_core.body`.
- `render(parse(text))` round-trip on the same legacy file yields the original bytes (up to trailing-newline normalisation).
- A synthetic 2-block file round-trips: `parse → render → parse` reproduces both block names, sources, and bodies, including extras (`authored_by: laukkonen`).
- `load_for_prompt` on a 2-block file returns `"Core.\n\nGoals."` — frontmatter stripped, blocks joined by blank line.
- `migrate_to_blocks` on a legacy file creates `identity.md.bak.pre-adr0024`, then rewrites the file with frontmatter + `## persona_core`; running it a second time returns `already_migrated=True` with no file change.
- `update_block` on a 2-block doc: refreshing `persona_core` updates its `last_updated_at` and `source=distill-identity`; the `current_goals` block's body and `last_updated_at` are bitwise unchanged.
- `distill_identity` integration test: with `generate` mocked to return `"raw analysis"` then `"refined identity"`, a 2-block file on disk produces an `IdentityResult` whose `text` starts with `---`, contains both `"refined identity"` and the untouched `"cooperation research"` body.

## Behaviour changes now live

**Runtime read path**:
- `llm._build_system_prompt()` now strips identity frontmatter before splicing into the prompt. For all 11 checked-in templates and any existing user identity.md this is a no-op — they parse as legacy and the function returns the verbatim bytes.
- If a file is malformed (e.g. broken frontmatter), the parser degrades to legacy mode rather than raising. The prompt build never crashes on a bad identity.md.

**Distill-identity write path**:
- On a legacy file, distill stays in legacy mode on disk (no surprise migration). The `persona_core` body is still the thing being refreshed.
- On a block-format file, only the `persona_core` block's body changes; non-persona blocks remain byte-stable. `last_updated_at` and `source` on the refreshed block are rewritten; others are untouched.

**Not wired yet (deferred)**:
- `~/.config/moltbook/identity_history.jsonl` is not written by the live distill path. The helper exists, is tested, and is ready to call; wiring happens in the same follow-up ADR that adds `migrate-identity` CLI and per-block distill routing.
- No CLI subcommand exists to migrate an existing identity file. Until then, a user can migrate explicitly from a Python shell (`identity_blocks.migrate_to_blocks(IDENTITY_PATH)`) or continue using legacy format with zero impact.

## Known caveats / follow-ups

- **No auto-migration**: deliberate. Users who have 11 checked-in templates or a hand-edited identity.md should not be surprised by an in-place format change. Migration must be an explicit action.
- **History log not yet appended by live path**: the next ADR will thread old/new hashes through `IdentityResult` and have the CLI append to `identity_history.jsonl` after a successful approval-gate write.
- **Per-block distill routing** (e.g. different view registries for `current_goals` vs `persona_core`) is explicitly out of scope; this ADR only commits the block *schema* and migration.
- **Agent-edit tool** for individual blocks at runtime is stubbed-out in the ADR but not built here.
- **Frontmatter parser** supports exactly the narrow YAML subset needed (`blocks:` → list of maps → string values). Any richer YAML (nested lists, flow style, multi-line strings) will fall back to legacy mode. Acceptable — the schema for this ADR is flat.

## Next step

Follow-up ADR (call it 0025 when filed): wire `identity_history.jsonl` append from CLI post-approval, add `contemplative-agent migrate-identity` subcommand (dry-run + `--yes` + `.bak` inspection), and begin exploring per-block distill routing (e.g. `current_goals` distilled from a `current_goals` view rather than `self_reflection`).

All four phases of the unified-booping-snowflake plan have landed in ADR form (0021 / 0022 / 0023 / 0024). IV-1 and IV-8 remain explicitly skipped with documented re-evaluation triggers (see master plan §Improvement Vectors).

# ADR-0035: Sunset ADR-0019 Migration Surface and Consolidate Artifact Extraction

## Status
accepted

## Date
2026-05-05

## Context

Two sources of friction have accumulated in the codebase since ADR-0019 landed and the post-2026-04-15 stabilization period began.

### 1. Migration commands kept their CLI surface long after migration completed

ADR-0019 moved `knowledge.json` from category-tagged rows to embedding + view shape. ADR-0021 added the provenance / bitemporal / trust schema. ADR-0026 retired the discrete `category` field. Each shipped with a one-shot CLI subcommand under `core/migration.py`:

- `embed-backfill` (ADR-0019) — compute embeddings for existing patterns + episode log
- `migrate-patterns` (ADR-0021) — fill provenance / bitemporal defaults; strip retired ADR-0028/0029 fields
- `migrate-categories` (ADR-0026) — drop `category` / `subcategory`; legacy `noise` becomes `gated=True`

The sole active deployment finished migrating on 2026-04-15. The schema is consistent on disk: `knowledge.json` keys are `{distilled, embedding, gated, importance, pattern, provenance, source, trust_score, trust_updated_at, valid_from, valid_until}`. No new caller has invoked the migration commands since then. They remain as ~700 LOC in `core/migration.py` plus ~390 LOC of tests, plus three CLI subparsers, plus migration-specific paragraphs in three doc files (`CHANGELOG.md`, `docs/CONFIGURATION.md`, `docs/CONFIGURATION.ja.md`) and one runbook (`docs/runbooks/adr-0019-migration.md`).

The `--dry-run` flag on the four approval-gate commands (`insight`, `rules-distill`, `distill-identity`, `amend-constitution`) was deprecated when ADR-0012 introduced the interactive approval gate (rejecting at the prompt is functionally equivalent to discarding a dry-run preview). The deprecation has shipped with a warning since then. The flag and its 4 handler-side `if _is_dry_run(args): ...` branches still occupy code paths that nothing outside their own deprecation warning exercises.

The `_parse_legacy_markdown` reader in `core/knowledge_store.py` survives from the v1.x format, before `knowledge.json` was JSON. Production data has been JSON-only since v2.0; the only reachable callers are two test cases that synthesize legacy Markdown to exercise the parser.

### 2. Artifact-extraction logic is duplicated across three commands

`insight` (ADR-0023), `rules-distill`, and `skill-reflect` (ADR-0023 again) each carry an extraction loop that:

1. iterates over a candidate set
2. calls the LLM to produce an artifact
3. validates the output against the identity-content sanitizer
4. extracts a title
5. slugifies a filename
6. guards against path-escape
7. wraps the result in a per-command `*Result` dataclass

Each implementation is 30–60 LOC. The three are nearly identical at the loop scaffold (steps 3, 5, 6); they diverge at the prompt (step 2), at marker handling (step 7), and at the result shape (step 7).

Likewise, the four CLI handlers `_handle_insight`, `_handle_skill_reflect`, `_handle_rules_distill`, `_handle_amend_constitution` carry a near-identical approval-gate boilerplate: snapshot, iterate, print, `_approve_write`, `_log_approval`, write-on-approve, summary print. Each is 30 LOC. The summary print and result shape differ; the gate mechanics do not.

A weaker form of duplication: eight retrieval / quality thresholds — `CLUSTER_THRESHOLD` (insight 0.70), `CLUSTER_THRESHOLD_RULES` (0.65), `NOISE_THRESHOLD` (distill 0.55), `SIM_DUPLICATE` (stocktake 0.90), `SIM_UPDATE` (stocktake 0.80), `SIM_CLUSTER_THRESHOLD` (stocktake 0.80), the skill-router default (0.45), and the rules-stocktake reflect threshold — are defined module-locally with ad-hoc ADR-reference comments. `core/snapshot.py` already does late-import collection to dump them into pivot snapshots, which is the de-facto registry pattern, just upside-down.

### 3. Constraint from the previous withdrawal cycle

ADR-0024/0025 introduced identity-block parsing and were withdrawn together by ADR-0030. ADR-0030 distilled the lesson into the `single-responsibility-per-artifact` heuristic: an artifact's responsibility lives at exactly one layer; do not push a new concern into an existing artifact's sub-structure when another layer can host it. The plan in this ADR has to honor that — any consolidation must avoid pulling per-command domain logic (prompts, marker handling, result fields) into a shared base class.

## Decision

This ADR records two coordinated changes. The first (Sunset) lands as the same PR; the second and third (Helper extraction, Loop consolidation) land as follow-up PRs. The ADR is the contract that those follow-ups inherit.

### 1. Sunset of the ADR-0019 migration surface

Delete the following:

- `src/contemplative_agent/core/migration.py` (~700 LOC), including `_ensure_adr0021_defaults` which has no caller outside this module
- `tests/test_migration.py` (~390 LOC)
- The `TestMigrationADR0021` class in `tests/test_knowledge_store.py` (~110 LOC)
- The two legacy-Markdown test cases in `tests/test_memory.py` (`test_legacy_markdown_migration`, `test_legacy_markdown_gets_default_importance`)
- `_handle_migrate_patterns`, `_handle_migrate_categories`, `_handle_embed_backfill` in `cli.py`, their three subparsers, and their dispatch entries in both the no-LLM and LLM handler tables
- The `EPISODE_EMBEDDINGS_PATH` import in `cli.py` (the sole consumer was `_handle_embed_backfill`)
- `_warn_dry_run_deprecated` and the `_APPROVAL_GATE_COMMANDS` frozenset in `cli.py`. The four handlers' `_warn_dry_run_deprecated(args)` calls and `if _is_dry_run(args): ...` branches go with them
- The `--dry-run` argparse declarations on `insight`, `rules-distill`, `distill-identity`, `amend-constitution`
- `_parse_legacy_markdown` and its caller in `core/knowledge_store.py`. A non-JSON `knowledge.json` now logs a warning and loads as empty
- `docs/runbooks/adr-0019-migration.md` and the table entry in `docs/runbooks/README.md`
- The "One-Time Migrations" section in `docs/CONFIGURATION.md` and `docs/CONFIGURATION.ja.md`

Update:

- `CHANGELOG.md` — replace the "Run these migrations once" block with a sunset note pointing at v2.0.x release tags for any latecomer migration
- `core/distill.py` — remove the `embed-backfill first to migrate` lines from `enrich`'s docstring and `distill_identity`'s docstring
- `core/constitution.py` — remove the `embed-backfill first to migrate` clause from the comment block above the constitutional view lookup

The on-disk `knowledge.json` and its `.bak.*` files are untouched. Anyone arriving with a v1.x `knowledge.json` after this PR is expected to run the migrations from a v2.0.x release tag and then upgrade.

### 2. Threshold registry and text utilities (PR2)

Add `src/contemplative_agent/core/thresholds.py`. Move the eight threshold constants there with a docstring per constant naming the ADR / calibration date / unit. `core/snapshot.collect_thresholds` reads from this module instead of late-importing each owner.

Add `src/contemplative_agent/core/text_utils.py` with `extract_title`, `slugify`, `strip_frontmatter`. Move `_extract_title` and `_slugify` from `core/insight.py` and `_strip_frontmatter` from `core/rules_distill.py`. Update callers in `cli.py`, `rules_distill.py`, and `stocktake.py`. The pre-existing `stocktake → rules_distill` import edge dissolves.

Rename `stocktake.format_report` to `format_stocktake_report` to remove the same-name collision with `metrics.format_report`. They format different report types; the rename is hygienic.

Do **not** extract the following modules (each was considered and rejected):

- `core/sanitizer.py` — `_sanitize_output` and `wrap_untrusted_content` are co-located in `core/llm.py` for the same reason: they share `_INJECTION_TOKENS` and operate on the same trust boundary. Splitting them into a 2-function module is overengineering
- `core/approval_gate.py` — `_log_approval`, `_approve_write`, `_stage_results`, `StageItem`, and `AUDIT_LOG_PATH` are CLI-bound (they reference `STAGED_DIR`, `MOLTBOOK_DATA_DIR`, `AUDIT_LOG_PATH`). Moving them into `core/` would invert ADR-0001's `cli.py → core/` import direction
- A new `core/io.py` — `core/_io.py` already exists; if a duplicated I/O helper appears in PR3, fold it into `_io.py`

### 3. Consolidate the artifact-extraction loop (PR3a/PR3b)

Add `src/contemplative_agent/core/artifact_extraction.py` exposing:

```python
@dataclass(frozen=True)
class ArtifactSpec:
    name: str                                      # "insight" | "rules" | "skill-reflect"
    target_dir: Path
    filename_template: str                         # e.g. "{slug}.md"
    validator: Callable[[str], bool]               # e.g. validate_identity_content
    no_change_marker: Optional[str] = None         # e.g. _NO_CHANGE
    no_rules_marker: Optional[str] = None          # e.g. _NO_RULES_MARKER

def extract_artifacts(spec: ArtifactSpec, items: Iterable[X]) -> ArtifactBatch: ...
```

Each caller in `insight.py` / `rules_distill.py` / `skill_reflect.py` builds its own `ArtifactSpec`, calls `extract_artifacts`, and wraps the result into its own `*Result` type. **The base-class framing is rejected** by the ADR-0030 rule: per-command differences (prompt content, marker semantics, result fields) live at the call site, not in a shared parent.

For the four CLI handlers, add `_run_approval_loop(items, *, command, snapshot_path)` inside `cli.py`. Each handler still owns its summary print (the dropped/skipped/no-change/revised wording differs by command). The loop body — print, approve, log, write-on-approve — collapses into the helper.

Reject splitting `cli.py` into a `cli/` package as part of PR3. The file is ~1700 LOC after PR1, every section is a CLI handler, and the cohesion is high. Re-evaluate after PR3b lands.

## Consequences

**Positive**:

- ~1100–1300 LOC removed from runtime + tests by the sunset alone
- The four approval-gate handlers no longer carry orphan deprecation paths; any future caller reading those handlers does not have to discover that `--dry-run` was deprecated five months earlier
- `knowledge_store._parse_json` is the only reader path; the contract is unambiguous
- After PR2, threshold provenance (which ADR set this value, when, against what calibration) is co-located. `snapshot.collect_thresholds` becomes a 3-line read instead of a 6-import collector
- After PR3, each of `insight.py`, `rules_distill.py`, `skill_reflect.py` should land under 250 LOC; each of the four CLI handlers under 30 LOC. The "duplicate cluster" finding (ten clusters identified in the audit) is resolved for the two heaviest clusters without re-creating ADR-0024/0025's over-extraction

**Negative**:

- A v1.x deployment that has not yet migrated cannot upgrade past this PR by pulling main; they must first checkout a v2.0.x release tag, run the migrations, then pull main. The README "v1 → v2.0 migration" link is updated to point at a tagged release rather than current main
- A non-JSON `knowledge.json` no longer reports its rows; it logs a warning and the store is empty. The earlier auto-fallback was a safety net for the v1 → v2 transition; that net is now removed
- Scripts that pass `--dry-run` to `insight` / `rules-distill` / `distill-identity` / `amend-constitution` will fail with `unrecognized arguments`. The CHANGELOG calls this out; the failure mode is loud rather than silent

**Neutral**:

- `~/.config/moltbook/knowledge.json.bak.*` files are untouched. Any v1 → v2 migration leaves these as a recovery path
- ADR-0019 (embedding + views) and ADR-0021 (pattern schema) remain accepted; the migration surface that delivered them retires, not the design
- ADR-0026 (retire categories) remains accepted; the `migrate-categories` command that completed it retires
- `core/distill.py`'s `_CategoryResult` dataclass is **not removed**. It is the return type of `_distill_category` (4 references inside the module). Despite the ADR-0026 category retirement, this is a meaningful internal type, not a leftover

## Lessons inherited from earlier ADRs

ADR-0030 produced `single-responsibility-per-artifact`. ADR-0034 added "validate a mechanism against actual LLM output before generalizing it." This ADR adds a third, recorded as `feedback_substrate-migration-sweep` was already capturing in part: **a one-shot CLI subcommand has a sunset condition; record it in the ADR that introduced it, and retire it together with its docs in one PR.** The cost of leaving migration commands resident is not zero — they accumulate tests, runbook entries, and `--dry-run` flags that the rest of the system has to keep step with. The retirement is itself a `chore` that protects the next refactor from inheriting them.

## References

- [ADR-0001](0001-core-adapter-separation.md) — `cli.py → core/` import direction; constraint that kept `_log_approval` / `_stage_results` from being extracted to `core/`
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — embedding + view shape and original embed-backfill motivation; not retired
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — pattern schema landing; not retired
- [ADR-0026](0026-retire-discrete-categories.md) — category retirement; the `migrate-categories` command that delivered it retires here
- [ADR-0028](0028-retire-pattern-level-forgetting.md) / [ADR-0029](0029-retire-sanitized-flag.md) — retired fields whose strip-on-load logic dies with `migration.py`
- [ADR-0030](0030-withdraw-identity-blocks.md) — first withdrawal ADR; the `single-responsibility-per-artifact` heuristic that constrains PR3's design
- [ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.md) — most recent withdrawal precedent; the same retire-with-docs-in-one-PR pattern

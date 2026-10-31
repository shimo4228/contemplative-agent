# Runbook: knowledge.json → embedding sidecar (ADR-0108)

One-time cutover of the live `$MOLTBOOK_HOME`. Moves the 768-dim pattern
vectors out of `knowledge.json` and into `pattern-embeddings.sqlite` beside it.

**Status**: the production cutover ran on 2026-09-12. Current code refuses a
`knowledge.json` with inline vectors or bare-string rows
(`reason=legacy_row_shape`, ADR-0108 amendment 2026-10-31), so the steps below
run from the **v2.13.0 release tag** (a checkout of that tag, against a copy of
the file), the last release that reads the inline shape. The script on the
current tree is the load/save report and the `--prune` broom only.

**Who runs this**: the operator, by hand, after the change is merged. Nothing
in the unattended chain performs the cutover as a step — though any run that
loads and saves the store performs it implicitly, which is why this should
happen *before* the next scheduled session rather than after.

**Expected effect** (measured on the live store, 2026-09-12, 8,467 rows):
`knowledge.json` 180 MiB → ~6 MiB, sidecar ~33 MiB, `KnowledgeStore.load()`
11.4 s → well under a second, peak RSS 1.6 GB → a fraction of it.

## Before

1. Pick a window with no scheduled session running (launchd fires at JST
   0/6/12/18 — see `docs/runbooks/runtime-backup-restore.md`). A session that
   saves the store mid-migration is not corrupting anything, but the
   before/after numbers stop meaning what this runbook says they mean.
2. Take a backup. This is the one step in the whole change that rewrites the
   live store:

   ```bash
   cd ~/MyAI_Lab/contemplative-agent
   cp ~/.config/moltbook/knowledge.json ~/.config/moltbook/knowledge.json.bak.pre-adr0108
   ./scripts/backup-runtime.sh   # optional; the local copy above is the one that matters
   ```

## Cutover

```bash
cd ~/MyAI_Lab/contemplative-agent

# 1. Look first. Writes nothing; prints row counts and any reason codes.
uv run python scripts/migrate-knowledge-sidecar.py --dry-run

# 2. Do it.
uv run python scripts/migrate-knowledge-sidecar.py
```

Read the output. `inline_legacy=<n>` on the first run is the expected state
(every row still carries its vector inline). A second run prints
`codes=['none']` and changes nothing — the migration is idempotent.

## After

```bash
# The invariant that would catch a half-migrated store: it asks both files.
uv run python scripts/state_invariant_check.py --home ~/.config/moltbook
```

`missing_embedding` must be ✅. If it is not, the rows named in the migration
script's output have no vector on either side; re-derive them (needs Ollama up
with the embedding model pulled):

```bash
uv run python scripts/restore-embed-knowledge.py
```

Then one end-to-end read, and the backup:

```bash
contemplative-agent generate-report   # reads knowledge + logs end to end
./scripts/backup-runtime.sh           # mirrors the now-small knowledge.json
```

## When to stop and roll back

Restore the `.bak.pre-adr0108` copy and delete `pattern-embeddings.sqlite` if:

- the migration script exits non-zero (it writes nothing on a failed load, so
  the store is untouched — investigate before re-running),
- `state_invariant_check.py` reports a `required_fields` or
  `timestamp_validity` FAIL that it did not report before, or
- the row count in the migration output does not match the row count the
  pre-migration `--dry-run` reported.

Rolling back: v2.13.0 reads an inline-vector file, so the pre-migration JSON
works unchanged with that tag. Current code refuses it (`reason=legacy_row_shape`)
without writing; convert it with v2.13.0 first.

## Housekeeping

Orphan vectors (sidecar rows no pattern claims — a soft-invalidated pattern
whose text was later revised) accumulate slowly and cost ~3 KB each. They are
counted by `state_invariant_check.py` and swept on demand:

```bash
uv run python scripts/migrate-knowledge-sidecar.py --prune
```

Do not put this on a schedule. ADR-0108 keeps pruning manual because a vector
whose row was invalidated today may be claimed again by a revision tomorrow.

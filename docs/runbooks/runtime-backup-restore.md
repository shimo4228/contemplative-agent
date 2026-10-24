# Runtime Backup & Restore

Disaster-recovery backup of `MOLTBOOK_HOME` (default `~/.config/moltbook`) to a
**private** git repo. Companion to `sync-data`, which publishes a curated
*public* projection and deliberately excludes `logs/` — episode logs are raw
untrusted external content and must never be published. This backup is the only
off-machine copy of those logs.

## What runs

- Script: `scripts/backup-runtime.sh` — rsync mirror of `MOLTBOOK_HOME` into
  the backup repo, then commit + push.
- Schedule: `contemplative-agent install-schedule --weekly-backup`
  (launchd job `com.moltbook.backup`, log `MOLTBOOK_HOME/logs/backup-launchd.log`).
- Failures write `ERROR:` lines to the launchd log, which the weekly
  log-anomaly sweep scans — a broken backup surfaces in the next weekly report.

## What is excluded (and why)

| Excluded | Reason |
|---|---|
| `credentials.json`, `*.env` (`cloud.env` among them) | API secrets — never in git, private or not. Both the rsync exclude and a post-transfer removal apply (an excluded-but-present mirror copy would otherwise keep being pushed). Rotation: [credential-rotation.md](./credential-rotation.md) |
| `knowledge.json` (raw) | mirrored **embedding-free** instead (see below) |
| `pattern-embeddings.sqlite` | the pattern vectors, after ADR-0108 moved them out of `knowledge.json`. Same reason as above — re-derivable, model-locked, ~35 MB of binary rewritten every run. The episode store's `embeddings.sqlite` (1.5 MB, a **different** basename) is still mirrored |
| `logs/ollama-serve.log`, `logs/ollama-serve.log.N.gz` | the local Ollama daemon's own stderr and its rotated generations — re-derivable operational noise, and at 96 MB it was one weekly run from crossing GitHub's 100 MB hard limit and stalling this backup entirely (2026-08-01). A copy already in the mirror is deleted, not just skipped: `rsync --exclude` also shields the destination from `--delete`. Rotation (`scripts/rotate-log.sh`, 7 generations) keeps the local copies bounded |
| `logs/mlx-server.log`, `logs/mlx-server.log.N.gz` | the optional MLX sibling's `mlx_lm.server` stderr (`run-with-mlx.sh` writes it under `$MOLTBOOK_HOME/logs/`, mode 0600) and its rotated generations — same treatment as `ollama-serve.log`: re-derivable noise from an external process that can carry prompt text at DEBUG verbosity. Rotated weekly by `backup-runtime.sh` (7 generations) |
| `.run.lock`, `.staged.lock` (`.*.lock`) | transient concurrency locks |
| `__pycache__/`, `.DS_Store` | junk |
| `README.md`, `.gitignore` (repo side) | backup-repo static files |

The names that are excluded for both this backup and the public sync live in
`config/sync-excludes.txt` (`--exclude-from`); the names withheld only from the
public repo (`logs/`, `*.bak*`, `.last_*`, `_gc_trash/`, ...) are in
`config/sync-excludes-public.txt`, which this backup does not read. The script
resolves an rsync 3.x (`scripts/lib-rsync.sh`) and logs its version line.

`knowledge.json` is regenerated into the mirror with the 768-dim embeddings
dropped (since 2026-07-12, `scripts/export-patterns-jsonl.py --format json`):
the vectors are model-locked (`nomic-embed-text`), fully re-derivable from
pattern text, and ~97% of the raw file's weight — the raw copy had passed
GitHub's 50 MB warning on its way to the 100 MB hard reject. Restore rebuilds
them in one step (see procedure). Historical `*.bak.*` snapshots stay as-is:
static blobs, committed once, no churn.

Between weekly backups, `KnowledgeStore.save()` keeps the three newest pre-save
copies of `knowledge.json` as `knowledge.backups/knowledge.json.save-<UTC stamp>`
(P0-04.6, D-P0-04-2 = A). Restore the newest one with a plain `cp` over
`knowledge.json`; the vectors live in the sidecar and are rebuilt by
`scripts/restore-embed-knowledge.py` if they no longer match. Rotation only
counts names beginning `knowledge.json.save-`, so other files in the directory
(for example `knowledge.json.bak-dup-cleanup-20260718`) are never removed.

Since ADR-0108 the raw `knowledge.json` is already text-only, so the export
boundary above is belt-and-braces for pre-migration files; the vectors it used
to strip now live in the separately excluded sidecar. Step 5 of the restore
procedure is unchanged in shape — it just writes into the sidecar instead of
back into the JSON.

Everything else — `logs/`, `reports/`, `snapshots/`, `skills/`, `views/`,
`identity.md`, `constitution/`, `rules/`, `agents.json` — is mirrored.

## Security invariants

1. The backup repo stays **private forever**. The script refuses to push if it
   can see (via `gh`) that the remote has been flipped public.
2. The repo is a **restore target, never a read path**: the CLAUDE.md ban on
   reading episode logs applies to the mirror too. Do not point LLM sessions
   at it.
3. Never embed a token in the backup repo's remote URL — use SSH or a
   credential-helper-backed HTTPS remote (an embedded PAT would surface in
   process args during the script's `gh repo view` call).

## Restore procedure

```bash
# 1. Clone the mirror
git clone git@github.com:shimo4228/contemplative-agent-runtime-backup.git restored-home

# 2. Point the agent at it (or move it into place)
mv restored-home ~/.config/moltbook   # or: export MOLTBOOK_HOME=$PWD/restored-home

# 3. Remove repo metadata from the restored home (optional but recommended)
rm -rf ~/.config/moltbook/.git

# 4. Re-issue the credential (credentials.json is not in the backup)
#    — re-register / copy from the secret store, then verify:
contemplative-agent status

# 5. Before re-embedding, check the embedder is the calibrated one: the
#    digest `ollama list` shows for nomic-embed-text must equal
#    CALIBRATED_EMBEDDING_DIGEST (core/embeddings.py). If it differs, the
#    re-backfill below is still required, but every similarity threshold is
#    on unmeasured weights until re-calibrated (docs/runbooks/model-swap.md,
#    section d). `contemplative-agent` prints the same finding as a drift
#    WARNING at startup.
#    Rebuild the pattern embeddings (the mirror stores knowledge.json
#    embedding-free). Needs the project venv + Ollama running with the
#    embedding model pulled. Idempotent; fails loudly without writing if
#    the embedder is unreachable.
cd ~/MyAI_Lab/contemplative-agent && uv run python scripts/restore-embed-knowledge.py

# 6. Sanity checks
contemplative-agent generate-report   # reads knowledge + logs end to end
```

Restore drills:

- 2026-07-11 (initial, pre-embedding-free): clone, inventory diff against
  live home 2575/2575 files zero difference, knowledge.json JSON parse OK
  with sha256 identical to live.
- Since 2026-07-12 the mirror's `knowledge.json` is embedding-free, so a
  drill's knowledge check is **no longer sha256-vs-live**. Verify instead:
  JSON parse OK, row count matches live, and (after step 5) the
  `missing_embedding` invariant passes. Re-derived vectors are only
  bit-identical to the originals under the same Ollama/model version — the
  store is self-consistent either way.

## Drill conditions

A drill proves the mirror restores; it is not a restore. Run it in isolation and read the result with `scripts/restore-drill-check.sh` (read-only: clones the mirror to a temp dir, then checks `git fsck`, the `logs/episodes/` file count and bytes against the live files not newer than the last backup commit, and the `knowledge.json` row count).

1. **Isolated target.** Restore into `MOLTBOOK_HOME=$PWD/restored-home`; a drill never `mv`s over the live home.
2. **When.** Not in the 00 / 06 / 12 / 18 JST session windows (Ollama contention, the run lock) and not Saturday 08:00-13:00 (the weekly chain).
3. **Before you start.** Free disk of at least twice the live home. `nomic-embed-text`'s digest equals the `embedding_model_digest` of the latest public snapshot manifest (the comparison itself is P1-07.12; on a mismatch do not run step 5 and follow the model-swap runbook). Note the backup repo's latest commit time.
4. **Pass criteria.** `scripts/restore-drill-check.sh` exits 0 (fresh clone + `git fsck` clean, episode files and bytes match, knowledge rows match); after step 5 `state_invariant_check.py` shows `missing_embedding` = 0; the episode store's `embeddings.sqlite` (restored with its old weights) and the re-derived sidecar do not mix two weights.
5. **RTO.** Time step 5 and record it in "Restore drills" below.
6. **Cadence.** Once per quarter (the T4 gate) and once after any ADR that changes where the store keeps its data. The backup cycle itself: D-P2-04-2 = A (owner, 2026-10-24), a daily push, because the episode logs are the only primary source and the cost is one `git push` a day. The installed job is still weekly (Mon 10:00); the daily installer change is pending (see docs/CONFIGURATION.md).
7. **Credentials.** `credentials.json` is not in the mirror. It is kept in: `<owner to fill: name of the password manager / secret store; never the value>`.

The first drill after ADR-0108 (sidecar embeddings) is owed: run it per the above in an isolated home and add a dated row to "Restore drills" with the JSON parse result, row counts, the `missing_embedding` invariant and the RTO.

## Known limits

GitHub warns on files over 50 MB and hard-blocks over 100 MB. The two
growth bombs were defused on 2026-07-12 by mirroring `knowledge.json`
embedding-free here (57 MB → ~1.6 MB) and in the public data repo (same
mechanism, `sync-research-data.sh`). Static already-committed blobs
(`embeddings.sqlite.bak.*` 61 MB, historical `knowledge.json.bak.*`) remain
in history but do not churn. If any *churning* file ever approaches 100 MB
again, move it to Git LFS or address growth at the source before the push
starts failing.

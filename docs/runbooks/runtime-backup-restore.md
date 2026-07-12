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
| `credentials.json` | API secret — never in git, private or not |
| `knowledge.json` (raw) | mirrored **embedding-free** instead (see below) |
| `.run.lock`, `.staged.lock` | transient concurrency locks |
| `__pycache__/`, `.DS_Store` | junk |
| `README.md`, `.gitignore` (repo side) | backup-repo static files |

`knowledge.json` is regenerated into the mirror with the 768-dim embeddings
dropped (since 2026-07-12, `scripts/export-patterns-jsonl.py --format json`):
the vectors are model-locked (`nomic-embed-text`), fully re-derivable from
pattern text, and ~97% of the raw file's weight — the raw copy had passed
GitHub's 50 MB warning on its way to the 100 MB hard reject. Restore rebuilds
them in one step (see procedure). Historical `*.bak.*` snapshots stay as-is:
static blobs, committed once, no churn.

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

# 5. Rebuild the pattern embeddings (the mirror stores knowledge.json
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

## Known limits

GitHub warns on files over 50 MB and hard-blocks over 100 MB. The two
growth bombs were defused on 2026-07-12 by mirroring `knowledge.json`
embedding-free here (57 MB → ~1.6 MB) and in the public data repo (same
mechanism, `sync-research-data.sh`). Static already-committed blobs
(`embeddings.sqlite.bak.*` 61 MB, historical `knowledge.json.bak.*`) remain
in history but do not churn. If any *churning* file ever approaches 100 MB
again, move it to Git LFS or address growth at the source before the push
starts failing.

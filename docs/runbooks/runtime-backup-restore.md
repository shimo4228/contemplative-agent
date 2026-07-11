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
| `.run.lock`, `.staged.lock` | transient concurrency locks |
| `__pycache__/`, `.DS_Store` | junk |
| `README.md`, `.gitignore` (repo side) | backup-repo static files |

Everything else — `logs/`, `knowledge.json` (+ historical `*.bak.*`),
`embeddings.sqlite`, `reports/`, `snapshots/`, `skills/`, `views/`,
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

# 5. Sanity checks
contemplative-agent generate-report   # reads knowledge + logs end to end
```

Last restore drill: 2026-07-11 (initial verification — clone, inventory diff
against live home: 2575/2575 files with zero difference, knowledge.json JSON
parse OK with sha256 identical to live).

## Known limits

GitHub warns on files over 50 MB and hard-blocks over 100 MB.
`knowledge.json` (52 MB at the first backup, and growing) is the file to
watch — if it approaches 100 MB, move it to Git LFS or address growth at the
source (pattern-store compaction) before the push starts failing. The same
limit applies to the public data repo, which also tracks `knowledge.json`.

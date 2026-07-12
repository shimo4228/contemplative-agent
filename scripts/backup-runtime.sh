#!/bin/bash
# Off-site disaster-recovery backup of MOLTBOOK_HOME to a PRIVATE git repo.
#
# Rationale: sync-data publishes a curated PUBLIC projection and deliberately
# excludes logs/ (episode logs are untrusted external content and must never
# be published). That leaves the irreplaceable research data — episode logs,
# audit trails — with a single copy on this machine. This script mirrors the
# runtime home, near-completely, to a private repo purely for restore.
#
# The backup repo MUST stay private forever: episode logs contain raw
# untrusted external content (prompt-injection vector). It is a restore
# target, never a read path for LLM sessions.
#
# Failure policy: loud, never silent. ERROR lines land in
# logs/backup-launchd.log which the weekly log-anomaly sweep scans, so a
# failing backup surfaces in the next weekly report even if unnoticed here.
set -euo pipefail

MOLTBOOK_HOME="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
BACKUP_REPO="${MOLTBOOK_BACKUP_REPO:-$HOME/MyAI_Lab/contemplative-agent-runtime-backup}"
# Resolve before any cd (same lesson as sync-research-data.sh 2026-07-12).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$MOLTBOOK_HOME" ]; then
    echo "ERROR: MOLTBOOK_HOME not found at $MOLTBOOK_HOME" >&2
    exit 1
fi

if [ ! -d "$BACKUP_REPO/.git" ]; then
    echo "ERROR: Backup repo not found at $BACKUP_REPO" >&2
    echo "Create it with: gh repo create <owner>/contemplative-agent-runtime-backup --private --clone" >&2
    exit 1
fi

# Refuse to push if the remote has been flipped to public (best-effort guard:
# needs gh + network; on "unknown" we warn and proceed rather than letting a
# gh outage silently halt backups).
REMOTE_URL="$(git -C "$BACKUP_REPO" remote get-url origin 2>/dev/null || echo "")"
if [ -n "$REMOTE_URL" ] && command -v gh >/dev/null 2>&1; then
    VISIBILITY="$(gh repo view "$REMOTE_URL" --json visibility -q .visibility 2>/dev/null || echo "unknown")"
    if [ "$VISIBILITY" = "PUBLIC" ]; then
        echo "ERROR: backup repo is PUBLIC — refusing to push episode logs." >&2
        echo "Make it private again: gh repo edit $REMOTE_URL --visibility private" >&2
        exit 1
    fi
    if [ "$VISIBILITY" = "unknown" ]; then
        echo "WARNING: could not verify repo visibility (gh offline?), proceeding" >&2
    fi
elif [ -n "$REMOTE_URL" ]; then
    echo "WARNING: gh not installed — cannot verify backup repo visibility, proceeding" >&2
fi

# Near-complete mirror. Excluded:
#   .git/ README.md .gitignore   — backup-repo static files (rsync --delete
#                                  would remove them from the repo otherwise)
#   credentials.json             — the API secret; never in git, private or not
#   .run.lock .staged.lock       — transient concurrency locks
#   __pycache__/ .DS_Store       — junk
#   knowledge.json               — mirrored embedding-free below (the 768-dim
#                                  vectors are re-derivable and ~97% of the
#                                  raw file, which was heading for GitHub's
#                                  100 MB hard limit; restore rebuilds them
#                                  with scripts/restore-embed-knowledge.py).
#                                  Historical *.bak.* stay as-is: static
#                                  blobs, committed once, no churn.
# Everything else — logs/, reports/ (including .private/), snapshots/,
# skills/, views/, agents.json — is state and goes in: a restore should need
# nothing but this repo, a re-issued credential, and one re-embed run.
rsync -a --delete \
    --exclude='.git/' \
    --exclude='README.md' \
    --exclude='.gitignore' \
    --exclude='credentials.json' \
    --exclude='knowledge.json' \
    --exclude='.run.lock' \
    --exclude='.staged.lock' \
    --exclude='__pycache__/' \
    --exclude='.DS_Store' \
    "$MOLTBOOK_HOME/" "$BACKUP_REPO/"

# knowledge.json is excluded above and regenerated embedding-free (set -e
# aborts the backup on filter failure rather than committing a stale copy).
MOLTBOOK_HOME="$MOLTBOOK_HOME" python3 \
    "$SCRIPT_DIR/export-patterns-jsonl.py" \
    "$BACKUP_REPO/knowledge.json" --format json

cd "$BACKUP_REPO"

# Belt and suspenders (codex P2): rsync --exclude also shields a destination
# copy from --delete, so a credentials.json ever seeded into the mirror by
# hand would survive and keep being pushed. Remove it here; `git add -A`
# below then stages the deletion if it was tracked.
rm -f credentials.json

git add -A

if git diff --cached --quiet; then
    echo "No changes to back up."
else
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    git commit -m "backup: $TIMESTAMP"
fi

if [ -z "$REMOTE_URL" ]; then
    echo "ERROR: no origin remote — local commits only, there is NO off-site copy." >&2
    exit 1
fi

# Always push, even on a no-change run (codex P2): a commit stranded by an
# earlier failed push must be retried, and an up-to-date push is a cheap no-op.
if ! git push; then
    echo "ERROR: push failed — the off-site copy is stale." >&2
    exit 1
fi

echo "Backup up to date at $(git rev-parse --short HEAD)"

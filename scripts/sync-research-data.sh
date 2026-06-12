#!/bin/bash
set -euo pipefail

MOLTBOOK_HOME="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
DATA_REPO="$HOME/MyAI_Lab/contemplative-agent-data"

if [ ! -d "$DATA_REPO/.git" ]; then
    echo "ERROR: Data repo not found at $DATA_REPO" >&2
    echo "Initialize with: git init $DATA_REPO" >&2
    exit 1
fi

if [ ! -d "$MOLTBOOK_HOME" ]; then
    echo "ERROR: MOLTBOOK_HOME not found at $MOLTBOOK_HOME" >&2
    exit 1
fi

# Sync safe files from MOLTBOOK_HOME (exclude dangerous files)
rsync -a --delete \
    --exclude='.git/' \
    --exclude='.gitignore' \
    --exclude='README.md' \
    --exclude='llms.txt' \
    --exclude='logs/' \
    --exclude='agents.json' \
    --exclude='credentials.json' \
    --exclude='rate_state.json' \
    --exclude='commented_cache.json' \
    --exclude='embeddings.sqlite' \
    --exclude='knowledge.backups/' \
    --exclude='*.bak.*' \
    --exclude='__pycache__/' \
    --exclude='.DS_Store' \
    --exclude='reports/.private/' \
    --exclude='.private/' \
    --exclude='.staged/' \
    "$MOLTBOOK_HOME/" "$DATA_REPO/"

# Git commit and push
cd "$DATA_REPO"
git add -A

if git diff --cached --quiet; then
    echo "No changes to sync."
    exit 0
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
MOLTBOOK_SYNC=1 git commit -m "sync: $TIMESTAMP"

if git remote get-url origin &>/dev/null; then
    # Refresh the remote-tracking ref first: a stale origin/main makes
    # --force-with-lease reject every push with "stale info" indefinitely.
    git fetch origin || echo "WARNING: fetch failed, lease may be stale" >&2
    git push --force-with-lease || {
        echo "WARNING: push failed, will retry next cycle" >&2
    }
fi

echo "Synced at $TIMESTAMP"

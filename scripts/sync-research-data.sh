#!/bin/bash
set -euo pipefail

MOLTBOOK_HOME="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
DATA_REPO="$HOME/MyAI_Lab/contemplative-agent-data"
# Resolve once, before any cd: $0 may be relative, and the script cds into
# $DATA_REPO before the HF block — a relative dirname breaks there (observed
# 2026-07-12 on a manual relative-path invocation; launchd always passes an
# absolute path, which is why it never surfaced).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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
# NOTE: hand-maintained governance/metadata files live in the data repo, NOT in
# MOLTBOOK_HOME. They MUST be excluded here, otherwise `rsync --delete` removes
# them on every sync. Keep this list in step with the data repo's static files.
#
# `.archive/` (ADR-0097 D5) is a deliberate exclusion, not an oversight. What a
# retirement publishes is not only the retired text — an archived file can carry
# a `superseded_by:` stamp the live store never had, so mirroring it would
# publish the *lineage* of every retirement decision as well. It matches at any
# depth, which is what reaches `skills/.archive/`. `--delete` means an archive
# published before this rule existed is withdrawn on the next sync (none were:
# the exit shipped 2026-08-22, after which no archive had run).
#
# `*.tmp` is load-bearing, not tidiness: every other exclusion matches an exact
# basename, while write_restricted publishes through `<basename>.<random>.tmp`
# (T-WRITE-TMP-NOFOLLOW, 2026-08-15) and an interrupted write leaves one behind
# permanently. Without it an orphan of credentials.json — or of the raw
# 130 MB knowledge.json, whose embeddings the export boundary below strips —
# would be pushed to this PUBLIC repo under a name no other rule covers.
rsync -a --delete \
    --exclude='.git/' \
    --exclude='.gitignore' \
    --exclude='README.md' \
    --exclude='README.ja.md' \
    --exclude='llms.txt' \
    --exclude='LICENSE' \
    --exclude='NOTICE' \
    --exclude='CITATION.cff' \
    --exclude='.zenodo.json' \
    --exclude='graph.jsonld' \
    --exclude='DATACARD.md' \
    --exclude='logs/' \
    --exclude='agents.json' \
    --exclude='credentials.json' \
    --exclude='rate_state.json' \
    --exclude='commented_cache.json' \
    --exclude='embeddings.sqlite' \
    --exclude='knowledge.json' \
    --exclude='knowledge.backups/' \
    --exclude='*.bak.*' \
    --exclude='*.tmp' \
    --exclude='__pycache__/' \
    --exclude='.DS_Store' \
    --exclude='reports/.private/' \
    --exclude='.private/' \
    --exclude='.staged/' \
    --exclude='.archive/' \
    "$MOLTBOOK_HOME/" "$DATA_REPO/"

# knowledge.json is excluded from the rsync above and regenerated here
# embedding-free (--format json): the 768-dim vectors are model-locked,
# re-derivable from pattern text, and ~97% of the raw file's weight — the
# raw copy had crossed GitHub's 50 MB warning on its way to the 100 MB
# hard reject. Runs before git add; set -e makes a filter failure abort
# the sync rather than commit a stale or half-written copy.
MOLTBOOK_HOME="$MOLTBOOK_HOME" python3 \
    "$SCRIPT_DIR/export-patterns-jsonl.py" \
    "$DATA_REPO/knowledge.json" --format json

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

# Mirror the knowledge.json patterns to the HF dataset (best-effort).
# Only runs when there were git changes (early-exit above skips it), so the
# HF projection tracks the data repo. A missing hf CLI / login / network must
# not break the data sync, hence every step is guarded. Set MOLTBOOK_HF_DATASET
# to an empty string to disable the upload (e.g. network-isolated runs).
HF_DATASET="${MOLTBOOK_HF_DATASET-Shimo4228/contemplative-agent-data}"
HF_BIN="$(command -v hf || echo "$HOME/.local/bin/hf")"
KNOWLEDGE="$MOLTBOOK_HOME/knowledge.json"

if [ -n "$HF_DATASET" ] && [ -x "$HF_BIN" ] && [ -f "$KNOWLEDGE" ]; then
    # mktemp default template: portable across BSD/GNU and lands in TMPDIR,
    # never under MOLTBOOK_HOME (which rsync --delete mirrors to the repo).
    TMP_JSONL="$(mktemp)"
    trap 'rm -f "$TMP_JSONL"' EXIT
    if MOLTBOOK_HOME="$MOLTBOOK_HOME" python3 \
        "$SCRIPT_DIR/export-patterns-jsonl.py" "$TMP_JSONL"; then
        if "$HF_BIN" upload "$HF_DATASET" "$TMP_JSONL" patterns.jsonl \
            --repo-type dataset; then
            echo "HF projection synced to $HF_DATASET"
        else
            echo "WARNING: hf upload failed, will retry next cycle" >&2
        fi
    else
        echo "WARNING: patterns projection failed, skipping HF upload" >&2
    fi
else
    echo "Skipping HF projection (hf / knowledge.json / dataset unavailable)" >&2
fi

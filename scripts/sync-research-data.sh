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
#
# `pattern-embeddings.sqlite*` is a separate rule, not covered by the
# `embeddings.sqlite*` line above: rsync matches these against the basename, and
# ADR-0108 moved the pattern vectors into a file with a different one. Its
# content is the same 768-dim model-locked data the export boundary below
# strips out of knowledge.json, so shipping it would undo that boundary — and
# at ~35 MB rewritten every sync it would do so while bloating a public repo.
#
# The trailing `*` is the load-bearing character, and the one exception to the
# exact-basename discipline above. SQLite runs in the default
# `journal_mode=delete`, so a save in progress leaves
# `pattern-embeddings.sqlite-journal` beside the database — measured at 2 MB
# for 500 rows, so ~35 MB for the live store. This sync takes no `.run.lock`,
# so it can rsync while a scheduled distill is mid-transaction, and an exact
# basename would let exactly the vectors this boundary exists to strip into a
# PUBLIC repo's history, where `--delete` cannot retract them (security
# review, 2026-09-12). `-wal` / `-shm` are covered by the same `*` if the
# journal mode ever changes.
#
# `embeddings.sqlite*` (the episode / post store) carries the trailing `*` for
# exactly that reason too: it is a SQLite file in the same default
# journal_mode=delete, so a write in flight leaves `embeddings.sqlite-journal`,
# which the former exact basename did not cover — the same public-repo leak one
# file over (2026-09-12, found reviewing the pattern sidecar and fixed here on
# the author's call). The two rules do not overlap: rsync anchors a
# slash-free pattern to the whole basename, so `embeddings.sqlite*` does not
# match `pattern-embeddings.sqlite`.
# `knowledge.json.*` and `*.bak*` close a gap the exact-basename rules left
# open (P0-03.1, 2026-10-11). The former `*.bak.*` did not match
# `knowledge.json.bak-dup-cleanup-20260718` — a hand-made copy of the raw
# store, 72 MB with every 768-dim embedding — because fnmatch needs a dot
# after `bak`. Any copy of the raw store, under whatever suffix, carries the
# vectors the export boundary below strips, so the whole `knowledge.json.*`
# family stays home; `*.bak*` covers backups of every other file the same way.
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
    --exclude='relevance_cache.json' \
    --exclude='embeddings.sqlite*' \
    --exclude='pattern-embeddings.sqlite*' \
    --exclude='knowledge.json' \
    --exclude='knowledge.json.*' \
    --exclude='knowledge.backups/' \
    --exclude='*.bak*' \
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

# Home-path gate (RFC-0051). The machine's home path names the OS user, and
# this repo is PUBLIC. The writers record paths relative to MOLTBOOK_HOME
# (core/portable_path.py); this gate is what keeps a writer added later, or a
# file written before the fix, from being committed anyway. It searches what
# `git add -A` below can publish, after the rsync and the export — and on a hit
# names the files, not their content, and stops before `git add`. It rewrites
# nothing: the fix belongs to the writer, and an old file is rewritten by
# scripts/rewrite_home_paths.py. A stopped sync exits nonzero, which _run_sync
# reports only as a warning; scripts/pipeline_watchdog.sh's sync-data row is
# what shows it.
#
# The searched set is git's, not the working tree's (RFC-0053): tracked files
# plus untracked files that are not ignored — exactly what `git add -A` stages.
# An ignored file is never published, and rsync's excludes leave one untouched
# (neither updated nor deleted) where rewrite_home_paths.py cannot reach it
# either, so searching the whole tree stopped every daily sync on one ignored
# file under `reports/.private/` (2026-10-15..17). `-z` keeps names with spaces
# or non-ASCII text intact (no core.quotePath quoting).
if [ "${#HOME}" -le 1 ]; then
    echo "ERROR: HOME is unset or '/'; the home-path gate cannot run, not committing" >&2
    exit 1
fi
publishable_paths() {
    git -C "$DATA_REPO" ls-files -z --cached --others --exclude-standard
}
# Regular files go to grep; a symlink is checked by its target below, since git
# stores the target as the file's content (grep would read what it points at).
# A tracked file gone from the working tree is still listed by --cached but has
# nothing to search — its deletion is what gets published.
regular_files_only() {
    while IFS= read -r -d '' path; do
        if [ -f "$path" ] && [ ! -L "$path" ]; then printf '%s\0' "$path"; fi
    done
}
# -i: macOS file systems are case-insensitive, so /users/<user> names the same
# user, and a writer that lowercases its text (log_anomaly_sweep) carries it.
# xargs keeps a large store under ARG_MAX; grep's exit 1 ("no match") is not an
# error, anything above it is, and the wrapper turns that into a nonzero xargs
# exit. pipefail carries a git failure out of the pipeline the same way.
# shellcheck disable=SC2016  # the inner sh expands its own (inherited) $HOME
LEAKS=$(cd "$DATA_REPO" && publishable_paths | regular_files_only |
    xargs -0 sh -c '[ "$#" -eq 0 ] || grep -liF -e "$HOME" -- "$@" || [ "$?" -eq 1 ]' sh) &&
    GREP_RC=0 || GREP_RC=$?
if [ "$GREP_RC" -ne 0 ]; then
    echo "ERROR: the home-path gate could not search $DATA_REPO (exit $GREP_RC), not committing" >&2
    exit 1
fi
LINK_LEAKS=$(cd "$DATA_REPO" && shopt -s nocasematch && publishable_paths |
    while IFS= read -r -d '' path; do
        if [ -L "$path" ] && [[ "$(readlink "$path")" == *"$HOME"* ]]; then printf '%s\n' "$path"; fi
    done) && LINK_RC=0 || LINK_RC=$?
if [ "$LINK_RC" -ne 0 ]; then
    echo "ERROR: the home-path gate could not list $DATA_REPO's symlinks (exit $LINK_RC), not committing" >&2
    exit 1
fi
if [ -n "$LEAKS$LINK_LEAKS" ]; then
    echo "ERROR: the home path appears in files bound for the public data repo; not committing (RFC-0051):" >&2
    printf '%s\n' "$LEAKS" "$LINK_LEAKS" | sed -e '/^$/d' -e 's/^/  /' >&2
    exit 1
fi

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

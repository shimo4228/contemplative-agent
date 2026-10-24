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

# The disclosure boundary below is rsync's matching rules: resolve an rsync 3.x
# once, or stop (P0-03.3).
# shellcheck disable=SC1091  # lib-rsync.sh is linted on its own
. "$SCRIPT_DIR/lib-rsync.sh"
resolve_rsync_bin || exit 1

# Sync safe files from MOLTBOOK_HOME (exclude dangerous files)
# NOTE: hand-maintained governance/metadata files live in the data repo, NOT in
# MOLTBOOK_HOME. They MUST be excluded here, otherwise `rsync --delete` removes
# them on every sync. Keep this list in step with the data repo's static files.
#
# Two layers decide what is published (P0-03.2 / .3):
#   1. config/sync-excludes.txt + config/sync-excludes-public.txt, read with
#      --exclude-from, name what is never published (secrets, locks, bak,
#      vectors, _gc_trash, ...). The first file is shared with backup-runtime.sh.
#   2. an allowlist of the top-level names that may appear: identity.md and
#      the directories below, then `--exclude='*'`. A new top-level name is NOT
#      published until it is added here; it is reported on stderr so it is not
#      lost silently. Rationale: every earlier leak came through a name nobody
#      had written down.
# The comments below on individual patterns were written when each lived in
# this file; the patterns now live in the two config files, the reasoning stays.
#
# `.archive/` (ADR-0097 D5) is a deliberate exclusion, not an oversight. What a
# retirement publishes is not only the retired text — an archived file can carry
# a `superseded_by:` stamp the live store never had, so mirroring it would
# publish the *lineage* of every retirement decision as well. It matches at any
# depth, which is what reaches `skills/.archive/`. `--exclude` also
# shields a copy already in the data repo from `--delete`, so an exclusion alone
# does not withdraw anything published earlier; the retraction step below does
# (P0-03.4).
#
# `.rejected/` (P1-12.2) holds the text of every candidate a human said no to,
# kept so the audit row's `content_hash` leads somewhere. Whether it is ever
# published is a separate decision (P2-05); until then it stays home, and the
# private runtime backup (backup-runtime.sh) carries it.
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
# PUBLIC repo's history, where nothing can retract them (security
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
# Allowlist of top-level names (see the header). knowledge.json is not here: it
# is regenerated embedding-free below.
PUBLIC_TOP_LEVEL=(identity.md constitution meditation pipeline reports rules skills snapshots views)

# Print (stderr) the top-level names that neither the allowlist nor an exclude
# pattern accounts for. Not an error: the transfer already skips them.
report_unlisted_names() {
    local path name pat known
    while IFS= read -r -d '' path; do
        name="$(basename "$path")"
        known=0
        for pat in "${PUBLIC_TOP_LEVEL[@]}" .git .gitignore README.md README.ja.md llms.txt LICENSE NOTICE \
            CITATION.cff .zenodo.json graph.jsonld DATACARD.md knowledge.json .private; do
            [ "$name" = "$pat" ] && known=1
        done
        if [ "$known" -eq 0 ]; then
            while IFS= read -r pat; do
                pat="${pat%/}"
                # shellcheck disable=SC2254  # the pattern is the point
                case "$name" in $pat) known=1 ;; esac
            done < <(grep -hvE '^[[:space:]]*(#|$)' "$SYNC_EXCLUDES" "$SYNC_EXCLUDES_PUBLIC")
        fi
        if [ "$known" -eq 0 ]; then
            echo "NOTE: not published, not on the allowlist: $name (add it to PUBLIC_TOP_LEVEL in sync-research-data.sh to publish it)" >&2
        fi
    done < <(find "$MOLTBOOK_HOME" -mindepth 1 -maxdepth 1 -print0)
}

SYNC_EXCLUDES="$SCRIPT_DIR/../config/sync-excludes.txt"
SYNC_EXCLUDES_PUBLIC="$SCRIPT_DIR/../config/sync-excludes-public.txt"
for f in "$SYNC_EXCLUDES" "$SYNC_EXCLUDES_PUBLIC"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: exclude list not found at $f" >&2
        exit 1
    fi
done
report_unlisted_names

ALLOW_ARGS=()
for name in "${PUBLIC_TOP_LEVEL[@]}"; do
    case "$name" in
        *.*) ALLOW_ARGS+=("--include=/$name") ;;
        # `/name/` + `/name/**` rather than `/name/***`: same set, and the
        # triple-star form is rsync 3.x only.
        *) ALLOW_ARGS+=("--include=/$name/" "--include=/$name/**") ;;
    esac
done

# Order matters (first match wins): the exclude lists, then the data repo's own
# files, then the allowlist, then everything else. The inline names below are
# receiver-owned (governance, the regenerated knowledge.json) or local-only
# (.private) and are NOT in the config lists, because the retraction step reads
# those lists as "remove if present".
"$RSYNC_BIN" -a --delete \
    --exclude-from="$SCRIPT_DIR/../config/sync-excludes.txt" \
    --exclude-from="$SYNC_EXCLUDES_PUBLIC" \
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
    --exclude='knowledge.json' \
    --exclude='reports/.private/' \
    --exclude='.rejected/' \
    --exclude='.private/' \
    "${ALLOW_ARGS[@]}" \
    --exclude='*' \
    "$MOLTBOOK_HOME/" "$DATA_REPO/"

# Retraction (P0-03.4). `--exclude` shields a destination copy from `--delete`,
# so a file excluded after it was published (or seeded by hand) would stay in
# the tree and keep being committed. Remove the "do not publish" class from the
# data repo here; `git add -A` below then stages the deletion. Only the names in
# the two config lists: the governance files and knowledge.json are excluded
# above to protect them from `--delete` and must never be removed here, and
# `.git/` and `.private/` are never entered. History still holds earlier
# copies; this only stops them being re-published.
retract_withheld() {
    local pat path
    while IFS= read -r pat; do
        if [ "${pat%/}" != "$pat" ]; then
            pat="${pat%/}"
            while IFS= read -r -d '' path; do rm -rf -- "$path"; done < <(
                find "$DATA_REPO" \( -name .git -o -name .private \) -prune -o -type d -name "$pat" -print0)
        else
            while IFS= read -r -d '' path; do rm -f -- "$path"; done < <(
                find "$DATA_REPO" \( -name .git -o -name .private \) -prune -o ! -type d -name "$pat" -print0)
        fi
    done < <(grep -hvE '^[[:space:]]*(#|$)' "$SYNC_EXCLUDES" "$SYNC_EXCLUDES_PUBLIC")
}
retract_withheld

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
# passes on (rc=1, P2-04.2); scripts/pipeline_watchdog.sh's sync-data row is
# the independent check.
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
PUSH_FAILED=0
cd "$DATA_REPO"
git add -A

if git diff --cached --quiet; then
    echo "No changes to sync."
    exit 0
fi

# Secret scan (P0-03.6). After `git add -A`, before the commit: search the index
# for secret VALUE shapes (config/secret-patterns.txt, one ERE per line, no
# comments — every line is a pattern). The same file is read by the data repo's
# gitleaks workflow, weekly-gate Step 6d and the harness hook. It names files
# and never prints a matching line. The words `api_key` / `Bearer ` are
# deliberately not patterns: other agents' text contains them, and one match
# would stop the daily sync. A hit unstages everything and stops, nonzero, so
# the watchdog shows it; git grep exits 1 for "no match", anything above is a
# failed scan, which also stops (fail closed).
SECRET_PATTERNS="$SCRIPT_DIR/../config/secret-patterns.txt"
if [ ! -f "$SECRET_PATTERNS" ]; then
    git reset -q
    echo "ERROR: secret pattern list not found at $SECRET_PATTERNS, not committing" >&2
    exit 1
fi
SECRET_HITS=$(git grep --cached -I -l -E -f "$SECRET_PATTERNS") && SECRET_RC=0 || SECRET_RC=$?
if [ "$SECRET_RC" -gt 1 ]; then
    git reset -q
    echo "ERROR: the secret scan could not search the index (exit $SECRET_RC), not committing" >&2
    exit 1
fi
if [ -n "$SECRET_HITS" ]; then
    git reset -q
    echo "ERROR: a secret-shaped value appears in files bound for the public data repo; not committing (P0-03.6):" >&2
    printf '%s\n' "$SECRET_HITS" | sed 's/^/  /' >&2
    exit 1
fi

# Divergence check BEFORE the commit (P0-03.16). This job is unattended and the
# repo is PUBLIC: the former fetch followed by a lease-guarded push made the
# lease always match, so it was a plain overwriting push that silently dropped
# any commit made on the remote. Now, if origin has a commit this checkout
# lacks, stop with ERROR and a nonzero exit WITHOUT committing, so that the
# watchdog's sync-data row (which looks for today's `sync:` commit) turns red
# instead of showing a healthy day while the public repo goes stale. The data
# repo is changed only from this checkout, with the job unloaded.
if git remote get-url origin &>/dev/null; then
    if ! git fetch origin; then
        git reset -q
        echo "ERROR: fetch from origin failed; not committing" >&2
        exit 1
    fi
    BRANCH="$(git rev-parse --abbrev-ref HEAD)"
    if git rev-parse --verify -q "origin/$BRANCH" >/dev/null &&
        ! git merge-base --is-ancestor "origin/$BRANCH" HEAD; then
        git reset -q
        echo "ERROR: origin/$BRANCH has commits this checkout does not; refusing to overwrite them, not committing. Reconcile by hand, then re-run." >&2
        exit 1
    fi
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Second line of the message: counts and the framework version, so
# `git log --format=%b` is a time series (P0-06.4). Best-effort — a failed
# summary must not stop the sync, so the commit then carries the rsync line only.
SUMMARY=$(python3 "$SCRIPT_DIR/sync-commit-summary.py" "$DATA_REPO" "$SCRIPT_DIR/../pyproject.toml") || {
    echo "WARNING: sync commit summary failed; committing with the rsync line only" >&2
    SUMMARY=""
}
if [ -n "$SUMMARY" ]; then
    MOLTBOOK_SYNC=1 git commit -m "sync: $TIMESTAMP" -m "$SUMMARY" -m "rsync: ${RSYNC_VERSION_LINE:-unknown}"
else
    MOLTBOOK_SYNC=1 git commit -m "sync: $TIMESTAMP" -m "rsync: ${RSYNC_VERSION_LINE:-unknown}"
fi

# Push without force (P0-03.16); the divergence check ran before the commit.
if git remote get-url origin &>/dev/null; then
    # A failed push is loud (P2-04.2, same policy as backup-runtime.sh): the
    # ERROR line lands in the launchd log (Log Anomaly Sweep) and the script
    # exits 1 at the end. The HF mirror below still runs first -- it is
    # independent of the git remote.
    if ! git push; then
        echo "ERROR: push failed; the public data repo is stale (next cycle retries)" >&2
        PUSH_FAILED=1
    fi
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

if [ "$PUSH_FAILED" -ne 0 ]; then
    exit 1
fi

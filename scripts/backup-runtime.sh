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

# Bound the agent's launchd log (T-LOG-DEBUG-CONTENT).
#
# Unlike ollama-serve.log this one is NOT excluded from the mirror below: it is
# the agent's own stderr — session reports, rate-limit decisions, the WARNING
# that catches a silently-dead gate — so it is research-adjacent and belongs in
# the restore set. Rotating bounds it instead; gzip makes eight generations
# cheap.
#
# Here rather than in the agent job because launchd opens StandardOutPath
# before exec: a job that renamed its own log would leave launchd writing into
# the renamed inode. This script is the natural owner anyway — keeping the
# mirror pushable is the same concern that made ollama-serve.log an exclusion.
#
# Placed ABOVE the backup-repo checks on purpose (cross-model review
# 2026-08-01): rotation needs nothing but MOLTBOOK_HOME, and every check below
# can `exit 1`. Downstream of them, a missing backup checkout or a remote gone
# public would stop rotating too — leaving the log to grow unbounded for as
# long as the misconfiguration lasts, which is exactly when nobody is watching
# it. The mirror simply picks up the rotated generation on the next run.
#
# Weekly is enough now that `-v` is gone from the plist (the DEBUG stream was
# the bulk of the growth). `|| echo` because `set -e` is on and a failed
# rotation must not stop the backup: an unbounded log costs disk, a missing
# off-site copy costs the episode logs this script exists to protect.
# rotate-log.sh refuses while a session still holds the file open, so a run
# landing inside a session window skips loudly instead of truncating.
"$SCRIPT_DIR/rotate-log.sh" "$MOLTBOOK_HOME/logs/agent-launchd.log" 8 \
    || echo "ERROR: agent-launchd log rotation failed; continuing with backup" >&2

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
#   logs/ollama-serve.log        — the local Ollama daemon's own stderr, plus
#   logs/ollama-serve.log.N.gz     its rotated generations. Re-derivable
#                                  operational noise from an external process,
#                                  not research data — and at 96 MB on
#                                  2026-08-01 it was one weekly run away from
#                                  failing the push and stalling the off-site
#                                  copy of the episode logs this backup exists
#                                  to protect (T-LOGROT-OLLAMA). Rotation keeps
#                                  the local copies bounded; nothing about them
#                                  is irreplaceable. The two patterns are
#                                  deliberate: leading `/` anchors them to the
#                                  transfer root (unlike the unanchored
#                                  basenames above), and matching the exact name
#                                  plus numeric generations keeps a future
#                                  ollama-serve.logger.jsonl from being swept
#                                  out by a wider `.log*` glob.
# Everything else — logs/, reports/ (including .private/), snapshots/,
# skills/, views/, agents.json — is state and goes in: a restore should need
# nothing but this repo, a re-issued credential, and one re-embed run.
# `*.tmp` is the exception that is not state: write_restricted publishes
# through `<basename>.<random>.tmp` (T-WRITE-TMP-NOFOLLOW, 2026-08-15), so an
# interrupted write leaves an orphan whose name matches none of the exact
# basenames above — including the credentials.json and knowledge.json rules
# this list depends on.
rsync -a --delete \
    --exclude='.git/' \
    --exclude='README.md' \
    --exclude='.gitignore' \
    --exclude='credentials.json' \
    --exclude='knowledge.json' \
    --exclude='/logs/ollama-serve.log' \
    --exclude='/logs/ollama-serve.log.[0-9]*.gz' \
    --exclude='.run.lock' \
    --exclude='.staged.lock' \
    --exclude='*.tmp' \
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

# Same trap, and this one is not hypothetical: logs/ollama-serve.log was
# mirrored until 2026-08-01, so the excluded-but-present copy would sit in the
# worktree forever and keep being pushed. The glob also collects rotated
# generations. Deleting here only drops them from the mirror going forward —
# history still holds the old blobs, which is fine: GitHub's limit applies to
# newly pushed objects.
rm -f logs/ollama-serve.log logs/ollama-serve.log.[0-9]*.gz

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

#!/bin/bash
# Restore-drill check (P2-04.19): is the private backup mirror a faithful copy?
#
# READ-ONLY. It clones the backup repo into a temp dir, runs `git fsck`, and
# compares the mirror with the live MOLTBOOK_HOME. It restores nothing and
# writes nothing outside that temp dir; the restore itself stays a human step
# (docs/runbooks/runtime-backup-restore.md). Exit 0 = every check passed,
# exit 1 = at least one ERROR line, exit 2 = bad usage / inputs.
#
# Checks:
#   1. fresh clone + `git fsck --full` is clean
#   2. logs/episodes/: file count and total bytes equal the live files that
#      are not newer than the backup's last commit (files written after the
#      last backup are expected to differ and are excluded)
#   3. knowledge.json parses and its row count equals the live one
# Not checked here (needs the restore, step 5 of the runbook): that
# `missing_embedding` is 0 after re-embedding, and that no mixed-weights
# embeddings exist. The runbook lists them as manual criteria.
#
# Reader (ADR-0101): the owner, at the drill cadence the runbook sets. Removal:
# if the backup mirror is retired or the drill stops being run.
#
# Usage:
#   scripts/restore-drill-check.sh [--repo PATH_OR_URL] [--live DIR]
#     --repo  backup repo to clone (default $MOLTBOOK_BACKUP_REPO or
#             ~/MyAI_Lab/contemplative-agent-runtime-backup)
#     --live  live home to compare against (default $MOLTBOOK_HOME or
#             ~/.config/moltbook)
set -uo pipefail

REPO="${MOLTBOOK_BACKUP_REPO:-$HOME/MyAI_Lab/contemplative-agent-runtime-backup}"
LIVE="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo) REPO="$2"; shift 2 ;;
        --live) LIVE="$2"; shift 2 ;;
        -h|--help) sed -n 2,28p "$0"; exit 0 ;;
        *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ -d "$LIVE" ]] || { echo "ERROR: live home not found: $LIVE" >&2; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILED=0
fail() { echo "ERROR: $*" >&2; FAILED=1; }
ok()   { echo "ok: $*"; }

if ! git clone -q "$REPO" "$TMP/clone" 2>"$TMP/clone.err"; then
    echo "ERROR: could not clone $REPO: $(head -n 1 "$TMP/clone.err")" >&2
    exit 1
fi
CLONE="$TMP/clone"

# 1. fsck
if git -C "$CLONE" fsck --full >"$TMP/fsck.out" 2>&1 && ! grep -qiE '^(error|fatal)' "$TMP/fsck.out"; then
    ok "git fsck clean"
else
    fail "git fsck reported problems: $(head -n 3 "$TMP/fsck.out" | tr '\n' ' ')"
fi

# Last backup commit time, and a reference file at that time for `find -newer`.
LAST_COMMIT=$(git -C "$CLONE" log -1 --format=%ct 2>/dev/null || echo 0)
echo "last backup commit: $(date -r "$LAST_COMMIT" '+%Y-%m-%d %H:%M' 2>/dev/null || date -d "@$LAST_COMMIT" '+%Y-%m-%d %H:%M')"
STAMP=$(date -r "$LAST_COMMIT" +%Y%m%d%H%M.%S 2>/dev/null || date -d "@$LAST_COMMIT" +%Y%m%d%H%M.%S)
touch -t "$STAMP" "$TMP/ref"

# 2. episodes: count + bytes
sum_dir() {  # sum_dir <dir> [find-args...] -> "<count> <bytes>"
    local dir="$1"; shift
    [[ -d "$dir" ]] || { echo "0 0"; return; }
    find "$dir" -type f "$@" -exec wc -c {} + 2>/dev/null \
        | awk '$2 != "total" { n++; b += $1 } END { print n + 0, b + 0 }'
}
read -r live_n live_b <<< "$(sum_dir "$LIVE/logs/episodes" ! -newer "$TMP/ref")"
read -r mir_n mir_b <<< "$(sum_dir "$CLONE/logs/episodes")"
if [[ "$live_n" == "$mir_n" && "$live_b" == "$mir_b" ]]; then
    ok "logs/episodes: $mir_n files, $mir_b bytes (live files not newer than the last backup)"
else
    fail "logs/episodes differ: live(not newer than backup) $live_n files / $live_b bytes, mirror $mir_n files / $mir_b bytes"
fi

# 3. knowledge.json: parses, same row count
rows() {  # rows <file> -> number, or "unreadable"
    python3 - "$1" <<'PY' 2>/dev/null || echo unreadable
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
if isinstance(data, dict):
    data = data.get("patterns", data.get("entries", data))
print(len(data))
PY
}
if [[ -f "$LIVE/knowledge.json" && -f "$CLONE/knowledge.json" ]]; then
    live_rows=$(rows "$LIVE/knowledge.json"); mir_rows=$(rows "$CLONE/knowledge.json")
    if [[ "$mir_rows" == unreadable ]]; then
        fail "mirror knowledge.json does not parse"
    elif [[ "$live_rows" != "$mir_rows" ]]; then
        fail "knowledge.json rows differ: live $live_rows, mirror $mir_rows (distill since the last backup can explain a small gap; re-run right after a backup)"
    else
        ok "knowledge.json parses, $mir_rows rows in both"
    fi
else
    fail "knowledge.json missing on one side (live: $([[ -f "$LIVE/knowledge.json" ]] && echo yes || echo no), mirror: $([[ -f "$CLONE/knowledge.json" ]] && echo yes || echo no))"
fi

if [[ "$FAILED" -ne 0 ]]; then
    echo "restore-drill-check: FAILED" >&2
    exit 1
fi
echo "restore-drill-check: all checks passed"

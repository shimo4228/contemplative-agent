#!/bin/bash
# Host check (P2-04.23): is this machine fit to run the unattended chain?
#
# READ-ONLY: prints one screen of facts and exits 1 when a requirement is not
# met. Run it after an OS / Homebrew / Ollama / Python update, at the end of a
# machine rebuild (docs/runbooks/machine-rebuild.md) and with each restore drill.
# Reader (ADR-0101): the owner, on those occasions. Removal: when the machine
# rebuild runbook is retired.
#
# Checks (rc=1 on any FAIL):
#   - PATH tools: git, python3, rsync, claude, hf, gh present (version printed);
#     a hang detector: timeout, gtimeout or $TIMEOUT_BIN
#   - .venv/bin/python starts
#   - embedding model digest equals --manifest-digest when that is given
#     (the latest public snapshot manifest's embedding_model_digest; the
#     manifest read itself is P1-07.12, so without the flag this prints SKIP)
#   - the number of loaded com.moltbook launchd jobs equals --expect-jobs when
#     given (the declaration of P2-04.22), else is just printed
# Ollama / model / home checks belong to `contemplative-agent doctor` (P0-05.1),
# which does not exist yet: this script prints SKIP for them rather than
# re-implementing them.
#
# Usage: scripts/host_check.sh [--manifest-digest SHA] [--expect-jobs N]
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_DIGEST=""
EXPECT_JOBS=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --manifest-digest) MANIFEST_DIGEST="$2"; shift 2 ;;
        --expect-jobs) EXPECT_JOBS="$2"; shift 2 ;;
        -h|--help) sed -n 2,23p "$0"; exit 0 ;;
        *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
    esac
done

RC=0
row()  { printf '%-14s %-5s %s\n' "$1" "$2" "$3"; }
good() { row "$1" ok "$2"; }
bad()  { row "$1" FAIL "$2"; RC=1; }

if command -v sw_vers >/dev/null 2>&1; then
    good "macOS" "$(sw_vers -productVersion) ($(sw_vers -buildVersion))"
else
    row "macOS" SKIP "sw_vers not found (not macOS)"
fi
if command -v xcode-select >/dev/null 2>&1; then
    if path=$(xcode-select -p 2>/dev/null); then good "xcode-select" "$path"; else bad "xcode-select" "no developer tools path"; fi
fi

for tool in git python3 rsync claude hf gh; do
    if p=$(command -v "$tool"); then
        v=$("$tool" --version 2>&1 | head -n 1)
        good "$tool" "$p — ${v:-version unreadable}"
    else
        bad "$tool" "not on PATH ($PATH)"
    fi
done

timeout_bin=""
for cand in timeout gtimeout; do
    if p=$(command -v "$cand"); then timeout_bin="$p"; break; fi
done
[[ -z "$timeout_bin" && -n "${TIMEOUT_BIN:-}" && -x "$TIMEOUT_BIN" ]] && timeout_bin="$TIMEOUT_BIN"
if [[ -n "$timeout_bin" ]]; then good "timeout" "$timeout_bin"; else bad "timeout" "none of timeout / gtimeout / \$TIMEOUT_BIN (brew install coreutils); the chain would run with NO_TIMEOUT_BIN"; fi

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]] && v=$("$PROJECT_ROOT/.venv/bin/python" -V 2>&1); then
    good "venv python" "$v"
else
    bad "venv python" "$PROJECT_ROOT/.venv/bin/python does not start (uv sync)"
fi

if [[ -n "$MANIFEST_DIGEST" ]]; then
    have=""
    if command -v ollama >/dev/null 2>&1; then
        have=$(ollama list 2>/dev/null | awk '$1 ~ /^nomic-embed-text/ { print $2; exit }')
    fi
    if [[ -z "$have" ]]; then
        bad "embed digest" "nomic-embed-text not listed by ollama"
    elif [[ "$MANIFEST_DIGEST" == "$have"* || "$have" == "$MANIFEST_DIGEST"* ]]; then
        good "embed digest" "$have matches the manifest"
    else
        bad "embed digest" "ollama has $have, manifest says $MANIFEST_DIGEST — stop and follow the model-swap runbook"
    fi
else
    row "embed digest" SKIP "no --manifest-digest (comparison is P1-07.12)"
fi

if command -v launchctl >/dev/null 2>&1; then
    jobs=$(launchctl list 2>/dev/null | grep -c 'com\.moltbook' || true)
    if [[ -z "$EXPECT_JOBS" ]]; then
        row "launchd jobs" info "$jobs com.moltbook jobs loaded (no --expect-jobs)"
    elif [[ "$jobs" == "$EXPECT_JOBS" ]]; then
        good "launchd jobs" "$jobs loaded, as declared"
    else
        bad "launchd jobs" "$jobs loaded, declaration says $EXPECT_JOBS"
    fi
else
    row "launchd jobs" SKIP "launchctl not found"
fi

row "doctor" SKIP "contemplative-agent doctor (P0-05.1) not available yet: Ollama / model / home checks pending"

if [[ "$RC" -ne 0 ]]; then
    echo "host_check: FAILED" >&2
fi
exit "$RC"

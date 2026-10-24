# shellcheck shell=bash
# Sourced by sync-research-data.sh and backup-runtime.sh (P0-03.3).
#
# The public-repo disclosure boundary is rsync's exclude/include matching, so
# the implementation has to be one we have tested: rsync 3.x. macOS 15 and
# later ship openrsync as /usr/bin/rsync, which is a different matcher; this
# resolves once and prefers a 3.x. With none it falls back to the rsync on PATH
# with one WARNING line (not a stop: a missing Homebrew rsync must not halt the
# daily sync or the weekly backup); with no rsync at all it stops with ERROR.
#
# Sets RSYNC_BIN and RSYNC_VERSION_LINE. An RSYNC_BIN already in the environment
# is used as given (the macOS test run points it at each build in turn), but it
# must exist.
resolve_rsync_bin() {
    local first cand
    if [ -n "${RSYNC_BIN:-}" ]; then
        if [ ! -x "$RSYNC_BIN" ]; then
            echo "ERROR: RSYNC_BIN=$RSYNC_BIN is not executable" >&2
            return 1
        fi
        RSYNC_VERSION_LINE="$("$RSYNC_BIN" --version 2>/dev/null | head -1 || true)"
        return 0
    fi
    for cand in /opt/homebrew/bin/rsync /usr/local/bin/rsync "$(command -v rsync || true)"; do
        [ -n "$cand" ] && [ -x "$cand" ] || continue
        first="$("$cand" --version 2>/dev/null | head -1 || true)"
        case "$first" in
            *openrsync*) continue ;;
        esac
        if printf '%s\n' "$first" | grep -Eq 'version ([3-9]|[1-9][0-9])\.'; then
            RSYNC_BIN="$cand"
            RSYNC_VERSION_LINE="$first"
            return 0
        fi
    done
    # No rsync 3.x: fall back to whatever rsync exists (macOS openrsync), loudly.
    # Stopping would halt the daily sync and the weekly backup on a machine
    # where Homebrew rsync was never installed. The rules the scripts pass are
    # limited to flags openrsync supports; what is lost is only that the
    # matching rules were verified against rsync 3.x, not this build.
    cand="$(command -v rsync || true)"
    if [ -n "$cand" ] && [ -x "$cand" ]; then
        RSYNC_BIN="$cand"
        RSYNC_VERSION_LINE="$("$cand" --version 2>/dev/null | head -1 || true)"
        echo "WARNING: no rsync 3.x found; using $RSYNC_BIN (${RSYNC_VERSION_LINE:-unknown version}). The disclosure boundary's matching rules are tested against rsync 3.x only; install it with: brew install rsync" >&2
        return 0
    fi
    echo "ERROR: no rsync found" >&2
    return 1
}

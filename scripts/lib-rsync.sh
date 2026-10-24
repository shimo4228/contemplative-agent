# Sourced by sync-research-data.sh and backup-runtime.sh (P0-03.3).
#
# The public-repo disclosure boundary is rsync's exclude/include matching, so
# the implementation has to be one we have tested: rsync 3.x. macOS 15 and
# later ship openrsync as /usr/bin/rsync, which is a different matcher; this
# resolves once, skips it, and stops with ERROR rather than quietly falling
# back to it.
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
    echo "ERROR: no rsync 3.x found (macOS /usr/bin/rsync is openrsync, which this boundary does not rely on); install it with: brew install rsync" >&2
    return 1
}

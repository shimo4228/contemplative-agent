#!/usr/bin/env bash
# Rotate an append-only log into N compressed generations.
#
#   rotate-log.sh <path> <keep-N>
#
# Two callers, with opposite premises about the writer:
#
#   com.moltbook.ollama-restart calls it on `ollama-serve.log` between its
#   `pkill` and the `ollama serve` restart. The writer is already dead there,
#   so the `mv` is safe and the shell's `>>` recreates the live file a moment
#   later. That job owns the log's lifecycle, which is why rotation lives
#   inside it rather than in a newsyslog rule (root-owned, outside the repo) or
#   a second launchd job (no ordering guarantee against the restart).
#
#   backup-runtime.sh (com.moltbook.backup, weekly) calls it on
#   `agent-launchd.log`, whose writer is a live agent session nobody killed.
#   Nothing sequences the two, so the open-writer check below is the whole of
#   the safety there: a run landing inside a session window must skip loudly.
#   That is the caller the open-writer check below exists for.
#
# Rotate, never truncate: the previous night's evidence survives a crash
# investigation. gzip makes that cheap — the real ollama-serve.log compresses
# 10.8x, so seven generations cost less than one uncompressed day.
#
# The contents are never inspected: this script only moves and compresses whole
# files, and never greps, parses, or branches on what is inside one. That
# matters because a daemon log can pick up content the caller does not control,
# and a rotation mechanism must not become a read path into it.
#
# Failures are loud but non-blocking by design, in both callers: ollama-restart
# chains this with `;`, backup-runtime.sh with `|| echo`. A failed rotation can
# never stop the daemon from starting or the off-site copy from running — a
# missing rotation costs disk, a missing daemon costs the whole agent and a
# missing backup costs the episode logs. The `ERROR:` prefix is what makes the
# failure visible: each job's stderr lands in its own log under the logs dir,
# which the weekly anomaly sweep reads.
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "ERROR: usage: rotate-log.sh <path> <keep-N>" >&2
    exit 2
fi

LOG_PATH=$1
KEEP=$2

# No default for a bad count: a typo'd plist argument must fail loudly rather
# than quietly rotate to zero generations.
if ! [[ "$KEEP" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: rotate-log.sh: keep-N must be a positive integer, got '$KEEP'" >&2
    exit 2
fi

# gzip follows symlinks: it would compress the target's bytes into a .gz beside
# the link and unlink only the link. Nothing here creates a symlink at this
# path, so its presence means something unexpected — stop rather than copy an
# unknown file into the archive.
if [ -L "$LOG_PATH" ]; then
    echo "ERROR: rotate-log.sh: $LOG_PATH is a symlink — not rotating" >&2
    exit 1
fi

# Missing or empty: a restart that produced no output must not burn a
# generation slot on 0 bytes and push real evidence off the end.
if [ ! -s "$LOG_PATH" ]; then
    exit 0
fi

# One caller kills the writer first; the other runs while a session may still
# hold the file open. Either way a process that outlives (or never received)
# the kill would keep writing into the renamed inode while gzip reads it —
# truncating the very evidence rotation exists to keep, into a file no path
# points at any more. Skipping loudly beats corrupting silently.
#
# The retry on an absolute path is not belt-and-braces: com.moltbook.backup
# pins a PATH without /usr/sbin, which is where macOS ships lsof, so a
# `command -v` miss was the normal case for that job rather than a sign the
# host lacks the tool. The literal is hardcoded rather than read from the
# environment — this script runs unattended, and an env-supplied probe path
# would be a knob the job's caller could steer.
LSOF_FALLBACK=/usr/sbin/lsof

if command -v lsof >/dev/null 2>&1; then
    LSOF=lsof
elif [ -x "$LSOF_FALLBACK" ]; then
    LSOF=$LSOF_FALLBACK
else
    LSOF=
fi

if [ -n "$LSOF" ]; then
    if "$LSOF" -t -- "$LOG_PATH" >/dev/null 2>&1; then
        echo "ERROR: rotate-log.sh: $LOG_PATH is still open by another process — not rotating" >&2
        exit 1
    fi
else
    echo "WARNING: rotate-log.sh: lsof not found — rotating without the open-writer check" >&2
fi

# A run whose gzip step failed leaves an uncompressed .1 behind, outside the
# .gz chain the shift loop walks. Fold it in before shifting: the `mv -f` at the
# bottom would otherwise overwrite it with tonight's log and lose that night for
# good — the exact "rotate, never truncate" promise this script makes.
if [ -e "$LOG_PATH.1" ]; then
    # Both present means something outside this script put them there: gzip -f
    # would overwrite the .gz and lose a generation, which is the failure this
    # whole branch exists to prevent. Stop and let a human look.
    if [ -e "$LOG_PATH.1.gz" ]; then
        echo "ERROR: rotate-log.sh: both $LOG_PATH.1 and $LOG_PATH.1.gz exist — not rotating" >&2
        exit 1
    fi
    gzip "$LOG_PATH.1"
fi

rm -f "$LOG_PATH.$KEEP.gz"

for (( gen = KEEP - 1; gen >= 1; gen-- )); do
    if [ -f "$LOG_PATH.$gen.gz" ]; then
        mv -f "$LOG_PATH.$gen.gz" "$LOG_PATH.$((gen + 1)).gz"
    fi
done

mv -f "$LOG_PATH" "$LOG_PATH.1"
gzip -f "$LOG_PATH.1"

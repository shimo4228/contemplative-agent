#!/usr/bin/env bash
# shellcheck disable=SC2154  # ipd_version, bench_commit, ... are set by the sourced _ipd_common.sh
# One IPD run per text, same calibration contract as ipd-two-arm.sh (P3-03.3 / .4).
#
# For the retro-measurement of constitution versions ("4 versions x IPD") and the
# placebo-constitution arms: each text is run ONCE (not once per pair, so a text
# shared by several comparisons is not run twice); the pairs that are read come
# from the pre-registration, and scripts/ipd_series_table.py reads them with the
# cell-wise SE rule (ADR-0090 Amendment 2026-10-24).
#
# Usage:
#   scripts/ipd-series.sh MANIFEST.tsv OUTDIR
#     MANIFEST.tsv: label <TAB> path <TAB> note   (# lines and blank lines ignored;
#     a path may start with $REPO_ROOT/ or $DATA_REPO/, expanded here)
# Env: as ipd-two-arm.sh (BENCH_DIR, OLLAMA_MODEL, N_SIMS, SKIP_WINDOW_GUARD).
#   DATA_REPO  checkout of contemplative-agent-data (default ../contemplative-agent-data)
# Resumable: a label whose OUTDIR/<label>.json exists is skipped. One run at a
# time, never beside another model (16 GB).
set -euo pipefail

[ $# -eq 2 ] || { echo "usage: $0 MANIFEST.tsv OUTDIR" >&2; exit 2; }
MANIFEST="$1"; OUTDIR="$2"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_REPO="${DATA_REPO:-$REPO_ROOT/../contemplative-agent-data}"
BENCH_DIR="${BENCH_DIR:-$REPO_ROOT/../contemplative-agent-rules/benchmarks/prisoners-dilemma}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b}"
N_SIMS="${N_SIMS:-10}"
IPD_BIN="$BENCH_DIR/.venv/bin/ipd-benchmark"

# shellcheck disable=SC1091  # _ipd_common.sh is linted on its own
. "$(dirname "$0")/_ipd_common.sh"

[ -f "$MANIFEST" ] || { echo "ERROR: manifest not found: $MANIFEST" >&2; exit 1; }
[ -x "$IPD_BIN" ] || { echo "ERROR: ipd-benchmark not found at $IPD_BIN" >&2; exit 1; }

# Resolve and verify every text before the first (hour-long) run starts.
labels=(); paths=()
while IFS=$'\t' read -r label path _note || [ -n "$label" ]; do
    case "$label" in ''|'#'*) continue ;; esac
    path="${path/#\$REPO_ROOT/$REPO_ROOT}"; path="${path/#\$DATA_REPO/$DATA_REPO}"
    [ -f "$path" ] || { echo "ERROR: text for '$label' not found: $path" >&2; exit 1; }
    case " ${labels[*]-} " in *" $label "*) echo "ERROR: duplicate label '$label'" >&2; exit 1 ;; esac
    labels+=("$label"); paths+=("$path")
done < "$MANIFEST"
[ "${#labels[@]}" -ge 1 ] || { echo "ERROR: manifest has no rows" >&2; exit 1; }

mkdir -p "$OUTDIR"
ipd_identity
{
    echo "started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "model: $OLLAMA_MODEL  n=$N_SIMS  weights digest: $model_digest"
    echo "bench: contemplative-ipd $ipd_version"
    echo "bench commit: $bench_commit"
    echo "ollama: $ollama_version"
    for i in "${!labels[@]}"; do
        echo "text ${labels[$i]}: $(basename "${paths[$i]}") sha256=$(sha256_of "${paths[$i]}")"
    done
} | tee "$OUTDIR/provenance.txt"

for i in "${!labels[@]}"; do
    out="$OUTDIR/${labels[$i]}.json"
    [ -f "$out" ] && { echo "[${labels[$i]}] exists, skipping"; continue; }
    wait_for_clear_window
    echo "[${labels[$i]}] start $(date '+%H:%M:%S %Z')"
    "$IPD_BIN" --protocol paper --prompt-file "${paths[$i]}" -n "$N_SIMS" -o "$out" \
        2>&1 | tee "$OUTDIR/${labels[$i]}.log"
    echo "[${labels[$i]}] done $(date '+%H:%M:%S %Z')"
done

python3 "$REPO_ROOT/scripts/ipd_series_table.py" "$MANIFEST" "$OUTDIR" | tee "$OUTDIR/table.md"

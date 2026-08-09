#!/usr/bin/env bash
# T-CONST-IPD (b): IPD two-arm bench for constitution amendments.
#
# Runs contemplative-ipd (paper protocol, Appendix E) twice — arm A with the
# current production constitution, arm B with the staged amendment — and emits
# a comparison report to attach to the human approval decision.
#
# Sits BETWEEN `amend-constitution --stage` and `adopt-staged`. Deliberately
# NOT wired into either CLI command: an approval-gated command must not embed
# a ~2h LLM step plus a cross-repo dependency (same instrument→human-judgment
# shape as weekly-gate).
#
# Interpretation contract (from the 2026-08-06 null pair,
# .notes/ipd-null-pair-2026-08-06/README.md): |Δ(custom−baseline)| < 0.13 is
# indistinguishable from run-to-run noise at n=10. Read only sign flips,
# α-gradient loss, or same-direction >0.13 moves across multiple cells.
#
# Usage:
#   scripts/ipd-two-arm.sh [OUTDIR]
# Env:
#   MOLTBOOK_HOME   data dir (default ~/.config/moltbook)
#   BENCH_DIR       prisoners-dilemma checkout (default sibling rules repo)
#   OLLAMA_MODEL    generation model (default gemma4:e4b, ADR-0069)
#   N_SIMS          simulations per cell (default 10 = null-pair calibration;
#                   changing it invalidates the ±0.13 noise floor)
#   SKIP_WINDOW_GUARD=1  disable the JST 0/6/12/18 schedule-session guard
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOLTBOOK_HOME="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
BENCH_DIR="${BENCH_DIR:-$REPO_ROOT/../contemplative-agent-rules/benchmarks/prisoners-dilemma}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b}"
N_SIMS="${N_SIMS:-10}"

CURRENT_CONST="$MOLTBOOK_HOME/constitution/contemplative-axioms.md"
STAGED_DIR="$MOLTBOOK_HOME/.staged"
OUTDIR="${1:-$REPO_ROOT/.notes/ipd-amend-$(date +%Y-%m-%d)}"

IPD_BIN="$BENCH_DIR/.venv/bin/ipd-benchmark"

# JST 0/6/12/18 are unattended production sessions (16 GB — concurrent heavy
# Ollama runs have caused Metal OOM). One arm runs ~51–68 min, so refuse to
# start an arm that would overlap a session, and wait out the session itself.
RUN_EST_MIN=75      # worst observed arm duration + margin
RESUME_OFFSET_MIN=60 # assume a schedule session is over this long after start

wait_for_clear_window() {
    [ "${SKIP_WINDOW_GUARD:-0}" = "1" ] && return 0
    while :; do
        local h m mins since_prev until_next
        h=$(TZ=Asia/Tokyo date +%H); m=$(TZ=Asia/Tokyo date +%M)
        mins=$((10#$h * 60 + 10#$m))
        since_prev=$((mins % 360))
        until_next=$((360 - since_prev))
        if ((since_prev < RESUME_OFFSET_MIN)); then
            echo "[guard] inside JST schedule window — waiting $((RESUME_OFFSET_MIN - since_prev)) min"
            sleep $(((RESUME_OFFSET_MIN - since_prev) * 60))
            continue
        fi
        if ((until_next < RUN_EST_MIN)); then
            echo "[guard] next JST schedule window in ${until_next} min < ${RUN_EST_MIN} min run estimate — waiting $((until_next + RESUME_OFFSET_MIN)) min"
            sleep $(((until_next + RESUME_OFFSET_MIN) * 60))
            continue
        fi
        break
    done
}

# --- preconditions: fail hard, no silent fallback ---------------------------
[ -x "$IPD_BIN" ] || { echo "ERROR: ipd-benchmark not found at $IPD_BIN (install: cd $BENCH_DIR && uv venv .venv && uv pip install -e '.[paper]')" >&2; exit 1; }
[ -f "$CURRENT_CONST" ] || { echo "ERROR: current constitution not found: $CURRENT_CONST" >&2; exit 1; }

# bash 3.2 (macOS default) has no mapfile — collect via command substitution
staged_list=$(find "$STAGED_DIR" -maxdepth 1 -name '*.md' 2>/dev/null | sort)
staged_count=$(printf '%s' "$staged_list" | grep -c . || true)
[ "$staged_count" -eq 1 ] || { echo "ERROR: expected exactly 1 staged .md in $STAGED_DIR, found $staged_count — run 'contemplative-agent amend-constitution --stage' first" >&2; exit 1; }
STAGED_CONST="$staged_list"

mkdir -p "$OUTDIR"
sha_current=$(shasum -a 256 "$CURRENT_CONST" | cut -d' ' -f1)
sha_staged=$(shasum -a 256 "$STAGED_CONST" | cut -d' ' -f1)
{
    echo "started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "model: $OLLAMA_MODEL  n=$N_SIMS"
    echo "arm A (current): $CURRENT_CONST sha256=$sha_current"
    echo "arm B (staged):  $STAGED_CONST sha256=$sha_staged"
} | tee "$OUTDIR/provenance.txt"

run_arm() { # $1=label $2=prompt-file $3=out-json
    wait_for_clear_window
    echo "[arm $1] start $(date '+%H:%M:%S %Z') prompt=$2"
    "$IPD_BIN" --protocol paper --prompt-file "$2" -n "$N_SIMS" -o "$3" \
        2>&1 | tee "$OUTDIR/arm-$1.log"
    echo "[arm $1] done $(date '+%H:%M:%S %Z')"
}

run_arm A "$CURRENT_CONST" "$OUTDIR/arm-A-current.json"
run_arm B "$STAGED_CONST" "$OUTDIR/arm-B-staged.json"

python3 "$REPO_ROOT/scripts/ipd_two_arm_report.py" \
    "$OUTDIR/arm-A-current.json" "$OUTDIR/arm-B-staged.json" \
    | tee "$OUTDIR/report.md"

echo
echo "Attach $OUTDIR/report.md to the approval decision, then run:"
echo "  contemplative-agent adopt-staged"

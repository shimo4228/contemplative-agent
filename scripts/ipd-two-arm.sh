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
# Noise rule (ADR-0090 Amendment 2026-10-24): the report reads the cell-wise
# SE (|z| > 2), not the single ±0.13 above. Failed moves (parse fallback and
# LLM no-response, both default to COOPERATE) are counted by the bench and the
# report abstains if the arms' failure rates differ by more than 2 SE.
#
# Usage:
#   scripts/ipd-two-arm.sh [OUTDIR]
#   scripts/ipd-two-arm.sh --files A.md B.md [OUTDIR]
#       Compare any two texts under the same calibration contract (n=10,
#       gemma4:e4b, window guard) — template vs template, an old constitution
#       vs the live one. No .staged/ lookup, no audit-hash comparison (the arms
#       are not "current"/"staged"), so no MOLTBOOK_HOME is needed. The report
#       labels the arms by file name + sha instead of "current"/"staged", and
#       provenance.txt records where each text came from. Env ARM_A_FILE /
#       ARM_B_FILE do the same as the two arguments.
#       Third-party (no audit history) default-mode runs still need
#       AUDIT_CHECK_BYPASS=1; --files runs do not.
# Env:
#   MOLTBOOK_HOME   data dir (default ~/.config/moltbook)
#   BENCH_DIR       prisoners-dilemma checkout (default sibling rules repo)
#   BENCH_REF       rules-repo tag the calibration contract is pinned to
#                   (default v0.2.0, D-P1-11-6 = A). The checkout's
#                   `git describe` is recorded in provenance.txt; a checkout
#                   that is not at this ref only warns (the tag may not be
#                   fetched yet), because the contract is what the ref names:
#                   the rules repo README, "Consumption contract"
#   OLLAMA_MODEL    generation model (default gemma4:e4b, ADR-0069). Part of
#                   the calibration contract: the ±0.13 noise floor was
#                   measured on gemma4:e4b — changing the model invalidates
#                   the floor and requires a new null pair, same as N_SIMS
#   N_SIMS          simulations per cell (default 10 = null-pair calibration;
#                   changing it invalidates the ±0.13 noise floor)
#   SKIP_WINDOW_GUARD=1  disable the JST 0/6/12/18 schedule-session guard
#   AUDIT_CHECK_BYPASS=1 skip the arm A ↔ audit-log hash comparison (only
#                   for non-production MOLTBOOK_HOMEs with no audit history)
set -euo pipefail

# --files A B (or ARM_A_FILE + ARM_B_FILE): arbitrary two texts, P3-03.1 (c)
if [ "${1:-}" = "--files" ]; then
    [ $# -ge 3 ] || { echo "usage: $0 --files A.md B.md [OUTDIR]" >&2; exit 2; }
    ARM_A_FILE="$2"; ARM_B_FILE="$3"; shift 3
fi
ARM_A_FILE="${ARM_A_FILE:-}"; ARM_B_FILE="${ARM_B_FILE:-}"
FILES_MODE=0
if [ -n "$ARM_A_FILE" ] || [ -n "$ARM_B_FILE" ]; then
    [ -n "$ARM_A_FILE" ] && [ -n "$ARM_B_FILE" ] || { echo "ERROR: --files / ARM_A_FILE+ARM_B_FILE need both texts" >&2; exit 2; }
    FILES_MODE=1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOLTBOOK_HOME="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
BENCH_DIR="${BENCH_DIR:-$REPO_ROOT/../contemplative-agent-rules/benchmarks/prisoners-dilemma}"
# The default is the served model's own resolver (core.llm.served_model), not a
# second copy of the literal (P1-07.11).
if [ -z "${OLLAMA_MODEL:-}" ]; then
    OLLAMA_MODEL="$(cd "$REPO_ROOT" && uv run --no-sync python -c \
        'from contemplative_agent.core.llm import served_model; print(served_model())')"
fi
export OLLAMA_MODEL
N_SIMS="${N_SIMS:-10}"
BENCH_REF="${BENCH_REF:-v0.2.0}"

CURRENT_CONST="$MOLTBOOK_HOME/constitution/contemplative-axioms.md"
STAGED_DIR="$MOLTBOOK_HOME/.staged"
OUTDIR="${1:-$REPO_ROOT/.notes/ipd-amend-$(date +%Y-%m-%d)}"

IPD_BIN="$BENCH_DIR/.venv/bin/ipd-benchmark"

# wait_for_clear_window, sha256_of and ipd_identity live in _ipd_common.sh
# shellcheck source=_ipd_common.sh
. "$(dirname "$0")/_ipd_common.sh"

# --- preconditions: fail hard, no silent fallback ---------------------------
[ -x "$IPD_BIN" ] || { echo "ERROR: ipd-benchmark not found at $IPD_BIN (install: cd $BENCH_DIR && uv venv .venv && uv pip install -e '.[paper]')" >&2; exit 1; }

if [ "$FILES_MODE" = "1" ]; then
    [ -f "$ARM_A_FILE" ] || { echo "ERROR: arm A text not found: $ARM_A_FILE" >&2; exit 1; }
    [ -f "$ARM_B_FILE" ] || { echo "ERROR: arm B text not found: $ARM_B_FILE" >&2; exit 1; }
    ARM_A_PATH="$ARM_A_FILE"; ARM_B_PATH="$ARM_B_FILE"
else
    [ -f "$CURRENT_CONST" ] || { echo "ERROR: current constitution not found: $CURRENT_CONST" >&2; exit 1; }
    # bash 3.2 (macOS default) has no mapfile — collect via command substitution
    staged_list=$(find "$STAGED_DIR" -maxdepth 1 -name '*.md' 2>/dev/null | sort)
    staged_count=$(printf '%s' "$staged_list" | grep -c . || true)
    [ "$staged_count" -eq 1 ] || { echo "ERROR: expected exactly 1 staged .md in $STAGED_DIR, found $staged_count — run 'contemplative-agent amend-constitution --stage' first" >&2; exit 1; }
    ARM_A_PATH="$CURRENT_CONST"; ARM_B_PATH="$staged_list"
fi

mkdir -p "$OUTDIR"
sha_a=$(sha256_of "$ARM_A_PATH")
sha_b=$(sha256_of "$ARM_B_PATH")

# Arm A must BE the last-approved constitution: compare its hash against the
# newest amend-constitution record in the audit log. A mismatch means the
# "current" arm is not what the approval history says is live — reading the
# bench against it would attribute the wrong baseline to the amendment.
# Not applicable in --files mode: neither arm claims to be the live text.
AUDIT_LOG="$MOLTBOOK_HOME/logs/audit.jsonl"
if [ "$FILES_MODE" = "0" ] && [ "${AUDIT_CHECK_BYPASS:-0}" != "1" ]; then
    [ -f "$AUDIT_LOG" ] || { echo "ERROR: audit log not found at $AUDIT_LOG (set AUDIT_CHECK_BYPASS=1 only for non-production homes)" >&2; exit 1; }
    last_approved=$(python3 -c "
import json, sys
last = None
for line in open('$AUDIT_LOG', encoding='utf-8'):
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        continue
    # decision=='approved' only: at two-arm time the newest record is the
    # just-staged NEW text, whose hash must NOT be compared against arm A
    if d.get('command') == 'amend-constitution' and d.get('decision') == 'approved' and d.get('content_hash'):
        last = d['content_hash']
print(last or '')")
    if [ -z "$last_approved" ]; then
        echo "ERROR: no approved amend-constitution record with content_hash in $AUDIT_LOG" >&2; exit 1
    fi
    # the audit log stores a truncated (16-hex) content_hash — compare prefixes
    if [ "$last_approved" != "${sha_a:0:${#last_approved}}" ]; then
        echo "ERROR: arm A hash $sha_a does not match the audit log's last approved amend-constitution hash $last_approved — the on-disk constitution is not the last-approved text" >&2
        exit 1
    fi
    echo "[audit] arm A matches last-approved constitution hash ($last_approved…)"
fi
bench_describe="$(git -C "$BENCH_DIR" describe --tags --always --dirty 2>/dev/null || echo unknown)"
if [ "$bench_describe" != "$BENCH_REF" ]; then
    echo "WARNING: rules checkout is at '$bench_describe', not BENCH_REF '$BENCH_REF' — the ±0.13 floor was measured on the contract the tag names" >&2
fi

# Where a text came from, for provenance.txt: home-relative or repo-relative,
# never this machine's absolute path (the file ships to docs/evidence/).
display_path() {
    case "$1" in
        "$MOLTBOOK_HOME"/*) printf '$MOLTBOOK_HOME/%s' "${1#"$MOLTBOOK_HOME"/}" ;;
        "$REPO_ROOT"/*) printf '%s' "${1#"$REPO_ROOT"/}" ;;
        /*) printf '%s' "$(basename "$1")" ;;
        *) printf '%s' "$1" ;;
    esac
}
if [ "$FILES_MODE" = "1" ]; then
    LABEL_A="$(basename "$ARM_A_PATH") sha256:${sha_a:0:8}"
    LABEL_B="$(basename "$ARM_B_PATH") sha256:${sha_b:0:8}"
    ORIGIN_A="--files $(display_path "$ARM_A_PATH")"
    ORIGIN_B="--files $(display_path "$ARM_B_PATH")"
    NAME_A="arm A (files)"; NAME_B="arm B (files)"
    OUT_A="arm-A-files.json"; OUT_B="arm-B-files.json"
else
    LABEL_A="current"; LABEL_B="staged"
    ORIGIN_A="$(display_path "$ARM_A_PATH")"; ORIGIN_B="$(display_path "$ARM_B_PATH")"
    NAME_A="arm A (current)"; NAME_B="arm B (staged)"
    OUT_A="arm-A-current.json"; OUT_B="arm-B-staged.json"
fi

ipd_identity

# provenance.txt ships to docs/evidence/, so name the arms by their location
# under MOLTBOOK_HOME / the repo rather than by this machine's absolute path —
# the sha256 is what identifies the text. Exactly 8 lines.
{
    echo "started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "model: $OLLAMA_MODEL  n=$N_SIMS  weights digest: $model_digest"
    echo "$NAME_A: $ORIGIN_A sha256=$sha_a"
    echo "$NAME_B: $ORIGIN_B sha256=$sha_b"
    echo "bench: contemplative-ipd $ipd_version"
    echo "bench commit: $bench_commit (describe $bench_describe, BENCH_REF=$BENCH_REF)"
    echo "ollama: $ollama_version"
    echo "mode: $([ "$FILES_MODE" = "1" ] && echo "--files (arbitrary texts; no audit-hash comparison)" || echo "default (current vs staged; arm A checked against audit log)")"
} | tee "$OUTDIR/provenance.txt"

run_arm() { # $1=label $2=prompt-file $3=out-json
    wait_for_clear_window
    echo "[arm $1] start $(date '+%H:%M:%S %Z') prompt=$2"
    "$IPD_BIN" --protocol paper --prompt-file "$2" -n "$N_SIMS" -o "$3" \
        2>&1 | tee "$OUTDIR/arm-$1.log"
    echo "[arm $1] done $(date '+%H:%M:%S %Z')"
}

run_arm A "$ARM_A_PATH" "$OUTDIR/$OUT_A"
run_arm B "$ARM_B_PATH" "$OUTDIR/$OUT_B"

python3 "$REPO_ROOT/scripts/ipd_two_arm_report.py" \
    "$OUTDIR/$OUT_A" "$OUTDIR/$OUT_B" --label-a "$LABEL_A" --label-b "$LABEL_B" \
    | tee "$OUTDIR/report.md"

echo
if [ "$FILES_MODE" = "1" ]; then
    echo "Reading saved to $OUTDIR/report.md (--files run: nothing to adopt)."
else
    echo "Attach $OUTDIR/report.md to the approval decision, then run:"
    echo "  contemplative-agent adopt-staged"
fi

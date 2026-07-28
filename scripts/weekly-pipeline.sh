#!/bin/bash
# Unattended weekly chain (ADR-0085): report → diagnosis → fix → insight
# review → decision packet. Human involvement is compressed into the single
# Saturday gate (/weekly-gate); nothing here commits, pushes, or adopts.
#
# Fail-forward: every stage failure becomes a reason code in the audit log
# and the run continues to the packet, which is always attempted. The one
# exception is Stage 1 (report): with no report there is no input for
# anything downstream, so the run aborts (the watchdog catches the missing
# packet). Iteration bounds and the wall-clock deadline are hard stops.
#
# Usage:
#   ./scripts/weekly-pipeline.sh                       # full chain, yesterday-ending week
#   ./scripts/weekly-pipeline.sh --end-date 2026-07-24 # explicit week
#   ./scripts/weekly-pipeline.sh --skip-report --end-date 2026-07-24
#                                                      # dry-run stages 2+ on an existing report
#   MOLTBOOK_PIPELINE_STAGES=report,diagnosis,insight,packet ./scripts/weekly-pipeline.sh
#                                                      # shadow mode: no fix stage
set -uo pipefail

# --- Config ---
MOLTBOOK_HOME="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$PROJECT_ROOT/scripts"
PROMPTS="$PROJECT_ROOT/config/prompts"
REPORT_DIR="$MOLTBOOK_HOME/reports/analysis"
STAGED_DIR="$MOLTBOOK_HOME/.staged"
AUDIT="$MOLTBOOK_HOME/logs/weekly-pipeline-audit.jsonl"
METRICS="$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl"
WORKTREE_ROOT="$MOLTBOOK_HOME/pipeline/worktrees"

# Iteration bounds (ADR-0085; all overridable for tests)
MAX_FIX_ATTEMPTS="${PIPELINE_MAX_FIX_ATTEMPTS:-2}"
MAX_FIX_TARGETS="${PIPELINE_MAX_FIX_TARGETS:-5}"
DIAGNOSIS_TIMEOUT="${PIPELINE_DIAGNOSIS_TIMEOUT:-1800}"
FIX_TIMEOUT="${PIPELINE_FIX_TIMEOUT:-1200}"
REVIEW_TIMEOUT="${PIPELINE_REVIEW_TIMEOUT:-600}"
INSIGHT_TIMEOUT="${PIPELINE_INSIGHT_TIMEOUT:-900}"
IMPROVE_TIMEOUT="${PIPELINE_IMPROVE_TIMEOUT:-900}"
CHAIN_DEADLINE_SECONDS="${PIPELINE_DEADLINE_SECONDS:-10800}"   # 09:00 → 12:00

STAGES="${MOLTBOOK_PIPELINE_STAGES:-report,diagnosis,fix,insight,improve,packet}"

END_DATE=""
DAYS=7
SKIP_REPORT=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --end-date)   END_DATE="$2"; shift 2 ;;
        --days)       DAYS="$2"; shift 2 ;;
        --skip-report) SKIP_REPORT=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--end-date YYYY-MM-DD] [--days N] [--skip-report]"
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done
[[ -z "$END_DATE" ]] && END_DATE=$(date -v-1d +%Y-%m-%d)

RUN_ID="weekly-${END_DATE}-$(date +%H%M%S)"
RUN_LOG_DIR="$MOLTBOOK_HOME/logs/weekly-pipeline/$RUN_ID"
PATCH_DIR="$REPORT_DIR/patches/weekly-$END_DATE/code"
PROMPT_PATCH_DIR="$REPORT_DIR/patches/weekly-$END_DATE/prompt"
REPORT_PATH="$REPORT_DIR/weekly-${END_DATE}.md"
FINDINGS_MD="$REPORT_DIR/weekly-${END_DATE}-findings.md"
FINDINGS_JSON="$RUN_LOG_DIR/findings.json"
INSIGHT_REVIEW="$REPORT_DIR/weekly-${END_DATE}-insight-review.md"
IMPROVEMENT="$REPORT_DIR/weekly-${END_DATE}-improvement.md"
PACKET="$REPORT_DIR/weekly-${END_DATE}-packet.md"

START_EPOCH=$(date +%s)
REASONS=""          # accumulated reason codes (comma separated)
IMPROVEMENT_ARG=()  # set only when the improvement stage produced a file

mkdir -p "$RUN_LOG_DIR" "$PATCH_DIR" "$PROMPT_PATCH_DIR"

# --- Helpers ---
audit() {  # audit <event> [k=v ...]
    local event="$1"; shift
    local fields=()
    for kv in "$@"; do fields+=(--field "$kv"); done
    # ${arr[@]+...} guard: macOS ships bash 3.2, where "${arr[@]}" on an
    # empty array trips `set -u`.
    python3 "$SCRIPTS/pipeline_audit.py" --log "$AUDIT" --run-id "$RUN_ID" \
        --event "$event" ${fields[@]+"${fields[@]}"} \
        || echo "WARNING: audit append failed for $event" >&2
}

add_reason() {
    case ",$REASONS," in *",$1,"*) return ;; esac
    REASONS="${REASONS:+$REASONS,}$1"
}

stage_enabled() { case ",$STAGES," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

deadline_exceeded() {
    (( $(date +%s) - START_EPOCH >= CHAIN_DEADLINE_SECONDS ))
}

with_timeout() {  # with_timeout <seconds> <cmd...>
    local secs="$1"; shift
    if command -v timeout >/dev/null 2>&1; then
        timeout "$secs" "$@"
    else
        "$@"   # same degradation as weekly-analysis.sh's translate guard
    fi
}

# --- Preflight (same rationale as weekly-analysis.sh: fail before burning work) ---
for bin in claude git uv python3; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo "ERROR: '$bin' not found on PATH ($PATH)" >&2
        audit stage_result stage=preflight result=fail reason=PREFLIGHT_MISSING_BIN "bin=$bin"
        exit 1
    fi
done

# Clean up worktree corpses from a crashed previous run before adding new ones.
git -C "$PROJECT_ROOT" worktree prune >/dev/null 2>&1
if [[ -d "$WORKTREE_ROOT" ]]; then
    rm -rf "$WORKTREE_ROOT"
    git -C "$PROJECT_ROOT" worktree prune >/dev/null 2>&1
fi
mkdir -p "$WORKTREE_ROOT"

audit chain_start end_date="$END_DATE" stages="$STAGES"
echo "[$RUN_ID] chain start (stages: $STAGES)"

# --- Stage 1: report ---
if stage_enabled report && [[ $SKIP_REPORT -eq 0 ]]; then
    echo "[$RUN_ID] stage 1: weekly-analysis"
    if bash "$SCRIPTS/weekly-analysis.sh" --end-date "$END_DATE" --days "$DAYS" \
            > "$RUN_LOG_DIR/report.log" 2>&1; then
        audit stage_result stage=report result=ok
    else
        audit stage_result stage=report result=fail reason=REPORT_FAIL
        echo "ERROR: weekly-analysis failed — no input for downstream stages, aborting" >&2
        echo "       (see $RUN_LOG_DIR/report.log; the watchdog reports the missing packet)" >&2
        exit 1
    fi
else
    audit stage_result stage=report result=skipped
fi

if [[ ! -s "$REPORT_PATH" ]]; then
    audit stage_result stage=report result=fail reason=REPORT_MISSING
    echo "ERROR: report $REPORT_PATH missing or empty — aborting" >&2
    exit 1
fi

# --- Stage 2: diagnosis (separate session; the skill writes findings itself) ---
if stage_enabled diagnosis && [[ ! -s "$FINDINGS_MD" ]]; then
    if deadline_exceeded; then
        add_reason CHAIN_DEADLINE
        audit stage_result stage=diagnosis result=skipped reason=CHAIN_DEADLINE
    else
        echo "[$RUN_ID] stage 2: diagnosis"
        with_timeout "$DIAGNOSIS_TIMEOUT" claude -p "/weekly-report-diagnosis $REPORT_PATH" \
            --add-dir "$MOLTBOOK_HOME" \
            --allowedTools "Read,Glob,Grep,Write,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(grep:*),Bash(ls:*),Bash(wc:*),Bash(head:*),Bash(tail:*),Bash(stat:*),Bash(python3:*)" \
            --output-format text \
            > "$RUN_LOG_DIR/diagnosis.log" 2>&1
        diag_rc=$?
        if [[ $diag_rc -eq 0 && -s "$FINDINGS_MD" ]]; then
            audit stage_result stage=diagnosis result=ok
        else
            add_reason DIAGNOSIS_FAIL
            audit stage_result stage=diagnosis result=fail reason=DIAGNOSIS_FAIL "rc=$diag_rc"
            echo "WARNING: diagnosis failed (rc=$diag_rc) — continuing to packet" >&2
        fi
    fi
elif [[ -s "$FINDINGS_MD" ]]; then
    echo "[$RUN_ID] stage 2: findings already exist, reusing $FINDINGS_MD"
    audit stage_result stage=diagnosis result=reused
else
    audit stage_result stage=diagnosis result=skipped
fi

# --- Stage 3: parse findings (deterministic) ---
if [[ -s "$FINDINGS_MD" ]]; then
    if python3 "$SCRIPTS/parse_findings.py" "$FINDINGS_MD" > "$FINDINGS_JSON" 2>"$RUN_LOG_DIR/parse.log"; then
        audit stage_result stage=parse result=ok
    else
        add_reason PARSE_FAIL
        audit stage_result stage=parse result=fail reason=PARSE_FAIL
        rm -f "$FINDINGS_JSON"
    fi
fi

# --- Stage 4: fix (one worktree + fresh claude context per F1) ---
run_verify() {  # run_verify <worktree> <logfile>
    local wt="$1" log="$2"
    (
        cd "$wt" || exit 1
        # uv.lock is gitignored, so the worktree checkout lacks it; the copy
        # happens at worktree add. Fall back to an unpinned sync if absent.
        if [[ -f uv.lock ]]; then
            uv sync --frozen -q >> "$log" 2>&1 || { echo "VERIFY: uv sync failed" >> "$log"; exit 1; }
        else
            uv sync -q >> "$log" 2>&1 || { echo "VERIFY: uv sync failed" >> "$log"; exit 1; }
        fi
        uv run -q ruff check src/ tests/ scripts/ >> "$log" 2>&1 || { echo "VERIFY: ruff failed" >> "$log"; exit 1; }
        uv run -q lint-imports >> "$log" 2>&1 || { echo "VERIFY: lint-imports failed" >> "$log"; exit 1; }
        uv run -q pytest tests/ -q -x >> "$log" 2>&1 || { echo "VERIFY: pytest failed" >> "$log"; exit 1; }
    )
}

fix_one() {  # fix_one <fid> <scope> <bodyfile>
    local fid="$1" scope="$2" bodyfile="$3"
    local wt="$WORKTREE_ROOT/${fid//./-}"
    local safe_fid="${fid//\//_}"
    local fixlog="$RUN_LOG_DIR/fix-$safe_fid"
    local verdict="—"

    if ! git -C "$PROJECT_ROOT" worktree add --detach "$wt" HEAD >/dev/null 2>&1; then
        audit fix_result fix_id="$fid" scope="$scope" result=failed attempts=0 reason=WORKTREE_FAIL
        add_reason WORKTREE_FAIL
        return
    fi
    # uv.lock is gitignored (absent from the checkout); carry the pin over so
    # Verify runs against the same resolution as production (2026-07-29 trial:
    # every attempt-1 Verify died on the missing lockfile).
    [[ -f "$PROJECT_ROOT/uv.lock" ]] && cp "$PROJECT_ROOT/uv.lock" "$wt/uv.lock"

    local attempt=1 passed=0
    local prompt_file="$RUN_LOG_DIR/fix-$safe_fid-prompt.md"
    cp "$bodyfile" "$prompt_file"
    while (( attempt <= MAX_FIX_ATTEMPTS )); do
        if deadline_exceeded; then
            add_reason CHAIN_DEADLINE
            audit fix_result fix_id="$fid" scope="$scope" result=failed \
                attempts="$((attempt - 1))" reason=CHAIN_DEADLINE
            git -C "$PROJECT_ROOT" worktree remove --force "$wt" >/dev/null 2>&1
            return
        fi
        echo "[$RUN_ID]   $fid attempt $attempt ($scope)"
        (
            cd "$wt" || exit 1
            with_timeout "$FIX_TIMEOUT" claude -p "$(cat "$prompt_file")" \
                --system-prompt "$(cat "$PROMPTS/fix-implementation.md")" \
                --allowedTools "Read,Glob,Grep,Edit,Write,Bash(uv run:*),Bash(git diff:*),Bash(git status:*),Bash(ls:*),Bash(grep:*)" \
                --output-format text
        ) > "$fixlog-attempt$attempt.log" 2>&1
        local rc=$?
        if [[ $rc -ne 0 ]]; then
            # 124 is coreutils timeout's exit code
            local code=FIX_SESSION_FAIL; [[ $rc -eq 124 ]] && code=FIX_TIMEOUT
            add_reason "$code"
            audit fix_attempt fix_id="$fid" attempt="$attempt" result=session_fail reason="$code"
            break
        fi
        if [[ "$scope" == "prompt" ]]; then
            passed=1   # prompt-scope diffs are not Verify-gated; the human reads full text
            break
        fi
        if run_verify "$wt" "$fixlog-verify$attempt.log"; then
            audit fix_attempt fix_id="$fid" attempt="$attempt" result=verify_pass
            passed=1
            break
        fi
        audit fix_attempt fix_id="$fid" attempt="$attempt" result=verify_fail
        # Never retry on identical input: feed the failure back (bounded).
        {
            cat "$bodyfile"
            echo ""
            echo "## Verify failure output (previous attempt $attempt — fix the cause, do not weaken checks)"
            echo '```'
            tail -n 120 "$fixlog-verify$attempt.log"
            echo '```'
        } > "$prompt_file"
        attempt=$((attempt + 1))
    done

    if [[ $passed -eq 1 ]]; then
        local out_dir="$PATCH_DIR"
        [[ "$scope" == "prompt" ]] && out_dir="$PROMPT_PATCH_DIR"
        local patch="$out_dir/$safe_fid.patch"
        if (cd "$wt" && git add -A && git diff --cached) > "$patch" 2>>"$fixlog-export.log" \
                && [[ -s "$patch" ]]; then
            audit fix_result fix_id="$fid" scope="$scope" result=patch_ready \
                attempts="$attempt" patch="$patch"
            if [[ "$scope" == "code" ]] && ! deadline_exceeded; then
                {
                    cat "$bodyfile"
                    echo ""
                    echo "## Diff under review"
                    echo '```diff'
                    cat "$patch"
                    echo '```'
                } | with_timeout "$REVIEW_TIMEOUT" claude -p \
                    --system-prompt "$(cat "$PROMPTS/fix-review.md")" \
                    --allowedTools "Read,Glob,Grep" \
                    --output-format text \
                    > "$fixlog-review.log" 2>&1
                verdict=$(grep -m1 '^VERDICT:' "$fixlog-review.log" | sed 's/^VERDICT: *//')
                [[ -z "$verdict" ]] && verdict="REVIEW_FAIL"
                audit review_result fix_id="$fid" verdict="$verdict"
            fi
        else
            rm -f "$patch"
            add_reason EMPTY_DIFF
            audit fix_result fix_id="$fid" scope="$scope" result=failed \
                attempts="$attempt" reason=EMPTY_DIFF
        fi
    elif (( attempt > MAX_FIX_ATTEMPTS )); then
        add_reason VERIFY_FAIL_MAX_ATTEMPTS
        audit fix_result fix_id="$fid" scope="$scope" result=failed \
            attempts="$MAX_FIX_ATTEMPTS" reason=VERIFY_FAIL_MAX_ATTEMPTS
    else
        audit fix_result fix_id="$fid" scope="$scope" result=failed \
            attempts="$attempt" reason="${code:-FIX_SESSION_FAIL}"
    fi

    git -C "$PROJECT_ROOT" worktree remove --force "$wt" >/dev/null 2>&1
    git -C "$PROJECT_ROOT" worktree prune >/dev/null 2>&1
}

if stage_enabled fix && [[ -s "$FINDINGS_JSON" ]]; then
    F1_COUNT=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))['f1']))" "$FINDINGS_JSON")
    if [[ "$F1_COUNT" -eq 0 ]]; then
        add_reason NO_F1_FINDINGS
        audit stage_result stage=fix result=skipped reason=NO_F1_FINDINGS
    else
        echo "[$RUN_ID] stage 4: fix ($F1_COUNT F1 findings, cap $MAX_FIX_TARGETS)"
        # Stale-finding gate baseline: a finding whose referenced paths
        # received commits AFTER the findings file was written is treated as
        # already resolved (deterministic — git history, not the fix agent's
        # self-declared claim). First fired by the pipeline's own improvement
        # loop on the 2026-07-29 trial, where EMPTY_DIFF conflated "already
        # implemented on main" with "session produced no work".
        FINDINGS_EPOCH=$(stat -f %m "$FINDINGS_MD" 2>/dev/null || echo "")
        FINDINGS_ISO=""
        [[ -n "$FINDINGS_EPOCH" ]] && FINDINGS_ISO=$(date -r "$FINDINGS_EPOCH" '+%Y-%m-%dT%H:%M:%S' 2>/dev/null || echo "")
        targeted=0
        while IFS=$'\t' read -r fid scope pathlist; do
            if [[ -n "$FINDINGS_ISO" && -n "$pathlist" ]]; then
                # shellcheck disable=SC2086 — pathlist is intentionally split
                if [[ -n $(git -C "$PROJECT_ROOT" log --oneline -1 \
                        --since="$FINDINGS_ISO" -- $pathlist 2>/dev/null) ]]; then
                    add_reason FINDING_STALE
                    audit fix_result fix_id="$fid" scope="$scope" result=skipped \
                        attempts=0 reason=FINDING_STALE
                    echo "[$RUN_ID]   $fid skipped (referenced paths changed after diagnosis)"
                    continue
                fi
            fi
            if (( targeted >= MAX_FIX_TARGETS )); then
                add_reason BUDGET_EXHAUSTED
                audit fix_result fix_id="$fid" scope="$scope" result=failed \
                    attempts=0 reason=BUDGET_EXHAUSTED
                continue
            fi
            bodyfile="$RUN_LOG_DIR/body-${fid//[.\/]/-}.md"
            python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
for f in data['f1']:
    if f['id'] == sys.argv[2]:
        print(f['body'])
        break
" "$FINDINGS_JSON" "$fid" > "$bodyfile"
            # </dev/null: the claude/uv calls inside fix_one would otherwise
            # drain the process substitution feeding this while-read loop,
            # silently dropping every finding after the first (observed on
            # the 2026-07-29 trial: targeted=1 of 2).
            fix_one "$fid" "$scope" "$bodyfile" < /dev/null
            targeted=$((targeted + 1))
        done < <(python3 -c "
import json, sys
for f in json.load(open(sys.argv[1]))['f1']:
    print(f['id'], f['scope'], ' '.join(f['paths']), sep='\t')
" "$FINDINGS_JSON")
        audit stage_result stage=fix result=ok targeted="$targeted"
    fi
else
    audit stage_result stage=fix result=skipped
fi

# --- Stage 5: insight staging review (read-only; never writes to staging) ---
if stage_enabled insight; then
    staged_files=("$STAGED_DIR"/*.md)
    if [[ ! -e "${staged_files[0]}" ]]; then
        printf 'No staged insight items this week (staging empty at run time).\n' > "$INSIGHT_REVIEW"
        audit stage_result stage=insight_review result=ok items=0
    elif deadline_exceeded; then
        add_reason CHAIN_DEADLINE
        audit stage_result stage=insight_review result=skipped reason=CHAIN_DEADLINE
    else
        echo "[$RUN_ID] stage 5: insight review (${#staged_files[@]} staged items)"
        {
            echo "Staged insight candidates for review ($END_DATE week):"
            echo ""
            for f in "${staged_files[@]}"; do
                echo "=== $(basename "$f") ==="
                cat "$f"
                meta="${f%.md}.meta.json"
                [[ -f "$meta" ]] && { echo "--- meta ---"; cat "$meta"; }
                echo ""
            done
        } > "$RUN_LOG_DIR/insight-input.md"
        INSIGHT_TMP="$INSIGHT_REVIEW.tmp.$$"
        if with_timeout "$INSIGHT_TIMEOUT" claude -p "$(cat "$RUN_LOG_DIR/insight-input.md")" \
                --system-prompt "$(cat "$PROMPTS/insight-recommendation.md")" \
                --add-dir "$MOLTBOOK_HOME" \
                --allowedTools "Read,Glob,Grep" \
                --output-format text \
                > "$INSIGHT_TMP" 2>"$RUN_LOG_DIR/insight.err" \
                && grep -q "RECOMMEND:" "$INSIGHT_TMP"; then
            mv "$INSIGHT_TMP" "$INSIGHT_REVIEW"
            audit stage_result stage=insight_review result=ok items="${#staged_files[@]}"
        else
            rm -f "$INSIGHT_TMP"
            add_reason INSIGHT_REVIEW_FAIL
            audit stage_result stage=insight_review result=fail reason=INSIGHT_REVIEW_FAIL
        fi
    fi
else
    audit stage_result stage=insight_review result=skipped
fi

# --- Stage 6: improvement check (P4-shaped, fires on 2-week recurrence) ---
# The orchestrator knows extra codes the builder will add for missing files.
[[ -s "$FINDINGS_JSON" ]] || add_reason DIAGNOSIS_UNAVAILABLE
[[ -s "$INSIGHT_REVIEW" ]] || add_reason INSIGHT_REVIEW_UNAVAILABLE
if stage_enabled improve && [[ -n "$REASONS" ]] && ! deadline_exceeded; then
    fired=$(python3 "$SCRIPTS/build_decision_packet.py" check-improvement \
        --metrics "$METRICS" --current-codes "$REASONS" 2>/dev/null)
    if [[ "$fired" == *'"fired": true'* ]]; then
        echo "[$RUN_ID] stage 6: improvement proposal (recurrence: $fired)"
        {
            echo "Recurring reason codes: $fired"
            echo ""
            echo "## Audit excerpts (this run and history)"
            echo '```'
            grep -h "\"run_id\": \"$RUN_ID\"" "$AUDIT" 2>/dev/null | tail -n 60
            tail -n 60 "$METRICS" 2>/dev/null
            echo '```'
            echo ""
            echo "## Current pipeline definition files are readable in this repo checkout."
        } > "$RUN_LOG_DIR/improve-input.md"
        IMPROVE_TMP="$IMPROVEMENT.tmp.$$"
        if (cd "$PROJECT_ROOT" && with_timeout "$IMPROVE_TIMEOUT" claude -p \
                "$(cat "$RUN_LOG_DIR/improve-input.md")" \
                --system-prompt "$(cat "$PROMPTS/pipeline-improvement.md")" \
                --allowedTools "Read,Glob,Grep" \
                --output-format text) > "$IMPROVE_TMP" 2>"$RUN_LOG_DIR/improve.err" \
                && [[ -s "$IMPROVE_TMP" ]]; then
            mv "$IMPROVE_TMP" "$IMPROVEMENT"
            IMPROVEMENT_ARG=(--improvement "$IMPROVEMENT")
            audit stage_result stage=improve result=ok
        else
            rm -f "$IMPROVE_TMP"
            add_reason IMPROVE_FAIL
            audit stage_result stage=improve result=fail reason=IMPROVE_FAIL
        fi
    else
        audit stage_result stage=improve result=skipped reason=NO_RECURRENCE
    fi
else
    audit stage_result stage=improve result=skipped
fi

# --- Stage 7: decision packet (always attempted — the fail-forward target) ---
echo "[$RUN_ID] stage 7: decision packet"
FINDINGS_ARG=()
[[ -s "$FINDINGS_JSON" ]] && FINDINGS_ARG=(--findings "$FINDINGS_JSON")
INSIGHT_ARG=()
[[ -s "$INSIGHT_REVIEW" ]] && INSIGHT_ARG=(--insight-review "$INSIGHT_REVIEW")
if python3 "$SCRIPTS/build_decision_packet.py" build \
        --end-date "$END_DATE" \
        --run-id "$RUN_ID" \
        --audit "$AUDIT" \
        --metrics "$METRICS" \
        ${FINDINGS_ARG[@]+"${FINDINGS_ARG[@]}"} \
        --patches-dir "$PATCH_DIR" \
        --prompt-patches-dir "$PROMPT_PATCH_DIR" \
        ${INSIGHT_ARG[@]+"${INSIGHT_ARG[@]}"} \
        ${IMPROVEMENT_ARG[@]+"${IMPROVEMENT_ARG[@]}"} \
        --out "$PACKET" > "$RUN_LOG_DIR/packet.log" 2>&1; then
    audit chain_end result=ok packet="$PACKET" reasons="${REASONS:-none}"
    echo "[$RUN_ID] packet: $PACKET"
    echo "[$RUN_ID] done (reasons: ${REASONS:-none})"
else
    audit chain_end result=fail reason=PACKET_FAIL
    echo "ERROR: packet build failed (see $RUN_LOG_DIR/packet.log)" >&2
    exit 1
fi

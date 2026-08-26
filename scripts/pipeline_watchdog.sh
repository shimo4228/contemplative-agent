#!/bin/bash
# Independent pipeline watchdog (ADR-0085).
#
# Verifies that every scheduled job produced its terminal artifact — the
# in-chain detection can only catch upstream failures (a dead report is
# noticed by the diagnosis that consumes it; a dead diagnosis or insight run
# has no consumer until Saturday), and a job that never started leaves
# nothing to notice. So this script checks the artifacts directly, against
# a declarative expectation table, anchored to the most recent period each
# job should have covered (a failure stays visible all week, not just on
# the day it happened).
#
# HARD CONSTRAINT: pure bash + BSD date/stat only. No claude, no uv, no
# python. The 2026-07-25 incident (0-byte weekly report) was caused by
# `claude` missing from launchd's PATH — a watchdog sharing that dependency
# would have died of the same cause it exists to report.
#
# Outputs:
#   1. $MOLTBOOK_HOME/reports/PIPELINE-STATUS.md  — always rewritten
#   2. macOS Notification Center                  — only when the FAIL set
#      changed since the previous run (no repeat-noise for a known failure)
set -u

MOLTBOOK_HOME="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
REPORT_DIR="$MOLTBOOK_HOME/reports/analysis"
LOG_DIR="$MOLTBOOK_HOME/logs"
STATUS="$MOLTBOOK_HOME/reports/PIPELINE-STATUS.md"

# 300, not the old 1024: the RFC-0010 instrument document declares "a quiet
# week is deliberately short" — a minimal valid document (title + inventory
# line + six one-line sections) sits well under 1 KB, and the structural
# heading gate in weekly-pipeline.sh, not size, is the completeness contract.
# This floor only catches the 0-byte / died-mid-write shape.
MIN_REPORT_BYTES=300
MIN_FINDINGS_BYTES=512

HOUR=$(date +%H)
WEEKDAY=$(date +%u)   # Mon=1 .. Sun=7 (Sat=6)

RESULTS=()   # "OK<TAB>job<TAB>detail" / "FAIL<TAB>job<TAB>detail"

ok()   { RESULTS+=("OK	$1	$2"); }
fail() { RESULTS+=("FAIL	$1	$2"); }
skip() { RESULTS+=("SKIP	$1	$2"); }

# A job whose plist is not installed is not a failure — a subset install
# (declarative reconcile removes unflagged jobs) would otherwise read as
# permanently broken (2026-07-29 codex review P2).
scheduled() { [[ -f "$HOME/Library/LaunchAgents/com.moltbook.$1.plist" ]]; }

mtime_of() { stat -f %m "$1" 2>/dev/null || echo 0; }
size_of()  { stat -f %z "$1" 2>/dev/null || echo 0; }

epoch_at() {  # epoch_at YYYY-MM-DD HH:MM
    date -j -f "%Y-%m-%d %H:%M" "$1 $2" +%s 2>/dev/null || echo 0
}

log_healthy() {  # log_healthy <job> <logfile> <min_mtime_epoch> <detail_period>
    local job="$1" log="$2" min_epoch="$3" period="$4"
    if [[ ! -f "$log" ]]; then
        fail "$job" "log missing: $log"
        return
    fi
    local mtime; mtime=$(mtime_of "$log")
    if (( mtime < min_epoch )); then
        fail "$job" "did not run for $period (log mtime $(date -r "$mtime" '+%m-%d %H:%M'))"
        return
    fi
    if tail -n 30 "$log" | grep -qiE 'traceback|^ERROR|error:'; then
        fail "$job" "ran for $period but the log tail shows errors: $log"
        return
    fi
    ok "$job" "last run $(date -r "$mtime" '+%m-%d %H:%M')"
}

# --- Anchor dates: the most recent period each job should have covered ---

# Saturday chain (insight 08:00, report 09:00, packet by 13:00). Before a
# job's own deadline on Saturday itself, the previous week is the anchor.
days_since_sat=$(( (WEEKDAY + 1) % 7 ))
anchor_sat() {  # anchor_sat <deadline_hour> → YYYY-MM-DD of the governing Saturday
    local deadline="$1" back="$days_since_sat"
    if (( days_since_sat == 0 )) && (( 10#$HOUR < deadline )); then
        back=7
    fi
    date -v-"${back}"d +%Y-%m-%d
}

# --- distill: daily 03:30 (check yesterday's run before 05:00) ---
if (( 10#$HOUR < 5 )); then
    distill_day=$(date -v-1d +%Y-%m-%d)
else
    distill_day=$(date +%Y-%m-%d)
fi
if scheduled distill; then
    log_healthy "distill" "$LOG_DIR/distill-launchd.log" \
        "$(epoch_at "$distill_day" "03:00")" "$distill_day"
else
    skip "distill" "not scheduled"
fi

# --- insight: Sat 08:00 (deadline 09:00) ---
if scheduled insight; then
    insight_sat=$(anchor_sat 9)
    log_healthy "insight" "$LOG_DIR/insight-launchd.log" \
        "$(epoch_at "$insight_sat" "07:30")" "Sat $insight_sat"
else
    skip "insight" "not scheduled"
fi

# --- weekly report + findings: both terminal artifacts of com.moltbook.weekly-pipeline ---
# (ADR-0098: the decision packet is retired; the findings file is the chain's
# last LLM artifact and the Saturday gate reads it directly.)
if scheduled weekly-pipeline; then
    # report: Sat 09:00, deadline 12:00; artifact = weekly-<Fri>.md
    report_sat=$(anchor_sat 12)
    report_end=$(date -j -f %Y-%m-%d -v-1d "$report_sat" +%Y-%m-%d 2>/dev/null)
    report_file="$REPORT_DIR/weekly-${report_end}.md"
    report_size=$(size_of "$report_file")
    if (( report_size >= MIN_REPORT_BYTES )); then
        ok "weekly-report" "weekly-${report_end}.md (${report_size} bytes)"
    elif [[ -f "$report_file" ]]; then
        # The exact 2026-07-25 failure shape: file exists, content does not.
        fail "weekly-report" "weekly-${report_end}.md is ${report_size} bytes (expected >= ${MIN_REPORT_BYTES})"
    else
        fail "weekly-report" "weekly-${report_end}.md not found (expected by Sat 12:00)"
    fi

    # findings: chain end, deadline Sat 13:00
    findings_sat=$(anchor_sat 13)
    findings_end=$(date -j -f %Y-%m-%d -v-1d "$findings_sat" +%Y-%m-%d 2>/dev/null)
    findings_file="$REPORT_DIR/weekly-${findings_end}-findings.md"
    findings_size=$(size_of "$findings_file")
    if (( findings_size >= MIN_FINDINGS_BYTES )); then
        ok "weekly-findings" "weekly-${findings_end}-findings.md (${findings_size} bytes)"
    elif [[ -f "$findings_file" ]]; then
        fail "weekly-findings" "weekly-${findings_end}-findings.md is ${findings_size} bytes (expected >= ${MIN_FINDINGS_BYTES})"
    else
        fail "weekly-findings" "weekly-${findings_end}-findings.md not found — the weekly session died before its diagnosis output (expected by Sat 13:00)"
    fi
else
    skip "weekly-report" "not scheduled (weekly-pipeline plist absent)"
    skip "weekly-findings" "not scheduled (weekly-pipeline plist absent)"
fi

# --- backup: Mon 10:00, deadline 11:00 ---
if scheduled backup; then
    days_since_mon=$(( (WEEKDAY - 1 + 7) % 7 ))
    if (( days_since_mon == 0 )) && (( 10#$HOUR < 11 )); then
        days_since_mon=7
    fi
    backup_mon=$(date -v-"${days_since_mon}"d +%Y-%m-%d)
    log_healthy "backup" "$LOG_DIR/backup-launchd.log" \
        "$(epoch_at "$backup_mon" "09:30")" "Mon $backup_mon"
else
    skip "backup" "not scheduled"
fi

# --- Previous FAIL set (for notification dedup), then rewrite status ---
prev_fails=""
[[ -f "$STATUS" ]] && prev_fails=$(grep -- '- ❌' "$STATUS" 2>/dev/null | awk '{print $3}' | sort | tr '\n' ',')

mkdir -p "$(dirname "$STATUS")"
STATUS_TMP="$STATUS.tmp.$$"
{
    echo "# Pipeline Status"
    echo ""
    echo "Last check: $(date '+%Y-%m-%d %H:%M %Z') — \`scripts/pipeline_watchdog.sh\`"
    echo ""
    fail_count=0
    for line in "${RESULTS[@]}"; do
        IFS=$'\t' read -r verdict job detail <<< "$line"
        if [[ "$verdict" == "OK" ]]; then
            echo "- ✅ ${job} — ${detail}"
        elif [[ "$verdict" == "SKIP" ]]; then
            echo "- ➖ ${job} — ${detail}"
        else
            echo "- ❌ ${job} — ${detail}"
            fail_count=$((fail_count + 1))
        fi
    done
    echo ""
    if (( fail_count == 0 )); then
        echo "All scheduled pipelines healthy."
    else
        echo "**${fail_count} pipeline(s) failing.** Logs: \`$LOG_DIR\`. The Saturday"
        echo "gate session (\`/weekly-gate\`) reads this file before any decision."
    fi
} > "$STATUS_TMP"
mv "$STATUS_TMP" "$STATUS"

# --- Notify only when the FAIL set changed (new failure or recovery) ---
cur_fails=""
for line in "${RESULTS[@]}"; do
    [[ "$line" == FAIL* ]] && cur_fails+="$(echo "$line" | cut -f2),"
done
# printf, not echo: an empty echo still emits a newline, which tr would turn
# into a lone "," — a truthy failure set on a fully healthy run.
if [[ -n "$cur_fails" ]]; then
    cur_fails=$(printf '%s' "${cur_fails%,}" | tr ',' '\n' | sort | tr '\n' ',')
fi

if [[ "$cur_fails" != "$prev_fails" ]]; then
    if [[ -n "$cur_fails" ]]; then
        failing=$(echo "${cur_fails%,}" | tr ',' ' ')
        /usr/bin/osascript -e "display notification \"failing: ${failing} — see PIPELINE-STATUS.md\" with title \"Moltbook pipeline\"" 2>/dev/null
    elif [[ -n "$prev_fails" ]]; then
        # Recovery is a state change too — without this the operator learns
        # the pipeline healed only by reading the status file.
        /usr/bin/osascript -e "display notification \"recovered — all pipelines healthy\" with title \"Moltbook pipeline\"" 2>/dev/null
    fi
fi

echo "watchdog: $(grep -c '^- ' "$STATUS") checks, failures: ${cur_fails:-none}"
[[ -z "$cur_fails" ]] || exit 2
exit 0

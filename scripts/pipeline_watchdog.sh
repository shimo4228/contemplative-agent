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
# HARD CONSTRAINT: pure bash + BSD date/stat/df/awk and `launchctl` (read-only:
# `launchctl list <label>`, ADR-0085's allowed external commands are date, stat
# and launchctl). No claude, no uv, no python. The 2026-07-25 incident (0-byte weekly report) was caused by
# `claude` missing from launchd's PATH — a watchdog sharing that dependency
# would have died of the same cause it exists to report.
#
# Readers of each row (ADR-0101; the Saturday gate's Step 0(c) reads the file):
#   distill / insight / backup / weekly-report / weekly-findings / sync-data
#     -> the gate, as before; agent -> the gate (a day with LLM calls but no
#     comment report is the Ollama-down shape); moltbook -> the gate (24 h of
#     calls with no 2xx is an outage or a closed platform); moltbook-7d ->
#     the gate and the P4-01 review event (no comment report for 7 days is the
#     platform-closure shape; the watchdog never stops anything); disk and
#     log-rotation -> the gate. P2-04.21's drift scan covers PARTIAL endpoint
#     retirement; the moltbook row here covers a full outage.
#
# Outputs:
#   1. $MOLTBOOK_HOME/reports/PIPELINE-STATUS.md  — always rewritten. It sits
#      under reports/, which the public data sync publishes, so every path in
#      it is written relative to MOLTBOOK_HOME (rel, RFC-0051)
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
# 512: the findings header plus one F-section. Below the retired decision
# packet's 1024 because a findings file with no F1 is legitimately short;
# like the report floor this only catches the died-mid-write shape.
MIN_FINDINGS_BYTES=512

HOUR=$(date +%H)
WEEKDAY=$(date +%u)   # Mon=1 .. Sun=7 (Sat=6)

RESULTS=()   # "OK<TAB>job<TAB>detail" / "FAIL<TAB>job<TAB>detail"

ok()   { RESULTS+=("OK	$1	$2"); }
fail() { RESULTS+=("FAIL	$1	$2"); }
skip() { RESULTS+=("SKIP	$1	$2"); }

# launchd_problem <job> <log> — prints why launchd's own view of the job is bad
# and returns 0, else returns 1. A job still holding a PID at check time has
# not finished ("still running"); a nonzero LastExitStatus is a failure even if
# the log tail shows no error line (P2-04.15). Read-only: nothing is stopped.
launchd_problem() {
    local out pid exit_status
    out=$(launchctl list "com.moltbook.$1" 2>/dev/null) || return 1
    pid=$(printf '%s\n' "$out" | sed -n 's/.*"PID" = \([0-9][0-9]*\);.*/\1/p')
    exit_status=$(printf '%s\n' "$out" | sed -n 's/.*"LastExitStatus" = \(-\{0,1\}[0-9][0-9]*\);.*/\1/p')
    if [[ -n "$pid" ]]; then
        local mtime; mtime=$(mtime_of "$2")
        printf 'still running (pid %s), log last written %s' "$pid" "$(date -r "$mtime" '+%m-%d %H:%M')"
        return 0
    fi
    if [[ -n "$exit_status" && "$exit_status" != 0 ]]; then
        printf 'last exit %s (launchctl LastExitStatus)' "$exit_status"
        return 0
    fi
    return 1
}

# A job whose plist is not installed is not a failure — a subset install
# (declarative reconcile removes unflagged jobs) would otherwise read as
# permanently broken (2026-07-29 codex review P2).
scheduled() { [[ -f "$HOME/Library/LaunchAgents/com.moltbook.$1.plist" ]]; }

# rel <path> — MOLTBOOK_HOME-relative, and the home as ~ in whatever is left
# (the rule of core/portable_path.py, RFC-0051). The tilde goes through a
# variable: a literal ~ in the replacement is tilde-expanded by some bashes.
rel() {
    local p="${1#"$MOLTBOOK_HOME"/}" tilde='~'
    (( ${#HOME} > 1 )) && p="${p//"$HOME"/$tilde}"
    printf '%s' "$p"
}

mtime_of() { stat -f %m "$1" 2>/dev/null || echo 0; }
size_of()  { stat -f %z "$1" 2>/dev/null || echo 0; }

epoch_at() {  # epoch_at YYYY-MM-DD HH:MM
    date -j -f "%Y-%m-%d %H:%M" "$1 $2" +%s 2>/dev/null || echo 0
}

log_healthy() {  # log_healthy <job> <logfile> <min_mtime_epoch> <detail_period>
    local job="$1" log="$2" min_epoch="$3" period="$4"
    if [[ ! -f "$log" ]]; then
        fail "$job" "log missing: $(rel "$log")"
        return
    fi
    local why
    if why=$(launchd_problem "$job" "$log"); then
        fail "$job" "$why"
        return
    fi
    local mtime; mtime=$(mtime_of "$log")
    if (( mtime < min_epoch )); then
        fail "$job" "did not run for $period (log mtime $(date -r "$mtime" '+%m-%d %H:%M'))"
        return
    fi
    if tail -n 30 "$log" | grep -qiE 'traceback|^ERROR|error:'; then
        fail "$job" "ran for $period but the log tail shows errors: $(rel "$log")"
        return
    fi
    ok "$job" "last run $(date -r "$mtime" '+%m-%d %H:%M')"
}

# --- Anchor dates: the most recent period each job should have covered ---

# Saturday chain (insight 08:00, report 09:00, findings by 13:00). Before a
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
    if why=$(launchd_problem weekly-pipeline "$LOG_DIR/weekly-pipeline-launchd.log"); then
        fail "weekly-report" "$why"
    elif (( report_size >= MIN_REPORT_BYTES )); then
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

    # docs-consistency: counts transcribed from the stage-6b JSON (P1-05.5), no
    # parsing beyond two integers and the abstained check names. An abstain is
    # shown, not failed — whether it needs a repair is the Saturday gate's call.
    docscan_json="$MOLTBOOK_HOME/pipeline/docs-consistency/docs-consistency-${report_end}.json"
    if [[ -f "$docscan_json" ]]; then
        docscan_readings=$(sed -n 's/^  "readings_count": *\([0-9][0-9]*\).*/\1/p' "$docscan_json")
        docscan_abstain=$(sed -n 's/^  "abstain_count": *\([0-9][0-9]*\).*/\1/p' "$docscan_json")
        docscan_checks=$(awk '/^  "errors": \[/ {f=1} f && /"check":/ {gsub(/.*"check": "|".*/, ""); print}' "$docscan_json" | sort -u | tr '\n' ',')
        if [[ -z "$docscan_abstain" ]]; then
            ok "docs-consistency" "docs-consistency-${report_end}.json (no counts: written before abstain_count)"
        elif (( docscan_abstain > 0 )); then
            ok "docs-consistency" "readings ${docscan_readings:-?} / abstain ${docscan_abstain} (${docscan_checks%,}) — docs-consistency-${report_end}.json"
        else
            ok "docs-consistency" "readings ${docscan_readings:-?} / abstain 0"
        fi
    fi

    # chain run: the same answer scripts/pipeline_run_status.py gives the gate,
    # from the same audit lines (P2-04.13 PR-B). Latest run for the week ending
    # $findings_end must have a chain_end and no `"result": "fail"` stage.
    chain_audit="$LOG_DIR/weekly-pipeline-audit.jsonl"
    chain_run=""
    [[ -f "$chain_audit" ]] && chain_run=$(grep -o "\"run_id\": \"weekly-${findings_end}-[0-9]*\"" "$chain_audit" \
        | tail -n 1 | sed 's/.*: "\(.*\)"/\1/')
    if [[ -z "$chain_run" ]]; then
        fail "weekly-chain" "no chain run recorded for the week ending ${findings_end} (expected by Sat 13:00)"
    else
        run_lines=$(grep -F "\"run_id\": \"${chain_run}\"" "$chain_audit")
        failed_stages=$(printf '%s\n' "$run_lines" | grep '"result": "fail"' \
            | sed -n 's/.*"stage": "\([a-z_0-9]*\)".*"reason": "\([A-Z_0-9]*\)".*/\1=\2/p' | tr '\n' ' ')
        chain_reasons=$(printf '%s\n' "$run_lines" | grep '"event": "chain_end"' | tail -n 1 \
            | sed -n 's/.*"reasons": "\([^"]*\)".*/\1/p')
        if ! printf '%s\n' "$run_lines" | grep -q '"event": "chain_end"'; then
            fail "weekly-chain" "${chain_run} has no chain_end (died mid-chain)"
        elif [[ -n "${failed_stages// /}" ]]; then
            fail "weekly-chain" "${chain_run} failed stages: ${failed_stages}— chain reasons: ${chain_reasons:-none}"
        else
            ok "weekly-chain" "${chain_run} completed — chain reasons: ${chain_reasons:-none}"
        fi
    fi
else
    skip "weekly-report" "not scheduled (weekly-pipeline plist absent)"
    skip "weekly-findings" "not scheduled (weekly-pipeline plist absent)"
    skip "weekly-chain" "not scheduled (weekly-pipeline plist absent)"
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

# --- sync-data: daily 05:30 (com.moltbook.sync-data, installed by hand, not by install-schedule) ---
# RFC-0051. Since P2-04.2 a failed sync (the home-path gate refusing to commit,
# a failed push) exits nonzero and puts its ERROR line in the launchd log; this
# row is the independent check that a sync commit actually landed.
# Expectation: a `sync:` commit from today's 05:30 run (yesterday's before
# 06:00). A healthy day always has something to commit — distill rewrites
# knowledge.json daily and every agent session rewrites its comment report; the
# data repo shows one sync commit per day 2026-09-23..10-15 — so a day with
# "No changes to sync." is itself a stopped pipeline.
# The commit time is read from the data repo's HEAD reflog as a file: calling
# git would add a dependency outside the HARD CONSTRAINT above.
DATA_REPO="$HOME/MyAI_Lab/contemplative-agent-data"   # as in scripts/sync-research-data.sh
if scheduled sync-data; then
    if (( 10#$HOUR < 6 )); then
        sync_day=$(date -v-1d +%Y-%m-%d)
    else
        sync_day=$(date +%Y-%m-%d)
    fi
    reflog="$DATA_REPO/.git/logs/HEAD"
    last_sync=""
    if [[ -r "$reflog" ]]; then
        # "<old> <new> <name> <email> <epoch> <tz>\tcommit: sync: <ts>"; last match wins
        last_sync=$(awk -F'\t' 'index($2, "commit: sync: ") == 1 { n = split($1, f, " "); e = f[n - 1] } END { print e }' "$reflog")
    fi
    if why=$(launchd_problem sync-data "$LOG_DIR/sync-data-launchd.log"); then
        fail "sync-data" "$why"
    elif [[ ! "$last_sync" =~ ^[0-9]+$ ]]; then
        fail "sync-data" "no sync commit in the data repo's reflog ($(rel "$reflog"))"
    elif (( last_sync < $(epoch_at "$sync_day" "05:00") )); then
        fail "sync-data" "no sync commit since $sync_day 05:30 (last $(date -r "$last_sync" '+%m-%d %H:%M')) — see logs/sync-data-launchd.log"
    else
        ok "sync-data" "last sync commit $(date -r "$last_sync" '+%m-%d %H:%M')"
    fi
else
    skip "sync-data" "not scheduled"
fi

# --- Last human gate (P2-01.6, dead-man reading) ---
# The newest gate_record in pipeline-metrics.jsonl, shown as a date and whole
# weeks. A reading only (D-P2-01-4 = B for the display; the fail row after N
# weeks of absence waits for D-P4-01-3 and is NOT added here): it is a SKIP-class
# row, so it can never put the FAIL set or the notification in motion. Pure
# grep/sed/date, within the HARD CONSTRAINT above.
gate_log="$LOG_DIR/pipeline-metrics.jsonl"
last_gate=""
if [[ -r "$gate_log" ]]; then
    last_gate=$(grep '"event": "gate_record"' "$gate_log" | tail -1 \
        | sed -n 's/.*"ts": "\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\)T.*/\1/p')
fi
if [[ "$last_gate" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    gate_epoch=$(epoch_at "$last_gate" "00:00")
    gate_weeks=$(( ($(date +%s) - gate_epoch) / 604800 ))
    skip "last-human-gate" "last human gate: ${last_gate} (${gate_weeks} weeks ago)"
else
    skip "last-human-gate" "last human gate: none recorded"
fi

# --- agent: today's sessions ran and left a comment report (P2-04.4a) ---
# Dates here are UTC: llm-calls-<date>.jsonl and comment-report-<date>.md are
# named by the writer's UTC day. A day with LLM-call rows but no comment report
# written since is the shape of "the model answered nothing" (Ollama down).
# A genuinely quiet day (a session that found nothing to answer) reads the same,
# so the row says which half is missing; the gate decides.
UTC_TODAY=$(date -u +%Y-%m-%d)
if scheduled agent; then
    calls_file="$LOG_DIR/llm-calls-${UTC_TODAY}.jsonl"
    report_file_today="$MOLTBOOK_HOME/reports/comment-reports/comment-report-${UTC_TODAY}.md"
    if why=$(launchd_problem agent "$LOG_DIR/agent-launchd.log"); then
        fail "agent" "$why"
    elif [[ ! -s "$calls_file" ]]; then
        fail "agent" "no LLM calls recorded for $UTC_TODAY (UTC): $(rel "$calls_file") — sessions not running or the model stopped"
    elif [[ ! -f "$report_file_today" ]] || (( $(mtime_of "$report_file_today") < $(mtime_of "$calls_file") - 7200 )); then
        fail "agent" "LLM calls recorded for $UTC_TODAY (UTC) but no fresh comment report: $(rel "$report_file_today")"
    else
        ok "agent" "comment report $UTC_TODAY, last LLM call $(date -r "$(mtime_of "$calls_file")" '+%m-%d %H:%M')"
    fi

    # --- moltbook: the last 24 h of api-audit.jsonl (P2-04.4b) ---
    # Rows >= 1 and none with 200 <= status < 300 is an outage, a revoked key
    # or a closed platform; a transport failure (status null) counts toward
    # the rows. 3xx is not a success: the client does not follow redirects.
    # The tail bounds the read; a quiet day has few rows and is not ❌ (rows=0).
    audit_file="$LOG_DIR/api-audit.jsonl"
    cutoff=$(date -u -v-24H +%Y-%m-%dT%H:%M:%S)
    if [[ -f "$audit_file" ]]; then
        read -r api_rows api_ok <<< "$(tail -n 20000 "$audit_file" | awk -v cutoff="$cutoff" '
            match($0, /"ts": *"[^"]*"/) {
                ts = substr($0, RSTART, RLENGTH); sub(/^"ts": *"/, "", ts); sub(/"$/, "", ts)
                if (substr(ts, 1, 19) < cutoff) next
                rows++
                if (match($0, /"status": *[0-9]+/)) {
                    st = substr($0, RSTART, RLENGTH); sub(/^"status": */, "", st)
                    if (st + 0 >= 200 && st + 0 < 300) okc++
                }
            }
            END { print rows + 0, okc + 0 }')"
    else
        api_rows=0; api_ok=0
    fi
    if (( api_rows > 0 && api_ok == 0 )); then
        fail "moltbook" "ERROR: $api_rows API calls in the last 24 h, none with a 2xx status ($(rel "$audit_file"))"
    else
        ok "moltbook" "$api_ok of $api_rows API calls in the last 24 h were 2xx"
    fi

    # --- moltbook-7d: no comment report for 7 days (P2-04.4c) ---
    # The platform-closure shape. Informational for the P4-01 review event: the
    # watchdog stops nothing.
    seen_report=""
    for back in 0 1 2 3 4 5 6; do
        day=$(date -u -v-"${back}"d +%Y-%m-%d)
        if [[ -f "$MOLTBOOK_HOME/reports/comment-reports/comment-report-${day}.md" ]]; then
            seen_report="$day"; break
        fi
    done
    if [[ -n "$seen_report" ]]; then
        ok "moltbook-7d" "latest comment report $seen_report"
    else
        fail "moltbook-7d" "no comment report in the last 7 days (UTC) — platform closed or sessions silent"
    fi
else
    skip "agent" "not scheduled"
    skip "moltbook" "not scheduled"
    skip "moltbook-7d" "not scheduled"
fi

# --- disk: free space under MOLTBOOK_HOME (P2-04.10) ---
# `df -kP`: 1 KiB blocks, POSIX columns, identical on BSD and GNU. Default
# floor 10 GB (override: WATCHDOG_MIN_FREE_KB).
MIN_FREE_KB="${WATCHDOG_MIN_FREE_KB:-10485760}"
free_kb=$(df -kP "$MOLTBOOK_HOME" 2>/dev/null | awk 'NR == 2 { print $4 }')
if [[ ! "$free_kb" =~ ^[0-9]+$ ]]; then
    fail "disk" "could not read free space for MOLTBOOK_HOME"
elif (( free_kb < MIN_FREE_KB )); then
    fail "disk" "$(( free_kb / 1024 )) MB free under MOLTBOOK_HOME (floor $(( MIN_FREE_KB / 1024 )) MB)"
else
    ok "disk" "$(( free_kb / 1048576 )) GB free"
fi

# --- log-rotation: agent-launchd.log rotated within two backup cycles (P2-04.10) ---
# com.moltbook.backup rotates it every Monday and SKIPS (ERROR in its log) when
# a session holds the file open. The newest generation's mtime is the last
# successful rotation (gzip keeps the file's last-write time); older than 14
# days means two skipped Mondays in a row. Needs no state file.
if scheduled backup; then
    rotated="$LOG_DIR/agent-launchd.log.1.gz"
    if [[ ! -f "$rotated" ]]; then
        skip "log-rotation" "no rotated generation yet ($(rel "$rotated"))"
    elif (( $(date +%s) - $(mtime_of "$rotated") > 14 * 86400 )); then
        fail "log-rotation" "agent-launchd.log last rotated $(date -r "$(mtime_of "$rotated")" '+%m-%d') — rotation skipped two weeks running (see logs/backup-launchd.log)"
    else
        ok "log-rotation" "last rotated $(date -r "$(mtime_of "$rotated")" '+%m-%d')"
    fi
else
    skip "log-rotation" "not scheduled"
fi

# --- Previous FAIL set (for notification dedup) ---
prev_fails=""
[[ -f "$STATUS" ]] && prev_fails=$(grep -- '- ❌' "$STATUS" 2>/dev/null | awk '{print $3}' | sort | tr '\n' ',')

cur_fails=""
for line in "${RESULTS[@]}"; do
    [[ "$line" == FAIL* ]] && cur_fails+="$(echo "$line" | cut -f2),"
done
# printf, not echo: an empty echo still emits a newline, which tr would turn
# into a lone "," — a truthy failure set on a fully healthy run.
if [[ -n "$cur_fails" ]]; then
    cur_fails=$(printf '%s' "${cur_fails%,}" | tr ',' '\n' | sort | tr '\n' ',')
fi

# --- Notify only when the FAIL set changed (new failure or recovery) ---
# Done BEFORE the status file is written so the attempt and its exit code can
# be recorded in it (P2-04.17c): Notification Center cannot be observed from
# here (no GUI session, Focus mode), but a nonzero osascript rc can, and a
# reader of the public copy needs to tell "no alert sent" from "alert failed".
notified="none (no change in the failing set)"
if [[ "$cur_fails" != "$prev_fails" ]]; then
    if [[ -n "$cur_fails" ]]; then
        failing=$(echo "${cur_fails%,}" | tr ',' ' ')
        /usr/bin/osascript -e "display notification \"failing: ${failing} — see PIPELINE-STATUS.md\" with title \"Moltbook pipeline\"" 2>/dev/null
        notify_rc=$?
        notified="$(date '+%Y-%m-%d %H:%M') rc=${notify_rc}"
    elif [[ -n "$prev_fails" ]]; then
        # Recovery is a state change too — without this the operator learns
        # the pipeline healed only by reading the status file.
        /usr/bin/osascript -e "display notification \"recovered — all pipelines healthy\" with title \"Moltbook pipeline\"" 2>/dev/null
        notify_rc=$?
        notified="$(date '+%Y-%m-%d %H:%M') rc=${notify_rc}"
    fi
fi

# Next scheduled run: daily 04:30, one hour of grace. A reader (the gate, or a
# person looking at the public copy) who sees "now" past this time knows the
# watchdog itself has gone quiet, which no ✅ row can say.
if (( 10#$HOUR < 5 )); then next_day=$(date +%Y-%m-%d); else next_day=$(date -v+1d +%Y-%m-%d); fi

mkdir -p "$(dirname "$STATUS")"
STATUS_TMP="$STATUS.tmp.$$"
{
    echo "# Pipeline Status"
    echo ""
    echo "Last check: $(date '+%Y-%m-%d %H:%M %Z') — \`scripts/pipeline_watchdog.sh\`"
    echo "Next check by: ${next_day} 05:30 (daily 04:30 run + 1 h)"
    echo "Notified: ${notified}"
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
        echo "**${fail_count} pipeline(s) failing.** Logs: \`$(rel "$LOG_DIR")\`. The Saturday"
        echo "gate session (\`/weekly-gate\`) reads this file before any decision."
    fi
} > "$STATUS_TMP"
if ! mv "$STATUS_TMP" "$STATUS"; then
    # A status file that silently stays old reads as "healthy since then".
    echo "ERROR: could not write $(rel "$STATUS") (mv failed)" >&2
    rm -f "$STATUS_TMP"
    exit 3
fi

echo "watchdog: $(grep -c '^- ' "$STATUS") checks, failures: ${cur_fails:-none}"
[[ -z "$cur_fails" ]] || exit 2
exit 0

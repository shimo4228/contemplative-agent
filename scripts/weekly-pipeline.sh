#!/bin/bash
# Unattended weekly chain (ADR-0085; single-session redesign 2026-08-24):
# materials ($MOLTBOOK_HOME/logs/weekly-pipeline/<run_id>/materials.md) → ONE
# claude session (/weekly-report: six-section instrument document + diagnosis
# + draft RFC filing) → Sample splice (RFC-0026: the collector's random sample
# is copied into the report's `## Sample` heading here, before promotion) →
# promote → deterministic instruments (value-layer due check, dead-code scan,
# docs-consistency scan, never-selected reading, confusion-pair reading +
# archive candidates, comment-outcome reading + the reply rate beside each
# candidate; the 7b/7d readings live in
# scripts/never_selected_reading.py / comment_outcomes_reading.py) → spawn
# recording. The dead-code and docs-consistency scans drop to monthly after 4
# empty runs (scan_cadence.py, P1-04.6). Human involvement stays compressed
# into the Saturday gate
# (/weekly-gate, which now reads the findings and instrument JSONs directly —
# the decision-packet builder is retired); repairs are NOT made here: the
# session files drafts into rfcs/ (the public ledger) and the task-triage loop
# (Sat 14:07 tick) judges and dispatches them. Nothing here commits, pushes,
# or adopts — the unattended run only writes the working tree, and the Saturday
# gate is what puts a filing into a public commit (2026-08-25 author decision,
# harness RFC-0001).
#
# Fail-forward: every stage failure becomes a reason code in the audit log and
# the run continues. The one hard requirement is the report WHEN THE SESSION
# RAN: with no complete report from a session that was asked for one there is
# no observation to gate on, so the run aborts (the watchdog catches the
# missing report). Instruments-only mode (P2-02.2): when the report stage is
# not requested (not in MOLTBOOK_PIPELINE_STAGES, or --skip-report) and no
# canonical report exists for the week, the deterministic stages still run —
# `claude` is not required, REPORT_ABSENT is recorded, and promote / ledger /
# spawn (which only make sense around a report) do not fire.
#
# Usage:
#   ./scripts/weekly-pipeline.sh                       # full chain, yesterday-ending week
#   ./scripts/weekly-pipeline.sh --end-date 2026-07-24 # explicit week
#   ./scripts/weekly-pipeline.sh --skip-report --end-date 2026-07-24
#                                                      # instruments only, existing report
#   MOLTBOOK_PIPELINE_STAGES=report ./scripts/weekly-pipeline.sh
#   MOLTBOOK_PIPELINE_STAGES=valuelayer,deadcode,docsscan ./scripts/weekly-pipeline.sh
#                                                      # instruments only, no claude needed
set -uo pipefail

# --- Config ---
MOLTBOOK_HOME="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
# The weekly session interpolates this into permission rules, so its shape is
# load-bearing (same reason END_DATE gets a shape check below):
#   absolute — rules are built by prefixing `/` to reach the `//absolute` form;
#     a relative value renders them project-root-anchored, where the allow rule
#     grants nothing (loud) but the deny rules protect nothing (silent).
#   no permission-spec metacharacters — `,` splits one rule into two malformed
#     ones, `()[]*?` reshape the glob, `\` is consumed as a glob escape
#     (measured 2026-08: a deny over a path containing `\` matched nothing
#     while the allow still matched). Stated as an ALLOWLIST.
MOLTBOOK_HOME="${MOLTBOOK_HOME%/}"
if [[ "$MOLTBOOK_HOME" != /* ]]; then
    echo "ERROR: MOLTBOOK_HOME must be an absolute path (got: $MOLTBOOK_HOME)" >&2
    exit 1
fi
if ! [[ "$MOLTBOOK_HOME" =~ ^[A-Za-z0-9._/@+-]+$ ]]; then
    echo "ERROR: MOLTBOOK_HOME may only contain [A-Za-z0-9._/@+-] — the weekly" >&2
    echo "       session builds tool-permission rules from it, and any other" >&2
    echo "       character can silently reshape a rule into one that protects" >&2
    echo "       nothing (got: $MOLTBOOK_HOME)" >&2
    exit 1
fi
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# `--setting-sources project` resolves "project" against the CWD, so the
# session's isolation below depends on where this script was started. The
# plist pins WorkingDirectory; a hand-run backfill does not, and from $HOME
# "project" IS the operator's user settings file — the flag silently becomes
# a no-op (2026-08-16 security review).
cd "$PROJECT_ROOT" || { echo "ERROR: cannot cd to PROJECT_ROOT: $PROJECT_ROOT" >&2; exit 1; }
# Same allowlist shape check as MOLTBOOK_HOME, same reason: the weekly
# session's Edit rule over the staging dir is built from this path.
if ! [[ "$PROJECT_ROOT" =~ ^[A-Za-z0-9._/@+-]+$ ]]; then
    echo "ERROR: PROJECT_ROOT contains permission-spec metacharacters: $PROJECT_ROOT" >&2
    exit 1
fi
SCRIPTS="$PROJECT_ROOT/scripts"
REPORT_DIR="$MOLTBOOK_HOME/reports/analysis"
STAGED_DIR="$MOLTBOOK_HOME/.staged"
AUDIT="$MOLTBOOK_HOME/logs/weekly-pipeline-audit.jsonl"
# pipeline-metrics.jsonl is now written only by the Saturday gate
# (weekly-gate Step 7 via pipeline_audit.py); the chain no longer appends to it.
# Overridable for tests only: the fault column must be able to point the
# filing seam at a sandbox store and a stub claims recorder without touching
# the real ledger (.notes/claims.jsonl is append-only history).
# rfcs/ is a TRACKED directory of the public repo (ADR-0049 / harness RFC-0001):
# the unattended run only WRITES here — the commit that puts a filing in front
# of the public is the Saturday weekly-gate's, after a human sensitivity pass
# (2026-08-25 author decision).
TASKS_DIR="${PIPELINE_TASKS_DIR:-$PROJECT_ROOT/rfcs}"
CLAIMS_PY="${PIPELINE_CLAIMS_PY:-$HOME/.claude/scripts/claims.py}"
# Same shape check as MOLTBOOK_HOME / PROJECT_ROOT, same reason: TASKS_DIR is
# interpolated into the session's Edit rule (2026-08-24 security review LOW).
if [[ "$TASKS_DIR" != /* ]] || ! [[ "$TASKS_DIR" =~ ^[A-Za-z0-9._/@+-]+$ ]]; then
    echo "ERROR: TASKS_DIR must be absolute and free of permission-spec metacharacters (got: $TASKS_DIR)" >&2
    exit 1
fi

# --- Session permission scope (T-CHAIN-PERM-SWEEP, 2026-08-15; redesigned
# --- to ONE unattended session 2026-08-24) -----------------------------------
# The chain now starts exactly one `claude -p` session. The six mechanics that
# decide how such a session is bounded were verified against the real binary
# (T-CHAIN-PERM-SWEEP; full text in git history of this file at 4f53259):
#   1. --allowedTools only ADDS; the ambient settings allow rules are consulted
#      before the permission mode.
#   2. Only DENY rules outrank both.
#   3. File writes are gated by Edit(...) rules, which cover every file-editing
#      tool including Write.
#   4. The Bash tool statically refuses `>` redirection outside the session's
#      working directories; what still writes are commands with FLAGS
#      (tee, cp, git log --output, sed -i, curl -o).
#   5. Denying `Bash` denies the NAME, not the capability — Monitor / Agent /
#      Workflow / CronCreate reach a shell anyway. `--tools` (the allowlist
#      over the built-in tool SET) removes them structurally;
#      `--strict-mcp-config` with no --mcp-config does the same for MCP.
#   6. A Bash deny list cannot be completed while the ambient allow list is
#      loaded (`Bash(uv:*)` is a universal wrapper). `--setting-sources
#      project` drops the user layer — 106 allow rules, hooks,
#      additionalDirectories — and keeps auth.
#
# The weekly session reads the materials file (which embeds other agents'
# post bodies inside a nonce frame — untrusted), synthesizes the report,
# diagnoses it, and files draft RFCs. It holds NO Bash: everything it
# writes goes through Edit/Write under the exact-path rules below, and the
# claims.jsonl spawn recording is done deterministically by this script from
# the staged filings (the session cannot append to the claims log).
#
# A name the CLI does not recognise in --tools is discarded in SILENCE
# (measured 2026-08-15), so a renamed built-in shrinks the session with no
# error path. C-SCOPE-8 in tests/test_weekly_pipeline_session_scope_shell.py
# asks the real CLI which names it honours. `--tools "default"` as a sole
# value fails OPEN to the whole built-in set — never reach for it.
WEEKLY_TOOLS="Read,Glob,Grep,Edit,Write,Skill"

# Writer model (P2-02.3). Unset = the CLI's own default, recorded as
# `model=default` in chain_start (the id the default resolves to is not
# readable from here; the document's `writer:` stamp carries what the writer
# reports). Set PIPELINE_WEEKLY_MODEL to pin the session — which id to pin is
# the owner's call (a model change is a regime boundary for the longitudinal
# readings: docs/runbooks/model-swap.md once it exists). The value is
# interpolated into argv only, but gets the same shape check as the paths.
WEEKLY_MODEL="${PIPELINE_WEEKLY_MODEL:-}"
if [[ -n "$WEEKLY_MODEL" ]] && ! [[ "$WEEKLY_MODEL" =~ ^[]A-Za-z0-9._:/[-]+$ ]]; then
    echo "ERROR: PIPELINE_WEEKLY_MODEL has characters outside []A-Za-z0-9._:/[-] (got: $WEEKLY_MODEL)" >&2
    exit 1
fi
MODEL_ARGS=()
[[ -n "$WEEKLY_MODEL" ]] && MODEL_ARGS=(--model "$WEEKLY_MODEL")

# Timeouts. The weekly session does the work of the former report (45min cap)
# + diagnosis (30min) sessions in one (the translation session was retired
# with RFC-0010, 2026-08-26); 90 min total is a hang detector, not a budget
# (the three-session chain measured 18-20 min end to end on real runs).
WEEKLY_TIMEOUT="${PIPELINE_WEEKLY_TIMEOUT:-5400}"
DEADCODE_TIMEOUT="${PIPELINE_DEADCODE_TIMEOUT:-300}"
DOCSCAN_TIMEOUT="${PIPELINE_DOCSCAN_TIMEOUT:-180}"
IDENTITY_TIMEOUT="${PIPELINE_IDENTITY_TIMEOUT:-900}"
CHAIN_DEADLINE_SECONDS="${PIPELINE_DEADLINE_SECONDS:-10800}"   # 09:00 → 12:00

STAGES="${MOLTBOOK_PIPELINE_STAGES:-report,valuelayer,deadcode,docsscan}"

# Installed launchd state the timing guards read (P2-04.9 / .17); overridable
# so the tests can point them at fixtures.
LAUNCH_AGENTS_DIR="${PIPELINE_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
WEEKLY_PLIST="$LAUNCH_AGENTS_DIR/com.moltbook.weekly-pipeline.plist"
AGENT_PLIST="$LAUNCH_AGENTS_DIR/com.moltbook.agent.plist"
WATCHDOG_STATUS="${PIPELINE_WATCHDOG_STATUS:-$MOLTBOOK_HOME/reports/PIPELINE-STATUS.md}"
LATE_START_MINUTES=60            # CHAIN_LATE_START threshold (warn only)
WATCHDOG_STALE_HOURS=72          # WATCHDOG_STALE threshold (warn only)
KEEP_RUN_DIRS="${PIPELINE_KEEP_RUNS:-12}"   # run-log generations kept at chain end

END_DATE=""
END_DATE_EXPLICIT=0
DAYS=7
SKIP_REPORT=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --end-date)   END_DATE="$2"; END_DATE_EXPLICIT=1; shift 2 ;;
        --days)       DAYS="$2"; shift 2 ;;
        --skip-report) SKIP_REPORT=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--end-date YYYY-MM-DD] [--days N] [--skip-report]"
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done
# Captured once and reused by the identity live-run guard below: a run started
# just before midnight would otherwise default END_DATE off one "yesterday" and
# compare against another.
# TZ premise: "yesterday" and every launchd slot are LOCAL time, records are
# UTC (docs/CONFIGURATION.md "Time zone and power"); END_DATE is not UTC-derived.
YESTERDAY=$(date -v-1d +%Y-%m-%d)
[[ -z "$END_DATE" ]] && END_DATE="$YESTERDAY"
# END_DATE flows into artifact paths, permission rules and the value-layer
# --as-of; validate the shape once for every consumer.
if ! [[ "$END_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "ERROR: --end-date must be YYYY-MM-DD (got: $END_DATE)" >&2
    exit 1
fi

RUN_ID="weekly-${END_DATE}-$(date +%H%M%S)"
RUN_LOG_DIR="$MOLTBOOK_HOME/logs/weekly-pipeline/$RUN_ID"
MATERIALS="$RUN_LOG_DIR/materials.md"
# weekly-analysis.sh writes the Random Sample section beside the materials
# (RFC-0026); the splice below copies it into the report's `## Sample` slot.
SAMPLE_SOURCE="${MATERIALS%.md}-sample.md"
# The session writes into reports/.private/ (excluded from the public
# sync-research-data rsync) and the chain promotes to the canonical paths only
# after the structural gate below — the tmp -> check -> promote order the old
# report generator had, restored at the pipeline seam (2026-08-24 security
# review MEDIUM: a truncated or injected report must never sit on a path the
# public sync or next week's PREV_REPORTS glob can pick up).
PRIVATE_DIR="$MOLTBOOK_HOME/reports/.private"
# Per-run task staging: the session files drafts HERE, never into the
# live store — the store supports concurrent sessions, so live-store writes
# plus a directory diff would misattribute concurrent filings and let a
# steered session clobber owner-written tasks (codex review 2026-08-24 P1).
# The chain validates, numbers and moves staged drafts after the report gate.
PRIVATE_TASKS="$PRIVATE_DIR/tasks-$END_DATE"
REPORT_PATH="$REPORT_DIR/weekly-${END_DATE}.md"
FINDINGS_MD="$REPORT_DIR/weekly-${END_DATE}-findings.md"
# Japanese translations retired with the RFC-0010 instrument redesign
# (2026-08-26): the operator no longer reads this document directly — the
# Saturday gate session explains each pending decision in Japanese instead.
# Historical .ja.md files stay in place untouched.
LEDGER_FILE="$REPORT_DIR/observation-ledger.jsonl"
LEDGER_DELTA_STAGED="$PRIVATE_DIR/ledger-delta-${END_DATE}.jsonl"

START_EPOCH=$(date +%s)
REASONS=""          # accumulated reason codes (comma separated)

mkdir -p "$RUN_LOG_DIR" "$TASKS_DIR"
# Session transcripts can carry content the session saw; keep them owner-only
# (2026-07-29 security review H2).
chmod 700 "$RUN_LOG_DIR" 2>/dev/null || true

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

# timeout binary (P2-04.18): `timeout`, then Homebrew coreutils' `gtimeout`,
# then an explicit $TIMEOUT_BIN. Recorded in chain_start as timeout_bin=; with
# none, the stages run without a hang detector and NO_TIMEOUT_BIN says so.
resolve_timeout_bin() {
    local cand
    for cand in timeout gtimeout; do
        if command -v "$cand" >/dev/null 2>&1; then command -v "$cand"; return; fi
    done
    if [[ -n "${TIMEOUT_BIN:-}" && -x "$TIMEOUT_BIN" ]]; then printf '%s' "$TIMEOUT_BIN"; return; fi
    printf 'none'
}
TIMEOUT_RESOLVED="$(resolve_timeout_bin)"

with_timeout() {  # with_timeout <seconds> <cmd...>
    local secs="$1"; shift
    if [[ "$TIMEOUT_RESOLVED" != none ]]; then
        "$TIMEOUT_RESOLVED" "$secs" "$@" 9>&-
    else
        "$@" 9>&-   # degradation: recorded as NO_TIMEOUT_BIN at preflight
    fi
}

# The report's machine contract (moved here from weekly-analysis.sh when that
# script became materials-only): a csv of the absent section headings,
# empty = complete. Size is not the contract — 2026-08-21 promoted a
# 37,409-byte report whose head was gone. Since the RFC-0010 instrument
# redesign (2026-08-26) the contract is the six instrument headings; content
# under each is conditional (one honest line is complete), the headings are
# not. Exact heading words, not letters: the format version is part of the
# calibration stamp longitudinal readers partition by.
report_missing_parts() {  # report_missing_parts <file>
    local file="$1" heading missing=""
    for heading in Inventory Ledger Deviations Exceptions Sample Discarded; do
        grep -q "^## $heading" "$file" || missing="${missing:+$missing,}$heading"
    done
    printf '%s' "$missing"
}

# The report's structural contract is exactly six H2 headings (P2-04.14): the
# Sample splice used to make it seven. Counted on the file as written.
REPORT_H2_COUNT=6
report_h2_count() {  # report_h2_count <file>
    grep -c '^## ' "$1" || true
}

# --- Single-instance lock (P2-04.8) ---
# A second chain (a hand-run backfill, or a late launchd start overlapping the
# previous one) would race on reports/.private, the staging dir and the
# observation ledger. The flock lives on fd 9 of THIS shell: python only takes
# it, and because the lock belongs to the open file description the shell
# keeps, it holds until this process exits. Stage commands run through
# with_timeout with fd 9 closed (9>&-), so a descendant that outlives the chain
# cannot keep the lock held and make next week's chain skip. The file sits under logs/, which
# the public sync never mirrors.
LOCK_FILE="$MOLTBOOK_HOME/logs/.weekly.lock"
exec 9>"$LOCK_FILE"
if ! python3 -c 'import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)' 2>/dev/null; then
    audit stage_result stage=preflight result=skipped reason=CHAIN_ALREADY_RUNNING
    echo "[$RUN_ID] another weekly chain holds $LOCK_FILE — exiting (CHAIN_ALREADY_RUNNING)" >&2
    exit 0
fi

# --- Preflight (fail before burning work) ---
# `claude` is required only when the weekly session will actually start; an
# instruments-only run (P2-02.2) needs none of it.
NEED_BINS="git uv python3"
if stage_enabled report && [[ $SKIP_REPORT -eq 0 ]]; then NEED_BINS="claude $NEED_BINS"; fi
for bin in $NEED_BINS; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo "ERROR: '$bin' not found on PATH ($PATH)" >&2
        audit stage_result stage=preflight result=fail reason=PREFLIGHT_MISSING_BIN "bin=$bin"
        exit 1
    fi
done

# Effective-permission pin (P1-10.13): the session runs `--setting-sources
# project`, which loads .claude/settings.json (NOT settings.local.json -- the
# session never reads that one). Allow rules / hooks there add to what
# `--allowedTools` can outrank. Record what is there. When it widens the
# session, skip ONLY the headless report stage (reason
# PREFLIGHT_PROJECT_SETTINGS_WIDEN); the deterministic intakes keep running.
# Retire together with the flag if the chain moves to `--setting-sources ""`
# (preflight_project_settings.py).
REPORT_SKIP_REASON=""
if ! PROJECT_SETTINGS=$(python3 "$SCRIPTS/preflight_project_settings.py" --project-root "$PROJECT_ROOT"); then
    audit stage_result stage=preflight result=fail reason=PREFLIGHT_PROJECT_SETTINGS_UNREADABLE
    echo "ERROR: cannot inspect project settings under $PROJECT_ROOT/.claude" >&2
    exit 1
fi
PS_FIELDS=()
while IFS= read -r ps_line; do
    [[ -n "$ps_line" ]] && PS_FIELDS+=("$ps_line")
done <<< "$PROJECT_SETTINGS"
audit project_settings "${PS_FIELDS[@]}"
if grep -qx 'widen=1' <<< "$PROJECT_SETTINGS"; then
    REPORT_SKIP_REASON=PREFLIGHT_PROJECT_SETTINGS_WIDEN
    echo "WARN: $PROJECT_ROOT/.claude/settings.json adds allow rules, hooks or" >&2
    echo "      additional directories to the unattended weekly session" >&2
    echo "      (--setting-sources project loads it). Skipping the report stage;" >&2
    echo "      deterministic intakes continue. Remove them to restore it." >&2
fi

# Tool-set drift (P2-02.6): `--tools` drops an unrecognised name in silence, so
# ask the CLI what WEEKLY_TOOLS resolves to before spending a session on it.
# Drift aborts (a shrunken session fails with no error path); a probe that
# cannot read an answer is a reason code and the run goes on.
if stage_enabled report && [[ $SKIP_REPORT -eq 0 && -z "$REPORT_SKIP_REASON" ]]; then
    TOOLSET_DIFF="$(python3 "$SCRIPTS/claude_toolset_probe.py" --tools "$WEEKLY_TOOLS" \
        --cwd "$PROJECT_ROOT" 2>/dev/null)"
    case $? in
        0) ;;
        1)  audit stage_result stage=preflight result=fail reason=PREFLIGHT_TOOLSET_DRIFT "diff=$TOOLSET_DIFF"
            echo "ERROR: the claude CLI does not resolve WEEKLY_TOOLS to its declared names ($TOOLSET_DIFF)" >&2
            exit 1 ;;
        *)  add_reason PREFLIGHT_TOOLSET_PROBE_FAIL
            echo "WARNING: could not read the CLI's resolved tool set (PREFLIGHT_TOOLSET_PROBE_FAIL)" >&2 ;;
    esac
fi

if [[ "$TIMEOUT_RESOLVED" == none ]]; then
    add_reason NO_TIMEOUT_BIN
    echo "WARNING: no timeout/gtimeout/\$TIMEOUT_BIN — stages run without a hang detector (NO_TIMEOUT_BIN)" >&2
fi

# Late start (P2-04.9): minutes after the plist's own slot. Warn only. A run
# given an explicit --end-date is a hand-run backfill, so there is no slot to
# be late for.
LATE_MINUTES=unknown
if [[ "$END_DATE_EXPLICIT" -eq 0 ]]; then
    LATE_MINUTES="$(python3 "$SCRIPTS/chain_schedule_probe.py" late-minutes \
        --plist "$WEEKLY_PLIST" --now "$(date +%s)" 2>/dev/null || echo unknown)"
    if [[ "$LATE_MINUTES" =~ ^[0-9]+$ ]] && (( LATE_MINUTES >= LATE_START_MINUTES )); then
        add_reason CHAIN_LATE_START
    fi
fi

# Watchdog freshness (P2-04.17): the watchdog rewrites its status file on every
# run, so the file's mtime is the age of its last check. A missing file or one
# older than 72 h means the detection surface itself is down. Warn only.
WATCHDOG_AGE_H=none
if [[ -f "$WATCHDOG_STATUS" ]]; then
    WATCHDOG_AGE_H="$(python3 -c '
import os, sys, time
print(int((time.time() - os.stat(sys.argv[1]).st_mtime) // 3600))
' "$WATCHDOG_STATUS" 2>/dev/null || echo none)"
fi
if [[ ! "$WATCHDOG_AGE_H" =~ ^[0-9]+$ ]] || (( WATCHDOG_AGE_H > WATCHDOG_STALE_HOURS )); then
    add_reason WATCHDOG_STALE
fi

# CLI version (P2-02.3): `none` when no session will start or the binary has
# no answer — a missing field would read as "not recorded", not "not used".
CLAUDE_VERSION=none
if command -v claude >/dev/null 2>&1; then
    CLAUDE_VERSION="$(claude --version 2>/dev/null | head -1)"
    [[ -n "$CLAUDE_VERSION" ]] || CLAUDE_VERSION=unknown
fi

# Input provenance (P2-02.7): what the session's instructions are made of —
# HEAD, branch, uncommitted instruction changes, an instruction-files digest
# and the skill inventory (tracked / untracked). The checkout is the one the
# owner's interactive sessions also edit, so a week written from a feature
# branch or an uncommitted SKILL.md must say so. WARNING only: a missing
# week costs more than a week from an odd checkout.
PROV_GIT_HEAD=unknown PROV_BRANCH=unknown PROV_DIRTY=unknown
PROV_INSTR_SHA12=unknown PROV_SKILLS=unknown PROV_DRIFT=""
while IFS='=' read -r prov_k prov_v; do
    case "$prov_k" in
        git_head) PROV_GIT_HEAD="$prov_v" ;;
        branch) PROV_BRANCH="$prov_v" ;;
        dirty) PROV_DIRTY="$prov_v" ;;
        instr_sha12) PROV_INSTR_SHA12="$prov_v" ;;
        skills) PROV_SKILLS="$prov_v" ;;
        drift) PROV_DRIFT="$prov_v" ;;
    esac
done < <(python3 "$SCRIPTS/input_provenance.py" chain --root "$PROJECT_ROOT" 2>/dev/null)
if [[ -n "$PROV_DRIFT" ]]; then
    add_reason PREFLIGHT_WORKTREE_DRIFT
    echo "WARNING: PREFLIGHT_WORKTREE_DRIFT ($PROV_DRIFT: branch=$PROV_BRANCH dirty=$PROV_DIRTY) —" >&2
    echo "         this week's session reads instructions from a checkout that is not a clean main" >&2
fi

audit chain_start end_date="$END_DATE" stages="$STAGES" \
    git_head="$PROV_GIT_HEAD" branch="$PROV_BRANCH" dirty="$PROV_DIRTY" \
    instr_sha12="$PROV_INSTR_SHA12" skills="$PROV_SKILLS" worktree_drift="${PROV_DRIFT:-none}" \
    late_minutes="$LATE_MINUTES" watchdog_age_h="$WATCHDOG_AGE_H" \
    timeout_bin="$TIMEOUT_RESOLVED" \
    model="${WEEKLY_MODEL:-default}" claude_version="$CLAUDE_VERSION"
echo "[$RUN_ID] chain start (stages: $STAGES)"

# --- Stage 1: materials + the ONE weekly session ---
REPORT_RAN=0
if stage_enabled report && [[ $SKIP_REPORT -eq 0 && -z "$REPORT_SKIP_REASON" ]]; then
    REPORT_RAN=1
    echo "[$RUN_ID] stage 1a: materials (weekly-analysis.sh)"
    # Leftover pendings from an earlier aborted run must not survive into this
    # one: with deterministic pending names a stale snapshot could otherwise
    # be promoted as this week's baseline if today's producer fails and emits
    # none (2026-08-24 security review MEDIUM — this rm is the "preamble
    # removes leftovers" weekly-analysis.sh's state discipline relies on).
    rm -f "$REPORT_DIR"/.anomaly-sweep-state.pending* \
          "$REPORT_DIR"/.api-drift-state.pending* \
          "$REPORT_DIR"/.approval-join-state.pending*
    mkdir -p "$PRIVATE_DIR" "$PRIVATE_TASKS"
    chmod 700 "$PRIVATE_DIR" 2>/dev/null || true
    rm -f "$PRIVATE_DIR"/weekly-"$END_DATE"*.md "$PRIVATE_TASKS"/*.md \
          "$PRIVATE_DIR"/ledger-delta-"$END_DATE".jsonl
    if ! bash "$SCRIPTS/weekly-analysis.sh" --end-date "$END_DATE" --days "$DAYS" \
            --out "$MATERIALS" > "$RUN_LOG_DIR/materials.log" 2>&1; then
        audit stage_result stage=materials result=fail reason=MATERIALS_FAIL
        echo "ERROR: materials collection failed — no input for the weekly session, aborting" >&2
        echo "       (see $RUN_LOG_DIR/materials.log; the watchdog reports the missing report)" >&2
        exit 1
    fi
    audit stage_result stage=materials result=ok

    if deadline_exceeded; then
        add_reason CHAIN_DEADLINE
        audit stage_result stage=report result=skipped reason=CHAIN_DEADLINE
    else
        echo "[$RUN_ID] stage 1b: weekly session (/weekly-report)"
        # --add-dir is scoped to reports/ + logs/ (materials lives under
        # logs/weekly-pipeline/), NOT $MOLTBOOK_HOME. Do NOT read --add-dir as
        # a read boundary: it bounds the workspace, not the Read tool
        # (measured 2026-08-15) — hence the explicit Read denies. This is the
        # one session holding --add-dir over $MOLTBOOK_HOME/logs, and
        # `--setting-sources project` drops the user hooks including the
        # episode-log guard, so the CLAUDE.md ban on the raw episode logs
        # (the daily per-date JSONL and its .bak — the 2026-08
        # prompt-injection channel — plus agent-launchd.log) is enforced here
        # by date-prefixed Read denies, scoped by the year prefix because the
        # session legitimately reads materials.md and the instrument logs
        # beside them. Read denies cover Grep too (verified 2026-08-15).
        #
        # UNMEASURED (P1-10.15): `Glob,Grep` below are BARE allows -- no
        # path -- while Read is positively scoped. Only the deny side was
        # ever checked. Whether a bare Grep/Glob reaches outside the Read
        # scope is a property of the CLI's permission evaluation; the opt-in
        # probe is test_c_scope_9 (CONTEMPLATIVE_RUN_CLAUDE_PROBE=1, owner's
        # machine, one model call). Record its result here (date, CLI
        # version) and drop the bare allow if the sentinel is reachable.
        #
        # Write grants (mechanic 3: Edit rules cover Write): everything the
        # session authors lands in reports/.private/ — the report and
        # findings files, the staged observation-ledger delta (RFC-0010:
        # the session proposes rows; this chain validates and appends to the
        # canonical ledger after the structural gate, so a steered session
        # cannot rewrite ledger history), plus a per-run task staging dir
        # for Phase 4 draft filing. The session NEVER touches the live
        # rfcs/ store:
        # the store supports concurrent sessions (a triage session or the
        # owner may write it during this 90-min run), so a live-store grant
        # plus a directory diff both misattributes concurrent filings and
        # lets a steered session clobber owner-written tasks with no history
        # to restore from (codex review 2026-08-24 P1). The chain validates
        # and moves the staged drafts below, deterministically, and the
        # session holds no Bash — the claims.jsonl spawn append is the
        # chain's too.
        #
        # Read is POSITIVELY scoped (2026-08-24 security review HIGH): this
        # session reads nonce-framed untrusted post bodies, and its outputs
        # are published by sync-research-data — a bare Read grant would let an
        # injected instruction quote any local file (~/.ssh, ~/.aws, tokens)
        # into a report the next sync pushes to the public data repo. The
        # allow list names the repo checkout, the analysis dir, the logs
        # workspace and the four live value-layer paths; everything else falls
        # to --permission-mode manual's refusal.
        #
        # The repo allow is a LIST OF SUBTREES, not `Read(/$PROJECT_ROOT/**)`
        # (P1-10.5): a deny only protects the names it spells, and the
        # checkout holds untracked secret-bearing paths (.env, .notes/,
        # .venv/, .claude/settings*, .claude/worktrees/<other branch's
        # working tree>, .deepeval/, evals/results/). Naming the subtrees the
        # session reads (audited against SKILL.md + references/diagnosis.md:
        # src, docs, rfcs, config, scripts, .claude/skills, tests) leaves
        # those outside the allow, so they fall to --permission-mode
        # manual's refusal with no deny to forget. The two denies below
        # cover the names that remain INSIDE an allowed subtree (.env* is
        # belt-and-braces; tests/fixtures/benchmark holds production-derived
        # episode rows). Glob/Grep stay bare allows: see P1-10.15 below.
        #
        # The value-layer reads (identity.md, constitution/, skills/, rules/)
        # are the F2 input contract (RFC-0019): references/diagnosis.md Step 3
        # requires their current full text and the F2 output contract quotes it
        # back, so without them that finding class was not thin but
        # structurally impossible — the 2026-08-29 run was refused and produced
        # zero. READ only: the Edit denies below are unchanged, so the session
        # stays read-only over the layer it diagnoses. The layer is the agent's
        # own distilled text and is already published verbatim by
        # sync-research-data, so the grant discloses nothing new -- with ONE
        # carve-out: `skills/.archive/**` is what that sync deliberately
        # excludes (retired skill bodies and their `superseded_by:` lineage),
        # so it gets a Read deny below, pairing the permission table with
        # config/sync-excludes-public.txt (`.archive/` and `_gc_trash/`, which
        # get the same deny). Without it a report
        # quoting a retired skill re-publishes by another route (2026-08-29
        # security review LOW).
        #
        # The episode-log deny still outranks the logs allow. Since
        # ADR-0107 the episode logs live in their own folder
        # (logs/episodes/ — .bak, .pre-cleanup.bak and any future backup
        # convention included), so the deny is a directory, not a filename
        # prefix; every other file under logs/ is self-written telemetry
        # the session may read. ~/.claude/hooks/_episode-log-common.sh
        # draws the same folder boundary.
        SESSION_ENVELOPE="$PRIVATE_DIR/.session-envelope-$RUN_ID.json"
        if with_timeout "$WEEKLY_TIMEOUT" claude -p "/weekly-report $MATERIALS" \
            --add-dir "$MOLTBOOK_HOME/reports" \
            --add-dir "$MOLTBOOK_HOME/logs" \
            --permission-mode manual \
            --tools "$WEEKLY_TOOLS" \
            ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
            --strict-mcp-config \
            --setting-sources project \
            --allowedTools "Glob,Grep,Read(/$PROJECT_ROOT/src/**),Read(/$PROJECT_ROOT/docs/**),Read(/$PROJECT_ROOT/rfcs/**),Read(/$PROJECT_ROOT/config/**),Read(/$PROJECT_ROOT/scripts/**),Read(/$PROJECT_ROOT/.claude/skills/**),Read(/$PROJECT_ROOT/.notes/archive/tasks/**),Read(/$PROJECT_ROOT/tests/**),Read(/$REPORT_DIR/**),Read(/$PRIVATE_DIR/**),Read(/$MOLTBOOK_HOME/logs/**),Read(/$MOLTBOOK_HOME/identity.md),Read(/$MOLTBOOK_HOME/constitution/**),Read(/$MOLTBOOK_HOME/skills/**),Read(/$MOLTBOOK_HOME/rules/**),Edit(/$PRIVATE_DIR/weekly-$END_DATE.md),Edit(/$PRIVATE_DIR/weekly-$END_DATE-findings.md),Edit(/$LEDGER_DELTA_STAGED),Edit(/$PRIVATE_TASKS/**)" \
            --disallowedTools "Bash,WebFetch,WebSearch,NotebookEdit,Read(/$PROJECT_ROOT/.env*),Read(/$PROJECT_ROOT/tests/fixtures/benchmark/**),Read(/$MOLTBOOK_HOME/credentials.json),Read(/$MOLTBOOK_HOME/skills/.archive/**),Read(/$MOLTBOOK_HOME/skills/_gc_trash/**),Read(/$MOLTBOOK_HOME/logs/episodes/**),Read(/$MOLTBOOK_HOME/logs/agent-launchd.log*),Edit(/$MOLTBOOK_HOME/logs/**),Edit(/$MOLTBOOK_HOME/.staged/**),Edit(/$MOLTBOOK_HOME/skills/**),Edit(/$MOLTBOOK_HOME/rules/**),Edit(/$MOLTBOOK_HOME/constitution/**),Edit(/$MOLTBOOK_HOME/identity.md),Edit(/$MOLTBOOK_HOME/knowledge.json)" \
            --output-format json \
            > "$SESSION_ENVELOPE" 2> "$RUN_LOG_DIR/weekly-session.log"; then
            SESSION_RC=0
        else
            SESSION_RC=1
        fi
        # Exit state from the JSON envelope (P2-02.8). The envelope's `result`
        # text is never kept: the report is the .private/ file, and the log
        # gets only the numbers. An unreadable envelope is a reason code, not
        # a guess — and a missing `permission_denials` key reads `unknown`,
        # never 0.
        SESSION_NUMBERS=()
        SESSION_IS_ERROR=unknown SESSION_DENIALS=unknown
        if [[ -s "$SESSION_ENVELOPE" ]]; then
            if SESSION_SUMMARY="$(python3 "$SCRIPTS/session_envelope.py" < "$SESSION_ENVELOPE" 2>/dev/null)"; then
                while IFS= read -r envline; do
                    [[ -n "$envline" ]] || continue
                    SESSION_NUMBERS+=("$envline")
                    case "$envline" in
                        is_error=*) SESSION_IS_ERROR="${envline#is_error=}" ;;
                        denials=*) SESSION_DENIALS="${envline#denials=}" ;;
                    esac
                done <<< "$SESSION_SUMMARY"
                printf '%s\n' "$SESSION_SUMMARY" >> "$RUN_LOG_DIR/weekly-session.log"
            else
                add_reason REPORT_SESSION_ENVELOPE_UNREADABLE
            fi
        elif [[ "$SESSION_RC" -eq 0 ]]; then
            add_reason REPORT_SESSION_ENVELOPE_UNREADABLE
        fi
        rm -f "$SESSION_ENVELOPE"
        SESSION_REASON=""
        if [[ "$SESSION_RC" -ne 0 ]]; then
            SESSION_RESULT=fail; SESSION_REASON=REPORT_SESSION_FAIL
        elif [[ "$SESSION_IS_ERROR" == true ]]; then
            SESSION_RESULT=fail; SESSION_REASON=REPORT_SESSION_ERROR
        else
            SESSION_RESULT=ok
            if [[ "$SESSION_DENIALS" =~ ^[0-9]+$ ]] && (( SESSION_DENIALS > 0 )); then
                SESSION_REASON=REPORT_SESSION_DENIED   # does not abort: the structural gate judges the report
            fi
        fi
        [[ -n "$SESSION_REASON" && "$SESSION_RESULT" == ok ]] && add_reason "$SESSION_REASON"
        audit stage_result stage=report result="$SESSION_RESULT" \
            ${SESSION_REASON:+reason="$SESSION_REASON"} \
            ${SESSION_NUMBERS[@]+"${SESSION_NUMBERS[@]}"}
    fi
else
    # Not asked for (or skipped by the project-settings preflight). With no
    # canonical report for the week this is the instruments-only shape
    # (P2-02.2): say so in a reason code instead of exiting at the report
    # check below. An existing report is the ordinary --skip-report rerun and
    # stays a plain skip.
    if [[ -s "$REPORT_PATH" ]]; then
        audit stage_result stage=report result=skipped ${REPORT_SKIP_REASON:+reason=$REPORT_SKIP_REASON}
    else
        add_reason REPORT_ABSENT
        audit stage_result stage=report result=skipped reason=REPORT_ABSENT ${REPORT_SKIP_REASON:+skip_reason=$REPORT_SKIP_REASON}
        echo "[$RUN_ID] no report for $END_DATE and none requested — instruments-only run (REPORT_ABSENT)"
    fi
fi

# Promote the session's outputs from reports/.private/ to the canonical
# paths — the structural gate runs BEFORE anything reaches a name the public
# sync or next week's PREV_REPORTS glob can see. A failed week leaves its
# partial artifacts quarantined in .private/ for inspection, and the previous
# canonical report untouched.
if [[ "$REPORT_RAN" -eq 1 ]]; then
    PRIVATE_REPORT="$PRIVATE_DIR/weekly-${END_DATE}.md"
    if [[ ! -s "$PRIVATE_REPORT" ]]; then
        audit stage_result stage=report result=fail reason=REPORT_MISSING
        echo "ERROR: session produced no report ($PRIVATE_REPORT) — aborting" >&2
        exit 1
    fi
    MISSING_PARTS="$(report_missing_parts "$PRIVATE_REPORT")"
    if [[ -n "$MISSING_PARTS" ]]; then
        audit stage_result stage=report result=fail reason=REPORT_INCOMPLETE "missing=$MISSING_PARTS"
        echo "ERROR: report structurally incomplete (missing: $MISSING_PARTS) —" >&2
        echo "       quarantined in $PRIVATE_DIR; canonical report untouched. Aborting" >&2
        exit 1
    fi
    H2_COUNT="$(report_h2_count "$PRIVATE_REPORT")"
    if [[ "$H2_COUNT" -ne "$REPORT_H2_COUNT" ]]; then
        audit stage_result stage=report result=fail reason=REPORT_INCOMPLETE_H2_COUNT "h2=$H2_COUNT"
        echo "ERROR: report has $H2_COUNT H2 headings (expected $REPORT_H2_COUNT) —" >&2
        echo "       quarantined in $PRIVATE_DIR; canonical report untouched. Aborting" >&2
        exit 1
    fi
    # Observation-ledger delta (RFC-0010): validate + append BEFORE the report
    # promote. The report cites the O-ids its delta introduces, and _next_id()
    # derives ids from ledger rows alone — promoting a report whose delta was
    # then rejected would let next week mint the same O-id for a different
    # observation (silent longitudinal corruption, code review 2026-08-26
    # MEDIUM-HIGH). Fail-closed per delta: any invalid row rejects the whole
    # file, the report is quarantined beside it, and the previous canonical
    # report stays untouched. An absent/empty delta is normal (a quiet week
    # stages no rows) — the structural gate above already passed, so the
    # ordering still guarantees "a week whose report never lands writes no
    # ledger history".
    if [[ -s "$LEDGER_DELTA_STAGED" ]]; then
        if python3 "$SCRIPTS/observation_ledger.py" append \
                --ledger "$LEDGER_FILE" --delta "$LEDGER_DELTA_STAGED" \
                >> "$RUN_LOG_DIR/ledger-append.log" 2>&1; then
            audit stage_result stage=ledger result=ok
            rm -f "$LEDGER_DELTA_STAGED"
        else
            audit stage_result stage=ledger result=fail reason=LEDGER_DELTA_INVALID
            echo "ERROR: observation-ledger delta rejected (see $RUN_LOG_DIR/ledger-append.log) —" >&2
            echo "       report + delta quarantined in $PRIVATE_DIR; canonical report untouched. Aborting" >&2
            exit 1
        fi
    fi
    # Sample splice (RFC-0026): the writer emits the `## Sample` heading and
    # nothing under it, and the collector's section is copied into that slot
    # here — before promotion, so a report reaching reports/analysis/ carries a
    # control channel the writer never retyped. A reason code, not an abort:
    # a heading that is missing / duplicated, or one the writer wrote under, is
    # left exactly as the writer left it (what happened stays legible in the
    # document) and the gate is told which shape it was.
    if SPLICE_REASON="$(python3 "$SCRIPTS/weekly_sample_splice.py" \
            --sample "$SAMPLE_SOURCE" --report "$PRIVATE_REPORT" \
            2>> "$RUN_LOG_DIR/sample-splice.log")"; then
        audit stage_result stage=sample_splice result=ok
    else
        # SAMPLE_SPLICE_FAILED is this script's code for "the splice died
        # instead of refusing"; the refusal codes are the splice's own.
        [[ "$SPLICE_REASON" =~ ^[A-Z_]+$ ]] || SPLICE_REASON=SAMPLE_SPLICE_FAILED
        add_reason "$SPLICE_REASON"
        audit stage_result stage=sample_splice result=fail reason="$SPLICE_REASON"
        echo "WARNING: Sample section not spliced (reason=$SPLICE_REASON)" >&2
    fi

    # A splice that adds a heading breaks the six-H2 contract the gate above
    # just verified (P2-04.14). Reason code, not an abort: the document is intact.
    if [[ "$(report_h2_count "$PRIVATE_REPORT")" -ne "$REPORT_H2_COUNT" ]]; then
        add_reason REPORT_H2_COUNT_AFTER_SPLICE
        audit stage_result stage=sample_splice result=fail reason=REPORT_H2_COUNT_AFTER_SPLICE
    fi

    # The stage below reads $REPORT_PATH, so a failed promote would have it
    # check LAST week's promoted report and answer for the wrong document.
    if ! mv "$PRIVATE_REPORT" "$REPORT_PATH"; then
        audit stage_result stage=promote result=fail reason=PROMOTE_FAILED
        echo "ERROR: could not promote $PRIVATE_REPORT to $REPORT_PATH — aborting" >&2
        exit 1
    fi

    # Sample verbatim check (RFC-0010 control channel, code review 2026-08-26
    # MEDIUM): the invariant the splice above is supposed to establish, checked
    # on the promoted bytes. Every sample line the collector emitted (entry
    # headers + excerpt lines) must appear verbatim in the report. A reason
    # code, not an abort — the document is still a valid observation record;
    # the broken control channel is what the gate needs to know. A
    # sampler-failed week emits no such lines and passes.
    #
    # The lines come from the collector's sidecar, not the materials: the
    # materials embed the previous weeks' reports, whose own Sample sections
    # carry `### Sample n/k` lines from OTHER weeks — grepping the whole file
    # demanded those too and produced a false SAMPLE_NOT_VERBATIM on
    # 2026-09-04. With no sidecar there is nothing to assert against, and a
    # silent pass would read as "sample intact"; say skipped instead.
    if [[ ! -s "$SAMPLE_SOURCE" ]]; then
        audit stage_result stage=sample_verbatim result=skipped reason=SAMPLE_SOURCE_MISSING
        SAMPLE_SOURCE=/dev/null
    fi
    SAMPLE_MISSING=""
    while IFS= read -r line; do
        if ! grep -qxF -- "$line" "$REPORT_PATH"; then
            SAMPLE_MISSING="$line"
            break
        fi
    done < <(grep -E '^### Sample [0-9]+/|^\*\*(Context \(counterparty, untrusted\)|Output \(agent\)):\*\*' "$SAMPLE_SOURCE" 2>/dev/null || true)
    if [[ -n "$SAMPLE_MISSING" ]]; then
        add_reason SAMPLE_NOT_VERBATIM
        audit stage_result stage=sample_verbatim result=fail reason=SAMPLE_NOT_VERBATIM
        echo "WARNING: report's Sample section is not a verbatim copy (first missing line logged)" >&2
        printf 'missing sample line: %s\n' "$SAMPLE_MISSING" >> "$RUN_LOG_DIR/sample-verbatim.log"
    else
        audit stage_result stage=sample_verbatim result=ok
    fi

    # Writer stamp (P2-02.3): the document's calibration line carries
    # `writer: <model>`; the audit repeats it so a reader partitioning the
    # longitudinal series by writer needs only one of the two. A missing stamp
    # is a reason code, not an abort — the document is still an observation.
    WRITER_STAMP="$(grep -oE 'writer: [^ ;,`*]+' "$REPORT_PATH" 2>/dev/null | head -1 | cut -c9-)"
    if [[ -n "$WRITER_STAMP" ]]; then
        audit stage_result stage=writer_stamp result=ok writer="$WRITER_STAMP"
    else
        add_reason REPORT_WRITER_STAMP_MISSING
        audit stage_result stage=writer_stamp result=fail reason=REPORT_WRITER_STAMP_MISSING
    fi

    # Findings are advisory (the repairs travel through the task ledger), so
    # an incomplete diagnosis is a reason code, not an abort — but an
    # incomplete findings file stays quarantined rather than promoted.
    PRIVATE_FINDINGS="$PRIVATE_DIR/weekly-${END_DATE}-findings.md"
    if [[ ! -s "$PRIVATE_FINDINGS" ]] || ! grep -q '^## Diagnosis Metadata' "$PRIVATE_FINDINGS"; then
        add_reason DIAGNOSIS_UNAVAILABLE
        audit stage_result stage=diagnosis result=fail reason=DIAGNOSIS_UNAVAILABLE
        # A same-week rerun must not leave an EARLIER attempt's findings
        # standing beside the fresh report — the gate and watchdog would read
        # them as this run's diagnosis (codex review 2026-08-24 P2).
        if [[ -e "$FINDINGS_MD" ]]; then
            mv "$FINDINGS_MD" "$PRIVATE_DIR/$(basename "$FINDINGS_MD").superseded-$RUN_ID"
        fi
    else
        mv "$PRIVATE_FINDINGS" "$FINDINGS_MD"
        audit stage_result stage=diagnosis result=ok
    fi
fi
# A session that ran must have produced the canonical report (the promote
# above already guarantees it; this is the belt for a future edit). A run that
# never asked for a report was recorded as REPORT_ABSENT above and goes on.
if [[ "$REPORT_RAN" -eq 1 && ! -s "$REPORT_PATH" ]]; then
    audit stage_result stage=report result=fail reason=REPORT_MISSING
    echo "ERROR: report $REPORT_PATH missing or empty — aborting" >&2
    exit 1
fi

# --- Promote the intake baselines (only now that a complete report exists) ---
# weekly-analysis.sh emits these aside (deterministic .pending paths, no PID);
# spending a baseline on a week whose report never landed would mean that
# week's novelty/drift was observed by nobody. -e, not -s: a clean sweep
# legitimately emits an empty snapshot, and that is a real baseline. Guarded
# on REPORT_RAN so a --skip-report rerun never promotes a leftover pending
# from an earlier aborted run.
SWEEP_STATE="$REPORT_DIR/.anomaly-sweep-state.tsv"
SWEEP_PENDING="$REPORT_DIR/.anomaly-sweep-state.pending"
SWEEP_CORPUS="$SWEEP_STATE.corpus.tsv"
SWEEP_PENDING_CORPUS="$SWEEP_PENDING.corpus.tsv"
DRIFT_STATE="$REPORT_DIR/.api-drift-state.tsv"
DRIFT_PENDING="$REPORT_DIR/.api-drift-state.pending"
JOIN_STATE="$REPORT_DIR/.approval-join-state.json"
JOIN_PENDING="$REPORT_DIR/.approval-join-state.pending"
if [[ "$REPORT_RAN" -eq 1 ]]; then
if [[ -e "$SWEEP_PENDING" ]]; then
    if mv "$SWEEP_PENDING" "$SWEEP_STATE"; then
        echo "[$RUN_ID] anomaly sweep state committed"
        # The census travels in lockstep with the snapshot — it is the
        # snapshot's measurement basis; a stale census beside fresh counts
        # would assert a corpus comparison that never happened.
        if ! { [[ -e "$SWEEP_PENDING_CORPUS" ]] && mv "$SWEEP_PENDING_CORPUS" "$SWEEP_CORPUS"; }; then
            rm -f "$SWEEP_CORPUS"
            echo "WARNING: sweep corpus census missing; next run reports no previous census" >&2
        fi
    else
        echo "WARNING: sweep state promote failed; next run compares against a wider window" >&2
    fi
fi
if [[ -e "$DRIFT_PENDING" ]]; then
    mv "$DRIFT_PENDING" "$DRIFT_STATE" \
        || echo "WARNING: drift state promote failed; next run re-reports this week's drift" >&2
fi
if [[ -e "$JOIN_PENDING" ]]; then
    mv "$JOIN_PENDING" "$JOIN_STATE" \
        || echo "WARNING: approval join state promote failed; next run reports no prior reading" >&2
fi

# --- Draft intake (deterministic; the session cannot touch the store) ---
# The session filed drafts into $PRIVATE_TASKS under its own `T-<SLUG>.md`
# diagnosis names. Each staged file is validated, RENAMED into the rfcs/
# convention (`NNNN-slug.md`, ID `RFC-NNNN` — ADR-0049), moved into the live
# store, and recorded in claims.jsonl. A file that fails validation stays
# quarantined in staging (visible to the Saturday reader), never silently
# dropped and never half-adopted. Producer citations are read from the file
# body (backtick `path:line`); a file with none is still recorded (origin gate
# does not require --producer). Failures here must not kill the chain — the
# moved files are the ground truth and the triage session reads the store, not
# the claims log.
#
# The BODY is never rewritten here beyond the `state:` line: the machine
# contract (`claims.py ready` shows the first non-heading body line as the
# summary) is the /weekly-report format's job — a filing that fails it is
# fixed by the Saturday gate, not by an unattended edit.
SPAWNED=0

# Next number for rfcs/: max existing NNNN + 1, zero-padded to 4. Gaps are
# never reused, so this is a max scan and not a count.
next_rfc_number() {
    local max=0 f base n
    for f in "$TASKS_DIR"/[0-9][0-9][0-9][0-9]-*.md; do
        [[ -e "$f" ]] || continue
        base="$(basename "$f")"
        n=$((10#${base:0:4}))   # 10# so 0009 is nine, not a bad octal
        if (( n > max )); then max=$n; fi
    done
    printf '%04d' $((max + 1))
}

for staged in "$PRIVATE_TASKS"/*.md; do
    [[ -e "$staged" ]] || continue
    staged_name="$(basename "$staged" .md)"
    if ! [[ "$staged_name" =~ ^T-[A-Z0-9][A-Z0-9-]*$ ]]; then
        echo "WARNING: staged filing with non-conforming name left in staging: $staged_name.md" >&2
        add_reason SPAWN_RECORD_SKIPPED
        continue
    fi
    # rfcs/ naming: the number is assigned HERE (the session cannot see the
    # store's high-water mark) and the diagnosis-side name survives as the
    # slug, so `T-OLLAMA-TOKENIZE` files as `0016-ollama-tokenize.md` /
    # RFC-0016. `${x,,}` is bash 4; macOS ships 3.2, hence tr.
    rfc_number="$(next_rfc_number)"
    task_id="RFC-$rfc_number"
    newfile="$rfc_number-$(printf '%s' "${staged_name#T-}" | tr '[:upper:]' '[:lower:]').md"
    if [[ -e "$TASKS_DIR/$newfile" ]]; then
        # Unreachable while the number is a max+1 scan, kept as the guard that
        # a filing never overwrites an entry already in the store — the
        # owner's or a concurrent session's.
        echo "WARNING: staged filing collides with an existing store entry, left in staging: $newfile" >&2
        add_reason SPAWN_RECORD_SKIPPED
        continue
    fi
    # ADR-0098 D2: filings are candidates — no readiness claim. In the rfcs/
    # vocabulary that state is `draft`. Any other `state:` line is normalized
    # and named; a file with NO parseable state line stays in staging
    # (claims.py would never surface it, so moving it would make the finding
    # vanish silently — codex review 2026-08-24 P2).
    if ! grep -q '^state:' "$staged"; then
        echo "WARNING: staged filing has no state: line, left in staging: $staged_name.md" >&2
        add_reason SPAWN_RECORD_SKIPPED
        continue
    fi
    if ! grep -q '^state: draft' "$staged"; then
        sed -i '' 's/^state: .*/state: draft/' "$staged"
        add_reason SPAWN_STATE_NORMALIZED
        echo "WARNING: $newfile filed with a non-draft state — normalized" >&2
    fi
    mv "$staged" "$TASKS_DIR/$newfile"
    # First backtick path:line citation in the body, if any.
    # shellcheck disable=SC2016  # the single-quoted backticks are a grep pattern, not an expansion
    producer=$(grep -oE '`[^` :]+:[0-9]+(-[0-9]+)?`' "$TASKS_DIR/$newfile" 2>/dev/null \
        | head -1 | tr -d '`')
    producer_args=()
    [[ -n "$producer" ]] && producer_args=(--producer "$producer")
    if (cd "$PROJECT_ROOT" && python3 "$CLAIMS_PY" spawn "$task_id" \
            --origin gate --note "weekly $END_DATE diagnosis ($staged_name)" \
            ${producer_args[@]+"${producer_args[@]}"}) \
            >> "$RUN_LOG_DIR/spawn.log" 2>&1; then
        SPAWNED=$((SPAWNED + 1))
    else
        add_reason SPAWN_RECORD_FAIL
        echo "WARNING: claims.py spawn failed for $task_id (see spawn.log)" >&2
    fi
done
audit stage_result stage=spawn result=ok spawned="$SPAWNED"
echo "[$RUN_ID] filed drafts recorded: $SPAWNED (uncommitted in rfcs/ — the Saturday gate commits)"
fi  # REPORT_RAN

# --- Stage 5b: value-layer cadence (read-only due check + monthly identity staging) ---
# The due check is a deterministic reading over the ADR-0012 approval audit
# log (value_layer_due_check.py). Identity staging fires only when ALL of:
#   (1) the interval has elapsed (due=true),
#   (2) this is a live run (END_DATE == yesterday) — a --end-date backfill
#       must never fire a real LLM run off a stale-dated reading and reset
#       the genuine cadence clock (code review 2026-08-10 HIGH),
#   (3) the weekly insight job has COMPLETED today (.last_insight marker is
#       fresh) — without this, staging identity into the momentarily-empty
#       dir would make the ADR-0074 pending guard discard the whole arriving
#       insight batch (adr review 2026-08-10 CRITICAL),
#   (4) staging is empty — race-free against the scheduled producer.
# Every deferral is an audit-visible reason code; the Saturday gate reads the
# JSON directly (value-layer-$END_DATE.json). Adoption always stays at the
# gate. The constitution reading is informational only (ADR-0090).
VALUE_LAYER_JSON="$MOLTBOOK_HOME/pipeline/value-layer/value-layer-$END_DATE.json"
# Identity window guard (P2-04.9): the distill must be able to finish before
# the next agent session starts (both use the one local model). Needs the
# distill timeout + 5 min; an unreadable agent plist is recorded as unknown and
# does not block (the guard cannot evaluate, and the stage's other guards
# still hold). The deferral persists the due state: nothing is recorded, so
# next week's due check fires again.
AGENT_GAP_MINUTES=unknown
identity_window_ok() {
    AGENT_GAP_MINUTES="$(python3 "$SCRIPTS/chain_schedule_probe.py" agent-gap-minutes \
        --plist "$AGENT_PLIST" --now "$(date +%s)" 2>/dev/null || echo unknown)"
    [[ "$AGENT_GAP_MINUTES" =~ ^[0-9]+$ ]] || return 0
    (( AGENT_GAP_MINUTES >= IDENTITY_TIMEOUT / 60 + 5 ))
}
# defer_identity <REASON> [k=v ...] — one place for a deferral: reason code,
# audit row, and the reason written into the week's value-layer JSON so the
# gate's direct read sees why `identity.due` produced no staged candidate
# (P2-04.13 PR-C). A failed annotation is a warning, never a stop.
defer_identity() {
    local reason="$1"; shift
    add_reason "$reason"
    audit stage_result stage=identity result=skipped reason="$reason" "$@"
    python3 "$SCRIPTS/value_layer_annotate.py" --json "$VALUE_LAYER_JSON" \
        --identity-deferred "$reason" 2>>"$RUN_LOG_DIR/valuelayer.err" \
        || echo "WARNING: could not record identity.deferred_reason ($reason)" >&2
}
INSIGHT_MARKER="$MOLTBOOK_HOME/skills/.last_insight"
INSIGHT_MARKER_MAX_AGE="${PIPELINE_INSIGHT_MARKER_MAX_AGE:-21600}"  # 6h: insight 08:00 → deadline 12:00
if stage_enabled valuelayer; then
    if deadline_exceeded; then
        add_reason CHAIN_DEADLINE
        audit stage_result stage=valuelayer result=skipped reason=CHAIN_DEADLINE
    else
        echo "[$RUN_ID] stage 5b: value-layer due check"
        mkdir -p "$(dirname "$VALUE_LAYER_JSON")"
        chmod 700 "$(dirname "$VALUE_LAYER_JSON")" 2>/dev/null || true
        # --rules-dir adds the ADR-0097 rules-layer maintenance reading; the
        # shell only parses identity/constitution/staging_pending out of the
        # JSON, the rules section reaches the human through the gate's read.
        if python3 "$SCRIPTS/value_layer_due_check.py" \
                --audit "$MOLTBOOK_HOME/logs/audit.jsonl" \
                --knowledge "$MOLTBOOK_HOME/knowledge.json" \
                --staged-dir "$STAGED_DIR" \
                --rules-dir "$MOLTBOOK_HOME/rules" \
                --as-of "$END_DATE" \
                > "$VALUE_LAYER_JSON" 2>"$RUN_LOG_DIR/valuelayer.err"; then
            vl_reading=$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
print(str(data['identity']['due']).lower(),
      str(data['constitution']['due']).lower(),
      data['staging_pending'])
" "$VALUE_LAYER_JSON" 2>/dev/null || echo "")
            if [[ -n "$vl_reading" ]]; then
                read -r vl_identity_due vl_constitution_due vl_staging_pending <<< "$vl_reading"
                audit stage_result stage=valuelayer result=ok \
                    identity_due="$vl_identity_due" \
                    constitution_due="$vl_constitution_due" \
                    staging_pending="$vl_staging_pending"
                if [[ "$vl_identity_due" == "true" ]]; then
                    # Read only on the monthly path that branches on it.
                    insight_fresh=$(python3 -c "
import sys
from datetime import datetime, timezone
try:
    with open(sys.argv[1], encoding='utf-8') as fh:
        ts = datetime.fromisoformat(fh.read().strip())
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    print('true' if 0 <= age <= float(sys.argv[2]) else 'false')
except Exception:
    print('false')
" "$INSIGHT_MARKER" "$INSIGHT_MARKER_MAX_AGE" 2>/dev/null || echo false)
                    if [[ "$END_DATE" != "$YESTERDAY" ]]; then
                        defer_identity IDENTITY_BACKFILL_SKIP
                    elif [[ "$insight_fresh" != "true" ]]; then
                        defer_identity IDENTITY_INSIGHT_PENDING
                    elif ! identity_window_ok; then
                        defer_identity IDENTITY_WINDOW_TOO_SHORT \
                            agent_gap_minutes="$AGENT_GAP_MINUTES"
                    elif [[ "$vl_staging_pending" != "0" ]]; then
                        defer_identity IDENTITY_STAGING_BUSY
                    else
                        echo "[$RUN_ID] stage 5b: identity distill (interval elapsed)"
                        (cd "$PROJECT_ROOT" && with_timeout "$IDENTITY_TIMEOUT" \
                            uv run --no-sync -q contemplative-agent distill-identity --stage) \
                            > "$RUN_LOG_DIR/identity.log" 2>&1
                        # The CLI exits 0 on a staging refusal and on an LLM
                        # failure alike — the staged files are the ground
                        # truth, and BOTH halves must exist (adopt-staged
                        # discovers candidates through the .meta.json sidecar;
                        # codex review 2026-08-10 P2).
                        if [[ -f "$STAGED_DIR/identity.md" \
                                && -f "$STAGED_DIR/identity.md.meta.json" ]]; then
                            audit stage_result stage=identity result=ok
                        # A concurrent producer winning the CLI's flock is an
                        # ADR-0074 designed outcome, not an LLM fault.
                        elif grep -q "refusing this batch (ADR-0074)" \
                                "$RUN_LOG_DIR/identity.log" 2>/dev/null; then
                            defer_identity IDENTITY_STAGING_RACE
                        else
                            add_reason IDENTITY_STAGE_FAIL
                            audit stage_result stage=identity result=fail \
                                reason=IDENTITY_STAGE_FAIL
                        fi
                    fi
                fi
            else
                add_reason VALUE_LAYER_CHECK_FAIL
                audit stage_result stage=valuelayer result=fail reason=VALUE_LAYER_CHECK_FAIL
                rm -f "$VALUE_LAYER_JSON"
            fi
        else
            add_reason VALUE_LAYER_CHECK_FAIL
            audit stage_result stage=valuelayer result=fail reason=VALUE_LAYER_CHECK_FAIL
            rm -f "$VALUE_LAYER_JSON"
        fi
    fi
else
    audit stage_result stage=valuelayer result=skipped
fi

# Cadence of the two low-yield scans below (P1-04.6, ADR-0085 / ADR-0093 Consumption
# plans): after 4 consecutive empty runs a scan drops to monthly, and one positive
# resumes weekly. State = the scan's own pipeline/ output history, read by
# scan_cadence.py; it fails toward running (an error is "due"), never toward silence.
# Exit code contract: 0 = due, 1 = skip (the ONLY skip signal). Any other code (argparse 2,
# missing interpreter 127, a crash) is logged as CADENCE_ERROR and treated as due.
scan_due() {  # scan_due <dir> <prefix> <count-key>
    local rc=0
    python3 "$SCRIPTS/scan_cadence.py" --dir "$1" --prefix "$2" --count-key "$3" \
        --end-date "$END_DATE" >&2 || rc=$?
    case "$rc" in
        0) return 0 ;;
        1) return 1 ;;
        *)
            echo "[$RUN_ID] scan_cadence exit $rc for $2: running the scan (CADENCE_ERROR)" >&2
            add_reason CADENCE_ERROR
            return 0
            ;;
    esac
}

# --- Stage 6: dead-code scan (deterministic; detection ONLY) ---
# Feeds the Saturday gate DIRECTLY (dead-code-$END_DATE.json) — a dead-code
# candidate must never become a finding an unattended session turns into a
# deletion patch; deletion is structurally a Saturday-gate human commit.
# Read-only over the repo checkout; vulture policy in pyproject [tool.vulture],
# exemptions in .vulture_whitelist.py. Observability only — a scan fault is a
# reason code, never a silent zero (dead_code_scan.py abstains nonzero).
DEADCODE_JSON="$MOLTBOOK_HOME/pipeline/dead-code/dead-code-$END_DATE.json"
if stage_enabled deadcode; then
    if deadline_exceeded; then
        add_reason CHAIN_DEADLINE
        audit stage_result stage=deadcode result=skipped reason=CHAIN_DEADLINE
    elif ! scan_due "$MOLTBOOK_HOME/pipeline/dead-code" dead-code candidates; then
        audit stage_result stage=deadcode result=skipped reason=CADENCE_MONTHLY
    else
        echo "[$RUN_ID] stage 6: dead-code scan"
        mkdir -p "$(dirname "$DEADCODE_JSON")"
        # --no-sync: the chain must never resolve/install packages from the
        # network unattended (security review M1).
        if (cd "$PROJECT_ROOT" && with_timeout "$DEADCODE_TIMEOUT" \
                uv run --no-sync -q python scripts/dead_code_scan.py) \
                > "$DEADCODE_JSON" 2>"$RUN_LOG_DIR/deadcode.err"; then
            dc_counts=$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
print(len(data['candidates']), data.get('unparsed_lines', 0), data.get('stderr_lines', 0))
" "$DEADCODE_JSON" 2>/dev/null || echo "")
            if [[ -n "$dc_counts" ]]; then
                read -r dc_count dc_unparsed dc_stderr <<< "$dc_counts"
                [[ "$dc_unparsed" != "0" ]] && add_reason DEADCODE_PARTIAL_PARSE
                [[ "$dc_stderr" != "0" ]] && add_reason DEADCODE_PARTIAL_SCAN
                audit stage_result stage=deadcode result=ok \
                    candidates="$dc_count" unparsed="$dc_unparsed" stderr_lines="$dc_stderr"
            else
                add_reason DEADCODE_SCAN_FAIL
                audit stage_result stage=deadcode result=fail reason=DEADCODE_SCAN_FAIL
                rm -f "$DEADCODE_JSON"
            fi
        else
            add_reason DEADCODE_SCAN_FAIL
            audit stage_result stage=deadcode result=fail reason=DEADCODE_SCAN_FAIL
            rm -f "$DEADCODE_JSON"
        fi
    fi
else
    audit stage_result stage=deadcode result=skipped
fi

# --- Stage 6b: docs-consistency scan (deterministic; ADR-0093) ---
# Same detection/repair separation: the scan output goes straight to the gate
# (docs-consistency-$END_DATE.json); a doc edit is a Saturday human commit.
# Reads only the repo's own self-authored docs. stdlib-only → python3, no uv.
DOCSCAN_JSON="$MOLTBOOK_HOME/pipeline/docs-consistency/docs-consistency-$END_DATE.json"
if stage_enabled docsscan; then
    if deadline_exceeded; then
        add_reason CHAIN_DEADLINE
        audit stage_result stage=docsscan result=skipped reason=CHAIN_DEADLINE
    elif ! scan_due "$MOLTBOOK_HOME/pipeline/docs-consistency" docs-consistency count; then
        audit stage_result stage=docsscan result=skipped reason=CADENCE_MONTHLY
    else
        echo "[$RUN_ID] stage 6b: docs-consistency scan"
        mkdir -p "$(dirname "$DOCSCAN_JSON")"
        if with_timeout "$DOCSCAN_TIMEOUT" python3 \
                "$SCRIPTS/docs_consistency_scan.py" --repo "$PROJECT_ROOT" \
                > "$DOCSCAN_JSON" 2>"$RUN_LOG_DIR/docsscan.err"; then
            ds_counts=$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
print(data['count'], len(data.get('errors', [])))
" "$DOCSCAN_JSON" 2>/dev/null || echo "")
            if [[ -n "$ds_counts" ]]; then
                read -r ds_count ds_errors <<< "$ds_counts"
                audit stage_result stage=docsscan result=ok \
                    findings="$ds_count" errors="$ds_errors"
            else
                add_reason DOCSCAN_FAIL
                audit stage_result stage=docsscan result=fail reason=DOCSCAN_FAIL
                rm -f "$DOCSCAN_JSON"
            fi
        else
            add_reason DOCSCAN_FAIL
            audit stage_result stage=docsscan result=fail reason=DOCSCAN_FAIL
            rm -f "$DOCSCAN_JSON"
        fi
    fi
else
    audit stage_result stage=docsscan result=skipped
fi

# --- Stage 7b: never-selected reading (ADR-0097 D5) ---
# The store's exit reading: strict (whole-history 0 selections AND >= the
# exposure floor — the archive candidates), dormant (0 in the trailing window,
# selected before) and below_floor. Runs under the venv (needs the
# selection-log grammar and the catalog loader).
#
# Not behind `stage_enabled`: the Saturday gate's missing-artifact check
# treats an absent file as NEVER_SELECTED_UNREADABLE, so gating this on a
# stage name would let a MOLTBOOK_PIPELINE_STAGES selection silently produce
# a week that reads "nothing to retire" (unit B silent-failure review,
# 2026-08-22).
NEVER_SELECTED_JSON="$MOLTBOOK_HOME/pipeline/never-selected/never-selected-$END_DATE.json"
NEVER_SELECTED_TIMEOUT="${PIPELINE_NEVER_SELECTED_TIMEOUT:-300}"
echo "[$RUN_ID] stage 7b: never-selected reading"
mkdir -p "$(dirname "$NEVER_SELECTED_JSON")"
chmod 700 "$(dirname "$NEVER_SELECTED_JSON")" 2>/dev/null || true
rm -f "$NEVER_SELECTED_JSON"
# --no-sync for the same reason as the dead-code scan.
if (cd "$PROJECT_ROOT" && with_timeout "$NEVER_SELECTED_TIMEOUT" \
        uv run --no-sync -q python scripts/never_selected_reading.py \
        --home "$MOLTBOOK_HOME" --end-date "$END_DATE") \
        > "$NEVER_SELECTED_JSON" 2>"$RUN_LOG_DIR/neverselected.err"; then
    ns_strict=$(python3 -c "
import json, sys
print(len(json.load(open(sys.argv[1]))['strict']))
" "$NEVER_SELECTED_JSON" 2>/dev/null || echo "")
    if [[ -n "$ns_strict" ]]; then
        audit stage_result stage=neverselected result=ok strict="$ns_strict"
    else
        add_reason NEVER_SELECTED_SCAN_FAIL
        audit stage_result stage=neverselected result=fail reason=NEVER_SELECTED_SCAN_FAIL
        rm -f "$NEVER_SELECTED_JSON"
    fi
else
    add_reason NEVER_SELECTED_SCAN_FAIL
    audit stage_result stage=neverselected result=fail reason=NEVER_SELECTED_SCAN_FAIL
    rm -f "$NEVER_SELECTED_JSON"
fi

# --- Stage 7c: confusion-pair reading + the week's archive candidates (ADR-0105) ---
# The second exit signal beside 7b's: a store entry the selector names its way
# INTO at least as often as it chooses it, paired with the entry its variants
# resemble second-best. Takes the never-selected half from 7b's JSON (so the
# two halves of the candidate file cannot disagree, and a lost 7b is NAMED
# rather than read as "nothing to list"), walks the selection log itself for
# the confusion half, writes the union as store filenames, and touches the
# store not at all — `adopt-staged --archive-names` is the Saturday gate's.
#
# Removal condition (ADR-0105 note 2026-10-24): 4 consecutive weeks in which no
# confusion pair names a store entry outside 7b's strict population -> the gate
# files a deletion PR for this stage, scripts/confusion_pair_reading.py and
# core/skill_confusion.py (a scripts-only module) with their tests.
# Not behind `stage_enabled`, for 7b's reason: a STAGES selection that silently
# skipped it would produce a week reading "no candidates" instead of "not read".
CONFUSION_JSON="$MOLTBOOK_HOME/pipeline/confusion-pairs/confusion-pairs-$END_DATE.json"
ARCHIVE_CANDIDATES="$REPORT_DIR/weekly-${END_DATE}-archive-candidates.txt"
CONFUSION_TIMEOUT="${PIPELINE_CONFUSION_TIMEOUT:-300}"
echo "[$RUN_ID] stage 7c: confusion-pair reading"
mkdir -p "$(dirname "$CONFUSION_JSON")"
chmod 700 "$(dirname "$CONFUSION_JSON")" 2>/dev/null || true
ARCHIVE_CONTEXT="$REPORT_DIR/weekly-${END_DATE}-archive-candidates.context.txt"
rm -f "$CONFUSION_JSON" "$ARCHIVE_CANDIDATES" "$ARCHIVE_CONTEXT"
# --no-sync for the same reason as the dead-code scan. The findings file is
# passed only when the diagnosis was promoted this run; the reading's own
# artifacts are the JSON and the candidate file, so a quarantined diagnosis
# costs the section, not the reading.
CONFUSION_ARGS=(--home "$MOLTBOOK_HOME" --end-date "$END_DATE"
    --never-selected "$NEVER_SELECTED_JSON"
    --json "$CONFUSION_JSON" --candidates "$ARCHIVE_CANDIDATES")
if [[ -s "$FINDINGS_MD" ]]; then
    CONFUSION_ARGS+=(--findings "$FINDINGS_MD")
fi
if cf_out=$(cd "$PROJECT_ROOT" && with_timeout "$CONFUSION_TIMEOUT" \
        uv run --no-sync -q python scripts/confusion_pair_reading.py \
        "${CONFUSION_ARGS[@]}" 2>"$RUN_LOG_DIR/confusion.err"); then
    audit stage_result stage=confusion result=ok summary="$cf_out"
else
    add_reason CONFUSION_READING_FAILED
    audit stage_result stage=confusion result=fail reason=CONFUSION_READING_FAILED
    # Both artifacts go or neither: a JSON without its candidate file (or the
    # reverse) reads at the gate as a complete reading with an empty half.
    rm -f "$CONFUSION_JSON" "$ARCHIVE_CANDIDATES"
fi

# --- Stage 7d: comment-outcome reading (RFC-0028 / ADR-0106) ---
# What the platform returned about the comments each skill was injected into:
# per skill, how many comments carried it, how many drew a reply, and the mean
# observed thread depth. Read-only and unjoined to any gate — the JSON is the
# whole artifact, and its `observation_note` says in the file that the rows are
# a distribution, not a contribution estimate.
#
# Not behind `stage_enabled`, for 7b's reason: a silently skipped instrument
# would read at the gate as "no reactions" instead of "not read".
#
# min-age 2 days: replies land hours to days after a comment, so the tail of
# the window would otherwise be counted as silence (RFC-0028 Drawbacks).
COMMENT_OUTCOMES_JSON="$MOLTBOOK_HOME/pipeline/comment-outcomes/comment-outcomes-$END_DATE.json"
COMMENT_OUTCOMES_TIMEOUT="${PIPELINE_COMMENT_OUTCOMES_TIMEOUT:-300}"
echo "[$RUN_ID] stage 7d: comment-outcome reading"
mkdir -p "$(dirname "$COMMENT_OUTCOMES_JSON")"
chmod 700 "$(dirname "$COMMENT_OUTCOMES_JSON")" 2>/dev/null || true
rm -f "$COMMENT_OUTCOMES_JSON"
# --no-sync for the same reason as the dead-code scan.
if (cd "$PROJECT_ROOT" && with_timeout "$COMMENT_OUTCOMES_TIMEOUT" \
        uv run --no-sync -q python scripts/comment_outcomes_reading.py \
        --home "$MOLTBOOK_HOME" --end-date "$END_DATE") \
        > "$COMMENT_OUTCOMES_JSON" 2>"$RUN_LOG_DIR/commentoutcomes.err"; then
    co_joined=$(python3 -c "
import json, sys
print(json.load(open(sys.argv[1]))['joined_publishes'])
" "$COMMENT_OUTCOMES_JSON" 2>/dev/null || echo "")
    if [[ -n "$co_joined" ]]; then
        audit stage_result stage=commentoutcomes result=ok joined="$co_joined"
    else
        add_reason COMMENT_OUTCOMES_SCAN_FAIL
        audit stage_result stage=commentoutcomes result=fail reason=COMMENT_OUTCOMES_SCAN_FAIL
        rm -f "$COMMENT_OUTCOMES_JSON"
    fi
else
    add_reason COMMENT_OUTCOMES_SCAN_FAIL
    audit stage_result stage=commentoutcomes result=fail reason=COMMENT_OUTCOMES_SCAN_FAIL
    rm -f "$COMMENT_OUTCOMES_JSON"
fi

# --- Stage 7d tail: the reply rate beside each archive candidate (P2-06.3 / ADR-0106 D6) ---
# Needs both halves, so it runs after 7d (7c is earlier and cannot see the
# outcomes). Writes a SIBLING file, never the candidate file: `--archive-names`
# aborts on a line it cannot parse, and nothing on the decision side reads this
# (tests/test_archive_candidate_context.py). A missing half means no sibling and
# one reason code, not a partial file.
if [[ -s "$ARCHIVE_CANDIDATES" && -s "$COMMENT_OUTCOMES_JSON" ]]; then
    if ac_out=$(cd "$PROJECT_ROOT" && with_timeout 60 \
            uv run --no-sync -q python scripts/archive_candidate_context.py \
            --candidates "$ARCHIVE_CANDIDATES" --comment-outcomes "$COMMENT_OUTCOMES_JSON" \
            --out "$ARCHIVE_CONTEXT" 2>"$RUN_LOG_DIR/archivecontext.err"); then
        audit stage_result stage=archivecontext result=ok summary="$ac_out"
    else
        add_reason ARCHIVE_CONTEXT_FAILED
        audit stage_result stage=archivecontext result=fail reason=ARCHIVE_CONTEXT_FAILED
        rm -f "$ARCHIVE_CONTEXT"
    fi
fi

# --- Run-log retention (P2-04.10) ---
# Keep the newest $KEEP_RUN_DIRS run directories under logs/weekly-pipeline/
# (names weekly-<date>-<time> sort chronologically); the current run is never
# a candidate. Only directories matching the run-id shape are touched.
PRUNED=0
RUNS_ROOT="$MOLTBOOK_HOME/logs/weekly-pipeline"
if [[ "$KEEP_RUN_DIRS" =~ ^[0-9]+$ ]] && (( KEEP_RUN_DIRS >= 1 )); then
    while IFS= read -r old_run; do
        [[ "$old_run" =~ ^weekly-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6}$ ]] || continue
        [[ "$old_run" == "$RUN_ID" ]] && continue
        rm -rf "${RUNS_ROOT:?}/$old_run" && PRUNED=$((PRUNED + 1))
    done < <(find "$RUNS_ROOT" -mindepth 1 -maxdepth 1 2>/dev/null | sed 's|.*/||' | sort -r | tail -n +"$((KEEP_RUN_DIRS + 1))")
fi
audit stage_result stage=prune result=ok pruned="$PRUNED" kept="$KEEP_RUN_DIRS"

# --- Chain end (no packet: the Saturday gate reads the artifacts directly) ---
CHAIN_REPORT="$REPORT_PATH"; [[ -s "$REPORT_PATH" ]] || CHAIN_REPORT=none
audit chain_end result=ok report="$CHAIN_REPORT" findings="$FINDINGS_MD" \
    reasons="${REASONS:-none}"
echo "[$RUN_ID] artifacts:"
echo "  report:    $REPORT_PATH"
echo "  findings:  $FINDINGS_MD"
echo "  valuelayer: $VALUE_LAYER_JSON"
echo "  deadcode:  $DEADCODE_JSON"
echo "  docsscan:  $DOCSCAN_JSON"
echo "  confusion: $CONFUSION_JSON"
echo "  candidates: $ARCHIVE_CANDIDATES"
echo "  candidates reply-rate (beside, not input): $ARCHIVE_CONTEXT"
echo "  neversel:  $NEVER_SELECTED_JSON"
echo "  outcomes:  $COMMENT_OUTCOMES_JSON"
echo "[$RUN_ID] done (reasons: ${REASONS:-none})"

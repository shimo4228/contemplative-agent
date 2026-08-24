#!/bin/bash
# Unattended weekly chain (ADR-0085; single-session redesign 2026-08-24):
# materials → ONE claude session (/weekly-report: A-E synthesis + ja + diagnosis
# + candidate task filing) → deterministic instruments (value-layer due check,
# dead-code scan, docs-consistency scan, never-selected reading) → spawn
# recording. Human involvement stays compressed into the Saturday gate
# (/weekly-gate, which now reads the findings and instrument JSONs directly —
# the decision-packet builder is retired); repairs are NOT made here: the
# session files candidates into .notes/tasks/ and the task-triage loop
# (Sat 14:07 tick) judges and dispatches them. Nothing here commits, pushes,
# or adopts.
#
# Fail-forward: every stage failure becomes a reason code in the audit log and
# the run continues. The one hard requirement is the report: with no complete
# A-E report there is no observation to gate on, so the run aborts (the
# watchdog catches the missing report).
#
# Usage:
#   ./scripts/weekly-pipeline.sh                       # full chain, yesterday-ending week
#   ./scripts/weekly-pipeline.sh --end-date 2026-07-24 # explicit week
#   ./scripts/weekly-pipeline.sh --skip-report --end-date 2026-07-24
#                                                      # instruments only, existing report
#   MOLTBOOK_PIPELINE_STAGES=report ./scripts/weekly-pipeline.sh
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
# session's Edit rule over .notes/tasks/ is built from this path.
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
TASKS_DIR="${PIPELINE_TASKS_DIR:-$PROJECT_ROOT/.notes/tasks}"
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
# diagnoses it, and files candidate tasks. It holds NO Bash: everything it
# writes goes through Edit/Write under the exact-path rules below, and the
# claims.jsonl spawn recording is done deterministically by this script from
# the .notes/tasks/ file diff (the session cannot append to the claims log).
#
# A name the CLI does not recognise in --tools is discarded in SILENCE
# (measured 2026-08-15), so a renamed built-in shrinks the session with no
# error path. C-SCOPE-8 in tests/test_weekly_pipeline_session_scope_shell.py
# asks the real CLI which names it honours. `--tools "default"` as a sole
# value fails OPEN to the whole built-in set — never reach for it.
WEEKLY_TOOLS="Read,Glob,Grep,Edit,Write,Skill"

# Timeouts. The weekly session does the work of the former report (45min cap)
# + translation (15min) + diagnosis (30min) sessions in one; 90 min total is
# a hang detector, not a budget (the three-session chain measured 18-20 min
# end to end on real runs).
WEEKLY_TIMEOUT="${PIPELINE_WEEKLY_TIMEOUT:-5400}"
DEADCODE_TIMEOUT="${PIPELINE_DEADCODE_TIMEOUT:-300}"
DOCSCAN_TIMEOUT="${PIPELINE_DOCSCAN_TIMEOUT:-180}"
IDENTITY_TIMEOUT="${PIPELINE_IDENTITY_TIMEOUT:-900}"
CHAIN_DEADLINE_SECONDS="${PIPELINE_DEADLINE_SECONDS:-10800}"   # 09:00 → 12:00

STAGES="${MOLTBOOK_PIPELINE_STAGES:-report,valuelayer,deadcode,docsscan}"

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
# Captured once and reused by the identity live-run guard below: a run started
# just before midnight would otherwise default END_DATE off one "yesterday" and
# compare against another.
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
# The session writes into reports/.private/ (excluded from the public
# sync-research-data rsync) and the chain promotes to the canonical paths only
# after the structural gate below — the tmp -> check -> promote order the old
# report generator had, restored at the pipeline seam (2026-08-24 security
# review MEDIUM: a truncated or injected report must never sit on a path the
# public sync or next week's PREV_REPORTS glob can pick up).
PRIVATE_DIR="$MOLTBOOK_HOME/reports/.private"
# Per-run task staging: the session files candidates HERE, never into the
# live store — the store supports concurrent sessions, so live-store writes
# plus a directory diff would misattribute concurrent filings and let a
# steered session clobber owner-written tasks (codex review 2026-08-24 P1).
# The chain validates and moves staged candidates after the report gate.
PRIVATE_TASKS="$PRIVATE_DIR/tasks-$END_DATE"
REPORT_PATH="$REPORT_DIR/weekly-${END_DATE}.md"
REPORT_JA="$REPORT_DIR/weekly-${END_DATE}.ja.md"
FINDINGS_MD="$REPORT_DIR/weekly-${END_DATE}-findings.md"
FINDINGS_JA="$REPORT_DIR/weekly-${END_DATE}-findings.ja.md"

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

with_timeout() {  # with_timeout <seconds> <cmd...>
    local secs="$1"; shift
    if command -v timeout >/dev/null 2>&1; then
        timeout "$secs" "$@"
    else
        "$@"   # degradation when coreutils is absent from launchd's PATH
    fi
}

# The report's machine contract (moved here from weekly-analysis.sh when that
# script became materials-only): a csv of the absent A-E section headings,
# empty = complete. Size is not the contract — 2026-08-21 promoted a
# 37,409-byte report whose A-C were gone. Letter prefix only: heading wording
# is the model's to vary, the letter is the format's.
report_missing_parts() {  # report_missing_parts <file>
    local file="$1" letter missing=""
    for letter in A B C D E; do
        grep -q "^## $letter\." "$file" || missing="${missing:+$missing,}$letter"
    done
    printf '%s' "$missing"
}

# --- Preflight (fail before burning work) ---
for bin in claude git uv python3; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo "ERROR: '$bin' not found on PATH ($PATH)" >&2
        audit stage_result stage=preflight result=fail reason=PREFLIGHT_MISSING_BIN "bin=$bin"
        exit 1
    fi
done

audit chain_start end_date="$END_DATE" stages="$STAGES"
echo "[$RUN_ID] chain start (stages: $STAGES)"

# --- Stage 1: materials + the ONE weekly session ---
REPORT_RAN=0
if stage_enabled report && [[ $SKIP_REPORT -eq 0 ]]; then
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
    rm -f "$PRIVATE_DIR"/weekly-"$END_DATE"*.md "$PRIVATE_TASKS"/*.md
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
        # Write grants (mechanic 3: Edit rules cover Write): everything the
        # session authors lands in reports/.private/ — the four report/
        # findings files plus a per-run task staging dir for Phase 4
        # candidate filing. The session NEVER touches the live task store:
        # the store supports concurrent sessions (a triage session or the
        # owner may write it during this 90-min run), so a live-store grant
        # plus a directory diff both misattributes concurrent filings and
        # lets a steered session clobber owner-written tasks with no history
        # to restore from (codex review 2026-08-24 P1). The chain validates
        # and moves the staged candidates below, deterministically, and the
        # session holds no Bash — the claims.jsonl spawn append is the
        # chain's too.
        #
        # Read is POSITIVELY scoped (2026-08-24 security review HIGH): this
        # session reads nonce-framed untrusted post bodies, and its outputs
        # are published by sync-research-data — a bare Read grant would let an
        # injected instruction quote any local file (~/.ssh, ~/.aws, tokens)
        # into a report the next sync pushes to the public data repo. The
        # allow list names the repo checkout, the analysis dir and the logs
        # workspace; everything else falls to --permission-mode manual's
        # refusal. The episode-log denies still outrank the logs allow, and
        # they are PREFIX-shaped (`20*.jsonl*` — covering .bak,
        # .pre-cleanup.bak and any future backup convention, the same rule
        # ~/.claude/hooks/_episode-log-common.sh moved to after the suffix
        # form was bypassed; 2026-08-24 security review HIGH).
        if with_timeout "$WEEKLY_TIMEOUT" claude -p "/weekly-report $MATERIALS" \
            --add-dir "$MOLTBOOK_HOME/reports" \
            --add-dir "$MOLTBOOK_HOME/logs" \
            --permission-mode manual \
            --tools "$WEEKLY_TOOLS" \
            --strict-mcp-config \
            --setting-sources project \
            --allowedTools "Glob,Grep,Read(/$PROJECT_ROOT/**),Read(/$REPORT_DIR/**),Read(/$PRIVATE_DIR/**),Read(/$MOLTBOOK_HOME/logs/**),Edit(/$PRIVATE_DIR/weekly-$END_DATE.md),Edit(/$PRIVATE_DIR/weekly-$END_DATE.ja.md),Edit(/$PRIVATE_DIR/weekly-$END_DATE-findings.md),Edit(/$PRIVATE_DIR/weekly-$END_DATE-findings.ja.md),Edit(/$PRIVATE_TASKS/**)" \
            --disallowedTools "Bash,WebFetch,WebSearch,NotebookEdit,Read(/$MOLTBOOK_HOME/credentials.json),Read(/$MOLTBOOK_HOME/logs/20*.jsonl*),Read(/$MOLTBOOK_HOME/logs/agent-launchd.log*),Edit(/$MOLTBOOK_HOME/logs/**),Edit(/$MOLTBOOK_HOME/.staged/**),Edit(/$MOLTBOOK_HOME/skills/**),Edit(/$MOLTBOOK_HOME/rules/**),Edit(/$MOLTBOOK_HOME/constitution/**),Edit(/$MOLTBOOK_HOME/identity.md),Edit(/$MOLTBOOK_HOME/knowledge.json)" \
            --output-format text \
            > "$RUN_LOG_DIR/weekly-session.log" 2>&1; then
            audit stage_result stage=report result=ok
        else
            audit stage_result stage=report result=fail reason=REPORT_SESSION_FAIL
        fi
    fi
else
    audit stage_result stage=report result=skipped
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
    mv "$PRIVATE_REPORT" "$REPORT_PATH"
    if [[ -s "$PRIVATE_DIR/weekly-${END_DATE}.ja.md" ]]; then
        mv "$PRIVATE_DIR/weekly-${END_DATE}.ja.md" "$REPORT_JA"
    else
        add_reason REPORT_JA_MISSING
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
        for stale in "$FINDINGS_MD" "$FINDINGS_JA"; do
            [[ -e "$stale" ]] && mv "$stale" "$PRIVATE_DIR/$(basename "$stale").superseded-$RUN_ID"
        done
    else
        mv "$PRIVATE_FINDINGS" "$FINDINGS_MD"
        if [[ -s "$PRIVATE_DIR/weekly-${END_DATE}-findings.ja.md" ]]; then
            mv "$PRIVATE_DIR/weekly-${END_DATE}-findings.ja.md" "$FINDINGS_JA"
        else
            add_reason FINDINGS_JA_MISSING
        fi
        audit stage_result stage=diagnosis result=ok
    fi
fi
# The canonical report is the chain's hard requirement whether or not the
# session ran (a --skip-report / partial STAGES rerun keeps -s semantics).
if [[ ! -s "$REPORT_PATH" ]]; then
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

# --- Candidate intake (deterministic; the session cannot touch the store) ---
# The session filed candidates into $PRIVATE_TASKS. Each staged file is
# validated, moved into the live store, and recorded in claims.jsonl. A file
# that fails validation stays quarantined in staging (visible to the Saturday
# reader), never silently dropped and never half-adopted. Producer citations
# are read from the file body (backtick `path:line`); a file with none is
# still recorded (origin gate does not require --producer). Failures here
# must not kill the chain — the moved task files are the ground truth and the
# triage session reads the store, not the claims log.
SPAWNED=0
for staged in "$PRIVATE_TASKS"/*.md; do
    [[ -e "$staged" ]] || continue
    newfile="$(basename "$staged")"
    task_id="${newfile%.md}"
    if ! [[ "$task_id" =~ ^T-[A-Z0-9][A-Z0-9-]*$ ]]; then
        echo "WARNING: staged task with non-conforming name left in staging: $newfile" >&2
        add_reason SPAWN_RECORD_SKIPPED
        continue
    fi
    if [[ -e "$TASKS_DIR/$newfile" ]]; then
        # Never overwrite a task that already exists in the store — it may be
        # the owner's or a concurrent session's.
        echo "WARNING: staged task collides with an existing store entry, left in staging: $newfile" >&2
        add_reason SPAWN_RECORD_SKIPPED
        continue
    fi
    # ADR-0098 D2: filings are candidates — no readiness claim. A `state:`
    # line other than candidate is normalized and named; a file with NO
    # parseable state line stays in staging (claims.py ready would never
    # surface it, so moving it would make the finding vanish silently —
    # codex review 2026-08-24 P2).
    if ! grep -q '^state:' "$staged"; then
        echo "WARNING: staged task has no state: line, left in staging: $newfile" >&2
        add_reason SPAWN_RECORD_SKIPPED
        continue
    fi
    if ! grep -q '^state: candidate' "$staged"; then
        sed -i '' 's/^state: .*/state: candidate/' "$staged"
        add_reason SPAWN_STATE_NORMALIZED
        echo "WARNING: $newfile filed with a non-candidate state — normalized" >&2
    fi
    mv "$staged" "$TASKS_DIR/$newfile"
    # First backtick path:line citation in the body, if any.
    # shellcheck disable=SC2016  # the single-quoted backticks are a grep pattern, not an expansion
    producer=$(grep -oE '`[^` :]+:[0-9]+(-[0-9]+)?`' "$TASKS_DIR/$newfile" 2>/dev/null \
        | head -1 | tr -d '`')
    producer_args=()
    [[ -n "$producer" ]] && producer_args=(--producer "$producer")
    if (cd "$PROJECT_ROOT" && python3 "$CLAIMS_PY" spawn "$task_id" \
            --origin gate --note "weekly $END_DATE diagnosis" \
            ${producer_args[@]+"${producer_args[@]}"}) \
            >> "$RUN_LOG_DIR/spawn.log" 2>&1; then
        SPAWNED=$((SPAWNED + 1))
    else
        add_reason SPAWN_RECORD_FAIL
        echo "WARNING: claims.py spawn failed for $task_id (see spawn.log)" >&2
    fi
done
audit stage_result stage=spawn result=ok spawned="$SPAWNED"
echo "[$RUN_ID] filed candidates recorded: $SPAWNED"
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
                        add_reason IDENTITY_BACKFILL_SKIP
                        audit stage_result stage=identity result=skipped \
                            reason=IDENTITY_BACKFILL_SKIP
                    elif [[ "$insight_fresh" != "true" ]]; then
                        add_reason IDENTITY_INSIGHT_PENDING
                        audit stage_result stage=identity result=skipped \
                            reason=IDENTITY_INSIGHT_PENDING
                    elif [[ "$vl_staging_pending" != "0" ]]; then
                        add_reason IDENTITY_STAGING_BUSY
                        audit stage_result stage=identity result=skipped \
                            reason=IDENTITY_STAGING_BUSY
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
                            add_reason IDENTITY_STAGING_RACE
                            audit stage_result stage=identity result=skipped \
                                reason=IDENTITY_STAGING_RACE
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
        uv run --no-sync -q python -c '
import json, sys
from datetime import date, timedelta
from pathlib import Path
from contemplative_agent.core.skill_selection import (
    NEVER_SELECTED_DORMANT_WINDOW_DAYS,
    never_selected_reading_json,
    read_never_selected,
)

# since/until rather than days=: the dormant cut must be anchored to the
# run END_DATE, not the wall clock, so a backfill run reads the window it
# claims to. Both ends inclusive, so since = END_DATE - (N - 1).
home = Path(sys.argv[1])
until = date.fromisoformat(sys.argv[2])
reading = read_never_selected(
    home / "logs",
    since=until - timedelta(days=NEVER_SELECTED_DORMANT_WINDOW_DAYS - 1),
    until=until,
    skills_dir=home / "skills",
)
print(json.dumps(never_selected_reading_json(reading)))
' "$MOLTBOOK_HOME" "$END_DATE") \
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

# --- Chain end (no packet: the Saturday gate reads the artifacts directly) ---
audit chain_end result=ok report="$REPORT_PATH" findings="$FINDINGS_MD" \
    reasons="${REASONS:-none}"
echo "[$RUN_ID] artifacts:"
echo "  report:    $REPORT_PATH"
echo "  findings:  $FINDINGS_MD"
echo "  valuelayer: $VALUE_LAYER_JSON"
echo "  deadcode:  $DEADCODE_JSON"
echo "  docsscan:  $DOCSCAN_JSON"
echo "  neversel:  $NEVER_SELECTED_JSON"
echo "[$RUN_ID] done (reasons: ${REASONS:-none})"

#!/bin/bash
# Unattended weekly chain (ADR-0085): report → diagnosis → fix → insight
# review → value-layer due check → dead-code scan → improvement check →
# decision packet. Human involvement is compressed into the single Saturday
# gate (/weekly-gate); nothing here commits, pushes, or adopts.
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
# Stage 2 interpolates this into permission rules, so its shape is load-bearing
# in two ways the rest of the script does not care about (same reason END_DATE
# gets a shape check below):
#
#   absolute — the rules are built by prefixing `/` to reach the `//absolute`
#     form. A RELATIVE value renders them single-slash = project-root-anchored,
#     where the allow rule grants nothing (loud: the stage fails) but the deny
#     rules protect nothing (silent). A trailing slash is harmless to anchoring
#     (`//home//reports` still reads as absolute) and is trimmed only so the
#     rendered rules stay legible.
#   no permission-spec metacharacters — `,` splits one rule into two malformed
#     ones, `()[]*?` reshape the glob, and `\` is consumed as a glob escape
#     (measured: a deny rule over a path containing `\` matched nothing while
#     the allow rule still matched — the exact "looks correct, protects
#     nothing" failure this guard exists to prevent). All are legal in a path.
#     Stated as an ALLOWLIST, for the same reason the test module rejects
#     blocklists of tool names: a blocklist silently admits whichever
#     metacharacter the matcher grows next.
MOLTBOOK_HOME="${MOLTBOOK_HOME%/}"
if [[ "$MOLTBOOK_HOME" != /* ]]; then
    echo "ERROR: MOLTBOOK_HOME must be an absolute path (got: $MOLTBOOK_HOME)" >&2
    exit 1
fi
if ! [[ "$MOLTBOOK_HOME" =~ ^[A-Za-z0-9._/@+-]+$ ]]; then
    echo "ERROR: MOLTBOOK_HOME may only contain [A-Za-z0-9._/@+-] — stage 2 builds" >&2
    echo "       tool-permission rules from it, and any other character can" >&2
    echo "       silently reshape a rule into one that protects nothing" >&2
    echo "       (got: $MOLTBOOK_HOME)" >&2
    exit 1
fi
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
# CONCERNS-driven re-entry fix sessions per finding (T-PIPELINE-REVIEWLOOP);
# reviews run at most MAX_REVIEW_ROUNDS+1 times. Orthogonal to
# MAX_FIX_ATTEMPTS, which bounds Verify retries within one round.
MAX_REVIEW_ROUNDS="${PIPELINE_MAX_REVIEW_ROUNDS:-1}"
DIAGNOSIS_TIMEOUT="${PIPELINE_DIAGNOSIS_TIMEOUT:-1800}"
FIX_TIMEOUT="${PIPELINE_FIX_TIMEOUT:-1200}"
VERIFY_TIMEOUT="${PIPELINE_VERIFY_TIMEOUT:-900}"
REVIEW_TIMEOUT="${PIPELINE_REVIEW_TIMEOUT:-600}"
INSIGHT_TIMEOUT="${PIPELINE_INSIGHT_TIMEOUT:-900}"
IMPROVE_TIMEOUT="${PIPELINE_IMPROVE_TIMEOUT:-900}"
DEADCODE_TIMEOUT="${PIPELINE_DEADCODE_TIMEOUT:-300}"
DOCSCAN_TIMEOUT="${PIPELINE_DOCSCAN_TIMEOUT:-180}"
LEDGERWATCH_TIMEOUT="${PIPELINE_LEDGERWATCH_TIMEOUT:-120}"
IDENTITY_TIMEOUT="${PIPELINE_IDENTITY_TIMEOUT:-900}"
CHAIN_DEADLINE_SECONDS="${PIPELINE_DEADLINE_SECONDS:-10800}"   # 09:00 → 12:00

STAGES="${MOLTBOOK_PIPELINE_STAGES:-report,diagnosis,fix,insight,valuelayer,deadcode,docsscan,ledgerwatch,improve,packet}"
# The ledger is repo-local by convention (rule: task-tracking); overridable
# so tests can point the scan at a fixture ledger.
LEDGER_PATH="${MOLTBOOK_LEDGER_PATH:-}"

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
# END_DATE flows into artifact paths and the value-layer --as-of; validate
# the shape once here for every consumer (2026-08-10 security review L5).
if ! [[ "$END_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "ERROR: --end-date must be YYYY-MM-DD (got: $END_DATE)" >&2
    exit 1
fi

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
# Session transcripts and patches can carry sensitive content the sessions
# saw; keep them owner-only (2026-07-29 security review H2).
chmod 700 "$RUN_LOG_DIR" "$PATCH_DIR" "$PROMPT_PATCH_DIR" 2>/dev/null || true
# The patch dirs are keyed by END_DATE, not RUN_ID: a same-week rerun would
# otherwise present leftovers from a previous attempt as this run's output
# (2026-07-29 codex review P2). This run owns the week's dirs — clear them.
rm -f "$PATCH_DIR"/*.patch "$PROMPT_PATCH_DIR"/*.patch 2>/dev/null || true

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

fence_for() {  # fence_for <file> — a backtick fence longer than any run in <file>
    # Diffs of this very repo contain ``` runs (prompt files, fenced strings in
    # tests); a hardcoded three-backtick fence would close early and let the
    # remainder of the embedded content render as prompt text (2026-08-01
    # security review H1).
    local longest
    longest=$(grep -o '`\{1,\}' "$1" 2>/dev/null \
        | awk '{ if (length($0) > m) m = length($0) } END { print m + 0 }')
    (( longest < 2 )) && longest=2
    printf '%.0s`' $(seq 1 $((longest + 1)))
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
# Completeness = the file terminates in the skill's mandatory closing section.
# A bare -s check would adopt a partial file from a timeout-killed previous
# attempt as a finished diagnosis (2026-07-29 review).
findings_complete() {
    [[ -s "$FINDINGS_MD" ]] && grep -q '^## Diagnosis Metadata' "$FINDINGS_MD"
}

if stage_enabled diagnosis && ! findings_complete; then
    if [[ -s "$FINDINGS_MD" ]]; then
        mv "$FINDINGS_MD" "$FINDINGS_MD.incomplete.$$" 2>/dev/null || true
        audit stage_result stage=diagnosis result=note reason=FINDINGS_INCOMPLETE_REPLACED
        echo "[$RUN_ID] stage 2: previous findings incomplete — set aside, regenerating"
    fi
    if deadline_exceeded; then
        add_reason CHAIN_DEADLINE
        audit stage_result stage=diagnosis result=skipped reason=CHAIN_DEADLINE
    else
        echo "[$RUN_ID] stage 2: diagnosis"
        # --add-dir is scoped to reports/ + logs/, NOT $MOLTBOOK_HOME (2026-07-29
        # security review C2). Keep that scoping, but do NOT read it as a read
        # boundary: --add-dir bounds the workspace, not the Read tool, and the
        # ambient bare `Read` allow is consulted before the mode — measured
        # 2026-08-15, this session read an absolute path outside both added
        # dirs. credentials.json therefore needs an explicit deny, not a
        # narrow --add-dir. It matters because the one file this session may
        # author, reports/analysis/weekly-*-findings.md, is rsynced to the
        # PUBLIC data repo by sync-research-data.sh (which excludes
        # credentials.json itself, but not reports/analysis/) — read-then-author
        # is a laundering path from the key to a published artifact.
        #
        # What this session must not reach: ADR-0091 made logs/audit.jsonl the
        # control input for stage 5b's identity-due read, so a write there
        # forges the trigger for a later unattended LLM run (2026-08-10 review
        # M1). Three mechanics, all verified against the real binary
        # 2026-08-15, decide how that is spelled:
        #
        # 1. --allowedTools only ever ADDS. It never narrows the ambient
        #    permission mode, and it never narrows the settings-file allow
        #    rules, which are consulted BEFORE the mode. So neither the mode
        #    nor a short allow list can bound this session on its own: with
        #    `--permission-mode manual` and no Bash grant at all, the operator's
        #    ~/.claude/settings.json `Bash(tee:*)` still executed
        #    `echo … | tee <path>`.
        # 2. Only DENY rules outrank both the allow rules and the mode. They
        #    are the sole control here that does not depend on ambient config.
        # 3. File writes are gated by Edit(...) rules; a Write(...) pattern
        #    parses but matches nothing (the CLI says so itself).
        #
        # Hence: writes are pinned to exactly the two files the skill authors,
        # and Bash is denied WHOLESALE rather than allow-listed. An allow list
        # could not have held — the read-only-looking `Bash(git log:*)` grant
        # this stage used to carry is itself an arbitrary-write primitive
        # (`git log --output=<any path> --format=tformat:<any content>`), and
        # ambient rules re-grant `git`, `tee`, `cp`, `ln`, `curl` regardless.
        # The skill needs no Bash: its reading is Read/Glob/Grep, including the
        # one episode-log grep in its F1 checklist. Redirection and `&&`
        # chaining do not defeat a Bash prefix rule (also verified), but that
        # only matters for sessions that still hold one.
        #
        # WebFetch/WebSearch are denied for the same reason and by the same
        # mechanism: they are ambiently allowed, the skill references no network
        # source, and this is the one session holding --add-dir over the raw
        # episode logs — so egress here is an exfiltration path for untrusted
        # content the session was given to read. (The old C1 comment asserted no
        # egress surface; that half was false too.)
        #
        # The Edit deny rules below are redundancy for the Edit face only —
        # they do NOT gate Bash. Converting the other four claude -p sites is
        # T-CHAIN-PERM-SWEEP; the durable fix for the inherited allow list is
        # config isolation, which needs credential provisioning (an isolated
        # CLAUDE_CONFIG_DIR is unauthenticated).
        with_timeout "$DIAGNOSIS_TIMEOUT" claude -p "/weekly-report-diagnosis $REPORT_PATH" \
            --add-dir "$MOLTBOOK_HOME/reports" \
            --add-dir "$MOLTBOOK_HOME/logs" \
            --permission-mode manual \
            --allowedTools "Read,Glob,Grep,Edit(/$REPORT_DIR/weekly-$END_DATE-findings.md),Edit(/$REPORT_DIR/weekly-$END_DATE-findings.ja.md)" \
            --disallowedTools "Bash,WebFetch,WebSearch,NotebookEdit,Read(/$MOLTBOOK_HOME/credentials.json),Edit(/$MOLTBOOK_HOME/logs/**),Edit(/$MOLTBOOK_HOME/.staged/**),Edit(/$REPORT_DIR/patches/**),Edit(/$REPORT_DIR/weekly-$END_DATE-packet.md),Edit(/$REPORT_DIR/weekly-$END_DATE-insight-review.md),Edit(/$REPORT_DIR/weekly-$END_DATE.md)" \
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
elif findings_complete; then
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
else
    audit stage_result stage=parse result=skipped
fi

# --- Stage 4: fix (one worktree + fresh claude context per F1) ---
run_verify() {  # run_verify <worktree> <logfile>
    local wt="$1" log="$2"
    # Each step is individually bounded: an unbounded Verify (network-stalled
    # uv sync, hung test) would blow straight through the chain deadline,
    # which is only checked between attempts (2026-07-29 review, HIGH).
    (
        cd "$wt" || exit 1
        # uv.lock is gitignored, so the worktree checkout lacks it; the copy
        # happens at worktree add. Fall back to an unpinned sync if absent.
        if [[ -f uv.lock ]]; then
            with_timeout "$VERIFY_TIMEOUT" uv sync --frozen -q >> "$log" 2>&1 || { echo "VERIFY: uv sync failed" >> "$log"; exit 1; }
        else
            with_timeout "$VERIFY_TIMEOUT" uv sync -q >> "$log" 2>&1 || { echo "VERIFY: uv sync failed" >> "$log"; exit 1; }
        fi
        with_timeout "$VERIFY_TIMEOUT" uv run -q ruff check src/ tests/ scripts/ >> "$log" 2>&1 || { echo "VERIFY: ruff failed" >> "$log"; exit 1; }
        with_timeout "$VERIFY_TIMEOUT" uv run -q lint-imports >> "$log" 2>&1 || { echo "VERIFY: lint-imports failed" >> "$log"; exit 1; }
        with_timeout "$VERIFY_TIMEOUT" uv run -q pytest tests/ -q -x >> "$log" 2>&1 || { echo "VERIFY: pytest failed" >> "$log"; exit 1; }
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

    local prompt_file="$RUN_LOG_DIR/fix-$safe_fid-prompt.md"
    # base_prompt holds what STARTED the current round (finding, plus the
    # reviewer concerns on a re-entry). Verify-failure retries rebuild
    # prompt_file from it so the concerns survive a failed attempt
    # (2026-08-01 codex review P2).
    local base_prompt="$RUN_LOG_DIR/fix-$safe_fid-base-prompt.md"
    # The finding text descends from external SNS content via the weekly
    # report's E section — wrap it as untrusted data before it becomes the
    # prompt of a tool-using session (ADR-0007; 2026-07-29 security review H1).
    {
        echo "<untrusted_finding>"
        cat "$bodyfile"
        echo "</untrusted_finding>"
    } > "$prompt_file"
    cp "$prompt_file" "$base_prompt"

    # --- fix / Verify / review rounds (T-PIPELINE-REVIEWLOOP, ADR-0085) ---
    # round 0 is the original fix; round N>=1 is a re-entry answering review
    # N's CONCERNS. Verify retries (MAX_FIX_ATTEMPTS) are re-granted per round
    # — a shared pool would let one flaky Verify starve the concern feedback.
    # Monotonicity: a round that cannot produce a verified diff rolls back to
    # the previous round's verified one instead of destroying it.
    local round=0 passed=0 rolled_back=0 total_attempts=0
    local diff_prev="" diff_cur="" names_prev="" names_cur=""
    while :; do
        local attempt=1 fail_code=""
        passed=0
        while (( attempt <= MAX_FIX_ATTEMPTS )); do
            if deadline_exceeded; then
                add_reason CHAIN_DEADLINE
                fail_code=CHAIN_DEADLINE
                if (( round == 0 )); then
                    audit fix_result fix_id="$fid" scope="$scope" result=failed \
                        attempts="$total_attempts" reason=CHAIN_DEADLINE
                    git -C "$PROJECT_ROOT" worktree remove --force "$wt" >/dev/null 2>&1
                    return
                fi
                break
            fi
            total_attempts=$((total_attempts + 1))
            echo "[$RUN_ID]   $fid round $round attempt $attempt ($scope)"
            # Edit/Write are path-scoped to the worktree (cwd): a bare grant would
            # let an injected finding write outside the worktree — invisible to
            # Verify, the reviewer, and the exported patch (2026-07-29 security
            # review C3). Bash is limited to the two Verify tools; no generic
            # `uv run:*` (it reaches `uv run python -c ...`).
            (
                cd "$wt" || exit 1
                with_timeout "$FIX_TIMEOUT" claude -p "$(cat "$prompt_file")" \
                    --system-prompt "$(cat "$PROMPTS/fix-implementation.md")" \
                    --allowedTools "Read,Glob,Grep,Edit(./**),Write(./**),Bash(uv run pytest:*),Bash(uv run ruff:*),Bash(git diff:*),Bash(git status:*),Bash(ls:*),Bash(grep:*)" \
                    --output-format text
            ) > "$fixlog-attempt$total_attempts.log" 2>&1
            local rc=$?
            if [[ $rc -ne 0 ]]; then
                # 124 is coreutils timeout's exit code
                fail_code=FIX_SESSION_FAIL; [[ $rc -eq 124 ]] && fail_code=FIX_TIMEOUT
                add_reason "$fail_code"
                audit fix_attempt fix_id="$fid" attempt="$total_attempts" \
                    result=session_fail reason="$fail_code"
                break
            fi
            if [[ "$scope" == "prompt" ]]; then
                # A prompt-scope finding may still have produced code edits (mixed
                # references). A pure-prompt diff needs no Verify — the human reads
                # it full text — but untested code changes must never be marked
                # ready (2026-07-29 codex review P2).
                local touches_code
                touches_code=$(cd "$wt" && git add -A >/dev/null 2>&1; git diff --cached --name-only \
                    | grep -E '^(src|scripts|tests)/' || true)
                if [[ -z "$touches_code" ]]; then
                    passed=1
                    break
                fi
            fi
            if run_verify "$wt" "$fixlog-verify$total_attempts.log"; then
                audit fix_attempt fix_id="$fid" attempt="$total_attempts" result=verify_pass
                passed=1
                break
            fi
            audit fix_attempt fix_id="$fid" attempt="$total_attempts" result=verify_fail
            # Never retry on identical input: feed the failure back (bounded).
            # Rebuilt from base_prompt, not from scratch — on a re-entry round
            # the reviewer concerns must survive the retry (codex P2).
            {
                cat "$base_prompt"
                echo ""
                echo "## Verify failure output (previous attempt — fix the cause, do not weaken checks)"
                echo '```'
                tail -n 120 "$fixlog-verify$total_attempts.log"
                echo '```'
            } > "$prompt_file"
            attempt=$((attempt + 1))
        done

        if (( passed == 0 )); then
            if (( round > 0 )) && [[ -s "$diff_prev" ]]; then
                # Roll back: the previous round's diff already passed Verify;
                # a failed re-entry must not cost the gate a working patch.
                add_reason REVIEW_ROUND_ABANDONED
                audit review_round_abandoned fix_id="$fid" round="$round" \
                    reason=REVIEW_ROUND_ABANDONED detail="${fail_code:-VERIFY_FAIL_MAX_ATTEMPTS}"
                echo "[$RUN_ID]   $fid round $round abandoned — keeping round $((round - 1)) diff"
                rolled_back=1
                passed=1
                break
            fi
            if [[ -z "$fail_code" ]]; then
                add_reason VERIFY_FAIL_MAX_ATTEMPTS
                audit fix_result fix_id="$fid" scope="$scope" result=failed \
                    attempts="$total_attempts" reason=VERIFY_FAIL_MAX_ATTEMPTS
            else
                audit fix_result fix_id="$fid" scope="$scope" result=failed \
                    attempts="$total_attempts" reason="$fail_code"
            fi
            git -C "$PROJECT_ROOT" worktree remove --force "$wt" >/dev/null 2>&1
            git -C "$PROJECT_ROOT" worktree prune >/dev/null 2>&1
            return
        fi

        # Snapshot this round's verified diff AND its touched-path list. The
        # export at the bottom and the scope check read the snapshots, never
        # live worktree state — after a rollback the worktree holds the
        # abandoned round. The path list comes from git (--name-only), not
        # from parsing the diff text: binary changes and pure renames emit no
        # `--- a/`/`+++ b/` header lines, which would blind a text-parsed
        # scope check (2026-08-01 security review C1).
        diff_cur="$fixlog-diff-round$round.patch"
        names_cur="$fixlog-names-round$round.txt"
        (cd "$wt" && git add -A && git diff --cached) > "$diff_cur" 2>>"$fixlog-export.log"
        (cd "$wt" && git diff --cached --name-only) > "$names_cur" 2>>"$fixlog-export.log"

        [[ "$scope" != "code" ]] && break
        if deadline_exceeded; then
            if (( round > 0 )); then
                # The re-entry diff passed Verify but its re-review never ran:
                # exporting it would pair a CONCERNS verdict (and review body)
                # with a diff the reviewer never saw. Roll back to keep the
                # packet's verdict↔diff coherent (2026-08-01 codex review P2).
                rolled_back=1
                add_reason REVIEW_ROUND_ABANDONED
                audit review_round_abandoned fix_id="$fid" round="$round" \
                    reason=REVIEW_ROUND_ABANDONED detail=CHAIN_DEADLINE
            fi
            break
        fi

        if (( round > 0 )) && cmp -s "$diff_prev" "$diff_cur"; then
            # Never retry on identical input: re-reviewing an unchanged diff
            # can only repeat the same verdict. The implementer's rebuttal
            # stays in its attempt log; the standing CONCERNS stays on record.
            # round is on the review axis (the review that was NOT run),
            # matching review_result's numbering (2026-08-01 code review).
            audit review_skipped fix_id="$fid" round="$((round + 1))" detail=DIFF_UNCHANGED
            echo "[$RUN_ID]   $fid round $round: diff unchanged — review not repeated"
            break
        fi

        local review_n=$((round + 1))
        local review_input="$RUN_LOG_DIR/fix-$safe_fid-review$review_n-input.md"
        # The finding descends from external SNS content — the reviewer gets
        # it wrapped exactly like the implementer does, and the diff fence is
        # sized to outrun any backtick run inside the diff (2026-08-01
        # security review H1).
        local diff_fence
        diff_fence=$(fence_for "$diff_cur")
        {
            echo "<untrusted_finding>"
            cat "$bodyfile"
            echo "</untrusted_finding>"
            if (( round > 0 )); then
                echo ""
                echo "## Previous review (round $round) — check whether the new diff addresses it"
                cat "$fixlog-review$round.log"
                echo ""
                echo "## Implementer's response to that review (its session summary — may rebut points instead of changing code)"
                tail -n 60 "$fixlog-attempt$total_attempts.log"
            fi
            echo ""
            echo "## Diff under review"
            echo "${diff_fence}diff"
            cat "$diff_cur"
            echo "$diff_fence"
        } > "$review_input"
        with_timeout "$REVIEW_TIMEOUT" claude -p \
            --system-prompt "$(cat "$PROMPTS/fix-review.md")" \
            --allowedTools "Read,Glob,Grep" \
            --output-format text \
            < "$review_input" \
            > "$fixlog-review$review_n.log" 2>&1
        verdict=$(grep -m1 '^VERDICT:' "$fixlog-review$review_n.log" | sed 's/^VERDICT: *//')
        [[ -z "$verdict" ]] && verdict="REVIEW_FAIL"
        audit review_result fix_id="$fid" round="$review_n" verdict="$verdict"
        # APPROVE ends the loop; REVIEW_FAIL is terminal too — no body to feed.
        [[ "$verdict" != "CONCERNS" ]] && break
        (( round >= MAX_REVIEW_ROUNDS )) && break

        # Re-entry: the review body becomes bounded feedback. It chains from
        # the finding text, so it is wrapped as untrusted data (same H1
        # rationale as the finding itself).
        {
            echo "<untrusted_finding>"
            cat "$bodyfile"
            echo "</untrusted_finding>"
            echo ""
            echo "## Reviewer concerns (round $review_n) — address each point, or rebut it in your summary; never weaken checks to satisfy the reviewer"
            echo "<untrusted_review>"
            # A reviewer output containing the literal closing tag would let
            # everything after it masquerade as trusted prompt text in the
            # tool-using fix session — neutralize the tag pair (2026-08-01
            # security review H1).
            sed 's@</\{0,1\}untrusted_review>@[stripped-tag]@g' "$fixlog-review$review_n.log"
            echo "</untrusted_review>"
        } > "$prompt_file"
        cp "$prompt_file" "$base_prompt"   # new round, new retry baseline
        diff_prev="$diff_cur"
        names_prev="$names_cur"
        round=$((round + 1))
    done

    # --- export the chosen diff (this round's, or the rollback target) ---
    local chosen_diff="$diff_cur" chosen_names="$names_cur"
    if (( rolled_back )); then
        chosen_diff="$diff_prev"
        chosen_names="$names_prev"
    fi
    local out_dir="$PATCH_DIR"
    [[ "$scope" == "prompt" ]] && out_dir="$PROMPT_PATCH_DIR"
    # Post-hoc scope check on the ACTUAL exported diff — the declared scope
    # was computed from the finding text before the session ran. A code-scope
    # patch that also touches a behavior-shaping path would otherwise reach
    # the gate as a summary row, bypassing the full-text rule (2026-07-29
    # security review C4). Deterministic, code-owned. Reads the git-computed
    # touched-path snapshot of the chosen round, never worktree state (after
    # a rollback they differ) and never the diff text (binary changes and
    # pure renames have no ---/+++ headers — 2026-08-01 security review C1).
    if [[ "$scope" == "code" ]]; then
        local out_of_scope
        out_of_scope=$(grep -Ev '^(src|scripts|tests)/' "$chosen_names" 2>/dev/null || true)
        if [[ -n "$out_of_scope" ]]; then
            out_dir="$PROMPT_PATCH_DIR"
            add_reason SCOPE_ESCALATED
            audit scope_escalation fix_id="$fid" \
                files="$(printf '%s' "$out_of_scope" | tr '\n' ' ')"
            echo "[$RUN_ID]   $fid escalated to full-text gate (touched: $out_of_scope)"
        fi
    fi
    local patch="$out_dir/$safe_fid.patch"
    if cp "$chosen_diff" "$patch" 2>>"$fixlog-export.log" && [[ -s "$patch" ]]; then
        audit fix_result fix_id="$fid" scope="$scope" result=patch_ready \
            attempts="$total_attempts" patch="$patch"
    else
        rm -f "$patch"
        add_reason EMPTY_DIFF
        audit fix_result fix_id="$fid" scope="$scope" result=failed \
            attempts="$total_attempts" reason=EMPTY_DIFF
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
                # noglob: path tokens come from LLM-authored text; a stray
                # `*` would glob-expand against the repo before reaching git
                # (2026-07-29 security review H3). Splitting is intentional.
                set -f
                # pathlist is intentionally word-split into separate git
                # pathspec arguments (directive must stay on its own line —
                # an em-dash after it silently voids it, SC1125).
                # shellcheck disable=SC2086
                stale_hit=$(git -C "$PROJECT_ROOT" log --oneline -1 \
                        --since="$FINDINGS_ISO" -- $pathlist 2>/dev/null)
                set +f
                if [[ -n "$stale_hit" ]]; then
                    add_reason FINDING_STALE
                    audit fix_result fix_id="$fid" scope="$scope" result=skipped \
                        attempts=0 reason=FINDING_STALE
                    echo "[$RUN_ID]   $fid skipped (referenced paths changed after diagnosis)"
                    continue
                fi
            fi
            if (( targeted >= MAX_FIX_TARGETS )); then
                add_reason BUDGET_EXHAUSTED
                # skipped, not failed: an over-cap finding was never attempted
                # and must not read as an error in the gate's fix table.
                audit fix_result fix_id="$fid" scope="$scope" result=skipped \
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
        # Staged items are already inlined in the prompt; --add-dir grants
        # only the adopted-skill store (dedup judgment), not the home root
        # with credentials.json (2026-07-29 security review C2).
        if with_timeout "$INSIGHT_TIMEOUT" claude -p "$(cat "$RUN_LOG_DIR/insight-input.md")" \
                --system-prompt "$(cat "$PROMPTS/insight-recommendation.md")" \
                --add-dir "$MOLTBOOK_HOME/skills" \
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

# --- Stage 5b: value-layer cadence (read-only due check + monthly identity staging) ---
# The due check is a deterministic reading over the ADR-0012 approval audit
# log (value_layer_due_check.py). Identity staging fires only when ALL of:
#   (1) the interval has elapsed (due=true),
#   (2) this is a live run (END_DATE == yesterday) — a --end-date backfill
#       must never fire a real LLM run off a stale-dated reading and reset
#       the genuine cadence clock (code review 2026-08-10 HIGH),
#   (3) the weekly insight job has COMPLETED today (.last_insight marker is
#       fresh). The insight job starts 08:00 but writes to staging only
#       after 1-2h of generation, INSIDE this chain's window — without this
#       guard, staging identity into the momentarily-empty dir would make
#       the ADR-0074 pending guard discard the whole arriving insight batch
#       (adr review 2026-08-10 CRITICAL). Marker-fresh ⟹ insight's staging
#       write already happened ("ledger first, marker last"), so
#   (4) staging is empty — is then race-free against the scheduled producer.
# Every deferral is a packet-visible reason code; the Saturday gate can run
# the distill manually right after adopt-staged empties staging. Adoption
# always stays at the gate. The constitution reading is informational only:
# an amendment is a deliberate, benched event (ADR-0090 /
# docs/runbooks/constitution-amendment.md) and must never be fired from an
# unattended chain.
VALUE_LAYER_JSON="$MOLTBOOK_HOME/pipeline/value-layer/value-layer-$END_DATE.json"
VALUE_LAYER_ARG=()
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
        if python3 "$SCRIPTS/value_layer_due_check.py" \
                --audit "$MOLTBOOK_HOME/logs/audit.jsonl" \
                --knowledge "$MOLTBOOK_HOME/knowledge.json" \
                --staged-dir "$STAGED_DIR" \
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
                VALUE_LAYER_ARG=(--value-layer "$VALUE_LAYER_JSON")
                audit stage_result stage=valuelayer result=ok \
                    identity_due="$vl_identity_due" \
                    constitution_due="$vl_constitution_due" \
                    staging_pending="$vl_staging_pending"
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
                if [[ "$vl_identity_due" == "true" ]]; then
                    if [[ "$END_DATE" != "$(date -v-1d +%Y-%m-%d)" ]]; then
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
                        # truth, and BOTH halves must exist: adopt-staged
                        # discovers candidates through the .meta.json sidecar,
                        # so a timeout kill between the two writes (or a
                        # pre-existing orphan .md) must read as fail, not as
                        # an adoptable candidate (codex review 2026-08-10 P2).
                        if [[ -f "$STAGED_DIR/identity.md" \
                                && -f "$STAGED_DIR/identity.md.meta.json" ]]; then
                            audit stage_result stage=identity result=ok
                        # A concurrent producer winning the CLI's flock is an
                        # ADR-0074 designed outcome, not an LLM fault — keep
                        # the two apart or the P4 detector counts a working
                        # guard as a recurring failure (code review M).
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

# --- Stage 6: dead-code scan (5th deterministic intake; detection ONLY) ---
# T-DEADCODE-INTAKE: unlike the four report-side intakes (weekly-analysis.sh),
# this one feeds the packet DIRECTLY, deliberately bypassing the diagnosis→fix
# LLM stages — a dead-code candidate must never become an F1 finding that the
# unattended fix stage turns into a deletion patch (deletion is structurally
# a Saturday-gate human commit; false positives are unavoidable: CLI entry
# points, config/prompts/*.md dynamic loads, Protocol indirection).
# Read-only over the repo checkout; vulture policy lives in pyproject
# [tool.vulture], exemptions in .vulture_whitelist.py. Observability only —
# a scan fault becomes a reason code, never a missing packet, and never a
# silent zero (dead_code_scan.py abstains nonzero on unparseable output; a
# PARTIAL parse is not a fault but is surfaced as DEADCODE_PARTIAL_PARSE).
# Runs BEFORE the improvement check so a recurring scan failure can feed the
# P4 recurrence detector (2026-08-07 codex review P2).
# Written OUTSIDE $MOLTBOOK_HOME/logs: next week's diagnosis session gets
# --add-dir over logs/, and the detection/deletion separation should be an
# access boundary, not just "not wired in" (2026-08-07 code review M3). The
# stable per-week path doubles as the code-owned artifact the Saturday gate
# cross-checks the packet's §5 against (security review H1).
DEADCODE_JSON="$MOLTBOOK_HOME/pipeline/dead-code/dead-code-$END_DATE.json"
DEADCODE_ARG=()
if stage_enabled deadcode; then
    if deadline_exceeded; then
        add_reason CHAIN_DEADLINE
        audit stage_result stage=deadcode result=skipped reason=CHAIN_DEADLINE
    else
        echo "[$RUN_ID] stage 6: dead-code scan"
        mkdir -p "$(dirname "$DEADCODE_JSON")"
        # --no-sync: the chain must never resolve/install packages from the
        # network unattended (security review M1) — a missing vulture then
        # fails loud as DEADCODE_SCAN_FAIL instead of auto-installing.
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
                DEADCODE_ARG=(--dead-code "$DEADCODE_JSON")
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

# --- Stage 6b: docs-consistency scan (6th deterministic intake; ADR-0093) ---
# Same detection/repair separation as the dead-code intake: the scan feeds
# the packet directly, bypassing the diagnosis→fix LLM stages — a doc edit is
# structurally a Saturday-gate human commit. Reads only the repo checkout's
# own self-authored docs (no untrusted text). stdlib-only → python3, no uv.
# Observability only — a scan fault becomes DOCSCAN_FAIL, never a missing
# packet, and never a silent "docs all clean" (the scan abstains nonzero).
DOCSCAN_JSON="$MOLTBOOK_HOME/pipeline/docs-consistency/docs-consistency-$END_DATE.json"
DOCSCAN_ARG=()
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
                DOCSCAN_ARG=(--docs-scan "$DOCSCAN_JSON")
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

# --- Stage 6c: ledger condition watch (7th deterministic intake; ADR-0093) ---
# Polls the machine-checkable unblock conditions annotated on blocked rows of
# the local task ledger (.notes/TASKS.md — gitignored, which is why this can
# only run here and never in a cloud agent). Network use is bounded reads of
# status fields mapped to a closed vocabulary inside the scan — no package
# resolution, no response text reaches the packet (ADR-0093). Acting on a
# fired condition stays a human decision at the gate. Observability only.
LEDGERWATCH_JSON="$MOLTBOOK_HOME/pipeline/ledger-watch/ledger-watch-$END_DATE.json"
LEDGERWATCH_ARG=()
if stage_enabled ledgerwatch; then
    if deadline_exceeded; then
        add_reason CHAIN_DEADLINE
        audit stage_result stage=ledgerwatch result=skipped reason=CHAIN_DEADLINE
    else
        echo "[$RUN_ID] stage 6c: ledger condition watch"
        mkdir -p "$(dirname "$LEDGERWATCH_JSON")"
        LEDGER_ARG=()
        [[ -n "$LEDGER_PATH" ]] && LEDGER_ARG=(--ledger "$LEDGER_PATH")
        if with_timeout "$LEDGERWATCH_TIMEOUT" python3 \
                "$SCRIPTS/ledger_condition_scan.py" \
                ${LEDGER_ARG[@]+"${LEDGER_ARG[@]}"} \
                > "$LEDGERWATCH_JSON" 2>"$RUN_LOG_DIR/ledgerwatch.err"; then
            lw_counts=$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
print(data['watch_count'], data['fired_count'], len(data.get('errors', [])))
" "$LEDGERWATCH_JSON" 2>/dev/null || echo "")
            if [[ -n "$lw_counts" ]]; then
                read -r lw_count lw_fired lw_errors <<< "$lw_counts"
                LEDGERWATCH_ARG=(--ledger-watch "$LEDGERWATCH_JSON")
                audit stage_result stage=ledgerwatch result=ok \
                    watches="$lw_count" fired="$lw_fired" errors="$lw_errors"
            else
                add_reason LEDGERWATCH_FAIL
                audit stage_result stage=ledgerwatch result=fail reason=LEDGERWATCH_FAIL
                rm -f "$LEDGERWATCH_JSON"
            fi
        else
            add_reason LEDGERWATCH_FAIL
            audit stage_result stage=ledgerwatch result=fail reason=LEDGERWATCH_FAIL
            rm -f "$LEDGERWATCH_JSON"
        fi
    fi
else
    audit stage_result stage=ledgerwatch result=skipped
fi

# --- Stage 7: improvement check (P4-shaped, fires on 2-week recurrence) ---
# The orchestrator knows extra codes the builder will add for missing files.
# Gated on stage_enabled: a deliberately disabled stage is not a failure and
# must not feed the recurrence detector (2026-07-29 review).
if stage_enabled diagnosis && [[ ! -s "$FINDINGS_JSON" ]]; then
    add_reason DIAGNOSIS_UNAVAILABLE
fi
if stage_enabled insight && [[ ! -s "$INSIGHT_REVIEW" ]]; then
    add_reason INSIGHT_REVIEW_UNAVAILABLE
fi
if stage_enabled improve && [[ -n "$REASONS" ]] && ! deadline_exceeded; then
    fired=$(python3 "$SCRIPTS/build_decision_packet.py" check-improvement \
        --metrics "$METRICS" --current-codes "$REASONS" --end-date "$END_DATE" 2>/dev/null)
    if [[ "$fired" == *'"fired": true'* ]]; then
        echo "[$RUN_ID] stage 7: improvement proposal (recurrence: $fired)"
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

# --- Stage 8: decision packet (always attempted — the fail-forward target) ---
echo "[$RUN_ID] stage 8: decision packet"
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
        ${DEADCODE_ARG[@]+"${DEADCODE_ARG[@]}"} \
        ${VALUE_LAYER_ARG[@]+"${VALUE_LAYER_ARG[@]}"} \
        ${DOCSCAN_ARG[@]+"${DOCSCAN_ARG[@]}"} \
        ${LEDGERWATCH_ARG[@]+"${LEDGERWATCH_ARG[@]}"} \
        --run-log-dir "$RUN_LOG_DIR" \
        --out "$PACKET" > "$RUN_LOG_DIR/packet.log" 2>&1; then
    audit chain_end result=ok packet="$PACKET" reasons="${REASONS:-none}"
    echo "[$RUN_ID] packet: $PACKET"
    echo "[$RUN_ID] done (reasons: ${REASONS:-none})"
else
    audit chain_end result=fail reason=PACKET_FAIL
    echo "ERROR: packet build failed (see $RUN_LOG_DIR/packet.log)" >&2
    exit 1
fi

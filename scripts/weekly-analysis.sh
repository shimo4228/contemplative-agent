#!/bin/bash
# Weekly analysis report generator for Moltbook agent.
# Collects daily reports + agent state diffs, passes to claude -p.
#
# Usage:
#   ./scripts/weekly-analysis.sh                          # past 7 days ending yesterday
#   ./scripts/weekly-analysis.sh --end-date 2026-03-30    # past 7 days ending 2026-03-30
#   ./scripts/weekly-analysis.sh --end-date 2026-03-30 --days 10  # custom range
set -euo pipefail

# --- Config ---
MOLTBOOK_HOME="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
DATA_REPO="$HOME/MyAI_Lab/contemplative-agent-data"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROMPT_TEMPLATE="$PROJECT_ROOT/config/prompts/weekly-analysis.md"
PRINCIPLES_FILE="$PROJECT_ROOT/config/prompts/principles.md"
REPORT_DIR="$MOLTBOOK_HOME/reports/analysis"
COMMENT_REPORT_DIR="$MOLTBOOK_HOME/reports/comment-reports"

DAYS=7
END_DATE=""
PREV_REPORT_COUNT="${WEEKLY_PREV_COUNT:-3}"

# --- Parse args ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --end-date) END_DATE="$2"; shift 2 ;;
        --days)     DAYS="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--end-date YYYY-MM-DD] [--days N]"
            echo "  Default: past 7 days ending yesterday"
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# --- Date calculation ---
if [[ -z "$END_DATE" ]]; then
    END_DATE=$(date -v-1d +%Y-%m-%d)
fi
START_DATE=$(date -j -f %Y-%m-%d -v-"$((DAYS - 1))"d "$END_DATE" +%Y-%m-%d)

echo "Analysis period: $START_DATE to $END_DATE ($DAYS days)"

# --- Preflight: the whole script exists to feed `claude -p` ---
# launchd does not inherit the login shell's PATH, and Claude Code's native
# installer moved the binary to ~/.local/bin. Discovering that at the generate
# step (line ~250) burns the full collection pass first and — before the
# temp-file write below — left a 0-byte report behind. Fail here instead.
if ! command -v claude >/dev/null 2>&1; then
    echo "ERROR: 'claude' not found on PATH ($PATH)." >&2
    echo "       Under launchd, add its directory to the plist's EnvironmentVariables PATH" >&2
    echo "       (config/launchd/com.moltbook.weekly-analysis.plist), then reinstall the schedule." >&2
    exit 1
fi

# --- Collect daily reports ---
DAILY_REPORTS=""
FOUND=0
current="$START_DATE"
while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    report="$COMMENT_REPORT_DIR/comment-report-${current}.md"
    if [[ -f "$report" ]]; then
        DAILY_REPORTS+="$(cat "$report")"
        DAILY_REPORTS+=$'\n\n---\n\n'
        FOUND=$((FOUND + 1))
    fi
    current=$(date -j -f %Y-%m-%d -v+1d "$current" +%Y-%m-%d)
done

if [[ $FOUND -eq 0 ]]; then
    echo "ERROR: No daily reports found for $START_DATE to $END_DATE" >&2
    exit 1
fi
echo "Found $FOUND daily reports"

# --- Agent state diffs from git history ---
STATE_DIFF=""
if [[ -d "$DATA_REPO/.git" ]]; then
    cd "$DATA_REPO"

    # Find sync commits closest to start and end dates
    # For start: nearest commit on or before start date; fallback to first commit ever
    start_commit=$(git log --before="${START_DATE}T23:59:59" --format="%H" -1 2>/dev/null || true)
    if [[ -z "$start_commit" ]]; then
        start_commit=$(git rev-list --max-parents=0 HEAD 2>/dev/null | head -1 || true)
    fi

    end_commit=$(git log --before="${END_DATE}T23:59:59" --format="%H" -1 2>/dev/null || true)

    if [[ -n "$start_commit" ]] && [[ -n "$end_commit" ]] && [[ "$start_commit" != "$end_commit" ]]; then
        echo "State diff: $start_commit (start) -> $end_commit (end)"

        STATE_DIFF+="## Agent State Diff ($START_DATE -> $END_DATE)"$'\n\n'

        # Identity
        STATE_DIFF+="### identity.md"$'\n'
        id_diff=$(git diff "$start_commit" "$end_commit" -- identity.md 2>/dev/null || true)
        if [[ -n "$id_diff" ]]; then
            STATE_DIFF+='```diff'$'\n'"$id_diff"$'\n''```'$'\n\n'
        else
            STATE_DIFF+="No changes."$'\n\n'
        fi

        # Constitution
        STATE_DIFF+="### constitution/"$'\n'
        const_diff=$(git diff "$start_commit" "$end_commit" -- constitution/ 2>/dev/null || true)
        if [[ -n "$const_diff" ]]; then
            STATE_DIFF+='```diff'$'\n'"$const_diff"$'\n''```'$'\n\n'
        else
            STATE_DIFF+="No changes."$'\n\n'
        fi

        # Skills
        STATE_DIFF+="### skills/"$'\n'
        skills_start=$(git ls-tree --name-only "$start_commit" -- skills/ 2>/dev/null | sort || true)
        skills_end=$(git ls-tree --name-only "$end_commit" -- skills/ 2>/dev/null | sort || true)
        if [[ "$skills_start" != "$skills_end" ]]; then
            STATE_DIFF+="Start: $(echo "$skills_start" | tr '\n' ', ')"$'\n'
            STATE_DIFF+="End: $(echo "$skills_end" | tr '\n' ', ')"$'\n\n'
            skills_diff=$(git diff "$start_commit" "$end_commit" -- skills/ 2>/dev/null || true)
            if [[ -n "$skills_diff" ]]; then
                STATE_DIFF+='```diff'$'\n'"$skills_diff"$'\n''```'$'\n\n'
            fi
        else
            STATE_DIFF+="No changes. Files: $(echo "$skills_end" | tr '\n' ', ')"$'\n\n'
        fi

        # Rules
        STATE_DIFF+="### rules/"$'\n'
        rules_start=$(git ls-tree --name-only "$start_commit" -- rules/ 2>/dev/null | sort || true)
        rules_end=$(git ls-tree --name-only "$end_commit" -- rules/ 2>/dev/null | sort || true)
        if [[ "$rules_start" != "$rules_end" ]]; then
            STATE_DIFF+="Start: $(echo "$rules_start" | tr '\n' ', ')"$'\n'
            STATE_DIFF+="End: $(echo "$rules_end" | tr '\n' ', ')"$'\n\n'
            rules_diff=$(git diff "$start_commit" "$end_commit" -- rules/ 2>/dev/null || true)
            if [[ -n "$rules_diff" ]]; then
                STATE_DIFF+='```diff'$'\n'"$rules_diff"$'\n''```'$'\n\n'
            fi
        else
            STATE_DIFF+="No changes. Files: $(echo "$rules_end" | tr '\n' ', ')"$'\n\n'
        fi

        # Knowledge pattern count
        STATE_DIFF+="### knowledge.json"$'\n'
        count_start=$(git show "$start_commit":knowledge.json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "N/A")
        count_end=$(git show "$end_commit":knowledge.json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "N/A")
        STATE_DIFF+="Pattern count: $count_start (start) -> $count_end (end)"$'\n\n'
    else
        STATE_DIFF="No state diff available (insufficient git history)."
    fi
    cd "$PROJECT_ROOT"
else
    STATE_DIFF="No state data available (data repo not found)."
fi

# --- Previous N weeks' analyses (Principle 4 guard ground) ---
# Discover prior reports by glob rather than exact END_DATE - i*7d probes:
# actual report end-dates drift (07-11 vs a probed 07-10), so the exact-name
# probe silently found nothing and dropped the trend baseline. The date-shaped
# glob naturally excludes -findings.md / .ja.md / -findings.ja.md variants.
# ISO dates compare lexicographically, so [[ < ]] and sort -r are date-correct.
PREV_REPORTS=""
PREV_FOUND=0
PREV_DATES=$(
    for f in "$REPORT_DIR"/weekly-????-??-??.md; do
        [[ -e "$f" ]] || continue          # unmatched glob stays literal
        [[ -s "$f" ]] || continue          # 0-byte leftovers from a failed run
        d=$(basename "$f" .md)
        d=${d#weekly-}
        if [[ "$d" < "$END_DATE" ]]; then  # strictly before this run's end
            printf '%s\n' "$d"
        fi
    done | sort -r | head -n "$PREV_REPORT_COUNT"
)
for prev_end in $PREV_DATES; do
    prev_file="$REPORT_DIR/weekly-${prev_end}.md"
    [[ -f "$prev_file" ]] || continue      # belt-and-braces vs odd filenames
    PREV_REPORTS+="## Previous Report (ending $prev_end)"$'\n\n'
    PREV_REPORTS+="$(cat "$prev_file")"$'\n\n---\n\n'
    PREV_FOUND=$((PREV_FOUND + 1))
    echo "Including previous report: $prev_file"
done
if [[ $PREV_FOUND -eq 0 ]]; then
    PREV_REPORTS="No previous reports available for trend comparison."
fi

# --- Methodological principles ---
PRINCIPLES=""
if [[ -f "$PRINCIPLES_FILE" ]]; then
    PRINCIPLES="## Methodological Principles (override defaults)"$'\n\n'
    PRINCIPLES+="$(cat "$PRINCIPLES_FILE")"
    echo "Including principles: $PRINCIPLES_FILE"
else
    echo "WARNING: principles.md not found at $PRINCIPLES_FILE" >&2
fi

# --- Log anomaly sweep (cheap recurring bug-discovery, 2026-06-24) ---
# Deterministic intake of *.log / audit.jsonl signal, ranked by novelty since
# the last sweep, so latent operational bugs surface week over week without a
# full multi-agent audit. Read-only; NEVER reads episode logs (injection
# boundary). Observability only — a failure must not break the weekly report.
#
# The sweep's state is NOT committed here. Its whole value is the Δ / 🆕
# columns, both defined against the last committed snapshot, so a run that
# spends the baseline and then dies leaves the *next* run measuring novelty
# against a partial window — nobody ever observes that week's real novelty.
# That happened twice in a row (07-18 session limit, 07-25 missing PATH).
# Emit the snapshot aside and promote it after the report lands.
ANOMALY_SWEEP=""
SWEEP_STATE="$REPORT_DIR/.anomaly-sweep-state.tsv"
SWEEP_PENDING="$REPORT_DIR/.anomaly-sweep-state.pending.$$"
OUTPUT_TMP=""   # set at the generate step; named here so the trap can cover it
trap 'rm -f "$SWEEP_PENDING" ${OUTPUT_TMP:+"$OUTPUT_TMP"}' EXIT
if [[ -d "$MOLTBOOK_HOME/logs" ]]; then
    mkdir -p "$REPORT_DIR"
    ANOMALY_SWEEP=$(python3 "$PROJECT_ROOT/scripts/log_anomaly_sweep.py" \
        --log-dir "$MOLTBOOK_HOME/logs" --state "$SWEEP_STATE" --top 25 \
        --no-update --emit-state "$SWEEP_PENDING" 2>/dev/null || true)
    if [[ -n "$ANOMALY_SWEEP" ]]; then
        echo "Included log anomaly sweep"
    fi
fi
[[ -z "$ANOMALY_SWEEP" ]] && ANOMALY_SWEEP="## Log Anomaly Sweep"$'\n\n'"No log sweep available."

# --- State invariant check (structural drift detection, 2026-06-24) ---
# Deterministic "this should hold" checks over knowledge.json / agents.json
# (sunset fields, dedup leaks, tombstone build-up, missing embeddings). Reads
# distilled state only — never episode logs. Observability only — a FAIL exit
# must not break the weekly report.
INVARIANTS=""
INVARIANTS=$(python3 "$PROJECT_ROOT/scripts/state_invariant_check.py" \
    --home "$MOLTBOOK_HOME" 2>/dev/null || true)
if [[ -n "$INVARIANTS" ]]; then
    echo "Included state invariant check"
else
    INVARIANTS="## State Invariant Check"$'\n\n'"No invariant check available."
fi

# --- Cross-day duplicate scan (deterministic identity check, 2026-07-25) ---
# The report's C — Duplicate section asserts facts that span entries and days,
# which is the one place it has actually failed: twice it published a cross-entry
# claim that is not in the artifacts (2026-06-15, 2026-07-25). Byte-identity is a
# structural property, so it is measured here rather than recalled there.
#
# This is the only intake that reads the episode logs. The boundary is the
# output: digests, counts, filename-derived dates and a fixed action vocabulary
# — never body text, post ids or counterparty names (ADR-0083). Holds no state,
# so a failed run costs nothing. Observability only.
DUP_SCAN=""
if [[ -d "$MOLTBOOK_HOME/logs" ]]; then
    DUP_SCAN=$(python3 "$PROJECT_ROOT/scripts/cross_day_duplicate_scan.py" \
        --log-dir "$MOLTBOOK_HOME/logs" --start "$START_DATE" --end "$END_DATE" \
        --top 25 2>/dev/null || true)
    if [[ -n "$DUP_SCAN" ]]; then
        echo "Included cross-day duplicate scan"
    fi
fi
[[ -z "$DUP_SCAN" ]] && DUP_SCAN="## Cross-Day Duplicate Scan"$'\n\n'"No duplicate scan available."

# --- Build prompt ---
SYSTEM_PROMPT=$(cat "$PROMPT_TEMPLATE")

USER_PROMPT="Analyze the following Moltbook agent activity for $START_DATE to $END_DATE ($DAYS days).

$PRINCIPLES

$STATE_DIFF

$ANOMALY_SWEEP

$INVARIANTS

$DUP_SCAN

$PREV_REPORTS

## Daily Reports

$DAILY_REPORTS"

# --- Output path ---
mkdir -p "$REPORT_DIR"
OUTPUT="$REPORT_DIR/weekly-${END_DATE}.md"

# --- Run claude ---
# Write to a temp file and promote on success. A direct `> "$OUTPUT"` truncates
# the target before the command runs, so any failure (or a run killed mid-flight)
# leaves a 0-byte weekly-<date>.md that reads as a report: the diagnosis skill
# has no E section to work from, and next week's glob feeds it back as an empty
# "previous report". 2026-07-25: that is exactly what happened.
echo "Running claude -p (this may take a few minutes)..."
OUTPUT_TMP="${OUTPUT}.tmp.$$"

if ! echo "$USER_PROMPT" | claude -p \
    --system-prompt "$SYSTEM_PROMPT" \
    --output-format text \
    > "$OUTPUT_TMP"; then
    echo "ERROR: claude -p failed; leaving any previous $OUTPUT untouched" >&2
    exit 1
fi

if [[ ! -s "$OUTPUT_TMP" ]]; then
    echo "ERROR: claude -p exited 0 but produced no output; $OUTPUT left untouched" >&2
    exit 1
fi

mv "$OUTPUT_TMP" "$OUTPUT"

echo "Report generated: $OUTPUT"
echo "Size: $(wc -c < "$OUTPUT") bytes"

# --- Commit the sweep's novelty baseline (only now that a report exists) ---
# Deliberately ahead of the Japanese translation: the translation is
# best-effort and is not a condition for having observed this week's novelty.
# -e, not -s: a clean sweep legitimately emits an empty snapshot, and that is a
# real baseline — rejecting it would keep last week's counts, so a signature that
# stopped and came back would read as recurring with a delta against stale
# numbers. The file exists only if the sweep ran to completion (write_state is
# its last step), which is the condition being tested.
if [[ -e "$SWEEP_PENDING" ]]; then
    if mv "$SWEEP_PENDING" "$SWEEP_STATE"; then
        echo "Anomaly sweep state committed: $SWEEP_STATE"
    else
        echo "WARNING: sweep state promote failed; next run compares against a wider window" >&2
    fi
fi

# --- Japanese version (best-effort; must never break the canonical English report) ---
# English weekly-<date>.md stays canonical (it is what next weeks' prompts re-read);
# the .ja.md is a translation for the operator. Sonnet is deliberate: translation
# does not need the session's larger model. Failure is logged, never fatal.
# timeout guards the unattended launchd job against a hung CLI call; when the
# coreutils binary is absent from launchd's PATH the call degrades to no cap.
TRANSLATE_TIMEOUT_SECONDS=900
run_claude_translate() {
    if command -v timeout >/dev/null 2>&1; then
        timeout "$TRANSLATE_TIMEOUT_SECONDS" claude -p "$@"
    else
        claude -p "$@"
    fi
}

TRANSLATE_PROMPT="$PROJECT_ROOT/config/prompts/weekly-analysis-ja.md"
OUTPUT_JA="$REPORT_DIR/weekly-${END_DATE}.ja.md"
if [[ -f "$TRANSLATE_PROMPT" ]]; then
    TRANSLATE_SYSTEM_PROMPT=$(cat "$TRANSLATE_PROMPT")
    echo "Translating report to Japanese (model: sonnet)..."
    if run_claude_translate \
        --model sonnet \
        --system-prompt "$TRANSLATE_SYSTEM_PROMPT" \
        --output-format text \
        < "$OUTPUT" > "$OUTPUT_JA" && [[ -s "$OUTPUT_JA" ]]; then
        en_bytes=$(wc -c < "$OUTPUT")
        ja_bytes=$(wc -c < "$OUTPUT_JA")
        # CLI exit 0 + non-empty file can still hide a mid-document cutoff;
        # a Japanese translation far smaller than the English source is the signal
        if (( ja_bytes * 10 < en_bytes * 3 )); then
            echo "WARNING: Japanese report is <30% of English size (${ja_bytes}/${en_bytes} bytes) — possible truncation" >&2
        fi
        echo "Japanese report generated: $OUTPUT_JA (${ja_bytes} bytes)"
    else
        rm -f "$OUTPUT_JA"
        echo "WARNING: Japanese translation failed — English report unaffected" >&2
    fi
else
    echo "WARNING: translation prompt not found at $TRANSLATE_PROMPT; skipping Japanese version" >&2
fi

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
REPORT_DIR="$MOLTBOOK_HOME/reports/analysis"
COMMENT_REPORT_DIR="$MOLTBOOK_HOME/reports/comment-reports"

DAYS=7
END_DATE=""

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

# --- Previous week's analysis ---
PREV_REPORT=""
prev_end=$(date -j -f %Y-%m-%d -v-1d "$START_DATE" +%Y-%m-%d)
prev_file="$REPORT_DIR/weekly-${prev_end}.md"
if [[ -f "$prev_file" ]]; then
    PREV_REPORT="## Previous Week's Analysis (ending $prev_end)"$'\n\n'
    PREV_REPORT+="$(cat "$prev_file")"
    echo "Including previous report: $prev_file"
fi

# --- Build prompt ---
SYSTEM_PROMPT=$(cat "$PROMPT_TEMPLATE")

USER_PROMPT="Analyze the following Moltbook agent activity for $START_DATE to $END_DATE ($DAYS days).

$STATE_DIFF

$PREV_REPORT

## Daily Reports

$DAILY_REPORTS"

# --- Output path ---
mkdir -p "$REPORT_DIR"
OUTPUT="$REPORT_DIR/weekly-${END_DATE}.md"

# --- Run claude ---
echo "Running claude -p (this may take a few minutes)..."
echo "$USER_PROMPT" | claude -p \
    --system-prompt "$SYSTEM_PROMPT" \
    --output-format text \
    > "$OUTPUT"

echo "Report generated: $OUTPUT"
echo "Size: $(wc -c < "$OUTPUT") bytes"

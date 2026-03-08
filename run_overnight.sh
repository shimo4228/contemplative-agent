#!/usr/bin/env bash
# Run contemplative-agent overnight in guarded mode.
# Usage: ./run_overnight.sh [STOP_HOUR]
#   STOP_HOUR: hour (0-23) to stop. Default: 7 (7:00 AM)
#
# Runs 30-minute sessions with 5-minute breaks.
# Stops when daily comment limit (50) is hit or STOP_HOUR reached.
# Logs to logs/overnight-YYYY-MM-DD.log

set -euo pipefail
cd "$(dirname "$0")"

STOP_HOUR="${1:-7}"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/overnight-$(date +%Y-%m-%d).log"

source .venv/bin/activate

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

session_count=0

log "=== Overnight session started. Stop at ${STOP_HOUR}:00 ==="

START_HOUR=$(date +%H | sed 's/^0//')

should_stop() {
    local current_hour
    current_hour=$(date +%H | sed 's/^0//')
    if [ "$START_HOUR" -gt "$STOP_HOUR" ]; then
        # Overnight: started at e.g. 23, stop at 7
        # Stop when hour is >= STOP_HOUR AND < START_HOUR (i.e. morning)
        [ "$current_hour" -ge "$STOP_HOUR" ] && [ "$current_hour" -lt "$START_HOUR" ]
    else
        # Same day: started at e.g. 10, stop at 18
        [ "$current_hour" -ge "$STOP_HOUR" ]
    fi
}

while true; do
    if should_stop; then
        log "Reached stop hour ($STOP_HOUR:00). Shutting down."
        break
    fi

    session_count=$((session_count + 1))
    log "--- Session #${session_count} starting ---"

    # Run 30-minute session, capture output
    if contemplative-moltbook --guarded run --session 30 >> "$LOG_FILE" 2>&1; then
        log "Session #${session_count} completed normally."
    else
        log "Session #${session_count} exited with error (code $?)."
    fi

    # Check if daily comment limit is exhausted
    remaining=$(python3 -c "
from contemplative_moltbook.scheduler import Scheduler
s = Scheduler()
print(s.comments_remaining_today)
" 2>/dev/null || echo "unknown")

    log "Comments remaining today: ${remaining}"

    if [ "$remaining" = "0" ]; then
        log "Daily comment limit reached. Sleeping 1 hour..."
        sleep 3600
        continue
    fi

    # Check if last session hit rate limit (429)
    if grep -q "Rate limited by server" "$LOG_FILE" 2>/dev/null; then
        log "Server rate limit hit. Sleeping 60 minutes before retry..."
        sleep 3600
        continue
    fi

    # Break between sessions: 5 minutes
    log "Next session in 5 minutes..."
    sleep 300
done

log "=== Overnight session ended. Total sessions: ${session_count} ==="

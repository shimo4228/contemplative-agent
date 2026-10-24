#!/usr/bin/env bash
# block-episode-logs-bash.sh -- PreToolUse hook for the Bash tool.
# Heuristic, and stated as one: it blocks a command that both NAMES the blocked
# set (logs/episodes, agent-launchd.log) and uses a content-reading verb or
# redirection. Metadata (`ls`, `wc -l`, `stat`) passes. A shell can always
# assemble a path this pattern cannot see; the structural guarantee for
# unattended sessions is the Read deny list, not this hook.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_episode-log-common.sh
# shellcheck disable=SC1091  # the common file is linted on its own
source "$HERE/_episode-log-common.sh"

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[[ -z "$COMMAND" ]] && exit 0

READERS='(^|[;&|(`[:space:]])(cat|head|tail|less|more|grep|egrep|fgrep|rg|ag|awk|sed|python3?|ruby|perl|node|jq|xxd|od|strings|base64|sort|uniq|cut|tr|nl|bat|tee|cp|mv|diff|source)[[:space:]]|<[[:space:]]*[^<[:space:]]'

# Names the blocked set directly.
if printf '%s' "$COMMAND" | grep -qE 'logs/episodes|agent-launchd\.log'; then
  if printf '%s' "$COMMAND" | grep -qE "$READERS"; then
    emit_block
  fi
  exit 0
fi

# Wildcard segment directly under logs/ (`logs/*/x.jsonl`, `logs/epi*/x`):
# any reader can expand it into logs/episodes, so a reader alone suffices.
if printf '%s' "$COMMAND" | grep -qE '/logs/[^/[:space:]]*[*?[][^/[:space:]]*/'; then
  if printf '%s' "$COMMAND" | grep -qE "$READERS"; then
    emit_block
    exit 0
  fi
fi

# Recursive reach: a reader aimed at the logs directory with a recursive or
# wildcard-over-directories form descends into logs/episodes.
if printf '%s' "$COMMAND" | grep -qE '(\.config/moltbook|MOLTBOOK_HOME\}?)/logs(/?\*\*|/\*/|[[:space:]]|/?$|/?["'"'"'])'; then
  if printf '%s' "$COMMAND" | grep -qE "$READERS" \
     && printf '%s' "$COMMAND" | grep -qE '(grep|rg|ag|find|sed|awk)[^|;&]*(-[a-zA-Z]*[rR]|--recursive|\*\*|/\*/|-exec)'; then
    emit_block
  fi
fi
exit 0

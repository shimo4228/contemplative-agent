#!/usr/bin/env bash
# block-episode-logs-grep.sh -- PreToolUse hook for the Grep tool.
# Blocks content searches that read the episode-log folder or agent-launchd.log*,
# including a recursive search rooted at logs/ or MOLTBOOK_HOME, which would
# descend into them (see _episode-log-common.sh).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_episode-log-common.sh
# shellcheck disable=SC1091  # the common file is linted on its own
source "$HERE/_episode-log-common.sh"

INPUT=$(cat)
SEARCH_PATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty')
GLOB_PATTERN=$(echo "$INPUT" | jq -r '.tool_input.glob // empty')

if [[ -n "$SEARCH_PATH" ]]; then
  if episode_path_blocked "$SEARCH_PATH" || logs_dir_reaches_blocked "$SEARCH_PATH"; then
    emit_block
    exit 0
  fi
fi

# A glob that names the folder or the log, whatever the root.
case "$GLOB_PATTERN" in
  *logs/episodes*|*agent-launchd.log*)
    emit_block
    exit 0
    ;;
esac

# A recursive jsonl glob with no path (cwd-rooted) or rooted at the logs tree
# would reach logs/episodes/*.jsonl.
case "$GLOB_PATTERN" in
  '**/*.jsonl'|'**/*.jsonl*'|'**/*.bak'|'**/*'|'**')
    if [[ -z "$SEARCH_PATH" ]]; then
      emit_block
      exit 0
    fi
    ;;
esac
exit 0

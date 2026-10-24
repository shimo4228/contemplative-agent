#!/usr/bin/env bash
# block-episode-logs-read.sh -- PreToolUse hook for the Read tool.
# Blocks direct reads of the episode-log folder and agent-launchd.log* (see
# _episode-log-common.sh for the boundary; logs/ top-level telemetry is allowed).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_episode-log-common.sh
source "$HERE/_episode-log-common.sh"

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" ]] && exit 0

if episode_path_blocked "$FILE_PATH"; then
  emit_block
fi
exit 0

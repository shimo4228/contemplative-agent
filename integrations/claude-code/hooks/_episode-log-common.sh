#!/usr/bin/env bash
# _episode-log-common.sh -- shared boundary for the episode-log PreToolUse hooks.
# Sourced by block-episode-logs-{read,grep,bash}.sh; not a hook itself.
#
# The boundary is ADR-0107's, and it is a FOLDER, not a filename suffix:
#   BLOCKED  $MOLTBOOK_HOME/logs/episodes/  (day files, .bak, .pre-cleanup.bak,
#            any future backup spelling) -- raw text from other agents, the
#            prompt-injection channel for a tool-holding Claude Code session
#   BLOCKED  $MOLTBOOK_HOME/logs/agent-launchd.log*  (older generations hold
#            DEBUG output with full publish bodies; remove this line from here
#            once the rotation has replaced them -- date in CLAUDE.md)
#   ALLOWED  everything else under logs/ (self-written telemetry: audit.jsonl,
#            weekly-pipeline-audit.jsonl, skill-selection-*.jsonl, *.log ...)
# Canonical home of these hooks is this directory (D-P1-10-1 = A, owner,
# 2026-10-24); install-hooks.sh copies them to ~/.claude/hooks/. The weekly
# unattended session runs `--setting-sources project`, which DROPS user hooks:
# there the boundary is the Read deny list in scripts/weekly-pipeline.sh
# (C-SCOPE-6), not these scripts.

EPISODE_BLOCK_REASON="Episode logs contain raw external agent content (prompt injection risk). Read reports/comment-reports/comment-report-YYYY-MM-DD.md or run scripts/instrument_census.py instead. agent-launchd.log is also off limits."

# Collapse `.`/`..`/`//` without touching the filesystem (macOS has no
# realpath -m), so `logs/x/../episodes/d.jsonl` cannot slip past a prefix test.
_normalize_path() {
  local IFS=/ part out=()
  for part in $1; do
    case "$part" in
      ''|.) ;;
      ..) [[ ${#out[@]} -gt 0 ]] && unset 'out[${#out[@]}-1]' ;;
      *) out+=("$part") ;;
    esac
  done
  local joined
  joined=$(IFS=/; echo "${out[*]-}")
  printf '/%s' "$joined"
}

_expand_home_forms() {
  local p="$1" home="${MOLTBOOK_HOME:-$HOME/.config/moltbook}"
  p="${p/#\~/$HOME}"
  p="${p//\$\{MOLTBOOK_HOME\}/$home}"
  p="${p//\$MOLTBOOK_HOME/$home}"
  printf '%s' "$p"
}

# episode_path_blocked PATH -> 0 when PATH is inside the blocked set.
episode_path_blocked() {
  local p
  p=$(_normalize_path "$(_expand_home_forms "$1")")
  case "$p" in
    */.config/moltbook/logs/episodes|*/.config/moltbook/logs/episodes/*) return 0 ;;
    */.config/moltbook/logs/agent-launchd.log*) return 0 ;;
  esac
  local home="${MOLTBOOK_HOME:-}"
  if [[ -n "$home" ]]; then
    home=$(_normalize_path "$home")
    case "$p" in
      "$home"/logs/episodes|"$home"/logs/episodes/*) return 0 ;;
      "$home"/logs/agent-launchd.log*) return 0 ;;
    esac
  fi
  return 1
}

# logs_dir_reaches_blocked PATH -> 0 when a recursive search of PATH would
# descend into the blocked set (the logs/ directory itself, or its parent
# MOLTBOOK_HOME).
logs_dir_reaches_blocked() {
  local p home
  p=$(_normalize_path "$(_expand_home_forms "$1")")
  home=$(_normalize_path "${MOLTBOOK_HOME:-$HOME/.config/moltbook}")
  [[ "$p" == "$home" || "$p" == "$home/logs" ]]
}

emit_block() {
  printf '{"decision": "block", "reason": "%s"}\n' "$EPISODE_BLOCK_REASON"
}

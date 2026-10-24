#!/bin/bash
# Install Claude Code safety hooks for Contemplative Agent
#
# Blocks coding agents from reading raw episode logs (prompt injection surface).
# Boundary: ADR-0107 (the logs/episodes/ folder + agent-launchd.log*); threat model:
# docs/security/threat-model.md. This directory is the canonical home of the hooks
# (D-P1-10-1 = A); re-run this script after pulling to refresh the copies.
#
# Usage: bash integrations/claude-code/install-hooks.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_SRC="$SCRIPT_DIR/hooks"
HOOKS_DST="$HOME/.claude/hooks"

mkdir -p "$HOOKS_DST"

echo "Installing episode log protection hooks..."
echo ""

count=0
for hook in "$HOOKS_SRC"/_episode-log-common.sh "$HOOKS_SRC"/block-episode-logs-*.sh; do
    [ -f "$hook" ] || continue
    name=$(basename "$hook")
    cp "$hook" "$HOOKS_DST/$name"
    chmod +x "$HOOKS_DST/$name"
    echo "  Installed: $HOOKS_DST/$name"
    count=$((count + 1))
done

echo ""
echo "$count hooks installed to $HOOKS_DST/"
echo ""
echo "Next step: add these entries to ~/.claude/settings.json"
echo "under \"hooks\" > \"PreToolUse\":"
echo ""
cat <<'SNIPPET'
{
  "matcher": "Read",
  "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-read.sh" }]
},
{
  "matcher": "Bash",
  "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-bash.sh" }]
},
{
  "matcher": "Grep",
  "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-grep.sh" }]
}
SNIPPET
echo ""
echo "The unattended weekly session runs with --setting-sources project, which"
echo "drops user hooks: there the boundary is the Read deny list in"
echo "scripts/weekly-pipeline.sh (C-SCOPE-6), not these hooks."
echo ""
echo "If an older copy of these hooks lives in ~/.claude/hooks under other names,"
echo "remove it: two sets side by side drift apart (this directory is canonical)."
echo ""
echo "If you already have a Bash PreToolUse hook, merge the episode"
echo "log check into your existing script instead of adding a new entry."

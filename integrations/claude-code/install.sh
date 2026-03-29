#!/bin/bash
# Install -ca skills for Claude Code
# Usage: bash integrations/claude-code/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/../skills"
TARGET_DIR=".claude/skills"

mkdir -p "$TARGET_DIR"

count=0
for skill in "$SKILLS_DIR"/*-ca.md; do
    cp "$skill" "$TARGET_DIR/"
    echo "  Installed: $(basename "$skill")"
    count=$((count + 1))
done

echo ""
echo "$count skills installed to $TARGET_DIR/"
echo "Available commands: /insight-ca, /skill-stocktake-ca, /rules-distill-ca, /amend-constitution-ca, /distill-identity-ca"

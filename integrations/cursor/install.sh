#!/bin/bash
# Install -ca skills as Cursor rules
# Usage: bash integrations/cursor/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/../skills"
TARGET_DIR=".cursor/rules"

mkdir -p "$TARGET_DIR"

count=0
for skill in "$SKILLS_DIR"/*-ca.md; do
    basename="$(basename "$skill" .md)"
    target="$TARGET_DIR/$basename.mdc"

    # Extract description from YAML frontmatter
    description=$(sed -n 's/^description: *"\(.*\)"/\1/p' "$skill" | head -1)

    # Write .mdc file with Cursor metadata header + skill content (skip YAML frontmatter)
    {
        echo "---"
        echo "description: \"$description\""
        echo "globs: []"
        echo "alwaysApply: false"
        echo "---"
        echo ""
        # Skip original YAML frontmatter, keep the rest
        sed '1,/^---$/{ /^---$/!d; }' "$skill" | sed '1d'
    } > "$target"

    echo "  Installed: $basename.mdc"
    count=$((count + 1))
done

echo ""
echo "$count rules installed to $TARGET_DIR/"
echo "Mention the skill name in conversation or use @rules to activate."

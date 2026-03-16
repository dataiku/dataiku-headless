#!/usr/bin/env bash
# Install the dku-cli skill for Claude Code into the current project.
# Usage: curl -fsSL https://raw.githubusercontent.com/dataiku/dataiku-cli/main/install-skill.sh | bash
set -euo pipefail

REPO="https://raw.githubusercontent.com/dataiku/dataiku-cli/main"
DEST=".claude/skills/dku-cli"

mkdir -p "$DEST/references"

curl -fsSL "$REPO/.claude/skills/dku-cli/SKILL.md" -o "$DEST/SKILL.md"
curl -fsSL "$REPO/.claude/skills/dku-cli/references/commands.md" -o "$DEST/references/commands.md"

echo "◆ Installed dku-cli skill to $DEST/"
echo "  Claude Code will auto-discover it in this project."

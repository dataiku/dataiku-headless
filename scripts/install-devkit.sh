#!/usr/bin/env bash
# Install Dataiku DevKit (skills + agents) into Claude Code's global directories.
# Creates symlinks so that `git pull` in this repo automatically updates everything.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEVKIT_DIR="$REPO_DIR/dataiku-devkit"

SKILLS_DIR="$HOME/.claude/skills"
AGENTS_DIR="$HOME/.claude/agents"

mkdir -p "$SKILLS_DIR" "$AGENTS_DIR"

echo "Installing Dataiku DevKit from $DEVKIT_DIR"
echo ""

# Skills — symlink each skill directory
for skill in "$DEVKIT_DIR"/skills/*/; do
    name="$(basename "$skill")"
    target="$SKILLS_DIR/$name"
    if [ -L "$target" ] || [ -e "$target" ]; then
        rm -rf "$target"
    fi
    ln -s "$skill" "$target"
    echo "  Skill: $name -> $skill"
done

# Agents — symlink each agent file
for agent in "$DEVKIT_DIR"/agents/*.md; do
    name="$(basename "$agent")"
    target="$AGENTS_DIR/$name"
    if [ -L "$target" ] || [ -e "$target" ]; then
        rm -f "$target"
    fi
    ln -s "$agent" "$target"
    echo "  Agent: $name -> $agent"
done

echo ""
echo "Done. Skills and agents will auto-update when you pull this repo."
echo "To also install the CLI: uv tool install --from $REPO_DIR dku-cli"

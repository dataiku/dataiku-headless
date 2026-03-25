#!/usr/bin/env bash
# Install the Dataiku DevKit skills for AI coding agents.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dataiku/dataiku-cli/main/install-plugin.sh | bash
#   curl -fsSL ... | bash -s -- --project       # Install to current project [default]
#   curl -fsSL ... | bash -s -- --global        # Install to user-level (~/.claude/skills/)
#   curl -fsSL ... | bash -s -- --agent claude  # Force agent type (claude/codex/cursor)
#
# Supports: Claude Code, OpenAI Codex, Cursor, and any agent that reads SKILL.md files.
set -euo pipefail

REPO="https://raw.githubusercontent.com/dataiku/dataiku-cli/main"
SCOPE="project"
AGENT=""

while [ $# -gt 0 ]; do
    case "$1" in
        --project) SCOPE="project"; shift ;;
        --global)  SCOPE="global"; shift ;;
        --agent)   [ -z "${2:-}" ] && echo "Error: --agent requires a value (claude/codex/cursor)" >&2 && exit 1; AGENT="$2"; shift 2 ;;
        *)  echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Determine skills directory based on agent and scope
detect_base() {
    local agent="${AGENT}"
    if [ -z "$agent" ]; then
        if [ -d ".claude" ] || [ -d "$HOME/.claude" ]; then agent="claude"
        elif command -v codex &>/dev/null; then agent="codex"
        elif [ -d ".cursor" ] || [ -d "$HOME/.cursor" ]; then agent="cursor"
        else agent="claude"; fi
    fi

    case "$agent" in
        claude) [ "$SCOPE" = "global" ] && echo "$HOME/.claude" || echo ".claude" ;;
        codex)  [ "$SCOPE" = "global" ] && echo "$HOME/.agents" || echo ".agents" ;;
        cursor) [ "$SCOPE" = "global" ] && echo "$HOME/.cursor" || echo ".cursor" ;;
        *)      echo ".claude" ;;
    esac
}

AGENT_DIR=$(detect_base)
SKILLS_DIR="$AGENT_DIR/skills"

echo "Installing Dataiku DevKit to $AGENT_DIR/"
echo ""

# Remove old single-skill install if present
if [ -f "$SKILLS_DIR/dku-cli/SKILL.md" ] && [ ! -f "$SKILLS_DIR/dataiku/SKILL.md" ]; then
    echo "  Upgrading from old dku-cli skill..."
    rm -rf "$SKILLS_DIR/dku-cli"
fi

FAILED=0

# All skills to install
SKILLS="dataiku dku-cli new-plugin new-tool new-recipe new-webapp new-guardrail deploy-plugin review-plugin"

for skill in $SKILLS; do
    mkdir -p "$SKILLS_DIR/$skill"
    echo "  skills/$skill/SKILL.md"
    if ! curl -fsSL "$REPO/skills/$skill/SKILL.md" -o "$SKILLS_DIR/$skill/SKILL.md"; then
        echo "    WARNING: failed to download $skill/SKILL.md" >&2
        FAILED=$((FAILED + 1))
    fi
done

# Download dku-cli command reference
mkdir -p "$SKILLS_DIR/dku-cli/references"
echo "  skills/dku-cli/references/commands.md"
if ! curl -fsSL "$REPO/skills/dku-cli/references/commands.md" -o "$SKILLS_DIR/dku-cli/references/commands.md"; then
    FAILED=$((FAILED + 1))
fi

# Download dataiku reference docs
mkdir -p "$SKILLS_DIR/dataiku/references"
REFS="plugin-structure recipes llm-tools webapps webapp-pitfalls parameters code-environments datasets macros testing best-practices plugin-workflow formulas llm-mesh structured-agents python-api scenarios mlops genai-features dataiku-reference styling plugin-review-checklist agent-tool-patterns webapp-patterns plugin-architecture visual-agent-blocks"

for ref in $REFS; do
    echo "  skills/dataiku/references/$ref.md"
    if ! curl -fsSL "$REPO/skills/dataiku/references/$ref.md" -o "$SKILLS_DIR/dataiku/references/$ref.md"; then
        echo "    WARNING: failed to download $ref.md" >&2
        FAILED=$((FAILED + 1))
    fi
done

# Download agents (Claude Code only — other agents don't support custom agents yet)
RESOLVED_AGENT="${AGENT}"
if [ -z "$RESOLVED_AGENT" ]; then
    if [ -d ".claude" ] || [ -d "$HOME/.claude" ]; then RESOLVED_AGENT="claude"
    elif command -v codex &>/dev/null; then RESOLVED_AGENT="codex"
    elif [ -d ".cursor" ] || [ -d "$HOME/.cursor" ]; then RESOLVED_AGENT="cursor"
    else RESOLVED_AGENT="claude"; fi
fi

if [ "$RESOLVED_AGENT" = "claude" ]; then
    AGENTS_DIR="$AGENT_DIR/agents"
    mkdir -p "$AGENTS_DIR"
    for agent in plugin-reviewer dss-explorer tool-designer; do
        echo "  agents/$agent.md"
        if ! curl -fsSL "$REPO/agents/$agent.md" -o "$AGENTS_DIR/$agent.md"; then
            echo "    WARNING: failed to download $agent.md" >&2
            FAILED=$((FAILED + 1))
        fi
    done
fi

echo ""
if [ "$FAILED" -gt 0 ]; then
    echo "Installed with $FAILED failed downloads. Re-run or use:"
    echo "  npx skills add dataiku/dataiku-cli --all"
else
    echo "Installed Dataiku DevKit (9 skills, 27 reference docs, 3 agents)."
fi
echo "Your AI agent will auto-discover them."

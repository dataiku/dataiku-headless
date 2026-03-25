#!/usr/bin/env bash
# Install the Dataiku DevKit skills for AI coding agents.
#
# Usage:
#   bash <(gh api repos/dataiku/dataiku-cli/contents/install-plugin.sh --jq '.content' | base64 -d)
#   ... --project       # Install to current project [default]
#   ... --global        # Install to user-level (~/.claude/skills/)
#   ... --agent claude  # Force agent type (claude/codex/cursor)
#
# For public repos:
#   curl -fsSL https://raw.githubusercontent.com/dataiku/dataiku-cli/main/install-plugin.sh | bash
#
# Supports: Claude Code, OpenAI Codex, Cursor, and any agent that reads SKILL.md files.
set -euo pipefail

REPO_OWNER="dataiku"
REPO_NAME="dataiku-cli"
REPO_RAW="https://raw.githubusercontent.com/$REPO_OWNER/$REPO_NAME/main"
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

# Download helper: tries gh api (authenticated, works for private repos), falls back to curl
download_file() {
    local remote_path="$1"
    local dest="$2"
    # Try gh api first (handles private repos)
    if command -v gh &>/dev/null; then
        if gh api "repos/$REPO_OWNER/$REPO_NAME/contents/$remote_path" --jq '.content' 2>/dev/null | base64 -d > "$dest" 2>/dev/null; then
            [ -s "$dest" ] && return 0
        fi
    fi
    # Fall back to curl (public repos only)
    if curl -fsSL "$REPO_RAW/$remote_path" -o "$dest" 2>/dev/null; then
        return 0
    fi
    return 1
}

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
SKILLS="dataiku dku-cli"

for skill in $SKILLS; do
    mkdir -p "$SKILLS_DIR/$skill"
    echo "  skills/$skill/SKILL.md"
    if ! download_file "skills/$skill/SKILL.md" "$SKILLS_DIR/$skill/SKILL.md"; then
        echo "    WARNING: failed to download $skill/SKILL.md" >&2
        FAILED=$((FAILED + 1))
    fi
done

# Download dku-cli command reference
mkdir -p "$SKILLS_DIR/dku-cli/references"
echo "  skills/dku-cli/references/commands.md"
if ! download_file "skills/dku-cli/references/commands.md" "$SKILLS_DIR/dku-cli/references/commands.md"; then
    FAILED=$((FAILED + 1))
fi

# Download dataiku reference docs
mkdir -p "$SKILLS_DIR/dataiku/references"
REFS="plugin-structure recipes llm-tools webapps webapp-pitfalls parameters code-environments datasets macros testing best-practices plugin-workflow formulas llm-mesh structured-agents python-api scenarios mlops genai-features dataiku-reference styling plugin-review-checklist agent-tool-patterns webapp-patterns plugin-architecture visual-agent-blocks scaffolding"

for ref in $REFS; do
    echo "  skills/dataiku/references/$ref.md"
    if ! download_file "skills/dataiku/references/$ref.md" "$SKILLS_DIR/dataiku/references/$ref.md"; then
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
        if ! download_file "agents/$agent.md" "$AGENTS_DIR/$agent.md"; then
            echo "    WARNING: failed to download $agent.md" >&2
            FAILED=$((FAILED + 1))
        fi
    done
fi

echo ""
if [ "$FAILED" -gt 0 ]; then
    echo "Installed with $FAILED failed downloads."
    if ! command -v gh &>/dev/null; then
        echo "Tip: install gh CLI (https://cli.github.com) for private repo access."
    fi
else
    echo "Installed Dataiku DevKit (2 skills, 28 reference docs, 3 agents)."
fi
echo "Your AI agent will auto-discover them."

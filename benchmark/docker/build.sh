#!/usr/bin/env bash
# Build bench-agents:latest. Stages a minimal context: dku-cli source (for the
# `dku` install only — removed from the final image) and the dataiku_mcp package.
#
# Usage: build.sh [--pull] [--no-cache]
#   --pull      git pull both repos (dku-cli + agent-dev-kit) before building,
#               so the baked dku CLI and MCP server are at the latest origin HEAD.
#   --no-cache  pass --no-cache to docker build (forces a fresh npm install of
#               the claude/codex CLIs, which are otherwise layer-cached).
set -euo pipefail

PULL=0
DOCKER_BUILD_FLAGS=()
for arg in "$@"; do
    case "$arg" in
        --pull) PULL=1 ;;
        --no-cache) DOCKER_BUILD_FLAGS+=(--no-cache) ;;
        *) echo "unknown flag: $arg (usage: build.sh [--pull] [--no-cache])" >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

AGENT_DEV_KIT_SRC="${AGENT_DEV_KIT_SRC:-$(cd "$REPO_ROOT/../dataiku-agent-dev-kit" 2>/dev/null && pwd || true)}"
[[ -d "$AGENT_DEV_KIT_SRC" ]] || {
    echo "agent-dev-kit not found. Set AGENT_DEV_KIT_SRC to its checkout path." >&2
    exit 1
}

if [[ "$PULL" == 1 ]]; then
    for repo in "$REPO_ROOT" "$AGENT_DEV_KIT_SRC"; do
        echo "Pulling latest in $repo"
        git -C "$repo" pull --ff-only || {
            echo "git pull failed in $repo (uncommitted changes or non-ff?). Resolve and retry." >&2
            exit 1
        }
    done
fi

STAGE="$(mktemp -d -t bench-agents-build.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

echo "Staging build context at $STAGE"
rsync -a --delete \
    --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
    --exclude 'node_modules' --exclude 'dist' --exclude 'build' --exclude '*.egg-info' \
    --exclude 'benchmark/reports' --exclude 'benchmark/.bench_*' \
    "$REPO_ROOT/" "$STAGE/dku-cli/"

mkdir -p "$STAGE/agent-dev-kit"
rsync -a --delete --exclude '__pycache__' \
    "$AGENT_DEV_KIT_SRC/dataiku_mcp/" "$STAGE/agent-dev-kit/dataiku_mcp/"

# Minimal pyproject so `uv run python -m dataiku_mcp` resolves deps in-container.
# fastmcp is pinned: the MCP sidecar relies on FastMCP honoring FASTMCP_HOST /
# FASTMCP_PORT to bind 0.0.0.0 (verified on 3.3.x). Pinning to the 3.x line keeps
# that binding behavior from silently drifting on a rebuild (a 4.x bump could
# change it). Patch/minor updates within 3.x stay allowed.
cat > "$STAGE/agent-dev-kit/pyproject.toml" <<'TOML'
[project]
name = "dataiku-mcp-bench"
version = "0.0.0"
requires-python = ">=3.10"
dependencies = ["fastmcp>=3.3,<4", "dataiku-api-client", "python-dotenv"]

[tool.uv]
package = false
TOML

cp "$SCRIPT_DIR/Dockerfile" "$STAGE/Dockerfile"
cp "$SCRIPT_DIR/Dockerfile.mcp" "$STAGE/Dockerfile.mcp"
cp "$SCRIPT_DIR/entrypoint.sh" "$STAGE/benchmark-entrypoint.sh"
chmod +x "$STAGE/benchmark-entrypoint.sh"

# Provenance baked into the image so runs are reproducible/attributable.
dku_sha="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
adk_sha="$(git -C "$AGENT_DEV_KIT_SRC" rev-parse --short HEAD 2>/dev/null || echo unknown)"
built_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$STAGE/build-info.json" <<JSON
{"dku_cli_sha": "$dku_sha", "agent_dev_kit_sha": "$adk_sha", "built_at": "$built_at"}
JSON

TAG="${BENCH_IMAGE_TAG:-bench-agents:latest}"
echo "Building $TAG (dku=$dku_sha adk=$adk_sha)"
docker build ${DOCKER_BUILD_FLAGS[@]+"${DOCKER_BUILD_FLAGS[@]}"} -t "$TAG" "$STAGE"
echo "Built $TAG"

# MCP sidecar image: the dataiku MCP server over HTTP. Built from the same
# staged context (-f Dockerfile.mcp). This is the only image that carries the
# MCP source; the agent image connects to it over the network with a URL only.
MCP_TAG="${BENCH_MCP_IMAGE_TAG:-bench-mcp:latest}"
echo "Building $MCP_TAG (adk=$adk_sha)"
docker build ${DOCKER_BUILD_FLAGS[@]+"${DOCKER_BUILD_FLAGS[@]}"} -f "$STAGE/Dockerfile.mcp" -t "$MCP_TAG" "$STAGE"
echo "Built $MCP_TAG"

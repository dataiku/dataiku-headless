#!/usr/bin/env bash
set -euo pipefail

# TODO(dist): once dataiku-headless is published to PyPI, switch the plugin
# manifests (.claude-plugin, .codex-plugin, .cursor-plugin) to
# `uvx dataiku-headless serve` and retire this local-clone launcher.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found on PATH." >&2
  echo "Install it from https://docs.astral.sh/uv/ (e.g. curl -LsSf https://astral.sh/uv/install.sh | sh)" >&2
  exit 1
fi

# Runtime launchers do not need the project's development dependencies.
cd "${REPO_ROOT}"
exec uv run --no-dev python -m dataiku_mcp

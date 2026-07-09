#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found on PATH." >&2
  echo "Install it from https://docs.astral.sh/uv/ (e.g. curl -LsSf https://astral.sh/uv/install.sh | sh)" >&2
  exit 1
fi

# `uv run` creates .venv and syncs deps from uv.lock on first launch.
cd "${REPO_ROOT}"
exec uv run python -m dataiku_mcp

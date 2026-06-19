#!/usr/bin/env bash
# Launch the dku-mcp stdio server from the wheel bundled in this plugin.
#
# Self-bootstraps `uv` (a single static binary) so the only prerequisite is a
# POSIX shell. Auth comes from DKU_URL + DKU_API_KEY, injected by Claude Code
# from the plugin's userConfig (your own DSS personal API key).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

# 1) Ensure uv/uvx is available (installs to ~/.local/bin if missing).
if ! command -v uvx >/dev/null 2>&1; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "[dku-mcp] installing uv (one-time)..." >&2
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh >&2; then
      echo "[dku-mcp] could not install uv automatically. Install it from" >&2
      echo "          https://docs.astral.sh/uv/ then restart your session." >&2
      exit 1
    fi
  fi
  # uv's installer writes an `env` file next to the installed binary — under
  # UV_INSTALL_DIR or XDG_BIN_HOME when those are set, else $HOME/.local/bin.
  # Source whichever exists so the correct bin dir lands on PATH.
  for _uvdir in "${UV_INSTALL_DIR:-}" "${XDG_BIN_HOME:-}" "$HOME/.local/bin"; do
    if [ -n "$_uvdir" ] && [ -f "$_uvdir/env" ]; then
      # shellcheck disable=SC1091
      . "$_uvdir/env"
      break
    fi
  done
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  if ! command -v uvx >/dev/null 2>&1; then
    echo "[dku-mcp] uv installed but 'uvx' is not on PATH. If UV_INSTALL_DIR or" >&2
    echo "          XDG_BIN_HOME is set, add that bin dir to PATH and retry." >&2
    exit 1
  fi
fi

# 2) Find the bundled wheel (version-independent).
WHEEL="$(ls "$ROOT"/wheels/*.whl 2>/dev/null | sort | tail -1 || true)"
if [ -z "${WHEEL:-}" ]; then
  echo "[dku-mcp] no bundled wheel in $ROOT/wheels (build with: make bundle)." >&2
  exit 1
fi

# 3) Run the stdio MCP server. uvx installs the wheel + the MCP runtime
#    (fastmcp) on first launch and caches them; subsequent launches are fast.
exec uvx --from "$WHEEL" --with "fastmcp>=2.0,<4" dku-mcp serve --transport stdio

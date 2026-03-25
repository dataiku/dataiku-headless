#!/usr/bin/env bash
# Check if the dku CLI is available on PATH.
# Used by skills that depend on the CLI for DSS operations.
set -euo pipefail

if command -v dku &>/dev/null; then
    dku --version 2>/dev/null || echo "dku installed"
else
    echo "dku-cli not found on PATH." >&2
    echo "" >&2
    echo "Install with one of:" >&2
    echo "  pip install dku-cli" >&2
    echo "  pipx install dku-cli" >&2
    echo "  uv tool install dku-cli" >&2
    echo "" >&2
    echo "Or use the one-liner:" >&2
    echo "  curl -fsSL https://raw.githubusercontent.com/dataiku/dataiku-cli/main/install.sh | bash" >&2
    exit 1
fi

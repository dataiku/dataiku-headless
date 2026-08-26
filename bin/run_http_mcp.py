#!/usr/bin/env -S uv run --locked --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "fastmcp==3.4.5",
#     "dataiku-api-client==14.7.2",
#     "python-dotenv==1.2.2",
# ]
# ///
"""PEP 723 entry point for the authenticated Streamable HTTP server.

The HTTP service is deliberately separate from ``run_mcp.py``: the latter is
the local stdio plugin, while this launcher requires OIDC verification and an
RFC 8693 token-exchange configuration.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


parser = argparse.ArgumentParser(description="Run the Dataiku MCP HTTP server.")
parser.add_argument(
    "--settings",
    type=Path,
    help="Path to the HTTP settings file (defaults to ~/.dataiku-mcp/http.json).",
)
args = parser.parse_args()

from dataiku_mcp import run_http_server  # noqa: E402

if __name__ == "__main__":
    run_http_server(args.settings)

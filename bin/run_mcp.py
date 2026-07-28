#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "fastmcp",
#     "dataiku-api-client>=14.7.0",
#     "python-dotenv",
# ]
# ///
"""PEP 723 launcher for the Dataiku MCP server.

The inline script metadata above lets any uv build the runtime environment on
the fly, so a harness can start the server without uv, Python, or the project
dependencies being installed first:

    npx -y @manzt/uv@0.8.13 run --quiet bin/run_mcp.py

uv resolves the dependencies into a cached, isolated environment on the first
launch and reuses it afterwards. Only the third-party runtime dependencies are
declared here (the CLI-only ``typer`` is not needed to serve); keep them in
lockstep with ``[project].dependencies`` in ``pyproject.toml`` — the test in
``tests/test_pep723_launcher.py`` enforces that.

``dataiku_mcp`` itself is imported from this clone rather than installed, so
the repository root goes on ``sys.path`` before the import.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dataiku_mcp import run_server  # noqa: E402

if __name__ == "__main__":
    run_server()

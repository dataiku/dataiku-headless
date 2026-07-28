#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "fastmcp",
#     "dataiku-api-client>=14.7.0",
#     "python-dotenv",
# ]
# ///
"""PEP 723 launcher for the Dataiku MCP server — used by every manifest.

The inline script metadata above lets any uv build the runtime environment on
the fly, so a harness can start the server without uv, Python, or the project
dependencies being installed first:

    npx -y @manzt/uv@0.8.13 run --frozen --quiet bin/run_mcp.py

uv resolves the dependencies into a cached, isolated environment on the first
launch and reuses it afterwards, pinned by the committed ``run_mcp.py.lock``.
That lockfile is only ever written by ``uv lock --script bin/run_mcp.py`` —
``uv run`` never creates a missing one, and ``--frozen`` stops it from
rewriting an existing one inside the harness's plugin directory. Note that this
is the script's own lockfile: ``uv.lock`` governs ``uv run``/``uv sync`` for
development and does not apply here.

Only the third-party runtime dependencies are declared above (the CLI-only
``typer`` is not needed to serve); keep them in lockstep with
``[project].dependencies`` in ``pyproject.toml`` — the test in
``tests/test_pep723_launcher.py`` enforces that.

``dataiku_mcp`` is imported from this clone rather than from an installed
distribution — the package is not published to a package index — so the
repository root goes on ``sys.path`` before the import.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dataiku_mcp import run_server  # noqa: E402

if __name__ == "__main__":
    run_server()

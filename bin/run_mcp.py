#!/usr/bin/env -S uv run --locked --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "fastmcp==3.4.5",
#     "dataiku-api-client==14.7.2",
#     "python-dotenv==1.2.2",
# ]
# ///
"""PEP 723 entry point for the Dataiku MCP server.

The inline script metadata above lets uv build the runtime environment on the
fly, so a harness with uv 0.12.0 or later can start the server without a
project install:

    uv run --quiet --locked --script bin/run_mcp.py

The plugin manifests invoke this script directly through uv. ``bin/launcher.sh``
is retained as inactive legacy code for a possible future fallback path.

uv installs the committed ``bin/run_mcp.py.lock`` resolution into a cached,
isolated environment on the first launch and reuses it afterwards. ``--locked``
prevents a launch from resolving or changing that lock. After deliberately
changing the inline metadata, regenerate the lock with
``uv lock --script bin/run_mcp.py`` and commit it. The ``==`` pins above remain
the direct dependency constraints; the lock also records their transitive
dependencies.

The third-party runtime dependencies are declared above. Each pin must satisfy
the corresponding entry in ``[project].dependencies`` in ``pyproject.toml``, and
the package set must match it — the test in ``tests/test_pep723_launcher.py``
enforces both.

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

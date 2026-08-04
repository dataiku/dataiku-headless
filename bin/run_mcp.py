#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "fastmcp==3.4.5",
#     "dataiku-api-client==14.7.2",
#     "python-dotenv==1.2.2",
# ]
# ///
"""PEP 723 entry point for the Dataiku MCP server.

The inline script metadata above lets any uv build the runtime environment on
the fly, so a harness can start the server without uv, Python, or the project
dependencies being installed first:

    npx -y @dataiku/uv@0.12.0 run --quiet bin/run_mcp.py

The manifests do not call this file directly; they run ``bin/launcher.sh``,
which reads the block above and provisions the runtime with whichever of uv, a
pip venv, or npx-vendored uv the host can offer.

uv resolves the dependencies into a cached, isolated environment on the first
launch and reuses it afterwards. There is no script lockfile, so the ``==``
pins above are what keeps every install on the same versions — bump them
deliberately rather than letting a launch float. Transitive dependencies are
not pinned by this block; ``mcp``, for instance, floats within whatever range
the pinned ``fastmcp`` allows.

The third-party runtime dependencies are declared above. Each pin must satisfy the corresponding entry in ``[project].dependencies`` in ``pyproject.toml``, and the package set must match it — the test in ``tests/test_pep723_launcher.py`` enforces both.

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

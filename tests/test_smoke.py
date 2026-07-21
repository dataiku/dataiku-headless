"""Smoke tests: the package imports cleanly and exposes its public surface.

These intentionally avoid any live Dataiku DSS connection — importing the
package must work without credentials (``config.py`` defaults every setting to
an empty value), so CI can run them on a bare runner.
"""

import importlib.metadata

import dataiku_mcp


def test_public_api():
    assert dataiku_mcp.__all__ == ["mcp", "run_server"]
    assert callable(dataiku_mcp.run_server)


def test_mcp_server_initialized():
    # Importing the package registers every tool module against this server.
    assert dataiku_mcp.mcp.name == "Dataiku DSS"


def test_distribution_version_is_resolvable():
    # The version is the commitizen / PEP 621 source of truth in pyproject.toml
    # and what the release workflow diffs to decide whether to publish.
    version = importlib.metadata.version("dataiku-headless")
    assert version and version[0].isdigit()

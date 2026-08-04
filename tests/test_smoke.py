"""Smoke tests: the package imports cleanly and exposes its public surface.

These intentionally avoid any live Dataiku connection — importing the
package must work without credentials (``config.py`` defaults every setting to
an empty value), so CI can run them on a bare runner.
"""

import importlib.metadata

import dataiku_mcp


def test_public_api():
    assert dataiku_mcp.__all__ == ["mcp", "run_server"]
    assert callable(dataiku_mcp.run_server)


def test_mcp_server_initialized():
    assert dataiku_mcp.mcp.name == "Dataiku"


def test_distribution_version_is_resolvable():
    # The version is the commitizen / PEP 621 source of truth in pyproject.toml
    # and what the bump workflow keeps in lockstep with the plugin manifests.
    version = importlib.metadata.version("dataiku-headless")
    assert version and version[0].isdigit()


def test_single_console_entry_point_uses_the_cli():
    entry_points = {
        entry_point.name: entry_point.value
        for entry_point in importlib.metadata.entry_points(group="console_scripts")
        if entry_point.name in {"dataiku-headless", "dataiku-mcp"}
    }
    assert entry_points == {"dataiku-headless": "dataiku_mcp.cli:main"}

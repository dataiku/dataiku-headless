"""Smoke tests: the package imports cleanly and exposes its public surface.

These intentionally avoid any live Dataiku DSS connection — importing the
package must work without credentials (``config.py`` defaults every setting to
an empty value), so CI can run them on a bare runner.
"""

import importlib.metadata

import dataiku_mcp
import pytest
from dataiku_mcp.tools.utils.auth import _resolve_api_key


def test_public_api():
    assert dataiku_mcp.__all__ == ["mcp", "run_server"]
    assert callable(dataiku_mcp.run_server)


def test_mcp_server_initialized():
    # Importing the package registers every tool module against this server.
    assert dataiku_mcp.mcp.name == "Dataiku DSS"


def test_run_server_uses_stdio(monkeypatch):
    calls = []
    monkeypatch.setattr(dataiku_mcp.mcp, "run", lambda **kwargs: calls.append(kwargs))

    dataiku_mcp.run_server()

    assert calls == [{"transport": "stdio"}]


def test_empty_api_key_requires_configured_credentials():
    with pytest.raises(ValueError, match="Set DKU_API_KEY"):
        _resolve_api_key("")


def test_distribution_version_is_resolvable():
    # The version is the commitizen / PEP 621 source of truth in pyproject.toml
    # and what the release workflow diffs to decide whether to publish.
    version = importlib.metadata.version("dataiku-headless")
    assert version and version[0].isdigit()

"""Smoke tests: the package imports cleanly and exposes its public surface.

These intentionally avoid any live Dataiku connection — importing the
package must work without credentials (the configuration package defaults every setting to
an empty value), so CI can run them on a bare runner.
"""

import importlib.metadata
import os
import subprocess
import sys

import dataiku_mcp


def test_public_api():
    assert dataiku_mcp.__all__ == ["mcp", "run_stdio_server", "run_http_server"]
    assert callable(dataiku_mcp.run_stdio_server)
    assert callable(dataiku_mcp.run_http_server)


def test_mcp_server_initialized():
    assert dataiku_mcp.mcp.name == "Dataiku"


def test_distribution_version_is_resolvable():
    # The version is the commitizen / PEP 621 source of truth in pyproject.toml
    # and what the bump workflow keeps in lockstep with the plugin manifests.
    version = importlib.metadata.version("dataiku-headless")
    assert version and version[0].isdigit()


def test_package_import_does_not_read_stdio_config(tmp_path):
    config_path = tmp_path / "invalid-config.json"
    config_path.write_text("{")
    environment = os.environ | {"DKU_CONFIG_FILE": str(config_path)}

    result = subprocess.run(
        [sys.executable, "-c", "import dataiku_mcp"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == 0, result.stderr

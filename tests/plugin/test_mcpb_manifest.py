"""Validate the Claude Desktop .mcpb bundle manifest.

Guards the manifest contract (sensitive key form → launcher env) and that the
bundle reuses the shared launcher from the dataiku-mcp plugin.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUNDLE = REPO / "dataiku-mcp-bundle"
MANIFEST = BUNDLE / "manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_has_required_mcpb_fields():
    m = _manifest()
    assert m["manifest_version"]
    assert m["name"] == "dataiku-mcp"
    assert m["version"]
    assert m["author"]["name"]


def test_server_type_is_spec_valid_and_launcher_is_executable():
    # server.type must be a value the .mcpb spec accepts, and the launcher the
    # bundle stages must actually be executable (the bundle relies on chmod +x).
    server = _manifest()["server"]
    assert server["type"] in {"node", "python", "binary"}
    launcher = REPO / "dataiku-mcp" / "bin" / "dku-mcp-launch.sh"
    assert os.access(launcher, os.X_OK), "staged launcher must be executable (chmod +x)"


def test_server_runs_the_shared_launcher_with_injected_auth():
    server = _manifest()["server"]
    assert "dku-mcp-launch.sh" in server["entry_point"]
    cfg = server["mcp_config"]
    assert cfg["command"] == "${__dirname}/bin/dku-mcp-launch.sh"
    assert cfg["env"]["DKU_URL"] == "${user_config.dss_url}"
    assert cfg["env"]["DKU_API_KEY"] == "${user_config.api_key}"


def test_user_config_prompts_for_a_sensitive_key():
    uc = _manifest()["user_config"]
    assert uc["dss_url"]["required"] is True
    assert uc["api_key"]["required"] is True
    assert uc["api_key"]["sensitive"] is True  # → OS keychain


def test_bundle_reuses_the_plugin_launcher():
    """The .mcpb stages the launcher from the dataiku-mcp plugin (no fork)."""
    launcher = REPO / "dataiku-mcp" / "bin" / "dku-mcp-launch.sh"
    assert launcher.is_file(), "shared launcher must exist to be staged into the bundle"

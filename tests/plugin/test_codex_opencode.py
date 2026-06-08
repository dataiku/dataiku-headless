"""Validate the Codex plugin + OpenCode config that ship alongside the Claude
Code plugin in dataiku-mcp/ (shared launcher + bundled wheel)."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "dataiku-mcp"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_codex_manifest_points_at_shared_config():
    m = _json(PLUGIN / ".codex-plugin" / "plugin.json")
    assert m["name"] == "dataiku-mcp"
    assert m["version"]
    # a non-".mcp.json" filename so Claude Code doesn't also pick it up
    assert m["mcpServers"] == "./codex-mcp.json"
    assert (PLUGIN / "codex-mcp.json").is_file()


def test_codex_mcp_config_runs_shared_launcher_with_env_auth():
    cfg = _json(PLUGIN / "codex-mcp.json")
    server = cfg["dku"]
    # reuses the SAME launcher as the Claude Code plugin, via Codex's PLUGIN_ROOT
    assert server["command"] == "${PLUGIN_ROOT}/bin/dku-mcp-launch.sh"
    assert server["env"]["DKU_URL"] == "${DKU_URL}"
    assert server["env"]["DKU_API_KEY"] == "${DKU_API_KEY}"


def test_codex_marketplace_lists_the_plugin():
    mk = _json(REPO / ".agents" / "plugins" / "marketplace.json")
    entry = next((p for p in mk["plugins"] if p["name"] == "dataiku-mcp"), None)
    assert entry is not None
    assert entry["source"]["path"] == "./dataiku-mcp"
    assert "dataiku-cli" in entry["source"]["url"]


def test_opencode_example_is_a_valid_local_stdio_server():
    cfg = _json(PLUGIN / "examples" / "opencode.json")
    dku = cfg["mcp"]["dku"]
    assert dku["type"] == "local"
    assert dku["command"] == ["dku-mcp", "serve", "--transport", "stdio"]
    assert dku["enabled"] is True
    assert set(dku["environment"]) == {"DKU_URL", "DKU_API_KEY"}

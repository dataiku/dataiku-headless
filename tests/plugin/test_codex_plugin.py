from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "dataiku-mcp"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_codex_manifest_points_at_plugin_mcp_config():
    m = _json(PLUGIN / ".codex-plugin" / "plugin.json")
    assert m["name"] == "dataiku-mcp"
    assert m["version"]
    assert m["mcpServers"] == "./.mcp.json"
    assert (PLUGIN / ".mcp.json").is_file()


def test_codex_mcp_config_runs_shared_launcher_with_env_auth():
    cfg = _json(PLUGIN / ".mcp.json")
    server = cfg["mcpServers"]["dku"]
    assert server["command"] == "./bin/dku-mcp-launch.sh"
    assert server["args"] == []
    assert server["cwd"] == "."
    assert server["env_vars"] == ["DKU_URL", "DKU_API_KEY"]


def test_codex_marketplace_lists_the_plugin():
    mk = _json(REPO / ".agents" / "plugins" / "marketplace.json")
    entry = next((p for p in mk["plugins"] if p["name"] == "dataiku-mcp"), None)
    assert entry is not None
    assert entry["source"]["path"] == "./dataiku-mcp"
    assert entry["source"]["url"] == "https://github.com/dataiku/dku-headless.git"

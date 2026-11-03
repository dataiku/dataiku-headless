# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Packaging invariants for the public stdio plugin."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_marketplace_plugin_uses_stdio():
    claude = _json(".claude-plugin/plugin.json")
    bundled_mcp = _json(".mcp.json")

    assert claude["mcpServers"]["dataiku"]["type"] == "stdio"
    assert bundled_mcp["mcpServers"]["dataiku"]["args"][-2:] == [
        "--transport",
        "stdio",
    ]


def test_marketplace_entry_matches_plugin_identity():
    claude = _json(".claude-plugin/plugin.json")
    marketplace = _json(".claude-plugin/marketplace.json")

    entries = [
        entry for entry in marketplace["plugins"] if entry["name"] == claude["name"]
    ]
    assert len(entries) == 1
    assert entries[0]["source"] == "./"


def test_native_plugin_matches_existing_identity():
    native = _json("plugin.json")
    claude = _json(".claude-plugin/plugin.json")

    assert native["$schema"] == (
        "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    )
    assert native["name"] == claude["name"]
    assert native["version"] == claude["version"]


def test_native_plugin_uses_same_stdio_launcher():
    native = _json("mcp.json")
    claude = _json(".claude-plugin/plugin.json")["mcpServers"]["dataiku"]
    server = native["mcpServers"]["dataiku"]

    assert native["$schema"] == (
        "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    )
    assert set(native["mcpServers"]) == {"dataiku"}
    assert server["type"] == claude["type"] == "stdio"
    assert server["command"] == claude["command"]
    assert server["args"] == [
        arg.replace("${CLAUDE_PLUGIN_ROOT}", "${PLUGIN_ROOT}") for arg in claude["args"]
    ]
    assert server["cwd"] == "${PLUGIN_ROOT}"
    script = server["args"][server["args"].index("--script") + 1]
    assert (ROOT / script.removeprefix("${PLUGIN_ROOT}/")).is_file()


def test_public_setup_skill_is_stdio_only():
    setup_skill = (ROOT / "skills" / "dataiku-headless-setup" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "--transport stdio" in setup_skill
    assert "references/http.md" not in setup_skill
    assert "customer-managed HTTP" not in setup_skill


def test_environment_configuration_is_passed_through():
    variables = _json(".mcp.json")["mcpServers"]["dataiku"]["env_vars"]
    assert {
        "DKU_DSS_URL",
        "DKU_API_KEY",
        "DKU_INSTANCE_TYPE",
        "DKU_IS_CODE_STUDIO",
        "DKU_NODE_TYPE",
        "DKU_BACKEND_PROTOCOL",
        "DKU_BACKEND_HOST",
        "DKU_BACKEND_PORT",
        "DKU_API_TICKET",
        "DKU_SERVER_CERT",
    }.issubset(variables)

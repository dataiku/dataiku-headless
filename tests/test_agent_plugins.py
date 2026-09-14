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

"""Agent Plugins v1.0.0 portable package contract.

The repository root is an Agent Plugins package: ``plugin.json`` + ``mcp.json``
+ the existing ``skills/``. Harness-specific manifests stay under
``.claude-plugin/`` and ``.codex-plugin/``.
"""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

# Closed set of manifest fields; a client ignores anything else.
PLUGIN_TOP_LEVEL = {
    "$schema",
    "name",
    "displayName",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_portable_plugin_manifest_is_agent_plugins_v1():
    manifest = _load_json(ROOT / "plugin.json")

    assert set(manifest) <= PLUGIN_TOP_LEVEL
    assert manifest["$schema"] == PLUGIN_SCHEMA
    assert manifest["name"] == "dataiku-headless"
    assert set(manifest["author"]) <= {"name", "email", "url"}


def test_portable_mcp_config_launches_the_packaged_script():
    config = _load_json(ROOT / "mcp.json")

    assert set(config) == {"$schema", "mcpServers"}
    assert config["$schema"] == MCP_SCHEMA

    server = config["mcpServers"]["dataiku"]
    assert set(server) <= {"type", "command", "args", "env", "cwd"}
    assert server["type"] == "stdio"
    # ${PLUGIN_ROOT} is expanded in args/env/cwd but never in command.
    assert server["command"] == "uv"
    assert server["cwd"] == "${PLUGIN_ROOT}"
    script = server["args"][-1]
    assert script.startswith("${PLUGIN_ROOT}/")
    assert (ROOT / script.removeprefix("${PLUGIN_ROOT}/")).is_file()


def test_plugin_versions_match_project_version():
    # importlib.metadata reads the installed project: no tomllib on 3.10.
    expected = importlib.metadata.version("dataiku-headless")
    assert (
        _load_json(ROOT / "plugin.json")["version"]
        == _load_json(ROOT / ".claude-plugin" / "plugin.json")["version"]
        == _load_json(ROOT / ".codex-plugin" / "plugin.json")["version"]
        == expected
    )

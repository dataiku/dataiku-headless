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

"""Cursor-native plugin packaging contract."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cursor_plugin_launches_the_stdio_server_from_its_install_root():
    manifest = json.loads(
        (ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    server = manifest["mcpServers"]["dataiku"]

    assert manifest["name"] == "dataiku-headless"
    assert manifest["version"] == importlib.metadata.version("dataiku-headless")
    assert manifest["skills"] == "./skills/"
    assert server["type"] == "stdio"
    assert server["command"] == "uv"
    assert server["args"] == [
        "run",
        "--quiet",
        "--locked",
        "--script",
        "${CURSOR_PLUGIN_ROOT}/runtime/run_mcp.py",
        "--transport",
        "stdio",
    ]
    assert server["cwd"] == "${CURSOR_PLUGIN_ROOT}"

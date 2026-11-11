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

"""Cursor-compatible portable plugin packaging contract."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cursor_uses_portable_launch_without_standard_placeholders():
    manifest = json.loads((ROOT / "plugin.json").read_text())
    server = json.loads((ROOT / "mcp.json").read_text())["mcpServers"]["dataiku"]
    assert manifest["version"] == importlib.metadata.version("dataiku-headless")
    assert server["cwd"] == "./"
    assert server["args"][4] == "./runtime/run_mcp.py"
    assert "${PLUGIN_" not in json.dumps(server)

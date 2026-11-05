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
import shutil
import subprocess
import sys
from pathlib import Path
from string import Template

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("host", ["claude", "codex", "cortex", "cursor", "github"])
def test_plugin_identity_is_headless(host):
    path = (
        ".github/plugin/plugin.json"
        if host == "github"
        else f".{host}-plugin/plugin.json"
    )
    assert _json(path)["name"] == "headless"


def test_marketplace_plugin_uses_stdio():
    claude = _json(".claude-plugin/plugin.json")
    bundled_mcp = _json(_json(".codex-plugin/plugin.json")["mcpServers"])

    assert claude["mcpServers"]["dataiku"]["type"] == "stdio"
    assert bundled_mcp["mcpServers"]["dataiku"]["args"][-2:] == [
        "--transport",
        "stdio",
    ]


@pytest.mark.parametrize("directory", [".claude-plugin", ".github/plugin"])
def test_marketplace_entry_matches_plugin_identity(directory):
    claude = _json(f"{directory}/plugin.json")
    marketplace = _json(f"{directory}/marketplace.json")

    entries = [
        entry for entry in marketplace["plugins"] if entry["name"] == claude["name"]
    ]
    assert len(entries) == 1
    assert entries[0]["source"] == "./"
    assert marketplace["name"] == "dataiku"
    assert marketplace["renames"]["dataiku-headless"] == claude["name"]


def test_public_setup_skill_is_stdio_only():
    setup_skill = (ROOT / "skills" / "dataiku-headless-setup" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "--transport stdio" in setup_skill
    assert "references/http.md" not in setup_skill
    assert "customer-managed HTTP" not in setup_skill


def test_environment_configuration_is_passed_through():
    bundled_mcp = _json(_json(".codex-plugin/plugin.json")["mcpServers"])
    variables = bundled_mcp["mcpServers"]["dataiku"]["env_vars"]
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


def test_copilot_launches_from_an_unrelated_working_directory(tmp_path):
    plugin_root = tmp_path / "installed plugin"
    runtime = plugin_root / "runtime"
    runtime.mkdir(parents=True)
    shutil.copy2(ROOT / "runtime" / "run_mcp.py", runtime / "run_mcp.py")
    for relative in (".github/plugin/plugin.json", ".claude-plugin/plugin.json"):
        target = plugin_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    claude_path = plugin_root / ".claude-plugin/plugin.json"
    claude = json.loads(claude_path.read_text())
    claude["mcpServers"]["dataiku"]["args"] = ["missing-script.py"]
    claude_path.write_text(json.dumps(claude))
    # Documented legacy discovery order; this is a launch replay, not a native CLI test.
    assert not (ROOT / ".mcp.json").exists()
    assert not (ROOT / ".github/mcp.json").exists()
    for relative in (
        ".plugin/plugin.json",
        "plugin.json",
        ".github/plugin/plugin.json",
        ".claude-plugin/plugin.json",
    ):
        assert (plugin_root / relative).exists() == (ROOT / relative).exists()
    manifest_path = next(
        plugin_root / relative
        for relative in (
            ".plugin/plugin.json",
            "plugin.json",
            ".github/plugin/plugin.json",
            ".claude-plugin/plugin.json",
        )
        if (plugin_root / relative).exists()
    )
    assert manifest_path == plugin_root / ".github/plugin/plugin.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["name"] == _json(".codex-plugin/plugin.json")["name"]
    assert (ROOT / manifest["skills"]).is_dir()
    server = manifest["mcpServers"]["dataiku"]
    assert server["command"] == "uv"
    assert server["type"] == "stdio"
    assert server["args"] == [
        "run",
        "--quiet",
        "--locked",
        "--script",
        "${PLUGIN_ROOT}/runtime/run_mcp.py",
        "--transport",
        "stdio",
    ]
    assert server["cwd"] == "${PLUGIN_ROOT}"
    session_directory = tmp_path / "customer project"
    session_directory.mkdir()
    variables = {
        "PLUGIN_ROOT": str(plugin_root),
        "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        "COPILOT_PLUGIN_ROOT": str(plugin_root),
    }
    cwd = Path(Template(server.get("cwd", "${PLUGIN_ROOT}")).substitute(variables))
    if not cwd.is_absolute():
        cwd = session_directory / cwd
    args = [Template(arg).substitute(variables) for arg in server["args"]]
    script_index = args.index("--script") + 1
    result = subprocess.run(
        [sys.executable, *args[script_index:], "--help"],
        cwd=cwd,
        env=variables,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "Run the Dataiku MCP server." in result.stdout

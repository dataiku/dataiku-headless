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
from jsonschema import validate

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("host", ["claude", "cortex"])
def test_plugin_identity_matches_host(host):
    path = f".{host}-plugin/plugin.json"
    assert _json(path)["name"] == (
        "headless" if host == "claude" else "dataiku-headless"
    )


def test_marketplace_plugin_uses_stdio():
    claude = _json(".claude-plugin/plugin.json")
    bundled_mcp = _json("mcp.json")

    assert claude["mcpServers"]["dataiku"]["type"] == "stdio"
    assert bundled_mcp["mcpServers"]["dataiku"]["args"][-2:] == [
        "--transport",
        "stdio",
    ]


@pytest.mark.parametrize(
    "directory, manifest_path",
    [
        (".claude-plugin", ".claude-plugin/plugin.json"),
        (".github/plugin", "plugin.json"),
        (".cursor-plugin", "plugin.json"),
        (".agents/plugins", "plugin.json"),
    ],
)
def test_marketplace_entry_matches_plugin_identity(directory, manifest_path):
    manifest = _json(manifest_path)
    marketplace = _json(f"{directory}/marketplace.json")
    assert len(marketplace["plugins"]) == 1
    entry = marketplace["plugins"][0]
    assert entry["name"] == manifest["name"]
    assert entry["source"] == "./"
    assert (ROOT / entry["source"]).resolve() == ROOT
    assert (ROOT / entry["source"] / manifest_path).is_file()
    assert marketplace["name"] == "dataiku"
    if directory == ".claude-plugin":
        assert marketplace["renames"]["dataiku-headless"] == "headless"
    else:
        assert "renames" not in marketplace


def test_codex_marketplace_declares_installation_and_authentication_policy():
    entry = _json(".agents/plugins/marketplace.json")["plugins"][0]
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert entry["category"] == "developer-tools"


def test_public_setup_skill_is_stdio_only():
    setup_skill = (ROOT / "skills" / "dataiku-headless-setup" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "--transport stdio" in setup_skill
    assert "references/http.md" not in setup_skill
    assert "customer-managed HTTP" not in setup_skill


def test_portable_schemas_and_metadata():
    for name in ("plugin", "mcp"):
        validate(_json(f"{name}.json"), _json(f"tests/schemas/{name}.schema.json"))
    manifest = _json("plugin.json")
    extension = manifest["extensions"]["com.openai"]
    assert (ROOT / extension["onboardingSkill"]).is_file()
    assert extension["review"]["test_cases"]["positive"]
    for key in ("composerIcon", "composerIconDark", "logo", "logoDark"):
        assert (ROOT / extension["interface"][key]).is_file()
    for path in (
        ".codex-plugin/plugin.json",
        ".codex-plugin/mcp.json",
        ".cursor-plugin/plugin.json",
        ".github/plugin/plugin.json",
    ):
        assert not (ROOT / path).exists()


def test_portable_launch_from_unrelated_directory(tmp_path):
    plugin_root = tmp_path / "installed plugin"
    runtime = plugin_root / "runtime"
    runtime.mkdir(parents=True)
    shutil.copy2(ROOT / "runtime/run_mcp.py", runtime / "run_mcp.py")
    session = tmp_path / "customer project"
    session.mkdir()
    server = _json("mcp.json")["mcpServers"]["dataiku"]
    assert server["command"] == "uv"
    assert server["type"] == "stdio"
    assert server["cwd"] == "./"
    assert server["args"] == [
        "run",
        "--quiet",
        "--locked",
        "--script",
        "./runtime/run_mcp.py",
        "--transport",
        "stdio",
    ]
    # Replay standard cwd resolution without invoking a native harness or uv.
    cwd = plugin_root / server["cwd"]
    assert cwd.resolve() != session.resolve()
    args = server["args"][server["args"].index("--script") + 1 :]
    result = subprocess.run(
        [sys.executable, *args, "--help"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "Run the Dataiku MCP server." in result.stdout

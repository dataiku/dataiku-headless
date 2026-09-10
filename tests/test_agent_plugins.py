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

This repo ships as an Agent Plugins package (root ``plugin.json`` + ``mcp.json``
+ ``skills/``) while retaining harness-specific manifests under
``.claude-plugin/`` and ``.codex-plugin/``. These tests pin the portable floor
and keep version fields in lockstep with ``[project].version``.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

# Closed portable manifest fields (Agent Plugins §5.2).
PLUGIN_TOP_LEVEL = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}

# Plugin name constraints (Agent Plugins §5.5).
PLUGIN_NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")

# cwd forms allowed by Agent Plugins §7.2.1 (stdio).
_CWD_RE = re.compile(
    r"^(?:\./(?!\.\.)|\$\{PLUGIN_ROOT\}(?:/|$)|\$\{PLUGIN_DATA\}(?:/|$))"
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _project_version() -> str:
    # Prefer the installed distribution so this works on Python 3.10 (no tomllib).
    return importlib.metadata.version("dataiku-headless")


def test_portable_plugin_manifest_is_agent_plugins_v1():
    manifest = _load_json(ROOT / "plugin.json")

    assert set(manifest) <= PLUGIN_TOP_LEVEL
    assert manifest["$schema"] == PLUGIN_SCHEMA
    assert isinstance(manifest["name"], str)
    assert 1 <= len(manifest["name"]) <= 64
    assert PLUGIN_NAME_RE.fullmatch(manifest["name"]), manifest["name"]
    assert manifest["name"] == "dataiku-headless"
    assert isinstance(manifest.get("version"), str) and manifest["version"]
    assert isinstance(manifest.get("description"), str) and manifest["description"]
    assert isinstance(manifest.get("license"), str) and manifest["license"]
    assert isinstance(manifest.get("keywords"), list)
    assert all(isinstance(k, str) for k in manifest["keywords"])

    author = manifest.get("author")
    if author is not None:
        assert isinstance(author, dict)
        assert set(author) <= {"name", "email", "url"}
        assert all(isinstance(v, str) for v in author.values())


def test_portable_mcp_config_is_agent_plugins_v1_stdio():
    config = _load_json(ROOT / "mcp.json")

    assert set(config) == {"$schema", "mcpServers"}
    assert config["$schema"] == MCP_SCHEMA
    assert isinstance(config["mcpServers"], dict)
    assert "dataiku" in config["mcpServers"]

    server = config["mcpServers"]["dataiku"]
    assert set(server) <= {"type", "command", "args", "env", "cwd"}
    assert server["type"] == "stdio"
    assert server["command"] == "uv"
    assert isinstance(server.get("args"), list)
    assert server["args"] == [
        "run",
        "--quiet",
        "--locked",
        "--script",
        "${PLUGIN_ROOT}/runtime/run_mcp.py",
    ]

    cwd = server.get("cwd")
    if cwd is not None:
        assert _CWD_RE.match(cwd), cwd
        assert ".." not in cwd


def test_plugin_and_mcp_schema_versions_match():
    plugin = _load_json(ROOT / "plugin.json")
    mcp = _load_json(ROOT / "mcp.json")
    plugin_version = plugin["$schema"].rsplit("/", 2)[1]
    mcp_version = mcp["$schema"].rsplit("/", 2)[1]
    assert plugin_version == mcp_version == "1.0.0"


def test_skill_is_discovered_as_immediate_child_of_skills():
    skill_md = ROOT / "skills" / "dataiku-headless" / "SKILL.md"
    assert skill_md.is_file()
    # Agent Plugins discovers only immediate children of skills/; nested
    # SKILL.md under references/ must not appear as sibling skills.
    skill_dirs = [
        p
        for p in (ROOT / "skills").iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    ]
    assert sorted(p.name for p in skill_dirs) == [
        "dataiku-headless",
        "dataiku-headless-setup",
    ]

    frontmatter = skill_md.read_text(encoding="utf-8").split("---", 2)
    assert len(frontmatter) >= 3, "SKILL.md missing YAML frontmatter"
    assert re.search(r"(?m)^name:\s*dataiku-headless\s*$", frontmatter[1])
    assert re.search(r"(?m)^description:\s*\S", frontmatter[1])


def test_mcp_script_path_exists_in_package():
    """Portable mcp.json must point at the supported script entry point."""
    config = _load_json(ROOT / "mcp.json")
    server = config["mcpServers"]["dataiku"]
    script_path = server["args"][-1].removeprefix("${PLUGIN_ROOT}/")
    assert (ROOT / script_path).is_file()


def test_plugin_versions_match_project_version():
    expected = _project_version()
    portable = _load_json(ROOT / "plugin.json")["version"]
    claude = _load_json(ROOT / ".claude-plugin" / "plugin.json")["version"]
    codex = _load_json(ROOT / ".codex-plugin" / "plugin.json")["version"]
    assert portable == claude == codex == expected


def test_commitizen_version_selector_preserves_schema_urls():
    """Simulate commitizen's path:pattern rewrite so schema 1.0.0 is not clobbered."""
    # Mirrors commitizen.bump.update_version_in_files: replace only on lines that
    # match the configured regex (here the version key).
    pattern = re.compile(r'"version":')
    text = (ROOT / "plugin.json").read_text(encoding="utf-8")
    current = _project_version()
    # Force a synthetic package version that collides with the schema segment.
    synthetic = text.replace(f'"version": "{current}"', '"version": "1.0.0"', 1)
    assert '"version": "1.0.0"' in synthetic
    assert PLUGIN_SCHEMA in synthetic

    rewritten = []
    for line in synthetic.splitlines(keepends=True):
        if pattern.search(line):
            rewritten.append(line.replace("1.0.0", "1.0.1"))
        else:
            rewritten.append(line)
    result = "".join(rewritten)
    assert '"version": "1.0.1"' in result
    assert PLUGIN_SCHEMA in result  # schema URL must keep 1.0.0

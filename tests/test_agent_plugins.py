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
    assert server["command"] == "sh"
    assert isinstance(server.get("args"), list)
    assert server["args"] == ["${PLUGIN_ROOT}/bin/launcher.sh"]

    env = server.get("env", {})
    assert isinstance(env, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())
    # Reserved names are client-supplied only (Agent Plugins §9.2).
    assert "PLUGIN_ROOT" not in env
    assert "PLUGIN_DATA" not in env
    assert env.get("UV_CACHE_DIR") == "${PLUGIN_DATA}/uv-cache"

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
        p for p in (ROOT / "skills").iterdir() if p.is_dir() and (p / "SKILL.md").is_file()
    ]
    assert [p.name for p in skill_dirs] == ["dataiku-headless"]

    frontmatter = skill_md.read_text(encoding="utf-8").split("---", 2)
    assert len(frontmatter) >= 3, "SKILL.md missing YAML frontmatter"
    assert re.search(r"(?m)^name:\s*dataiku-headless\s*$", frontmatter[1])
    assert re.search(r"(?m)^description:\s*\S", frontmatter[1])


def test_mcp_launcher_path_exists_in_package():
    """Portable mcp.json must point at a real package path after expansion."""
    config = _load_json(ROOT / "mcp.json")
    server = config["mcpServers"]["dataiku"]
    for arg in server.get("args", []):
        # Expand only the placeholders this package uses.
        expanded = arg.replace("${PLUGIN_ROOT}", str(ROOT)).replace(
            "${PLUGIN_DATA}", str(ROOT / ".deps")
        )
        if expanded.endswith("launcher.sh"):
            assert Path(expanded).is_file(), expanded


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


def test_launcher_prefers_agent_plugins_data_dir(tmp_path):
    """PLUGIN_DATA / PLUGIN_ROOT win over Claude-specific and local defaults."""
    import os
    import subprocess

    launcher = (ROOT / "bin" / "launcher.sh").read_text(encoding="utf-8")
    # Extract the real assignment lines so this test cannot drift from launcher.sh.
    match = re.search(
        r"^PLUGIN_ROOT=\$\{PLUGIN_ROOT:-.*\nDATA_DIR=\$\{PLUGIN_DATA:-.*$",
        launcher,
        re.MULTILINE,
    )
    assert match, "launcher.sh lost PLUGIN_ROOT/DATA_DIR assignment order"
    probe = tmp_path / "probe.sh"
    probe.write_text(
        "set -eu\n"
        'HERE=$(CDPATH=\'\' cd -- "$(dirname -- "$0")" && pwd)\n'
        f"{match.group(0)}\n"
        'printf \'%s\\n\' "$PLUGIN_ROOT"\n'
        'printf \'%s\\n\' "$DATA_DIR"\n',
        encoding="utf-8",
    )
    probe.chmod(0o755)

    env = os.environ.copy()
    for key in (
        "PLUGIN_ROOT",
        "PLUGIN_DATA",
        "CLAUDE_PLUGIN_ROOT",
        "CLAUDE_PLUGIN_DATA",
    ):
        env.pop(key, None)

    agent_root = tmp_path / "agent-root"
    agent_data = tmp_path / "agent-data"
    claude_root = tmp_path / "claude-root"
    claude_data = tmp_path / "claude-data"
    for path in (agent_root, agent_data, claude_root, claude_data):
        path.mkdir()

    env.update(
        {
            "PLUGIN_ROOT": str(agent_root),
            "PLUGIN_DATA": str(agent_data),
            "CLAUDE_PLUGIN_ROOT": str(claude_root),
            "CLAUDE_PLUGIN_DATA": str(claude_data),
        }
    )
    out = subprocess.check_output(["sh", str(probe)], env=env, text=True)
    root, data = out.splitlines()
    assert root == str(agent_root)
    assert data == str(agent_data)

    env.pop("PLUGIN_ROOT")
    env.pop("PLUGIN_DATA")
    out = subprocess.check_output(["sh", str(probe)], env=env, text=True)
    root, data = out.splitlines()
    assert root == str(claude_root)
    assert data == str(claude_data)

    # Local checkout fallback when no harness vars are set.
    env.pop("CLAUDE_PLUGIN_ROOT")
    env.pop("CLAUDE_PLUGIN_DATA")
    # Put the probe under a fake bin/ so HERE/.. resolves like launcher.sh.
    fake_bin = tmp_path / "checkout" / "bin"
    fake_bin.mkdir(parents=True)
    local_probe = fake_bin / "probe.sh"
    local_probe.write_text(probe.read_text(encoding="utf-8"), encoding="utf-8")
    local_probe.chmod(0o755)
    out = subprocess.check_output(["sh", str(local_probe)], env=env, text=True)
    root, data = out.splitlines()
    assert root == str(tmp_path / "checkout")
    assert data == str(tmp_path / "checkout" / ".deps")

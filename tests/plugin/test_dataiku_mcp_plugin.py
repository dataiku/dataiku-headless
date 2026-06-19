"""Validate the dataiku-mcp Claude Code plugin packaging.

These guard the manifest/launcher contract so a malformed plugin can't ship:
the install flow (userConfig key prompt → stdio server via the bundled wheel)
depends on these exact fields.
"""

from __future__ import annotations

import json
import os
import subprocess
import zipfile
from pathlib import Path
import shutil

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "dataiku-mcp"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
LAUNCHER = PLUGIN / "bin" / "dku-mcp-launch.sh"
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
SKILLS = PLUGIN / "skills" / "dku-cli"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_is_valid_and_named():
    m = _manifest()
    assert m["name"] == "dataiku-mcp"
    assert m["version"]


def test_userconfig_prompts_for_a_sensitive_key():
    uc = _manifest()["userConfig"]
    assert uc["dss_url"]["required"] is True
    assert uc["api_key"]["required"] is True
    # the key must be stored securely (OS keychain), never plaintext
    assert uc["api_key"]["sensitive"] is True


def test_mcp_server_runs_the_launcher_with_injected_auth():
    server = _manifest()["mcpServers"]["dku"]
    assert "dku-mcp-launch.sh" in server["command"]
    assert "${CLAUDE_PLUGIN_ROOT}" in server["command"]
    env = server["env"]
    # model A: the caller's own DSS key flows in from userConfig
    assert env["DKU_URL"] == "${user_config.dss_url}"
    assert env["DKU_API_KEY"] == "${user_config.api_key}"


def test_marketplace_lists_the_plugin():
    plugins = json.loads(MARKETPLACE.read_text(encoding="utf-8"))["plugins"]
    entry = next((p for p in plugins if p["name"] == "dataiku-mcp"), None)
    assert entry is not None
    assert entry["source"]["path"] == "dataiku-mcp"


def test_marketplace_name_matches_plugin_manifest():
    plugins = json.loads(MARKETPLACE.read_text(encoding="utf-8"))["plugins"]
    entry = next((p for p in plugins if p["name"] == "dataiku-mcp"), None)
    assert entry is not None
    assert entry["name"] == _manifest()["name"]


def test_launcher_is_executable_valid_bash_and_self_contained():
    assert os.access(LAUNCHER, os.X_OK), "launcher must be executable"
    text = LAUNCHER.read_text(encoding="utf-8")
    assert text.startswith("#!")
    # serves stdio from the bundled wheel via uvx, bootstrapping uv if needed
    assert "--transport stdio" in text
    assert "uvx" in text and "wheels/*.whl" in text
    assert "astral.sh/uv/install.sh" in text  # uv self-bootstrap
    # the fastmcp runtime constraint is upper-bounded so a breaking 4.x can't be
    # resolved at launch (fastmcp 3.x is the validated current major).
    assert "fastmcp>=2.0,<4" in text
    assert 'fastmcp>=2.0"' not in text  # the old unbounded form is gone
    # bash syntax check (skip if bash unavailable)
    if not (os.path.exists("/bin/bash") or os.path.exists("/usr/bin/bash")):
        pytest.skip("bash not available")
    subprocess.run(["bash", "-n", str(LAUNCHER)], check=True)


def test_a_wheel_is_bundled():
    wheels = list((PLUGIN / "wheels").glob("*.whl"))
    assert wheels, "run `make bundle` in dataiku-mcp/ to vendor the wheel"


def test_bundled_wheel_matches_current_version():
    """Catch a stale wheel after a version bump — `make bundle` must be re-run."""
    import dku_cli

    names = [w.name for w in (PLUGIN / "wheels").glob("*.whl")]
    assert any(f"-{dku_cli.__version__}-" in n for n in names), (
        f"bundled wheel {names} != current version {dku_cli.__version__}; "
        "run `make bundle` in dataiku-mcp/"
    )


def test_bundled_wheel_contains_current_mcp_sources():
    """Catch stale wheels when MCP source changes without a version bump."""
    wheels = sorted((PLUGIN / "wheels").glob("*.whl"))
    assert wheels, "run `make bundle` in dataiku-mcp/ to vendor the wheel"
    wheel = wheels[-1]

    with zipfile.ZipFile(wheel) as zf:
        for source in sorted((REPO / "src" / "dku_cli" / "mcp").glob("*.py")):
            wheel_path = f"dku_cli/mcp/{source.name}"
            assert zf.read(wheel_path) == source.read_bytes(), (
                f"{wheel_path} in {wheel.name} is stale; run `make bundle` "
                "in dataiku-mcp/"
            )


def test_plugin_bundles_skill_corpus():
    plugin_files = {str(p.relative_to(SKILLS)) for p in SKILLS.rglob("*.md")}
    assert plugin_files, "plugin skills/ is empty"
    assert "SKILL.md" in plugin_files
    assert any(path.startswith("playbooks/") for path in plugin_files)
    assert any(path.startswith("references/") for path in plugin_files)


def test_launcher_executes_like_an_installed_plugin(tmp_path):
    """Smoke-test the real install path without Claude.

    Stage a minimal installed-plugin layout, put a fake ``uvx`` on PATH, run the
    launcher, and assert it resolves the bundled wheel relative to itself and
    execs the expected stdio server command with the injected DSS env.
    """
    staged = tmp_path / "dataiku-mcp"
    (staged / "bin").mkdir(parents=True)
    (staged / "wheels").mkdir(parents=True)
    shutil.copy2(LAUNCHER, staged / "bin" / LAUNCHER.name)
    wheel = sorted((PLUGIN / "wheels").glob("*.whl"))[-1]
    shutil.copy2(wheel, staged / "wheels" / wheel.name)

    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    capture = tmp_path / "uvx-call.json"
    uvx = fakebin / "uvx"
    uvx.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, os, sys",
                f"path = {str(capture)!r}",
                "payload = {",
                '  "argv": sys.argv[1:],',
                '  "env": {k: os.environ.get(k, "") ',
                '          for k in ("DKU_URL", "DKU_API_KEY")},',
                "}",
                "open(path, 'w', encoding='utf-8').write(json.dumps(payload))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(uvx, 0o755)

    env = dict(os.environ)
    env["PATH"] = f"{fakebin}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "home")
    env["DKU_URL"] = "https://dss.example.com"
    env["DKU_API_KEY"] = "test-personal-key"

    subprocess.run(
        [str(staged / "bin" / LAUNCHER.name)],
        check=True,
        env=env,
        cwd=tmp_path,
    )

    payload = json.loads(capture.read_text(encoding="utf-8"))
    expected_wheel = str(staged / "wheels" / wheel.name)
    assert payload["argv"] == [
        "--from",
        expected_wheel,
        "--with",
        "fastmcp>=2.0,<4",
        "dku-mcp",
        "serve",
        "--transport",
        "stdio",
    ]
    assert payload["env"]["DKU_URL"] == "https://dss.example.com"
    assert payload["env"]["DKU_API_KEY"] == "test-personal-key"

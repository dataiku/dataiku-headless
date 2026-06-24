"""Validate the dataiku-mcp Claude Code plugin packaging.

These guard the manifest/launcher contract so a malformed plugin can't ship:
the install flow (userConfig key prompt → stdio server via the bundled wheel)
depends on these exact fields.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "dataiku-mcp"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
CODEX_MANIFEST = PLUGIN / ".codex-plugin" / "plugin.json"
BUNDLE_MANIFEST = REPO / "dataiku-mcp-bundle" / "manifest.json"
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
    assert uc["api_key"]["sensitive"] is True


def test_mcp_server_runs_the_launcher_with_injected_auth():
    server = _manifest()["mcpServers"]["dku"]
    assert "dku-mcp-launch.sh" in server["command"]
    assert "${CLAUDE_PLUGIN_ROOT}" in server["command"]
    env = server["env"]
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
    assert "--transport stdio" in text
    assert "uvx" in text and "wheels/*.whl" in text
    assert "astral.sh/uv/install.sh" in text
    assert "fastmcp>=2.0,<4" in text
    assert 'fastmcp>=2.0"' not in text
    if not (os.path.exists("/bin/bash") or os.path.exists("/usr/bin/bash")):
        pytest.skip("bash not available")
    subprocess.run(["bash", "-n", str(LAUNCHER)], check=True)


def test_a_wheel_is_bundled():
    wheels = list((PLUGIN / "wheels").glob("*.whl"))
    assert wheels, "run `make bundle` in dataiku-mcp/ to vendor the wheel"


def test_bundled_wheel_matches_current_version():
    import dku_cli

    names = [w.name for w in (PLUGIN / "wheels").glob("*.whl")]
    assert any(f"-{dku_cli.__version__}-" in n for n in names), (
        f"bundled wheel {names} != current version {dku_cli.__version__}; "
        "run `make bundle` in dataiku-mcp/"
    )


def test_shipped_manifest_versions_track_package():
    import dku_cli

    for manifest in (MANIFEST, CODEX_MANIFEST, BUNDLE_MANIFEST):
        version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
        assert version == dku_cli.__version__, (
            f"{manifest.relative_to(REPO)} version {version} != "
            f"package {dku_cli.__version__}"
        )

    marketplace_version = json.loads(MARKETPLACE.read_text(encoding="utf-8"))[
        "metadata"
    ]["version"]
    assert marketplace_version == dku_cli.__version__


def test_bundled_wheel_contains_current_sources():
    wheels = sorted((PLUGIN / "wheels").glob("*.whl"))
    assert wheels, "run `make plugin` to vendor the wheel"
    wheel = wheels[-1]

    src_root = REPO / "src" / "dku_cli"
    sources = sorted(
        p for p in src_root.rglob("*") if p.is_file() and "__pycache__" not in p.parts
    )
    assert sources, "no dku_cli sources found"

    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        for source in sources:
            wheel_path = f"dku_cli/{source.relative_to(src_root).as_posix()}"
            assert wheel_path in names, (
                f"{wheel_path} missing from {wheel.name}; run `make plugin`"
            )
            assert zf.read(wheel_path) == source.read_bytes(), (
                f"{wheel_path} in {wheel.name} is stale; run `make plugin`"
            )


def test_semantic_release_commits_generated_plugin_assets():
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    semantic = config["tool"]["semantic_release"]

    assert semantic["build_command"] == "make plugin"
    assert set(semantic["assets"]) >= {
        ".claude-plugin/marketplace.json",
        "dataiku-mcp/.claude-plugin/plugin.json",
        "dataiku-mcp/.codex-plugin/plugin.json",
        "dataiku-mcp-bundle/manifest.json",
        "dataiku-mcp/wheels",
    }


def test_release_workflow_runs_semantic_release_build_hook():
    workflow = yaml.safe_load(
        (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["release"]["steps"]
    semantic_step = next(step for step in steps if step.get("id") == "semantic")
    run_command = semantic_step["run"]

    assert "uses" not in semantic_step
    assert "uvx --from python-semantic-release semantic-release" in run_command
    assert "--no-build" not in run_command


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

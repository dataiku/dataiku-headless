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

"""The HTTP plugin renderer must leave the stdio source untouched."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_http_plugin.py"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_renders_http_plugin_with_http_only_setup_skill(tmp_path):
    output = tmp_path / "dataiku-headless-http"
    endpoint = "https://mcp.customer.example/mcp"
    source_mcp = (ROOT / ".mcp.json").read_text(encoding="utf-8")
    source_codex = _json(ROOT / ".codex-plugin" / "plugin.json")
    source_claude = _json(ROOT / ".claude-plugin" / "plugin.json")

    result = _run("--url", endpoint, "--output", str(output))

    assert result.returncode == 0, result.stderr
    assert _json(output / ".mcp.json")["mcpServers"]["dataiku"] == {
        "type": "http",
        "url": endpoint,
    }
    assert _json(output / ".claude-plugin" / "plugin.json")["mcpServers"][
        "dataiku"
    ] == {"type": "http", "url": endpoint}
    assert _json(output / ".codex-plugin" / "plugin.json")["name"] == (
        "dataiku-headless-http"
    )
    assert (
        _json(output / ".claude-plugin" / "marketplace.json")["plugins"][0]["name"]
        == "dataiku-headless-http"
    )
    rendered_codex = _json(output / ".codex-plugin" / "plugin.json")
    rendered_claude = _json(output / ".claude-plugin" / "plugin.json")
    assert rendered_codex["version"] == source_codex["version"]
    assert rendered_codex["description"] == source_codex["description"]
    assert rendered_claude["version"] == source_claude["version"]
    assert rendered_claude["description"] == source_claude["description"]

    setup = (output / "skills" / "dataiku-headless-setup" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "ask whether the user wants to authenticate now" in setup
    assert "codex mcp login dataiku" in setup
    assert "claude mcp login dataiku" in setup
    assert "retry `list_instances`" in setup
    assert "uv" not in setup
    assert "API key" not in setup
    assert "Never call `configure_instance` or `delete_instance`" in setup
    assert not (output / "skills" / "dataiku-headless-setup" / "references").exists()
    assert (ROOT / ".mcp.json").read_text(encoding="utf-8") == source_mcp


def test_renders_zip_with_one_plugin_root(tmp_path):
    output = tmp_path / "dataiku-headless-http"

    result = _run(
        "--url",
        "https://mcp.customer.example/mcp",
        "--output",
        str(output),
        "--zip",
    )

    assert result.returncode == 0, result.stderr
    archive = output.with_suffix(".zip")
    assert archive.is_file()
    assert not output.exists()
    with zipfile.ZipFile(archive) as bundle:
        assert "dataiku-headless-http/.mcp.json" in bundle.namelist()
        assert "dataiku-headless-http/skills/dataiku-headless-setup/SKILL.md" in (
            bundle.namelist()
        )


def test_rejects_invalid_url_and_existing_artifact(tmp_path):
    output = tmp_path / "dataiku-headless-http"

    invalid = _run("--url", "http://mcp.customer.example/mcp", "--output", str(output))
    assert invalid.returncode == 2
    assert "absolute HTTPS URL" in invalid.stderr
    assert not output.exists()

    output.mkdir()
    marker = output / "preserve"
    marker.write_text("keep", encoding="utf-8")
    existing = _run(
        "--url", "https://mcp.customer.example/mcp", "--output", str(output)
    )
    assert existing.returncode == 2
    assert "already exists" in existing.stderr
    assert marker.read_text(encoding="utf-8") == "keep"

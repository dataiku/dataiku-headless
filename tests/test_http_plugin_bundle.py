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

"""Customer HTTP plugin bundles are portable and contain no server secrets."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_http_plugin.py"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_builds_codex_and_claude_marketplace_with_shared_skills(tmp_path):
    output = tmp_path / "customer-marketplace"
    endpoint = "https://mcp.customer.example/mcp"

    result = _run("--interactive-oauth-url", endpoint, "--output", str(output))

    assert result.returncode == 0, result.stderr
    plugin = output / "plugins" / "dataiku-headless-http"
    assert _json(plugin / "mcp.json")["mcpServers"]["dataiku"] == {
        "type": "streamable-http",
        "url": endpoint,
    }
    assert _json(plugin / ".claude-plugin" / "plugin.json")["mcpServers"][
        "dataiku"
    ] == {"type": "http", "url": endpoint}
    assert (plugin / "skills" / "dataiku-headless" / "SKILL.md").is_file()
    assert (plugin / "skills" / "dataiku-headless-setup" / "SKILL.md").is_file()

    codex_entry = _json(output / ".agents" / "plugins" / "marketplace.json")["plugins"][
        0
    ]
    assert _json(output / ".agents" / "plugins" / "marketplace.json")["name"] == (
        "dataiku-http"
    )
    assert codex_entry["source"]["path"] == ("./plugins/dataiku-headless-http")
    assert codex_entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert (
        _json(output / ".claude-plugin" / "marketplace.json")["plugins"][0]["source"]
        == "./plugins/dataiku-headless-http"
    )


def test_derives_endpoint_without_copying_http_config_secrets(tmp_path):
    config = tmp_path / "http-config.json"
    output = tmp_path / "customer-marketplace"
    secret = "do-not-copy-this-secret"
    config.write_text(
        json.dumps(
            {
                "server": {
                    "public_url": "https://mcp.customer.example/",
                    "path": "/dataiku/mcp",
                },
                "auth": {
                    "provider": "entra",
                    "interactive_login": True,
                    "client_secret": secret,
                },
            }
        ),
        encoding="utf-8",
    )

    result = _run("--http-config", str(config), "--output", str(output))

    assert result.returncode == 0, result.stderr
    payload = (output / "plugins" / "dataiku-headless-http" / "mcp.json").read_text(
        encoding="utf-8"
    )
    assert "https://mcp.customer.example/dataiku/mcp" in payload
    assert secret not in "".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file()
    )


def test_rejects_direct_bearer_config(tmp_path):
    config = tmp_path / "http-config.json"
    output = tmp_path / "customer-marketplace"
    config.write_text(
        json.dumps(
            {
                "server": {
                    "public_url": "https://mcp.customer.example",
                    "path": "/mcp",
                },
                "auth": {"provider": "entra"},
            }
        ),
        encoding="utf-8",
    )

    result = _run("--http-config", str(config), "--output", str(output))

    assert result.returncode == 2
    assert "requires auth.interactive_login" in result.stderr
    assert "direct bearer" in result.stderr
    assert not output.exists()


def test_rejects_insecure_url_and_existing_output(tmp_path):
    output = tmp_path / "customer-marketplace"

    insecure = _run(
        "--interactive-oauth-url",
        "http://mcp.customer.example/mcp",
        "--output",
        str(output),
    )
    assert insecure.returncode == 2
    assert "absolute HTTPS URL" in insecure.stderr
    assert not output.exists()

    output.mkdir()
    marker = output / "keep"
    marker.write_text("preserve", encoding="utf-8")
    existing = _run(
        "--interactive-oauth-url",
        "https://mcp.customer.example/mcp",
        "--output",
        str(output),
    )
    assert existing.returncode == 2
    assert "already exists" in existing.stderr
    assert marker.read_text(encoding="utf-8") == "preserve"

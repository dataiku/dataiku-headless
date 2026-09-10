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

"""Build a customer-specific remote Dataiku Headless plugin marketplace."""

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _validate_identifier(value: str, description: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(
            f"{description} must contain only letters, numbers, hyphens, "
            "underscores, or dot-separated segments."
        )
    return value


def _validate_endpoint(value: str) -> str:
    endpoint = value.strip().rstrip("/")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("The MCP endpoint must be an absolute HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("The MCP endpoint must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("The MCP endpoint must not contain a query or fragment.")
    return endpoint


def _interactive_endpoint_from_config(path: Path) -> str:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        server = document["server"]
        public_url = server["public_url"]
        mcp_path = server["path"]
        auth = document["auth"]
        provider = auth["provider"]
        interactive_login = auth.get("interactive_login")
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as err:
        raise ValueError(
            "Could not read server.public_url, server.path, and auth.provider "
            f"from '{path}'."
        ) from err
    if not isinstance(public_url, str) or not isinstance(mcp_path, str):
        raise ValueError("server.public_url and server.path must be strings.")
    if provider == "entra":
        interactive_enabled = interactive_login is True
    elif provider == "generic_oidc":
        interactive_enabled = isinstance(interactive_login, dict)
    else:
        raise ValueError(f"Unsupported auth.provider in '{path}': {provider!r}.")
    if not interactive_enabled:
        raise ValueError(
            "Customer plugin generation requires auth.interactive_login. "
            "Use managed MCP configuration for direct bearer deployments."
        )
    return _validate_endpoint(f"{public_url.rstrip('/')}/{mcp_path.lstrip('/')}")


def _version() -> str:
    manifest = json.loads(
        (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    return manifest["version"]


def _copy_skills(destination: Path) -> None:
    shutil.copytree(
        ROOT / "skills",
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def _bundle_readme(
    *, endpoint: str, marketplace_name: str, plugin_name: str, display_name: str
) -> str:
    return f"""# {display_name}

This customer-specific marketplace bundles the Dataiku Headless skills with the
remote MCP endpoint:

`{endpoint}`

It is intended for a server with interactive OAuth enabled. It does not contain
a local server, Dataiku credentials, OAuth secrets, or the deployment's HTTP
configuration.

## Publish for Codex

Publish this whole directory as a private GitHub repository. A ChatGPT workspace
administrator can import it from **Admin > Plugins**, then set `{plugin_name}` to
Available or Installed for the appropriate roles. Workspace-imported plugins that
contain MCP servers run in the Codex app on ChatGPT desktop only.

For Codex CLI, an administrator must add the marketplace through managed or system
configuration. Users can then install the plugin from `/plugins`, or receive it
automatically, and complete interactive OAuth when prompted. Codex plugins are not
available in the IDE extension; distribute the MCP configuration and skills there
instead.

## Publish for Claude Code

Publish this whole directory as a private GitHub repository and register it as
the `{marketplace_name}` marketplace in managed Claude Code settings. Enable
`{plugin_name}@{marketplace_name}` for the appropriate users. Claude Desktop
users can then install it from **Add plugin**, or receive it through managed
settings, and complete OAuth when prompted.

This bundle is not suitable for direct bearer authentication. For clients that
obtain tokens themselves, distribute the MCP endpoint, token-provider configuration,
and skills through managed client configuration.

Keep the local `dataiku-headless` stdio plugin disabled for these users. Only
one Dataiku MCP server should be enabled in a client.
"""


def build_marketplace(
    output: Path,
    *,
    endpoint: str,
    plugin_name: str,
    marketplace_name: str,
    display_name: str,
) -> Path:
    """Create a complete Codex and Claude marketplace without overwriting files."""
    endpoint = _validate_endpoint(endpoint)
    plugin_name = _validate_identifier(plugin_name, "Plugin name")
    marketplace_name = _validate_identifier(marketplace_name, "Marketplace name")
    if not display_name.strip():
        raise ValueError("Display name must not be empty.")

    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError(f"Output path already exists: '{output}'.")
    output.parent.mkdir(parents=True, exist_ok=True)

    version = _version()
    description = (
        "Connect to the organization's Dataiku Headless service over HTTPS and "
        "use shared skills to inspect and build Dataiku projects."
    )
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent)
    )
    bundle = temporary_root / "bundle"
    plugin = bundle / "plugins" / plugin_name

    try:
        plugin.mkdir(parents=True)
        _copy_skills(plugin / "skills")
        shutil.copy2(ROOT / "LICENSE", plugin / "LICENSE")

        _write_json(
            plugin / "plugin.json",
            {
                "$schema": PLUGIN_SCHEMA,
                "name": plugin_name,
                "version": version,
                "description": description,
                "author": {"name": "Dataiku", "url": "https://www.dataiku.com/"},
                "homepage": "https://github.com/dataiku/dataiku-headless",
                "repository": "https://github.com/dataiku/dataiku-headless",
                "license": "Apache-2.0",
                "keywords": ["dataiku", "cobuild"],
            },
        )
        _write_json(
            plugin / "mcp.json",
            {
                "$schema": MCP_SCHEMA,
                "mcpServers": {"dataiku": {"type": "streamable-http", "url": endpoint}},
            },
        )
        _write_json(
            plugin / ".codex-plugin" / "plugin.json",
            {
                "name": plugin_name,
                "version": version,
                "description": description,
                "author": {"name": "Dataiku", "url": "https://www.dataiku.com/"},
                "homepage": "https://github.com/dataiku/dataiku-headless",
                "repository": "https://github.com/dataiku/dataiku-headless",
                "license": "Apache-2.0",
                "keywords": ["dataiku", "cobuild"],
                "interface": {
                    "displayName": display_name,
                    "shortDescription": "Connect to your organization's Dataiku service",
                    "longDescription": description,
                    "developerName": "Dataiku",
                    "category": "developer-tools",
                    "capabilities": ["Interactive", "Write"],
                    "websiteURL": "https://github.com/dataiku/dataiku-headless",
                    "defaultPrompt": [
                        "Set up Dataiku Headless",
                        "How many projects are in this Dataiku instance?",
                    ],
                    "brandColor": "#00A6A6",
                },
            },
        )
        _write_json(
            plugin / ".claude-plugin" / "plugin.json",
            {
                "name": plugin_name,
                "displayName": display_name,
                "version": version,
                "description": description,
                "author": {"name": "Dataiku", "url": "https://www.dataiku.com/"},
                "homepage": "https://github.com/dataiku/dataiku-headless",
                "repository": "https://github.com/dataiku/dataiku-headless",
                "license": "Apache-2.0",
                "keywords": ["dataiku", "cobuild"],
                "mcpServers": {"dataiku": {"type": "http", "url": endpoint}},
            },
        )

        _write_json(
            bundle / ".agents" / "plugins" / "marketplace.json",
            {
                "name": marketplace_name,
                "interface": {"displayName": f"{display_name} Plugins"},
                "plugins": [
                    {
                        "name": plugin_name,
                        "source": {
                            "source": "local",
                            "path": f"./plugins/{plugin_name}",
                        },
                        "policy": {
                            "installation": "AVAILABLE",
                            "authentication": "ON_INSTALL",
                        },
                        "category": "developer-tools",
                    }
                ],
            },
        )
        _write_json(
            bundle / ".claude-plugin" / "marketplace.json",
            {
                "name": marketplace_name,
                "owner": {"name": "Dataiku"},
                "description": f"Customer-managed {display_name} plugins.",
                "plugins": [
                    {
                        "name": plugin_name,
                        "source": f"./plugins/{plugin_name}",
                        "description": description,
                        "category": "developer-tools",
                    }
                ],
            },
        )
        (bundle / "README.md").write_text(
            _bundle_readme(
                endpoint=endpoint,
                marketplace_name=marketplace_name,
                plugin_name=plugin_name,
                display_name=display_name,
            ),
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "LICENSE", bundle / "LICENSE")
        bundle.rename(output)
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    else:
        temporary_root.rmdir()
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a customer-specific plugin marketplace containing the Dataiku "
            "Headless skills and a fixed Streamable HTTP endpoint."
        )
    )
    endpoint = parser.add_mutually_exclusive_group(required=True)
    endpoint.add_argument(
        "--interactive-oauth-url",
        help=(
            "Externally visible HTTPS MCP endpoint for a server already "
            "configured for interactive OAuth."
        ),
    )
    endpoint.add_argument(
        "--http-config",
        type=Path,
        help=(
            "HTTP server config; verifies interactive login and derives the endpoint "
            "from server.public_url and path."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plugin-name", default="dataiku-headless-http")
    parser.add_argument("--marketplace-name", default="dataiku-http")
    parser.add_argument("--display-name", default="Dataiku Headless")
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        endpoint = (
            _interactive_endpoint_from_config(args.http_config)
            if args.http_config is not None
            else args.interactive_oauth_url
        )
        output = build_marketplace(
            args.output,
            endpoint=endpoint,
            plugin_name=args.plugin_name,
            marketplace_name=args.marketplace_name,
            display_name=args.display_name,
        )
    except ValueError as err:
        parser.error(str(err))
    print(f"Built customer plugin marketplace at {output}")


if __name__ == "__main__":
    main()

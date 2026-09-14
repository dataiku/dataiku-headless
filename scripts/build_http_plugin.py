#!/usr/bin/env python3

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

"""Render the HTTP Dataiku Headless plugin variant from the stdio source tree."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "scripts" / "http_plugin_assets"
PLUGIN_NAME = "dataiku-headless-http"
COPY_PATHS = (
    "LICENSE",
    "skills",
    "docs/assets",
    ".mcp.json",
    ".codex-plugin",
    ".claude-plugin",
)


def validate_url(value: str) -> str:
    """Return a safe, absolute Streamable HTTP endpoint."""
    endpoint = value.strip().rstrip("/")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("The MCP URL must be an absolute HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("The MCP URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("The MCP URL must not contain a query or fragment.")
    return endpoint


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def update_manifests(destination: Path, *, endpoint: str) -> None:
    """Apply the HTTP-specific differences to copied source manifests."""
    mcp = read_json(destination / ".mcp.json")
    mcp["mcpServers"]["dataiku"] = {"type": "http", "url": endpoint}
    write_json(destination / ".mcp.json", mcp)

    codex = read_json(destination / ".codex-plugin" / "plugin.json")
    codex["name"] = PLUGIN_NAME
    codex["interface"]["displayName"] = "Dataiku Headless (HTTP)"
    write_json(destination / ".codex-plugin" / "plugin.json", codex)

    claude = read_json(destination / ".claude-plugin" / "plugin.json")
    claude["name"] = PLUGIN_NAME
    claude["displayName"] = "Dataiku Headless (HTTP)"
    claude["mcpServers"]["dataiku"] = {"type": "http", "url": endpoint}
    write_json(destination / ".claude-plugin" / "plugin.json", claude)

    marketplace = read_json(destination / ".claude-plugin" / "marketplace.json")
    marketplace["plugins"][0]["name"] = PLUGIN_NAME
    write_json(destination / ".claude-plugin" / "marketplace.json", marketplace)


def populate_plugin(destination: Path, *, endpoint: str) -> None:
    """Copy shared plugin content and overlay the HTTP-specific assets."""
    destination.mkdir(parents=True)
    for relative_path in COPY_PATHS:
        source = ROOT / relative_path
        target = destination / relative_path
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    shutil.rmtree(destination / "skills" / "dataiku-headless-setup")
    shutil.copytree(
        ASSETS / "skills" / "dataiku-headless-setup",
        destination / "skills" / "dataiku-headless-setup",
    )

    update_manifests(destination, endpoint=endpoint)


def render(output: Path, *, endpoint: str, archive: bool) -> Path:
    """Render an HTTP plugin directory, or a ZIP containing that directory."""
    endpoint = validate_url(endpoint)
    output = output.expanduser().resolve()
    artifact = output.with_suffix(".zip") if archive else output
    if artifact.exists():
        raise ValueError(f"Output path already exists: '{artifact}'.")
    if output.exists() and archive:
        raise ValueError(f"Output path already exists: '{output}'.")

    artifact.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{output.name}-", dir=artifact.parent)
    )
    staged_plugin = temporary_root / PLUGIN_NAME
    try:
        populate_plugin(staged_plugin, endpoint=endpoint)
        if archive:
            staged_archive = shutil.make_archive(
                str(temporary_root / output.name), "zip", temporary_root, PLUGIN_NAME
            )
            Path(staged_archive).rename(artifact)
        else:
            staged_plugin.rename(artifact)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    return artifact


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render the Dataiku Headless HTTP plugin variant."
    )
    parser.add_argument(
        "--url", required=True, help="HTTPS Streamable HTTP MCP endpoint."
    )
    parser.add_argument("--output", type=Path, required=True, help="Artifact path.")
    parser.add_argument(
        "--zip", action="store_true", help="Write <output>.zip instead of a directory."
    )
    return parser


def main() -> None:
    args = parser().parse_args()
    try:
        artifact = render(args.output, endpoint=args.url, archive=args.zip)
    except ValueError as error:
        parser().error(str(error))
    print(f"Rendered {PLUGIN_NAME} at {artifact}")


if __name__ == "__main__":
    main()

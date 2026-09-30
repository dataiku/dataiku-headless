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

"""Validate release versions and extract the matching changelog section."""

import argparse
import json
from pathlib import Path
import re

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 test environments
    import tomli as tomllib


def validate(root: Path) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text())
    version = project["project"]["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError(f"Expected a stable release version, got {version}")
    required = {
        f".{name}-plugin/plugin.json"
        for name in ("claude", "codex", "cortex", "cursor")
    }
    for relative in required:
        if not (root / relative).is_file():
            raise ValueError(f"Missing release manifest: {relative}")
    manifests = sorted(root.glob(".*-plugin/plugin.json"))
    if (root / "plugin.json").exists():
        manifests.append(root / "plugin.json")
    configured = project["tool"]["commitizen"]["version_files"]
    for path in manifests:
        relative = path.relative_to(root).as_posix()
        if relative not in [entry.split(":", 1)[0] for entry in configured]:
            raise ValueError(f"{relative} is missing from Commitizen version_files")
        if json.loads(path.read_text())["version"] != version:
            raise ValueError(f"{relative} must carry version {version}")
    marketplace = json.loads((root / ".claude-plugin/marketplace.json").read_text())
    for entry in marketplace["plugins"]:
        if entry["name"] == project["project"]["name"]:
            if entry.get("version", version) != version:
                raise ValueError("Marketplace version differs from project version")
    return version


def release_notes(root: Path, version: str) -> str:
    changelog = (root / "CHANGELOG.md").read_text()
    sections = re.split(r"(?m)(?=^## )", changelog)
    for section in sections:
        if re.match(rf"^## v{re.escape(version)} \(\d{{4}}-\d{{2}}-\d{{2}}\)", section):
            return section.strip() + "\n"
    raise ValueError(f"No changelog section for v{version}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    version = validate(root)
    print(
        release_notes(root, version) if args.notes else version,
        end="" if args.notes else "\n",
    )

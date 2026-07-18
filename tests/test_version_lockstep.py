"""Release-version lockstep guard.

A single source of truth drives every version string in the repo: `[project].version`
in pyproject.toml, kept in sync by `cz bump` (`version_files` + `tag_format`). This
test asserts that source agrees with the three plugin manifests and the top heading
in CHANGELOG.md, so a hand-edit or a half-finished bump fails here rather than
shipping a mismatched release. It reads files only — no network, no live DSS.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on the 3.10 floor
    tomllib = None

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFESTS = (
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
)


def _project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(text)["project"]["version"]
    # 3.10 fallback (no tomllib, no tomli dependency): pull [project].version.
    section = re.search(r"^\[project\]\s*$(.*?)^\[", text, re.MULTILINE | re.DOTALL)
    body = section.group(1) if section else text
    match = re.search(r'^version\s*=\s*"([^"]+)"', body, re.MULTILINE)
    assert match, "could not locate [project].version in pyproject.toml"
    return match.group(1)


def test_plugin_manifests_match_project_version():
    version = _project_version()
    for manifest in PLUGIN_MANIFESTS:
        data = json.loads((ROOT / manifest).read_text(encoding="utf-8"))
        assert data["version"] == version, (
            f"{manifest} version {data['version']!r} != [project].version "
            f"{version!r} — run `uv run cz bump` instead of hand-editing versions."
        )


def test_changelog_top_heading_matches_project_version():
    version = _project_version()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^##\s+v(\S+)", changelog, re.MULTILINE)
    assert match, "no `## vX.Y.Z` release heading found in CHANGELOG.md"
    assert match.group(1) == version, (
        f"CHANGELOG.md top release is v{match.group(1)} but [project].version is "
        f"{version} — regenerate the changelog with `uv run cz bump`."
    )

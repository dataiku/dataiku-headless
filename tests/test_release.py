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

"""Release validation and publishing against disposable local git repositories."""

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HELPERS = runpy.run_path(str(ROOT / "scripts/check_release.py"))


@pytest.fixture
def release_tree(tmp_path):
    for name in ("pyproject.toml", "CHANGELOG.md"):
        shutil.copy(ROOT / name, tmp_path / name)
    for path in ROOT.glob(".*-plugin/*.json"):
        target = tmp_path / path.relative_to(ROOT)
        target.parent.mkdir(exist_ok=True)
        shutil.copy(path, target)
    return tmp_path


def test_current_release_and_notes(release_tree):
    version = HELPERS["validate"](release_tree)
    notes = HELPERS["release_notes"](release_tree, version)
    assert notes.startswith(f"## v{version} ")
    assert notes.count("\n## ") == 0


@pytest.mark.parametrize("name", ["claude", "codex", "cortex", "cursor"])
def test_reject_manifest_version_drift(release_tree, name):
    path = release_tree / f".{name}-plugin/plugin.json"
    manifest = json.loads(path.read_text())
    manifest["version"] = "0.0.1"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="must carry version"):
        HELPERS["validate"](release_tree)


def test_reject_missing_bump_configuration(release_tree):
    path = release_tree / "pyproject.toml"
    path.write_text(path.read_text().replace('    ".cursor-plugin/plugin.json",\n', ""))
    with pytest.raises(ValueError, match="version_files"):
        HELPERS["validate"](release_tree)


def test_reject_marketplace_pin(release_tree):
    path = release_tree / ".claude-plugin/marketplace.json"
    data = json.loads(path.read_text())
    data["plugins"][0]["version"] = "0.0.1"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Marketplace"):
        HELPERS["validate"](release_tree)


def test_reject_missing_changelog(release_tree):
    with pytest.raises(ValueError, match="No changelog section"):
        HELPERS["release_notes"](release_tree, "999.0.0")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def init_repo(root):
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Release Test")
    git(root, "config", "user.email", "release@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "tag.gpgsign", "false")
    git(root, "config", "core.hooksPath", "/dev/null")
    git(root, "add", ".")
    git(root, "commit", "-m", "chore: baseline")


def test_commitizen_updates_all_manifests_without_publishing(release_tree):
    init_repo(release_tree)
    current = HELPERS["validate"](release_tree)
    git(release_tree, "tag", f"v{current}")
    git(release_tree, "commit", "--allow-empty", "-m", "feat: next release")
    result = subprocess.run(
        [shutil.which("cz"), "bump", "--version-files-only", "--changelog"],
        cwd=release_tree,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    version = HELPERS["validate"](release_tree)
    assert version != current
    assert HELPERS["release_notes"](release_tree, version)
    assert git(release_tree, "tag", "--list") == f"v{current}"


@pytest.mark.parametrize("collision", [False, True])
def test_publish_retry_and_tag_collision(tmp_path, collision):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file").write_text("release")
    init_repo(repo)
    sha = git(repo, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    git(repo, "remote", "add", "origin", str(remote))
    if collision:
        git(repo, "tag", "dataiku-headless--v1.2.3")
        git(repo, "commit", "--allow-empty", "-m", "fix: another commit")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        '#!/bin/sh\nif [ "$2" = list ]; then echo "[]"; else echo "release operation"; fi\n'
    )
    gh.chmod(0o755)
    workflow = yaml.safe_load((ROOT / ".github/workflows/bump.yml").read_text())
    script = workflow["jobs"]["publish"]["steps"][-1]["run"]
    env = dict(
        os.environ,
        VERSION="1.2.3",
        RUNNER_TEMP=str(tmp_path),
        GITHUB_STEP_SUMMARY=str(tmp_path / "summary"),
        PATH=f"{bin_dir}:{os.environ['PATH']}",
    )
    for _ in range(2):
        result = subprocess.run(
            ["bash", "-c", script], cwd=repo, env=env, capture_output=True, text=True
        )
        if collision:
            assert result.returncode != 0
            assert "points to another commit" in result.stdout
            assert git(remote, "tag", "--list") == ""
            assert git(repo, "tag", "--list", "v1.2.3") == ""
        else:
            assert result.returncode == 0, result.stderr
            for tag in ("v1.2.3", "dataiku-headless--v1.2.3"):
                assert git(remote, "rev-parse", f"{tag}^{{commit}}") == sha

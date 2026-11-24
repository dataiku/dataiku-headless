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
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HELPERS = runpy.run_path(str(ROOT / "scripts/check_release.py"))


@pytest.fixture
def release_tree(tmp_path):
    for name in ("pyproject.toml", "CHANGELOG.md"):
        shutil.copy(ROOT / name, tmp_path / name)
    for path in [*ROOT.glob(".*-plugin/*.json"), *ROOT.glob(".github/plugin/*.json")]:
        target = tmp_path / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, target)
    return tmp_path


def test_current_release_and_notes(release_tree):
    version = HELPERS["validate"](release_tree)
    notes = HELPERS["release_notes"](release_tree, version)
    assert notes.startswith(f"## v{version} ")
    assert notes.count("\n## ") == 0


@pytest.mark.parametrize(
    "directory",
    [
        ".antigravity-plugin",
        ".claude-plugin",
        ".codex-plugin",
        ".cortex-plugin",
        ".cursor-plugin",
        ".github/plugin",
    ],
)
def test_reject_manifest_version_drift(release_tree, directory):
    path = release_tree / directory / "plugin.json"
    manifest = json.loads(path.read_text())
    manifest["version"] = "0.0.1"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="must carry version"):
        HELPERS["validate"](release_tree)


@pytest.mark.parametrize(
    "directory", [".antigravity-plugin", ".cursor-plugin", ".github/plugin"]
)
def test_reject_missing_bump_configuration(release_tree, directory):
    path = release_tree / "pyproject.toml"
    path.write_text(path.read_text().replace(f'    "{directory}/plugin.json",\n', ""))
    with pytest.raises(ValueError, match="version_files"):
        HELPERS["validate"](release_tree)


@pytest.mark.parametrize("directory", [".claude-plugin", ".github/plugin"])
def test_reject_marketplace_pin(release_tree, directory):
    path = release_tree / directory / "marketplace.json"
    data = json.loads(path.read_text())
    data["plugins"][0]["version"] = "0.0.1"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Marketplace"):
        HELPERS["validate"](release_tree)


def test_reject_missing_github_manifest(release_tree):
    (release_tree / ".github/plugin/plugin.json").unlink()
    with pytest.raises(ValueError, match="Missing release manifest"):
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
    major, minor, _ = map(int, current.split("."))
    target = f"{major}.{minor + 1}.0"
    branch = f"release/{target}"
    git(release_tree, "switch", "-c", branch)
    assert HELPERS["validate_target_branch"](branch, current) == target
    result = subprocess.run(
        [shutil.which("cz"), "bump", target, "--version-files-only", "--changelog"],
        cwd=release_tree,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    version = HELPERS["validate"](release_tree)
    assert version == target
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


@pytest.mark.parametrize(
    "branch",
    ["main", "release/0.7", "release/0.7.0", "release/0.6.9", "release/0.8.0;echo bad"],
)
def test_reject_invalid_or_already_finalized_target(branch):
    with pytest.raises(ValueError):
        HELPERS["validate_target_branch"](branch, "0.7.0")


@pytest.mark.parametrize(
    "branch,repo,accepted",
    [
        ("release/0.8.0", "org/project", True),
        ("release/0.7.1", "org/project", True),
        ("feat/tool", "org/project", False),
        ("release/0.8.0", "fork/project", False),
        ("release/0.8", "org/project", False),
    ],
)
def test_main_source_policy(branch, repo, accepted):
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/release-source.yml").read_text()
    )
    script = workflow["jobs"]["release-source"]["steps"][0]["run"]
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=dict(
            os.environ, HEAD_BRANCH=branch, HEAD_REPO=repo, BASE_REPO="org/project"
        ),
    )
    assert (result.returncode == 0) == accepted


@pytest.mark.parametrize("mode", ["merge", "squash", "wrong-head", "main-only-change"])
def test_publish_requires_release_merge_commit(tmp_path, mode):
    (tmp_path / "baseline").write_text("baseline")
    init_repo(tmp_path)
    git(tmp_path, "switch", "-c", "release/0.8.0")
    (tmp_path / "feature").write_text("feature")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: release feature")
    release_head = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "switch", "main")
    if mode == "main-only-change":
        (tmp_path / "extra").write_text("not reviewed in release branch")
        git(tmp_path, "add", ".")
        git(tmp_path, "commit", "-m", "fix: main-only change")
    if mode == "squash":
        git(tmp_path, "merge", "--squash", "release/0.8.0")
        git(tmp_path, "commit", "-m", "bump: squash release")
    else:
        git(tmp_path, "merge", "--no-ff", "release/0.8.0", "-m", "Merge release")
    if mode == "wrong-head":
        release_head = git(tmp_path, "rev-parse", "HEAD^1")
    if mode == "merge":
        HELPERS["validate_merge"](tmp_path, release_head)
    else:
        with pytest.raises(ValueError):
            HELPERS["validate_merge"](tmp_path, release_head)


def test_workflows_cover_release_targets_and_trusted_source_check():
    for name in ("ci.yml", "pr-title.yml"):
        # BaseLoader preserves YAML's 'on' as a string rather than a boolean.
        workflow = yaml.load(
            (ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader
        )
        assert workflow["on"]["pull_request"]["branches"] == ["main", "release/*"]
    workflow = yaml.load(
        (ROOT / ".github/workflows/release-source.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    assert workflow["on"]["pull_request_target"]["branches"] == ["main"]
    assert workflow["permissions"] == {}
    assert all(
        "uses" not in step for step in workflow["jobs"]["release-source"]["steps"]
    )


@pytest.mark.parametrize(
    "mode",
    [
        "automatic",
        "manual",
        "no-release",
        "fork",
        "wrong-merge",
        "ambiguous",
        "failed-ci",
        "wrong-ci-sha",
        "wrong-ci-branch",
        "wrong-ci-repo",
    ],
)
def test_resolve_publication_target(tmp_path, mode):
    """Run the actual resolver with API fixtures; only verified commits get outputs."""
    pr = {
        "number": 42,
        "merged": True,
        "merged_at": "2026-11-24T12:00:00Z",
        "base": {"ref": "main"},
        "head": {
            "ref": "release/1.2.3",
            "sha": "release-head",
            "repo": {"full_name": "org/project"},
        },
        "merge_commit_sha": "merge-sha",
    }
    if mode == "fork":
        pr["head"]["repo"]["full_name"] = "fork/project"
    candidates = [] if mode == "no-release" else [pr]
    if mode == "ambiguous":
        candidates.append(pr)
    (tmp_path / "pulls-fixture.json").write_text(json.dumps([candidates]))
    if mode == "wrong-merge":
        pr["merge_commit_sha"] = "other-sha"
    (tmp_path / "pr-fixture.json").write_text(json.dumps(pr))
    ci = {
        "head_sha": "wrong" if mode == "wrong-ci-sha" else "merge-sha",
        "head_branch": "release/1.2.3" if mode == "wrong-ci-branch" else "main",
        "head_repository": {
            "full_name": "fork/project" if mode == "wrong-ci-repo" else "org/project"
        },
        "event": "push",
        "status": "completed",
        "conclusion": "failure" if mode == "failed-ci" else "success",
    }
    (tmp_path / "ci-fixture.json").write_text(json.dumps({"workflow_runs": [ci]}))
    gh = tmp_path / "gh"
    gh.write_text("""#!/bin/sh
case "$*" in
  *commits/*/pulls*) cat "$RUNNER_TEMP/pulls-fixture.json" ;;
  *pulls/42*) cat "$RUNNER_TEMP/pr-fixture.json" ;;
  *workflows/ci.yml/runs*) cat "$RUNNER_TEMP/ci-fixture.json" ;;
  *) exit 1 ;;
esac
""")
    gh.chmod(0o755)
    workflow = yaml.safe_load((ROOT / ".github/workflows/bump.yml").read_text())
    result = subprocess.run(
        ["bash", "-c", workflow["jobs"]["publish"]["steps"][0]["run"]],
        capture_output=True,
        text=True,
        env=dict(
            os.environ,
            GH_REPO="org/project",
            PR_NUMBER="42" if mode == "manual" else "",
            EVENT_NAME="workflow_dispatch" if mode == "manual" else "workflow_run",
            CI_SHA="merge-sha",
            RUNNER_TEMP=str(tmp_path),
            GITHUB_STEP_SUMMARY=str(tmp_path / "summary"),
            GITHUB_OUTPUT=str(tmp_path / "output"),
            PATH=f"{tmp_path}:{os.environ['PATH']}",
        ),
    )
    if mode in {"automatic", "manual"}:
        assert result.returncode == 0, result.stderr
        assert (
            tmp_path / "output"
        ).read_text() == "head_sha=release-head\nsha=merge-sha\nversion=1.2.3\n"
    else:
        assert not (tmp_path / "output").exists()
        assert (result.returncode == 0) == (mode in {"no-release", "fork"})


def test_automatic_publication_only_follows_trusted_main_push_ci():
    workflow = yaml.load(
        (ROOT / ".github/workflows/bump.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert workflow["on"]["workflow_run"] == {
        "workflows": ["CI"],
        "types": ["completed"],
        "branches": ["main"],
    }
    condition = workflow["jobs"]["publish"]["if"]
    for guard in (
        "github.event.workflow_run.conclusion == 'success'",
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.head_branch == 'main'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
    ):
        assert guard in condition
    for step in workflow["jobs"]["publish"]["steps"][1:]:
        assert step["if"] == "steps.target.outputs.sha != ''"


@pytest.fixture
def finalization_repo(release_tree, tmp_path, monkeypatch):
    # Exercise real uv locking without registry packages or a developer's cache.
    monkeypatch.setenv(
        "UV_CACHE_DIR", str(tmp_path.parent / f"{tmp_path.name}-uv-cache")
    )
    monkeypatch.setenv("UV_OFFLINE", "1")
    monkeypatch.setenv("UV_PYTHON", sys.executable)
    monkeypatch.setenv("UV_PYTHON_DOWNLOADS", "never")
    pyproject = release_tree / "pyproject.toml"
    settings = HELPERS["tomllib"].loads(pyproject.read_text())
    sections = {
        "project": {
            key: settings["project"][key]
            for key in ("name", "version", "requires-python")
        },
        "tool.commitizen": settings["tool"]["commitizen"],
    }
    pyproject.write_text(
        "\n".join(
            f"[{section}]\n"
            + "\n".join(f"{key} = {json.dumps(value)}" for key, value in values.items())
            + "\n"
            for section, values in sections.items()
        )
    )
    subprocess.run(["uv", "lock"], cwd=release_tree, check=True, capture_output=True)
    (release_tree / "runtime").mkdir()
    for name in ("run_mcp.py", "run_mcp.py.lock"):
        shutil.copy(ROOT / "runtime" / name, release_tree / "runtime" / name)
    init_repo(release_tree)
    baseline = HELPERS["validate"](release_tree)
    major, minor, _ = map(int, baseline.split("."))
    branch = f"release/{major}.{minor + 1}.0"
    git(release_tree, "tag", f"v{baseline}")
    git(release_tree, "branch", branch)
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    git(release_tree, "remote", "add", "origin", str(remote))
    git(release_tree, "push", "origin", "main", branch, "--tags")
    git(release_tree, "switch", "-c", "feat/final-feature")
    git(release_tree, "commit", "--allow-empty", "-m", "feat: final capability")
    return release_tree, branch


def run_finalization(repo, branch):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/finalize_release.py"), branch],
        cwd=repo,
        capture_output=True,
        text=True,
        env=dict(os.environ, UV_OFFLINE="1"),
    )


def test_local_finalization_refreshes_notes_without_publishing(finalization_repo):
    repo, branch = finalization_repo
    target = branch.removeprefix("release/")
    head = git(repo, "rev-parse", "HEAD")
    main = git(repo, "rev-parse", "origin/main")
    previous_notes = (repo / "CHANGELOG.md").read_text()
    result = run_finalization(repo, branch)
    assert result.returncode == 0, result.stdout + result.stderr
    assert HELPERS["validate"](repo) == target
    assert "final capability" in HELPERS["release_notes"](repo, target)
    assert (repo / "CHANGELOG.md").read_text().endswith(previous_notes)
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "rev-parse", "origin/main") == main
    assert git(repo, "rev-parse", f"origin/{branch}") == main
    assert git(repo, "tag", "--list", f"*v{target}") == ""
    assert git(repo, "branch", "--show-current") == "feat/final-feature"
    git(repo, "add", "-u")
    git(repo, "commit", "-m", f"bump: finalize {target}")
    git(repo, "commit", "--allow-empty", "-m", "fix: late correction")
    result = run_finalization(repo, branch)
    assert result.returncode == 0, result.stdout + result.stderr
    notes = HELPERS["release_notes"](repo, target)
    assert "late correction" in notes
    assert "final capability" in notes
    assert (repo / "CHANGELOG.md").read_text().count(f"## v{target} (") == 1
    assert (repo / "CHANGELOG.md").read_text().endswith(previous_notes)
    assert set(git(repo, "diff", "--name-only").splitlines()) == {"CHANGELOG.md"}


@pytest.mark.parametrize(
    "mode",
    [
        "dirty",
        "main",
        "release",
        "detached",
        "stale-main",
        "stale-release",
        "tag",
        "plugin-tag",
        "invalid-target",
    ],
)
def test_local_finalization_rejects_unsafe_state(finalization_repo, mode):
    repo, branch = finalization_repo
    target = branch.removeprefix("release/")
    if mode == "dirty":
        (repo / "untracked").write_text("preserve me")
    elif mode in {"main", "release"}:
        git(repo, "switch", "main" if mode == "main" else branch)
    elif mode == "detached":
        git(repo, "checkout", "--detach")
    elif mode in {"stale-main", "stale-release"}:
        git(repo, "switch", "main" if mode == "stale-main" else branch)
        git(repo, "commit", "--allow-empty", "-m", "fix: new upstream change")
        git(repo, "push", "origin", "HEAD")
        git(repo, "switch", "feat/final-feature")
    elif mode in {"tag", "plugin-tag"}:
        git(
            repo,
            "tag",
            f"v{target}" if mode == "tag" else f"dataiku-headless--v{target}",
        )
    elif mode == "invalid-target":
        branch = "release/1.2.3;echo unsafe"
    original = {
        name: (repo / name).read_bytes()
        for name in ("pyproject.toml", "CHANGELOG.md", "uv.lock")
    }
    result = run_finalization(repo, branch)
    assert result.returncode != 0
    assert "Finalization failed" in result.stderr
    for name, content in original.items():
        assert (repo / name).read_bytes() == content
    if mode == "dirty":
        assert (repo / "untracked").read_text() == "preserve me"


def test_release_workflow_only_publishes():
    workflow = yaml.load(
        (ROOT / ".github/workflows/bump.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert set(workflow["jobs"]) == {"publish"}
    assert set(workflow["on"]["workflow_dispatch"]["inputs"]) == {"release_pr"}
    assert workflow["jobs"]["publish"]["permissions"]["pull-requests"] == "read"

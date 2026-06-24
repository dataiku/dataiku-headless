"""Tests for git commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# --- status ---


def test_git_status(patch_client):
    result = runner.invoke(app, ["git", "status", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "master" in result.output


def test_git_status_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "status", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["currentBranch"] == "master"
    assert parsed["clean"] is True


# --- log ---


def test_git_log(patch_client):
    result = runner.invoke(app, ["git", "log", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "abc123de" in result.output
    assert "Initial commit" in result.output


def test_git_log_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "log", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "entries" in parsed
    assert len(parsed["entries"]) == 1


def test_git_log_with_count(patch_client):
    result = runner.invoke(app, ["git", "log", "--count", "5", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.log.assert_called_once_with(path=None, start_commit=None, count=5)


# --- diff ---


def test_git_diff(patch_client):
    result = runner.invoke(app, ["git", "diff", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "10" in result.output  # addedLines


def test_git_diff_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "diff", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["addedLines"] == 10
    assert parsed["removedLines"] == 5


# --- commit ---


def test_git_commit(patch_client):
    result = runner.invoke(
        app, ["git", "commit", "-m", "test message", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Committed" in result.output
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.commit.assert_called_once_with("test message")


# --- pull ---


def test_git_pull(patch_client):
    result = runner.invoke(app, ["git", "pull", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Pull complete" in result.output


def test_git_pull_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "pull", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["success"] is True


def test_git_pull_with_branch(patch_client):
    result = runner.invoke(
        app, ["git", "pull", "--branch", "feature/test", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.pull.assert_called_once_with(branch_name="feature/test")


# --- push ---


def test_git_push(patch_client):
    result = runner.invoke(app, ["git", "push", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Push complete" in result.output


def test_git_push_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "push", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["success"] is True


# --- fetch ---


def test_git_fetch(patch_client):
    result = runner.invoke(app, ["git", "fetch", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Fetch complete" in result.output


def test_git_fetch_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "fetch", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["success"] is True


# --- failure exit codes (a failed git action must exit non-zero in BOTH formats
#     so `dku git push && <next>` cannot chain past a failure) ---


def _git(patch_client):
    return patch_client.get_project("PROJ1").get_project_git()


def test_git_pull_failure_exits_nonzero(patch_client):
    _git(patch_client).pull.return_value = {"success": False, "output": "conflict"}
    result = runner.invoke(app, ["git", "pull", "--project", "PROJ1"])
    assert result.exit_code == 1
    assert "Pull failed" in result.output


def test_git_pull_failure_json_exits_nonzero(patch_client):
    _git(patch_client).pull.return_value = {"success": False, "output": "conflict"}
    result = runner.invoke(
        app, ["--format", "json", "git", "pull", "--project", "PROJ1"]
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["success"] is False


def test_git_push_failure_exits_nonzero(patch_client):
    _git(patch_client).push.return_value = {"success": False, "output": "rejected"}
    result = runner.invoke(app, ["git", "push", "--project", "PROJ1"])
    assert result.exit_code == 1
    assert "Push failed" in result.output


def test_git_push_failure_json_exits_nonzero(patch_client):
    _git(patch_client).push.return_value = {"success": False, "output": "rejected"}
    result = runner.invoke(
        app, ["--format", "json", "git", "push", "--project", "PROJ1"]
    )
    assert result.exit_code == 1


def test_git_fetch_failure_exits_nonzero(patch_client):
    _git(patch_client).fetch.return_value = {"success": False, "output": ""}
    result = runner.invoke(app, ["git", "fetch", "--project", "PROJ1"])
    assert result.exit_code == 1
    assert "Fetch failed" in result.output


def test_git_switch_failure_exits_nonzero(patch_client):
    _git(patch_client).switch.return_value = {"success": False, "output": "dirty tree"}
    result = runner.invoke(app, ["git", "switch", "main", "--project", "PROJ1"])
    assert result.exit_code == 1


# --- branches ---


def test_git_branches(patch_client):
    result = runner.invoke(app, ["git", "branches", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "master" in result.output
    assert "feature/test" in result.output


def test_git_branches_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "branches", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "master" in parsed
    assert "feature/test" in parsed


def test_git_branches_remote(patch_client):
    result = runner.invoke(app, ["git", "branches", "--remote", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.list_branches.assert_called_once_with(remote=True)


# --- create-branch ---


def test_git_create_branch(patch_client):
    result = runner.invoke(
        app, ["git", "create-branch", "new-branch", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created branch" in result.output
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.create_branch.assert_called_once_with("new-branch", commit=None)


def test_git_create_branch_from_commit(patch_client):
    result = runner.invoke(
        app,
        [
            "git",
            "create-branch",
            "new-branch",
            "--from",
            "abc123",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.create_branch.assert_called_once_with("new-branch", commit="abc123")


# --- delete-branch ---


def test_git_delete_branch_blocks_without_yes(patch_client):
    result = runner.invoke(
        app, ["git", "delete-branch", "old-branch", "--project", "PROJ1"]
    )
    assert result.exit_code == 77
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.delete_branch.assert_not_called()


def test_git_delete_branch(patch_client):
    result = runner.invoke(
        app, ["git", "delete-branch", "old-branch", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted branch" in result.output
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.delete_branch.assert_called_once_with(
        "old-branch", force_delete=False, remote=False
    )


def test_git_delete_branch_force_requires_confirm_name(patch_client):
    """--force elevates to tier-3; --yes alone is not enough."""
    result = runner.invoke(
        app,
        [
            "git",
            "delete-branch",
            "old-branch",
            "--force",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 77


def test_git_delete_branch_force_with_matching_confirm_name(patch_client):
    result = runner.invoke(
        app,
        [
            "git",
            "delete-branch",
            "old-branch",
            "--force",
            "--project",
            "PROJ1",
            "--yes",
            "--confirm-name",
            "old-branch",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.delete_branch.assert_called_once_with(
        "old-branch", force_delete=True, remote=False
    )


# --- switch ---


def test_git_switch(patch_client):
    result = runner.invoke(app, ["git", "switch", "feature/test", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Switched" in result.output


def test_git_switch_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "switch", "feature/test", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["success"] is True


# --- tags ---


def test_git_tags(patch_client):
    result = runner.invoke(app, ["git", "tags", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "v1.0" in result.output


def test_git_tags_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "tags", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["shortName"] == "v1.0"


# --- create-tag ---


def test_git_create_tag(patch_client):
    result = runner.invoke(app, ["git", "create-tag", "v2.0", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created tag" in result.output
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.create_tag.assert_called_once_with("v2.0", reference="HEAD", message="")


def test_git_create_tag_with_ref_and_message(patch_client):
    result = runner.invoke(
        app,
        [
            "git",
            "create-tag",
            "v2.0",
            "--ref",
            "abc123",
            "-m",
            "Release v2.0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.create_tag.assert_called_once_with(
        "v2.0", reference="abc123", message="Release v2.0"
    )


# --- remote ---


def test_git_remote_get(patch_client):
    result = runner.invoke(app, ["git", "remote", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "https://github.com/example/project.git" in result.output


def test_git_remote_get_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "git", "remote", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["url"] == "https://github.com/example/project.git"
    assert parsed["name"] == "origin"


def test_git_remote_set(patch_client):
    result = runner.invoke(
        app,
        [
            "git",
            "remote",
            "--set",
            "git@github.com:new/repo.git",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Set remote" in result.output
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.set_remote.assert_called_once_with("git@github.com:new/repo.git", name="origin")


# --- reset-to-upstream ---


def test_git_reset_to_upstream_blocks_without_yes(patch_client):
    result = runner.invoke(app, ["git", "reset-to-upstream", "--project", "PROJ1"])
    assert result.exit_code == 77
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.reset_to_upstream.assert_not_called()


def test_git_reset_to_upstream(patch_client):
    result = runner.invoke(
        app, ["git", "reset-to-upstream", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Reset" in result.output
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.reset_to_upstream.assert_called_once_with()


def test_git_reset_to_upstream_no_upstream_is_prescriptive(patch_client):
    """A local-only branch has no upstream; DSS fails with an opaque NPE.

    The CLI must explain the cause and the recovery commands instead of leaking
    the raw 'name is null' server error.
    """
    git = patch_client.get_project("PROJ1").get_project_git()
    git.reset_to_upstream.side_effect = Exception(
        'NullPointerException: Cannot invoke "String.length()" because "name" is null'
    )
    git.get_status.return_value = {
        "currentBranch": "fix/local-only",
        "remotes": [{"name": "origin", "url": "git@github.com:x/y.git"}],
    }
    git.list_branches.return_value = ["origin/master", "origin/feature/test"]

    result = runner.invoke(
        app, ["git", "reset-to-upstream", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 1
    # Headline is the prescriptive diagnosis, not the raw server error.
    assert "Cannot reset to upstream" in result.output
    assert "fix/local-only" in result.output
    assert "no branch on the remote" in result.output
    assert "dku git push -P PROJ1" in result.output
    assert "reset-to-head" in result.output


def test_git_reset_to_upstream_other_failure_falls_through(patch_client):
    """When the branch DOES track a remote, an unrelated failure is not masked
    by the no-upstream guidance -- it goes through the normal error handler."""
    git = patch_client.get_project("PROJ1").get_project_git()
    git.reset_to_upstream.side_effect = Exception("500 Internal Server Error")
    git.get_status.return_value = {
        "currentBranch": "master",
        "remotes": [{"name": "origin", "url": "git@github.com:x/y.git"}],
    }
    git.list_branches.return_value = ["origin/master"]

    result = runner.invoke(
        app, ["git", "reset-to-upstream", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 1
    assert "no branch on the remote" not in result.output
    assert "500 Internal Server Error" in result.output


# --- reset-to-head ---


def test_git_reset_to_head_blocks_without_yes(patch_client):
    result = runner.invoke(app, ["git", "reset-to-head", "--project", "PROJ1"])
    assert result.exit_code == 77
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.reset_to_head.assert_not_called()


def test_git_reset_to_head(patch_client):
    result = runner.invoke(app, ["git", "reset-to-head", "--project", "PROJ1", "--yes"])
    assert result.exit_code == 0
    assert "Reset" in result.output
    proj = patch_client.get_project("PROJ1")
    git = proj.get_project_git()
    git.reset_to_head.assert_called_once_with()

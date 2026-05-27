"""Tests for library commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_library_list_table(patch_client):
    result = runner.invoke(app, ["library", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "utils.py" in result.output
    assert "__init__.py" in result.output


def test_library_list_json(patch_client):
    result = runner.invoke(app, ["library", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["path"] == "python/mylib/__init__.py"


def test_library_list_with_path(patch_client):
    result = runner.invoke(
        app, ["library", "list", "--path", "python", "--project", "PROJ1"]
    )
    assert result.exit_code == 0


def test_library_read(patch_client):
    result = runner.invoke(
        app, ["library", "read", "python/mylib/utils.py", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "def transform(df):" in result.output


def test_library_write_inline(patch_client):
    result = runner.invoke(
        app,
        [
            "library",
            "write",
            "python/mylib/new.py",
            "--content",
            "print('hello')",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    f = lib.get_file("python/mylib/new.py")
    f.write.assert_called_once_with(b"print('hello')")


def test_library_write_creates_new_file(patch_client):
    """When get_file returns None (file missing), write creates via add_file."""
    from unittest.mock import MagicMock

    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    # Real dataikuapi: get_file returns None for missing files (does NOT raise)
    lib.get_file.return_value = None
    new_file = MagicMock()
    new_file.write.return_value = None
    lib_folder = lib.get_folder.return_value
    lib_folder.add_file.return_value = new_file
    result = runner.invoke(
        app,
        [
            "library",
            "write",
            "python/mylib/new.py",
            "--content",
            "print('hello')",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    new_file.write.assert_called_once_with(b"print('hello')")


def test_library_write_from_file(patch_client, tmp_path):
    local_file = tmp_path / "local_script.py"
    local_file.write_text("import pandas as pd\ndf = pd.DataFrame()")
    result = runner.invoke(
        app,
        [
            "library",
            "write",
            "python/mylib/script.py",
            "--content",
            f"@{local_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    f = lib.get_file("python/mylib/script.py")
    f.write.assert_called_once()
    call_args = f.write.call_args
    assert b"import pandas as pd" in call_args[0][0]


def test_library_write_missing_file(patch_client):
    result = runner.invoke(
        app,
        [
            "library",
            "write",
            "python/mylib/script.py",
            "--content",
            "@/nonexistent/file.py",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_library_delete(patch_client):
    result = runner.invoke(
        app,
        [
            "library",
            "delete",
            "python/mylib/old.py",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    f = lib.get_file("python/mylib/old.py")
    f.delete.assert_called_once()


# ── delete-folder (tier-3 cascade) ────────────────────────────────────────


def test_library_delete_folder_without_yes_blocks(patch_client):
    result = runner.invoke(
        app, ["library", "delete-folder", "python/temp", "--project", "PROJ1"]
    )
    assert result.exit_code == 77


def test_library_delete_folder_without_confirm_name_blocks(patch_client):
    """Tier-3 cascade needs both --yes and --confirm-name."""
    result = runner.invoke(
        app,
        ["library", "delete-folder", "python/temp", "--project", "PROJ1", "--yes"],
    )
    assert result.exit_code == 77


def test_library_delete_folder_with_wrong_confirm_name_blocks(patch_client):
    result = runner.invoke(
        app,
        [
            "library",
            "delete-folder",
            "python/temp",
            "--project",
            "PROJ1",
            "--yes",
            "--confirm-name",
            "wrong_folder",
        ],
    )
    assert result.exit_code == 77


def test_library_delete_folder_with_matching_confirm_name(patch_client):
    result = runner.invoke(
        app,
        [
            "library",
            "delete-folder",
            "python/temp",
            "--project",
            "PROJ1",
            "--yes",
            "--confirm-name",
            "python/temp",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    folder = lib.get_folder("python/temp")
    folder.delete.assert_called_once()


def test_library_delete_folder_not_found(patch_client):
    """A missing folder (get_folder returns None) errors with guidance."""
    lib = patch_client.get_project("PROJ1").get_library()
    lib.get_folder.return_value = None
    result = runner.invoke(
        app,
        [
            "library",
            "delete-folder",
            "python/missing",
            "--project",
            "PROJ1",
            "--yes",
            "--confirm-name",
            "python/missing",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output


def test_library_delete_folder_refuses_root(patch_client):
    result = runner.invoke(
        app,
        [
            "library",
            "delete-folder",
            "/",
            "--project",
            "PROJ1",
            "--yes",
            "--confirm-name",
            "/",
        ],
    )
    assert result.exit_code != 0
    assert "root" in result.output


def test_library_delete_on_folder_points_to_delete_folder(patch_client):
    """`delete` on a folder path should steer the agent to `delete-folder`."""
    lib = patch_client.get_project("PROJ1").get_library()
    lib.get_file.side_effect = Exception(
        "The item python/temp is a folder, not a file "
    )
    result = runner.invoke(
        app,
        ["library", "delete", "python/temp", "--project", "PROJ1", "--yes"],
    )
    assert result.exit_code != 0
    assert "delete-folder" in result.output


def test_library_mkdir(patch_client):
    result = runner.invoke(
        app, ["library", "mkdir", "python/mylib/subdir", "--project", "PROJ1"]
    )
    assert result.exit_code == 0


def test_library_list_csv(patch_client):
    result = runner.invoke(app, ["library", "list", "--project", "PROJ1", "-o", "csv"])
    assert result.exit_code == 0
    assert "utils.py" in result.output


# ── sync ────────────────────────────────────────────────────────────────


def test_library_sync_basic(patch_client, tmp_path):
    """Sync a local dir with 2 files to the library."""
    (tmp_path / "utils.py").write_text("print('hello')")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "module.py").write_text("import os")

    result = runner.invoke(
        app,
        ["library", "sync", str(tmp_path), "/", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Synced 2 file(s)" in result.output


def test_library_sync_dry_run(patch_client, tmp_path):
    """Dry-run should not upload, but report what would happen."""
    (tmp_path / "data.py").write_text("x = 1")

    result = runner.invoke(
        app,
        ["library", "sync", str(tmp_path), "/", "--project", "PROJ1", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "(dry-run)" in result.output
    assert "Would upload" in result.output
    assert "Would sync 1 file(s)" in result.output


def test_library_sync_exclude(patch_client, tmp_path):
    """Exclude patterns should skip matching files."""
    (tmp_path / "keep.py").write_text("keep")
    (tmp_path / "skip.log").write_text("skip")

    result = runner.invoke(
        app,
        [
            "library",
            "sync",
            str(tmp_path),
            "/",
            "--project",
            "PROJ1",
            "--exclude",
            "*.log",
        ],
    )
    assert result.exit_code == 0
    assert "Synced 1 file(s)" in result.output


def test_library_sync_default_excludes(patch_client, tmp_path):
    """Default excludes (.git, __pycache__, *.pyc) should be skipped."""
    (tmp_path / "good.py").write_text("ok")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "bad.pyc").write_text("cached")
    (tmp_path / ".DS_Store").write_text("ds")
    (tmp_path / "also_bad.pyc").write_text("pyc")

    result = runner.invoke(
        app,
        ["library", "sync", str(tmp_path), "/", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Synced 1 file(s)" in result.output


def test_library_sync_with_remote_dir(patch_client, tmp_path):
    """Sync to a specific remote subdirectory."""
    (tmp_path / "app.py").write_text("run()")

    result = runner.invoke(
        app,
        [
            "library",
            "sync",
            str(tmp_path),
            "webapps/my_app",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Synced 1 file(s)" in result.output


def test_library_sync_nonexistent_dir(patch_client):
    """Sync from non-existent local dir should error."""
    result = runner.invoke(
        app,
        ["library", "sync", "/nonexistent/path", "/", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "not found" in result.output


def test_library_sync_empty_dir(patch_client, tmp_path):
    """Sync from empty dir should report no files."""
    result = runner.invoke(
        app,
        ["library", "sync", str(tmp_path), "/", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "No files to sync" in result.output

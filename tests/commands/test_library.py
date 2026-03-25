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
    """When get_file raises, write should create the file via folder.add_file."""
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    lib.get_file.side_effect = Exception("not found")
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
    # Restores side_effect for other tests
    lib.get_file.side_effect = None


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
        app, ["library", "delete", "python/mylib/old.py", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    f = lib.get_file("python/mylib/old.py")
    f.delete.assert_called_once()


def test_library_mkdir(patch_client):
    result = runner.invoke(
        app, ["library", "mkdir", "python/mylib/subdir", "--project", "PROJ1"]
    )
    assert result.exit_code == 0


def test_library_list_csv(patch_client):
    result = runner.invoke(app, ["library", "list", "--project", "PROJ1", "-o", "csv"])
    assert result.exit_code == 0
    assert "utils.py" in result.output

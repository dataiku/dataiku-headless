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
    assert parsed[1]["size"] == 256


def test_library_list_with_path(patch_client):
    result = runner.invoke(app, ["library", "list", "--path", "/python", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_library_read(patch_client):
    result = runner.invoke(app, ["library", "read", "python/mylib/utils.py", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "def transform(df):" in result.output


def test_library_write_inline(patch_client):
    result = runner.invoke(app, ["library", "write", "python/mylib/new.py", "--content", "print('hello')", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    lib.put_file.assert_called_once_with("python/mylib/new.py", b"print('hello')")


def test_library_write_from_file(patch_client, tmp_path):
    local_file = tmp_path / "local_script.py"
    local_file.write_text("import pandas as pd\ndf = pd.DataFrame()")
    result = runner.invoke(app, ["library", "write", "python/mylib/script.py", "--content", f"@{local_file}", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    lib.put_file.assert_called_once()
    call_args = lib.put_file.call_args
    assert call_args[0][0] == "python/mylib/script.py"
    assert b"import pandas as pd" in call_args[0][1]


def test_library_write_missing_file(patch_client):
    result = runner.invoke(app, ["library", "write", "python/mylib/script.py", "--content", "@/nonexistent/file.py", "--project", "PROJ1"])
    assert result.exit_code != 0


def test_library_delete(patch_client):
    result = runner.invoke(app, ["library", "delete", "python/mylib/old.py", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    lib.delete_file.assert_called_once_with("python/mylib/old.py")


def test_library_mkdir(patch_client):
    result = runner.invoke(app, ["library", "mkdir", "python/mylib/subdir", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    lib = proj.get_library()
    lib.add_folder.assert_called_once_with("python/mylib/subdir")


def test_library_list_csv(patch_client):
    result = runner.invoke(app, ["library", "list", "--project", "PROJ1", "-o", "csv"])
    assert result.exit_code == 0
    assert "path,size" in result.output.lower() or "PATH" in result.output
    assert "utils.py" in result.output

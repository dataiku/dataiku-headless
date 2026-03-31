"""Tests for folder commands."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_folder_list(patch_client):
    result = runner.invoke(app, ["folder", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "folder1" in result.output


def test_folder_list_json(patch_client):
    result = runner.invoke(app, ["folder", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "folder1"


def test_folder_ls(patch_client):
    result = runner.invoke(app, ["folder", "ls", "folder1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "data.csv" in result.output


def test_folder_upload(patch_client):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"col1,col2\na,b\n")
        f.flush()
        result = runner.invoke(
            app, ["folder", "upload", "folder1", f.name, "--project", "PROJ1"]
        )
        assert result.exit_code == 0
        Path(f.name).unlink()


def test_folder_upload_missing_file(patch_client):
    result = runner.invoke(
        app,
        ["folder", "upload", "folder1", "/nonexistent/file.csv", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


# --- create ---


def test_folder_create_basic(patch_client):
    result = runner.invoke(app, ["folder", "create", "MyFolder", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_managed_folder.assert_called_once_with(
        "MyFolder", folder_type=None, connection_name="filesystem_folders"
    )
    assert "aBcDeFgH" in result.output


def test_folder_create_with_connection(patch_client):
    result = runner.invoke(
        app,
        [
            "folder",
            "create",
            "MyFolder",
            "--connection",
            "s3_data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_managed_folder.assert_called_once_with(
        "MyFolder", folder_type=None, connection_name="s3_data"
    )


def test_folder_create_with_type(patch_client):
    result = runner.invoke(
        app,
        ["folder", "create", "MyFolder", "--type", "S3", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_managed_folder.assert_called_once_with(
        "MyFolder", folder_type="S3", connection_name="filesystem_folders"
    )


def test_folder_create_json(patch_client):
    result = runner.invoke(
        app,
        ["folder", "create", "MyFolder", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "aBcDeFgH"
    assert parsed["name"] == "MyFolder"
    assert parsed["project"] == "PROJ1"


def test_folder_create_if_not_exists(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_managed_folder.side_effect = Exception("already exists")

    result = runner.invoke(
        app,
        ["folder", "create", "MyFolder", "--project", "PROJ1", "--if-not-exists"],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output.lower()

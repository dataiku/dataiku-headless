"""Tests for folder commands."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# --- Existing tests ---


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


# --- Create tests ---


def test_folder_create_basic(patch_client):
    result = runner.invoke(
        app, ["folder", "create", "Test Folder", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "aBcDeFgH" in result.output
    assert "Created managed folder" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_managed_folder.assert_called_once_with(
        "Test Folder", folder_type=None, connection_name="filesystem_folders"
    )


def test_folder_create_with_connection(patch_client):
    result = runner.invoke(
        app,
        [
            "folder",
            "create",
            "S3 Folder",
            "--connection",
            "s3_data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_managed_folder.assert_called_once_with(
        "S3 Folder", folder_type=None, connection_name="s3_data"
    )


def test_folder_create_with_type(patch_client):
    result = runner.invoke(
        app,
        [
            "folder",
            "create",
            "Typed",
            "--type",
            "S3",
            "--connection",
            "s3_conn",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_managed_folder.assert_called_once_with(
        "Typed", folder_type="S3", connection_name="s3_conn"
    )


def test_folder_create_if_not_exists_skip(patch_client):
    """When folder with same name exists, --if-not-exists should skip."""
    result = runner.invoke(
        app,
        [
            "folder",
            "create",
            "Data Folder",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_managed_folder.assert_not_called()


def test_folder_create_if_not_exists_new(patch_client):
    """When no matching name, --if-not-exists should create normally."""
    result = runner.invoke(
        app,
        [
            "folder",
            "create",
            "Brand New Folder",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created managed folder" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_managed_folder.assert_called_once()


def test_folder_create_json(patch_client):
    result = runner.invoke(
        app,
        ["folder", "create", "JSON Folder", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "aBcDeFgH"
    assert parsed["status"] == "created"


# --- Delete tests ---


def test_folder_delete_with_yes(patch_client):
    result = runner.invoke(
        app, ["folder", "delete", "folder1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted managed folder" in result.output
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.delete.assert_called_once()


def test_folder_delete_prompts(patch_client):
    result = runner.invoke(
        app, ["folder", "delete", "folder1", "--project", "PROJ1"], input="y\n"
    )
    assert result.exit_code == 0
    assert "Deleted managed folder" in result.output


def test_folder_delete_aborts_on_no(patch_client):
    result = runner.invoke(
        app, ["folder", "delete", "folder1", "--project", "PROJ1"], input="n\n"
    )
    assert result.exit_code != 0
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.delete.assert_not_called()


# --- Delete-file tests ---


def test_folder_delete_file(patch_client):
    result = runner.invoke(
        app,
        ["folder", "delete-file", "folder1", "/data.csv", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Deleted /data.csv" in result.output
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.delete_file.assert_called_once_with("/data.csv")


# --- Get tests ---


def test_folder_get_table(patch_client):
    result = runner.invoke(app, ["folder", "get", "folder1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Data Folder" in result.output
    assert "Filesystem" in result.output
    assert "filesystem_folders" in result.output


def test_folder_get_json(patch_client):
    result = runner.invoke(
        app, ["folder", "get", "folder1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "Data Folder"
    assert parsed["type"] == "Filesystem"
    assert parsed["params"]["connection"] == "filesystem_folders"


# --- Create-dataset tests ---


def test_folder_create_dataset(patch_client):
    result = runner.invoke(
        app,
        ["folder", "create-dataset", "folder1", "my_files_ds", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Created FilesInFolder dataset" in result.output
    assert "my_files_ds" in result.output
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.create_dataset_from_files.assert_called_once_with("my_files_ds")


def test_folder_create_dataset_already_exists(patch_client):
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.create_dataset_from_files.side_effect = Exception(
        "Dataset 'my_files_ds' already exists"
    )
    result = runner.invoke(
        app,
        ["folder", "create-dataset", "folder1", "my_files_ds", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


# --- Resolve by name test ---


def test_folder_ls_by_name(patch_client):
    """resolve_folder should fall back to name lookup when ID lookup fails."""
    from unittest.mock import MagicMock

    proj = patch_client.get_project("PROJ1")

    # Create separate mocks: one that fails (ID lookup), one that works (name lookup)
    bad_folder = MagicMock()
    bad_folder.get_settings.side_effect = Exception("NotFoundException: not found")

    good_folder = MagicMock()
    good_folder.id = "folder1"
    good_folder_settings = MagicMock()
    good_folder_settings.get_raw.return_value = {"name": "Data Folder"}
    good_folder.get_settings.return_value = good_folder_settings
    good_folder.list_contents.return_value = {
        "items": [{"path": "/data.csv", "size": 1024, "lastModified": 1700000000000}]
    }

    def side_effect(ref):
        if ref == "Data Folder":
            return bad_folder  # ID lookup fails
        return good_folder  # ID from list_managed_folders works

    proj.get_managed_folder.side_effect = side_effect

    result = runner.invoke(app, ["folder", "ls", "Data Folder", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "data.csv" in result.output


# --- set-metadata ---


def test_folder_set_metadata_description(patch_client):
    result = runner.invoke(
        app,
        [
            "folder",
            "set-metadata",
            "folder1",
            "--description",
            "Raw data files",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated metadata" in result.output
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.set_definition.assert_called_once()
    defn = folder.set_definition.call_args[0][0]
    assert defn["description"] == "Raw data files"


def test_folder_set_metadata_tags(patch_client):
    result = runner.invoke(
        app,
        [
            "folder",
            "set-metadata",
            "folder1",
            "--tags",
            "raw,source",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    defn = folder.set_definition.call_args[0][0]
    assert defn["tags"] == ["raw", "source"]


def test_folder_set_metadata_no_args(patch_client):
    result = runner.invoke(
        app, ["folder", "set-metadata", "folder1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0

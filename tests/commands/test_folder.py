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


def test_folder_delete_blocks_without_yes(patch_client):
    result = runner.invoke(app, ["folder", "delete", "folder1", "--project", "PROJ1"])
    assert result.exit_code == 77
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.delete.assert_not_called()


# --- Delete-file tests ---


def test_folder_delete_file(patch_client):
    result = runner.invoke(
        app,
        [
            "folder",
            "delete-file",
            "folder1",
            "/data.csv",
            "--project",
            "PROJ1",
            "--yes",
        ],
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


def test_folder_create_dataset_excel_sheet(patch_client):
    """--sheet implies --format excel and writes sheets/sheetSelectionMode."""
    from unittest.mock import MagicMock

    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    ds = MagicMock()
    settings = MagicMock()
    raw: dict = {}
    settings.get_raw.return_value = raw
    ds.get_settings.return_value = settings
    folder.create_dataset_from_files.return_value = ds

    result = runner.invoke(
        app,
        [
            "folder",
            "create-dataset",
            "folder1",
            "xls_inv",
            "--sheet",
            "FY24",
            "--skip-rows-before",
            "3",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw["formatType"] == "excel"
    assert raw["formatParams"]["sheets"] == "FY24"
    assert raw["formatParams"]["sheetSelectionMode"] == "NAMES"
    assert raw["formatParams"]["skipRowsBeforeHeader"] == 3


def test_folder_create_dataset_sheet_with_wrong_format_errors(patch_client):
    """--sheet on a non-excel format must reject."""
    result = runner.invoke(
        app,
        [
            "folder",
            "create-dataset",
            "folder1",
            "ds",
            "--format",
            "csv",
            "--sheet",
            "S1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "excel" in result.output.lower()


def test_folder_create_dataset_sheet_and_index_mutex(patch_client):
    """--sheet and --sheet-index are mutually exclusive."""
    result = runner.invoke(
        app,
        [
            "folder",
            "create-dataset",
            "folder1",
            "ds",
            "--sheet",
            "S1",
            "--sheet-index",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


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


# --- Rename tests ---


def test_folder_rename(patch_client):
    result = runner.invoke(
        app,
        ["folder", "rename", "folder1", "New Name", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Renamed" in result.output
    assert "New Name" in result.output
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.rename.assert_called_once_with("New Name")


# --- Copy tests ---


def test_folder_copy(patch_client):
    result = runner.invoke(
        app,
        ["folder", "copy", "folder1", "folder1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Copied" in result.output
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.copy_to.assert_called_once()


def test_folder_copy_write_mode(patch_client):
    result = runner.invoke(
        app,
        [
            "folder",
            "copy",
            "folder1",
            "folder1",
            "--write-mode",
            "APPEND",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    call_kwargs = folder.copy_to.call_args
    assert call_kwargs[1]["write_mode"] == "APPEND"


# --- Upload-dir tests ---


def test_folder_upload_dir(patch_client, tmp_path):
    # Create test directory structure
    sub = tmp_path / "docs" / "sub"
    sub.mkdir(parents=True)
    (tmp_path / "docs" / "a.txt").write_text("hello")
    (sub / "b.txt").write_text("world")

    result = runner.invoke(
        app,
        [
            "folder",
            "upload-dir",
            "folder1",
            str(tmp_path / "docs"),
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # New summary format: "Uploaded N/M from <dir> → <prefix>". N is the
    # count successfully uploaded, M is the total attempted.
    assert "Uploaded 2/2" in result.output
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    assert folder.put_file.call_count == 2


def test_folder_upload_dir_partial_failure_tallies(patch_client, tmp_path):
    """One transient failure per-file is recovered via retry; permanent failures
    are tallied in a non-zero exit summary instead of aborting the batch."""
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")

    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")

    call_log: list[str] = []

    def _put(remote_path, _fh):
        call_log.append(remote_path)
        # 'b.txt' fails permanently across all retries (3 attempts default).
        if remote_path.endswith("b.txt"):
            raise RuntimeError("permanent: DSS proxy timeout")

    folder.put_file.side_effect = _put

    result = runner.invoke(
        app,
        [
            "folder",
            "upload-dir",
            "folder1",
            str(tmp_path),
            "--project",
            "PROJ1",
        ],
    )
    # Permanent failure on one file → non-zero exit, but the other uploaded.
    assert result.exit_code != 0
    assert "1/2" in result.output  # 1 succeeded out of 2 attempted
    assert "failed: 1" in result.output


def test_folder_upload_dir_fail_fast(patch_client, tmp_path):
    """--fail-fast aborts on the first hard failure."""
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")

    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    folder.put_file.side_effect = RuntimeError("boom")

    result = runner.invoke(
        app,
        [
            "folder",
            "upload-dir",
            "folder1",
            str(tmp_path),
            "--fail-fast",
            "--retry",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_folder_upload_dir_not_directory(patch_client, tmp_path):
    result = runner.invoke(
        app,
        [
            "folder",
            "upload-dir",
            "folder1",
            str(tmp_path / "nonexistent"),
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_folder_upload_dir_with_prefix(patch_client, tmp_path):
    (tmp_path / "file.txt").write_text("data")
    result = runner.invoke(
        app,
        [
            "folder",
            "upload-dir",
            "folder1",
            str(tmp_path),
            "--prefix",
            "/uploads",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    call_args = folder.put_file.call_args[0]
    assert call_args[0].startswith("/uploads/")


# --- Delete-files tests ---


def test_folder_delete_files(patch_client):
    result = runner.invoke(
        app,
        [
            "folder",
            "delete-files",
            "folder1",
            "/a.txt",
            "/b.txt",
            "/c.txt",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert "Deleted 3 file(s)" in result.output
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    assert folder.delete_file.call_count == 3


# --- Decompress tests ---


def test_folder_decompress(patch_client):
    import io
    import zipfile

    # Create a real zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("hello.txt", "Hello!")
        zf.writestr("sub/world.txt", "World!")
    zip_bytes = zip_buffer.getvalue()

    # Mock get_file to return zip content
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    file_resp = type("Response", (), {"content": zip_bytes})()
    folder.get_file.return_value = file_resp

    result = runner.invoke(
        app,
        ["folder", "decompress", "folder1", "/archive.zip", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Extracted 2 file(s)" in result.output
    folder.get_file.assert_called_once_with("/archive.zip")
    # Should have uploaded 2 files
    assert folder.put_file.call_count == 2


def test_folder_decompress_json(patch_client):
    import io
    import zipfile

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("file.txt", "content")
    zip_bytes = zip_buffer.getvalue()

    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    file_resp = type("Response", (), {"content": zip_bytes})()
    folder.get_file.return_value = file_resp

    result = runner.invoke(
        app,
        [
            "--quiet",
            "folder",
            "decompress",
            "folder1",
            "/test.zip",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["files_extracted"] == 1
    assert parsed["archive_deleted"] is False


def test_folder_decompress_delete_archive(patch_client):
    import io
    import zipfile

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("file.txt", "content")
    zip_bytes = zip_buffer.getvalue()

    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    file_resp = type("Response", (), {"content": zip_bytes})()
    folder.get_file.return_value = file_resp

    result = runner.invoke(
        app,
        [
            "folder",
            "decompress",
            "folder1",
            "/test.zip",
            "--delete-archive",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    folder.delete_file.assert_called_once_with("/test.zip")


def test_folder_decompress_with_dest(patch_client):
    import io
    import zipfile

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("file.txt", "content")
    zip_bytes = zip_buffer.getvalue()

    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    file_resp = type("Response", (), {"content": zip_bytes})()
    folder.get_file.return_value = file_resp

    result = runner.invoke(
        app,
        [
            "folder",
            "decompress",
            "folder1",
            "/archive.zip",
            "--dest",
            "/extracted",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # Check the uploaded path starts with /extracted/
    call_args = folder.put_file.call_args[0]
    assert call_args[0].startswith("/extracted/")


def test_folder_decompress_invalid_zip(patch_client):
    # Mock get_file to return non-zip content
    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    file_resp = type("Response", (), {"content": b"not a zip file"})()
    folder.get_file.return_value = file_resp

    result = runner.invoke(
        app,
        ["folder", "decompress", "folder1", "/bad.zip", "--project", "PROJ1"],
    )
    assert result.exit_code != 0

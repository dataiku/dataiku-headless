"""Tests for dataset commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_dataset_list_table(patch_client):
    result = runner.invoke(app, ["dataset", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ds1" in result.output


def test_dataset_list_json(patch_client):
    result = runner.invoke(app, ["dataset", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "ds1"


def test_dataset_list_with_env(patch_client, monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["dataset", "list"])
    assert result.exit_code == 0


def test_dataset_schema(patch_client):
    result = runner.invoke(app, ["dataset", "schema", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "col1" in result.output


def test_dataset_schema_json(patch_client):
    result = runner.invoke(app, ["dataset", "schema", "ds1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "col1"


def test_dataset_head(patch_client):
    result = runner.invoke(app, ["dataset", "head", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_dataset_build(patch_client):
    result = runner.invoke(app, ["dataset", "build", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_dataset_build_wait(patch_client):
    result = runner.invoke(app, ["dataset", "build", "ds1", "--project", "PROJ1", "--wait"])
    assert result.exit_code == 0


# --- New commands ---


def test_dataset_create_basic(patch_client):
    result = runner.invoke(app, ["dataset", "create", "new_ds", "--type", "SQL", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created dataset" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_dataset.assert_called_once()
    call_args = proj.create_dataset.call_args
    assert call_args[0][0] == "new_ds"
    assert call_args[0][1] == "SQL"


def test_dataset_create_with_connection(patch_client):
    result = runner.invoke(app, [
        "dataset", "create", "new_ds",
        "--type", "SQL",
        "--connection", "my_pg",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_dataset.call_args[1]
    assert call_kwargs["params"]["connection"] == "my_pg"


def test_dataset_create_with_definition(patch_client, tmp_path):
    def_file = tmp_path / "def.json"
    def_file.write_text(json.dumps({"type": "SQL", "params": {"connection": "pg_conn"}}))
    result = runner.invoke(app, [
        "dataset", "create", "new_ds",
        "--type", "SQL",
        "--definition", f"@{def_file}",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_dataset.call_args[1]
    assert call_kwargs["params"]["connection"] == "pg_conn"


def test_dataset_create_with_definition_format_fields(patch_client, tmp_path):
    def_file = tmp_path / "def.json"
    def_file.write_text(json.dumps({
        "type": "S3",
        "params": {"connection": "s3_conn", "path": "/bucket/path"},
        "formatType": "csv",
        "formatParams": {"separator": ","},
    }))
    result = runner.invoke(app, [
        "dataset", "create", "new_ds",
        "--type", "S3",
        "--definition", f"@{def_file}",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.create_dataset.call_args
    call_kwargs = call_args[1]
    assert call_args[0][1] == "S3"
    assert call_kwargs["params"] == {"connection": "s3_conn", "path": "/bucket/path"}
    assert call_kwargs["formatType"] == "csv"
    assert call_kwargs["formatParams"] == {"separator": ","}


def test_dataset_create_fails_on_conflicting_definition_type(patch_client, tmp_path):
    def_file = tmp_path / "def.json"
    def_file.write_text(json.dumps({"type": "S3", "params": {"connection": "s3_conn"}}))
    result = runner.invoke(app, [
        "dataset", "create", "new_ds",
        "--type", "SQL",
        "--definition", f"@{def_file}",
        "--project", "PROJ1",
    ])
    assert result.exit_code != 0
    assert "conflicts with definition type" in result.output


def test_dataset_delete(patch_client):
    result = runner.invoke(app, ["dataset", "delete", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Deleted dataset" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.delete.assert_called_once()


def test_dataset_clear(patch_client):
    result = runner.invoke(app, ["dataset", "clear", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Cleared dataset" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.clear.assert_called_once()


def test_dataset_get_definition(patch_client):
    result = runner.invoke(app, ["dataset", "get-definition", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "schema" in parsed
    assert parsed["schema"]["columns"][0]["name"] == "col1"


def test_dataset_get_definition_with_output_flag(patch_client):
    result = runner.invoke(app, ["dataset", "get-definition", "ds1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["schema"]["columns"][1]["name"] == "col2"


def test_dataset_set_definition(patch_client):
    new_def = json.dumps({"schema": {"columns": [{"name": "x", "type": "string"}]}})
    result = runner.invoke(app, [
        "dataset", "set-definition", "ds1",
        "--definition", new_def,
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.set_definition.assert_called_once()


def test_dataset_set_schema(patch_client):
    schema = json.dumps({"columns": [{"name": "new_col", "type": "float"}]})
    result = runner.invoke(app, [
        "dataset", "set-schema", "ds1",
        "--definition", schema,
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Updated schema" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.set_definition.assert_called_once()
    # Verify the schema was merged into the existing definition
    call_arg = ds.set_definition.call_args[0][0]
    assert call_arg["schema"]["columns"][0]["name"] == "new_col"


def test_dataset_upload(patch_client, tmp_path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("col1,col2\na,1\nb,2")
    result = runner.invoke(app, ["dataset", "upload", "raw_data", str(csv_file), "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Uploaded" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("raw_data")
    ds.uploaded_add_file.assert_called_once()
    call_args = ds.uploaded_add_file.call_args[0]
    assert call_args[1] == "data.csv"
    # Verify autodetect was called and settings saved
    ds.autodetect_settings.assert_called_once_with(infer_storage_types=True)
    ds.autodetect_settings.return_value.save.assert_called_once()
    assert "Format detected" in result.output


def test_dataset_create_filesystem_requires_connection(patch_client):
    result = runner.invoke(app, [
        "dataset", "create", "fs_ds",
        "--type", "Filesystem",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 1
    assert "requires --connection" in result.output
    patch_client.get_project("PROJ1").new_managed_dataset.assert_not_called()


def test_dataset_create_filesystem_uses_managed_dataset_builder(patch_client):
    result = runner.invoke(app, [
        "dataset", "create", "fs_ds",
        "--type", "Filesystem",
        "--connection", "filesystem_folders",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_managed_dataset.assert_called_once_with("fs_ds")
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("filesystem_folders")
    builder.create.assert_called_once()
    proj.create_dataset.assert_not_called()


def test_dataset_upload_no_autodetect(patch_client, tmp_path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("col1,col2\na,1\nb,2")
    result = runner.invoke(app, [
        "dataset", "upload", "raw_data", str(csv_file),
        "--project", "PROJ1", "--no-autodetect",
    ])
    assert result.exit_code == 0
    assert "Uploaded" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("raw_data")
    ds.uploaded_add_file.assert_called_once()
    ds.autodetect_settings.assert_not_called()


def test_dataset_upload_file_not_found(patch_client):
    result = runner.invoke(app, ["dataset", "upload", "raw_data", "/nonexistent/file.csv", "--project", "PROJ1"])
    assert result.exit_code != 0


def test_dataset_upload_env_project(patch_client, tmp_path, monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("col1,col2\na,1")
    result = runner.invoke(app, ["dataset", "upload", "raw_data", str(csv_file)])
    assert result.exit_code == 0
    assert "Uploaded" in result.output


def test_dataset_set_schema_from_file(patch_client, tmp_path):
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps({"columns": [{"name": "file_col", "type": "bigint"}]}))
    result = runner.invoke(app, [
        "dataset", "set-schema", "ds1",
        "--definition", f"@{schema_file}",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    call_arg = ds.set_definition.call_args[0][0]
    assert call_arg["schema"]["columns"][0]["name"] == "file_col"

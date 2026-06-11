"""Dataset command tests split from tests/commands/test_dataset.py."""

from __future__ import annotations

import json
from tests.commands.dataset.helpers import app, runner


# --- dataset create --if-not-exists ---


def test_dataset_create_if_not_exists_when_exists(patch_client):
    """--if-not-exists silently succeeds when dataset already exists."""
    proj = patch_client.get_project("PROJ1")
    proj.create_dataset.side_effect = Exception("Dataset 'new_ds' already exists")
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "new_ds",
            "--type",
            "SQL",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output.lower()


def test_dataset_create_if_not_exists_when_new(patch_client):
    """--if-not-exists creates normally when dataset doesn't exist."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "new_ds",
            "--type",
            "SQL",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_dataset.assert_called_once()


def test_dataset_delete(patch_client):
    result = runner.invoke(
        app, ["dataset", "delete", "ds1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted dataset" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.delete.assert_called_once()


def test_dataset_delete_blocks_without_yes(patch_client):
    """Without --yes, guarded mode refuses and emits AGENT INSTRUCTION."""
    result = runner.invoke(app, ["dataset", "delete", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 77
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.delete.assert_not_called()


def test_dataset_delete_dangerous_env_bypasses(patch_client, monkeypatch):
    """DKU_DANGEROUS=1 skips the guard."""
    monkeypatch.setenv("DKU_DANGEROUS", "1")
    result = runner.invoke(app, ["dataset", "delete", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.delete.assert_called_once()


def test_dataset_delete_warns_about_dependent_recipes(patch_client):
    """Dataset delete enumerates recipe dependents via get_usages() and warns
    about them before proceeding. The default dataset_mock has one RECIPE_INPUT
    usage on 'compute_output', which should surface in the output."""
    result = runner.invoke(
        app, ["dataset", "delete", "ds1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert "dependent recipe" in result.output
    assert "compute_output" in result.output
    assert "Deleted dataset" in result.output


def test_dataset_delete_drop_data_alias_accepted(patch_client):
    """--drop-data is accepted as a no-op alias for symmetry with project delete."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "delete",
            "ds1",
            "--project",
            "PROJ1",
            "--yes",
            "--drop-data",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "--drop-data is accepted" in result.output
    assert "Deleted dataset" in result.output


def test_dataset_delete_no_dependents_no_warning(patch_client):
    """When get_usages() returns an empty list, no cascade warning is shown."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_usages.return_value = []
    result = runner.invoke(
        app, ["dataset", "delete", "ds1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert "dependent recipe" not in result.output
    assert "Deleted dataset" in result.output


def test_dataset_clear_requires_yes(patch_client):
    """dataset clear is tier-2 destructive — needs --yes."""
    result = runner.invoke(app, ["dataset", "clear", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 77
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.clear.assert_not_called()


def test_dataset_clear_with_yes(patch_client):
    result = runner.invoke(
        app, ["dataset", "clear", "ds1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Cleared dataset" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.clear.assert_called_once()


def test_dataset_get_definition(patch_client):
    result = runner.invoke(
        app, ["dataset", "get-definition", "ds1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "schema" in parsed
    assert parsed["schema"]["columns"][0]["name"] == "col1"


def test_dataset_get_definition_with_output_flag(patch_client):
    result = runner.invoke(
        app,
        ["--format", "json", "dataset", "get-definition", "ds1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["schema"]["columns"][1]["name"] == "col2"


def test_dataset_set_definition(patch_client):
    new_def = json.dumps({"schema": {"columns": [{"name": "x", "type": "string"}]}})
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-definition",
            "ds1",
            "--definition",
            new_def,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.set_definition.assert_called_once()


def test_dataset_set_definition_merge(patch_client):
    """--merge overlays top-level keys onto the current definition (no wipe)."""
    patch_json = json.dumps({"formatParams": {"separator": "\t", "quoteChar": ""}})
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-definition",
            "ds1",
            "--definition",
            patch_json,
            "--merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "merged" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    sent = ds.set_definition.call_args[0][0]
    # Existing top-level keys preserved
    assert sent["type"] == "UploadedFiles"
    assert sent["formatType"] == "csv"
    # New key overlaid
    assert sent["formatParams"]["separator"] == "\t"


def test_dataset_set_definition_deep_merge(patch_client):
    """--deep-merge keeps sibling keys inside nested dicts."""
    # Seed the mock to have nested params we want to preserve.
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_definition.return_value = {
        "type": "UploadedFiles",
        "params": {"uploadConnection": "filesystem_managed", "keep_me": "yes"},
        "formatParams": {"separator": ",", "quoteChar": '"'},
    }
    patch_json = json.dumps({"formatParams": {"separator": "\t"}})
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-definition",
            "ds1",
            "--definition",
            patch_json,
            "--deep-merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    sent = ds.set_definition.call_args[0][0]
    assert sent["formatParams"]["separator"] == "\t"
    # Sibling formatParams.quoteChar preserved (deep merge)
    assert sent["formatParams"]["quoteChar"] == '"'
    # Sibling params.* preserved
    assert sent["params"]["keep_me"] == "yes"


def test_dataset_set_definition_merge_and_deep_merge_conflict(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-definition",
            "ds1",
            "--definition",
            "{}",
            "--merge",
            "--deep-merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Use either --merge or --deep-merge" in result.output


def test_dataset_set_schema(patch_client):
    schema = json.dumps({"columns": [{"name": "new_col", "type": "float"}]})
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-schema",
            "ds1",
            "--definition",
            schema,
            "--project",
            "PROJ1",
        ],
    )
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
    result = runner.invoke(
        app, ["dataset", "upload", "raw_data", str(csv_file), "--project", "PROJ1"]
    )
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


def test_dataset_upload_header_eaten_warning(patch_client, tmp_path):
    """Warns with the parseHeaderRow fix when columns auto-detect as col_0, col_1, …

    Reproduces the numeric-header CSV trap (World Bank year columns on
    Challenge_109): DSS's header heuristic fails when the header row is mostly
    numeric, leaving generic col_<n> names that downstream recipes KeyError on.
    """
    csv_file = tmp_path / "years.csv"
    csv_file.write_text("Country,1960,1961\nAruba,1,2\nAfg,3,4")
    ds = patch_client.get_project("PROJ1").get_dataset("year_data")
    ds.autodetect_settings.return_value.get_raw.return_value = {
        "formatType": "csv",
        "formatParams": {"parseHeaderRow": False},
        "schema": {
            "columns": [
                {"name": "col_0", "type": "string"},
                {"name": "col_1", "type": "string"},
                {"name": "col_2", "type": "string"},
            ]
        },
    }
    result = runner.invoke(
        app, ["dataset", "upload", "year_data", str(csv_file), "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Header row NOT parsed" in result.output
    assert "parseHeaderRow" in result.output
    assert "set-schema" in result.output


def test_dataset_upload_no_header_warning_when_named(patch_client, tmp_path):
    """No header-eaten warning when columns have real names."""
    csv_file = tmp_path / "named.csv"
    csv_file.write_text("name,age\nA,1\nB,2")
    ds = patch_client.get_project("PROJ1").get_dataset("named_data")
    ds.autodetect_settings.return_value.get_raw.return_value = {
        "formatType": "csv",
        "formatParams": {"parseHeaderRow": True},
        "schema": {
            "columns": [
                {"name": "name", "type": "string"},
                {"name": "age", "type": "int"},
            ]
        },
    }
    result = runner.invoke(
        app, ["dataset", "upload", "named_data", str(csv_file), "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Header row NOT parsed" not in result.output


def test_dataset_create_filesystem_defaults_to_filesystem_managed(patch_client):
    """Filesystem without -c defaults to filesystem_managed connection."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "fs_ds",
            "--type",
            "Filesystem",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_managed_dataset.assert_called_once_with("fs_ds")
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("filesystem_managed")
    builder.create.assert_called_once()


def test_dataset_create_default_type_is_filesystem(patch_client):
    """No --type flag defaults to Filesystem on filesystem_managed."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "fs_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_managed_dataset.assert_called_once_with("fs_ds")
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("filesystem_managed")


def test_dataset_create_filesystem_success_is_last_line(patch_client):
    """Filesystem create — success verdict is the last printed line."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "fs_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    last_nonblank = [line for line in result.output.splitlines() if line.strip()][-1]
    assert "Created dataset" in last_nonblank


def test_dataset_create_already_exists_shows_hint(patch_client):
    """Already-exists error without --if-not-exists shows actionable hint."""
    proj = patch_client.get_project("PROJ1")
    proj.new_managed_dataset.return_value.create.side_effect = Exception(
        "Dataset already exists"
    )
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "fs_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--if-not-exists" in result.output
    assert "--yes" in result.output


def test_dataset_create_filesystem_uses_managed_dataset_builder(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "fs_ds",
            "--type",
            "Filesystem",
            "--connection",
            "filesystem_folders",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_managed_dataset.assert_called_once_with("fs_ds")
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("filesystem_folders")
    builder.create.assert_called_once()
    proj.create_dataset.assert_not_called()


def test_dataset_create_uploaded_files_maps_connection_to_upload_connection(
    patch_client,
):
    """--connection for UploadedFiles should set params.uploadConnection, not params.connection."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "upload_ds",
            "--type",
            "UploadedFiles",
            "--connection",
            "dataiku-managed-storage",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_dataset.call_args[1]
    assert call_kwargs["params"]["uploadConnection"] == "dataiku-managed-storage"
    assert "connection" not in call_kwargs["params"]


def test_dataset_create_uploaded_files_auto_detects_connection(patch_client):
    """UploadedFiles without --connection should auto-detect from available connections."""
    patch_client.list_connections.return_value = {
        "dataiku-managed-storage": {},
        "filesystem_managed": {},
    }
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "upload_ds",
            "--type",
            "UploadedFiles",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_dataset.call_args[1]
    assert call_kwargs["params"]["uploadConnection"] == "dataiku-managed-storage"


def test_dataset_upload_no_autodetect(patch_client, tmp_path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("col1,col2\na,1\nb,2")
    result = runner.invoke(
        app,
        [
            "dataset",
            "upload",
            "raw_data",
            str(csv_file),
            "--project",
            "PROJ1",
            "--no-autodetect",
        ],
    )
    assert result.exit_code == 0
    assert "Uploaded" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("raw_data")
    ds.uploaded_add_file.assert_called_once()
    ds.autodetect_settings.assert_not_called()


def test_dataset_upload_overwrite_blocked_without_yes(patch_client, tmp_path):
    """--overwrite without --yes is blocked by the safety guard."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("col1,col2\na,1")
    result = runner.invoke(
        app,
        [
            "dataset",
            "upload",
            "raw_data",
            str(csv_file),
            "--project",
            "PROJ1",
            "--overwrite",
            "--no-autodetect",
        ],
    )
    assert result.exit_code == 77, result.output


def test_dataset_upload_overwrite_clears_first(patch_client, tmp_path):
    """--overwrite calls ds.clear() before uploading."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("col1,col2\na,1")
    result = runner.invoke(
        app,
        [
            "dataset",
            "upload",
            "raw_data",
            str(csv_file),
            "--project",
            "PROJ1",
            "--overwrite",
            "--yes",
            "--no-autodetect",
        ],
    )
    assert result.exit_code == 0, result.output
    ds = patch_client.get_project("PROJ1").get_dataset("raw_data")
    ds.clear.assert_called_once()
    ds.uploaded_add_file.assert_called_once()


def test_dataset_upload_file_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "upload",
            "raw_data",
            "/nonexistent/file.csv",
            "--project",
            "PROJ1",
        ],
    )
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
    schema_file.write_text(
        json.dumps({"columns": [{"name": "file_col", "type": "bigint"}]})
    )
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-schema",
            "ds1",
            "--definition",
            f"@{schema_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    call_arg = ds.set_definition.call_args[0][0]
    assert call_arg["schema"]["columns"][0]["name"] == "file_col"


def test_dataset_set_schema_plain_array(patch_client):
    """set-schema accepts a plain columns array and auto-wraps it."""
    schema = json.dumps([{"name": "arr_col", "type": "double"}])
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-schema",
            "ds1",
            "--definition",
            schema,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    call_arg = ds.set_definition.call_args[0][0]
    assert call_arg["schema"]["columns"][0]["name"] == "arr_col"
    assert call_arg["schema"]["columns"][0]["type"] == "double"


def test_dataset_set_schema_shorthand_single(patch_client):
    """set-schema accepts 'col type' shorthand for one column."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-schema",
            "ds1",
            "--definition",
            "id int",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    call_arg = ds.set_definition.call_args[0][0]
    assert call_arg["schema"]["columns"] == [{"name": "id", "type": "int"}]


def test_dataset_set_schema_shorthand_multi(patch_client):
    """set-schema accepts 'col1 type1, col2 type2, ...' shorthand."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-schema",
            "ds1",
            "--definition",
            "id int, name string, amount double",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    call_arg = ds.set_definition.call_args[0][0]
    assert call_arg["schema"]["columns"] == [
        {"name": "id", "type": "int"},
        {"name": "name", "type": "string"},
        {"name": "amount", "type": "double"},
    ]


def test_dataset_set_schema_shorthand_with_extra_whitespace(patch_client):
    """Whitespace within and around chunks is forgiving."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-schema",
            "ds1",
            "--definition",
            "  id   bigint ,  flag boolean  ",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    call_arg = ds.set_definition.call_args[0][0]
    assert call_arg["schema"]["columns"] == [
        {"name": "id", "type": "bigint"},
        {"name": "flag", "type": "boolean"},
    ]


def test_dataset_set_schema_shorthand_falls_through_on_three_tokens(patch_client):
    """A chunk that doesn't match 'col type' shape falls through to JSON
    parsing and produces a clean error."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-schema",
            "ds1",
            "--definition",
            "id int extra, name string",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid JSON" in result.output or "JSON" in result.output


def test_dataset_set_schema_json_preferred_when_present(patch_client):
    """JSON-shaped input always parses as JSON, not shorthand."""
    schema = '{"columns": [{"name": "x", "type": "string"}]}'
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-schema",
            "ds1",
            "--definition",
            schema,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    call_arg = ds.set_definition.call_args[0][0]
    assert call_arg["schema"]["columns"] == [{"name": "x", "type": "string"}]

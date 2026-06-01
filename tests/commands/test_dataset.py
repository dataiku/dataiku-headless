"""Tests for dataset commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

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
    names = [d["name"] for d in parsed]
    assert "ds1" in names
    assert "shared_ds" in names  # foreign datasets included by default


def test_dataset_list_with_env(patch_client, monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["dataset", "list"])
    assert result.exit_code == 0


def test_dataset_schema(patch_client):
    result = runner.invoke(app, ["dataset", "schema", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "col1" in result.output


def test_dataset_schema_json(patch_client):
    result = runner.invoke(
        app, ["dataset", "schema", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "col1"


def test_dataset_head(patch_client):
    result = runner.invoke(app, ["dataset", "head", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_dataset_head_columns_filter(patch_client):
    """--columns filters output to specific columns."""
    result = runner.invoke(
        app,
        ["dataset", "head", "ds1", "--columns", "col1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    # Rich renders column headers uppercase; check values are present
    assert "a" in result.output
    assert "b" in result.output


def test_dataset_head_columns_json(patch_client):
    """--columns works with JSON output."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "head",
            "ds1",
            "--columns",
            "col2",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    # Only col2 should be present
    assert list(parsed[0].keys()) == ["col2"]


def test_dataset_head_columns_missing(patch_client):
    """--columns with nonexistent column gives prescriptive error."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "head",
            "ds1",
            "--columns",
            "nonexistent",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "nonexistent" in result.output


def test_dataset_build(patch_client):
    result = runner.invoke(app, ["dataset", "build", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_dataset_build_wait(patch_client):
    result = runner.invoke(
        app, ["dataset", "build", "ds1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0


def test_dataset_build_with_type(patch_client):
    """Build with --type uses job builder."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "build",
            "ds1",
            "--type",
            "RECURSIVE_BUILD",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_called_once_with("RECURSIVE_BUILD")
    builder = proj.new_job.return_value
    builder.with_output.assert_called_once_with("ds1")


def test_dataset_build_with_auto_update_schema(patch_client):
    """Build with --auto-update-schema uses job builder."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "build",
            "ds1",
            "--auto-update-schema",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_job.return_value
    builder.with_auto_update_schema_before_each_recipe_run.assert_called_once_with(True)


def test_dataset_build_recursive_auto_schema_wait(patch_client):
    """Full pipeline build: recursive + auto schema + wait."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "build",
            "ds1",
            "--type",
            "RECURSIVE_BUILD",
            "--auto-update-schema",
            "--wait",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_called_once_with("RECURSIVE_BUILD")


# --- New commands ---


def test_dataset_create_basic(patch_client):
    result = runner.invoke(
        app, ["dataset", "create", "new_ds", "--type", "SQL", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created dataset" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_dataset.assert_called_once()
    call_args = proj.create_dataset.call_args
    assert call_args[0][0] == "new_ds"
    assert call_args[0][1] == "SQL"


def test_dataset_create_success_is_last_line(patch_client):
    """Agents using `dku dataset create … | tail -1` must see the success verdict.

    Regression: the trailing "Tip: code recipes …" info block was the last line
    in batch loops, making every iteration look like a failure.
    """
    result = runner.invoke(
        app, ["dataset", "create", "new_ds", "--type", "SQL", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    last_nonblank = [line for line in result.output.splitlines() if line.strip()][-1]
    assert "Created dataset" in last_nonblank, (
        f"last line was: {last_nonblank!r}; full output:\n{result.output}"
    )


def test_dataset_create_with_connection(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "new_ds",
            "--type",
            "SQL",
            "--connection",
            "my_pg",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_dataset.call_args[1]
    assert call_kwargs["params"]["connection"] == "my_pg"


def test_dataset_create_with_definition(patch_client, tmp_path):
    def_file = tmp_path / "def.json"
    def_file.write_text(
        json.dumps({"type": "SQL", "params": {"connection": "pg_conn"}})
    )
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "new_ds",
            "--type",
            "SQL",
            "--definition",
            f"@{def_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_dataset.call_args[1]
    assert call_kwargs["params"]["connection"] == "pg_conn"


def test_dataset_create_with_definition_format_fields(patch_client, tmp_path):
    def_file = tmp_path / "def.json"
    def_file.write_text(
        json.dumps(
            {
                "type": "S3",
                "params": {"connection": "s3_conn", "path": "/bucket/path"},
                "formatType": "csv",
                "formatParams": {"separator": ","},
            }
        )
    )
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "new_ds",
            "--type",
            "S3",
            "--definition",
            f"@{def_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.create_dataset.call_args
    call_kwargs = call_args[1]
    assert call_args[0][1] == "S3"
    assert call_kwargs["params"] == {"connection": "s3_conn", "path": "/bucket/path"}
    assert call_kwargs["formatType"] == "csv"
    assert call_kwargs["formatParams"] == {"separator": ","}


def test_dataset_create_databricks_with_catalog(patch_client):
    """--catalog wires up Databricks Unity Catalog 3-level namespace."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "sales",
            "--type",
            "Databricks",
            "--connection",
            "dbk",
            "--catalog",
            "prod_catalog",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    params = proj.create_dataset.call_args[1]["params"]
    assert params["catalog"] == "prod_catalog"


def test_dataset_create_jobsdb_with_view(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "metrics",
            "--type",
            "JobsDB",
            "--view",
            "METRICS_HISTORY",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    params = proj.create_dataset.call_args[1]["params"]
    assert params["view"] == "METRICS_HISTORY"


def test_dataset_create_jobsdb_invalid_view(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "metrics",
            "--type",
            "JobsDB",
            "--view",
            "FOO",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid --view" in result.output


def test_dataset_create_redshift_dist_and_sort(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "events",
            "--type",
            "Redshift",
            "--connection",
            "redshift_prod",
            "--dist-style",
            "key",
            "--dist-key",
            "user_id",
            "--sort-key",
            "compound",
            "--sort-key-columns",
            "ts,event_type",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    params = proj.create_dataset.call_args[1]["params"]
    assert params["redshiftDistStyle"] == "KEY"
    assert params["redshiftDistKey"] == "user_id"
    assert params["redshiftSortKey"] == "COMPOUND"
    assert params["redshiftSortKeyColumns"] == ["ts", "event_type"]


def test_dataset_create_bigquery_partitioning(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "events",
            "--type",
            "BigQuery",
            "--connection",
            "bq",
            "--use-bigquery-partitioning",
            "--bigquery-partitioning-type",
            "TIME",
            "--bigquery-partitioning-period",
            "DAY",
            "--require-partition-filter",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    params = proj.create_dataset.call_args[1]["params"]
    assert params["useBigQueryPartitioning"] is True
    assert params["bigQueryPartitioningType"] == "TIME"
    assert params["bigQueryPartitioningPeriod"] == "DAY"
    assert params["requirePartitionFilter"] is True


def test_dataset_create_s3_with_globs_and_metastore(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "raw_files",
            "--type",
            "S3",
            "--connection",
            "s3_prod",
            "--include-glob",
            "*.csv",
            "--include-glob",
            "*.tsv",
            "--exclude-glob",
            "_temp_*",
            "--metastore-sync",
            "--metastore-database",
            "prod",
            "--metastore-table",
            "raw_files",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    params = proj.create_dataset.call_args[1]["params"]
    sel = params["filesSelectionRules"]
    assert {r["expr"] for r in sel["includeRules"]} == {"*.csv", "*.tsv"}
    assert sel["excludeRules"][0]["expr"] == "_temp_*"
    assert params["metastoreSynchronizationEnabled"] is True
    assert params["metastoreDatabase"] == "prod"
    assert params["metastoreTable"] == "raw_files"


def test_dataset_create_csv_format_flags(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "rows",
            "--type",
            "S3",
            "--connection",
            "s3_prod",
            "--with-header",
            "--csv-dialect",
            "excel",
            "--compress",
            "GZIP",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    kwargs = proj.create_dataset.call_args[1]
    fmt = kwargs["formatParams"]
    assert fmt["parseHeaderRow"] is True
    assert fmt["style"] == "excel"
    params = kwargs["params"]
    assert params["compress"] == "GZIP"


def test_dataset_create_postgresql_auto_populates_mode_and_table(patch_client):
    """--type PostgreSQL -c rds (no --definition) should inject mode=table +
    table=${projectKey}_<name> so the dataset is writable by recipes."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "orders",
            "--type",
            "PostgreSQL",
            "--connection",
            "rds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    params = proj.create_dataset.call_args[1]["params"]
    assert params["connection"] == "rds"
    assert params["mode"] == "table"
    assert params["table"] == "${projectKey}_orders"
    assert params["tableCreationMode"] == "auto"


def test_dataset_create_inline_basic(patch_client):
    """--type Inline creates an editable in-DSS dataset (no connection needed)."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "lookup_table",
            "--type",
            "Inline",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    call_args = proj.create_dataset.call_args
    assert call_args[0][1] == "Inline"
    params = call_args[1]["params"]
    # Inline must not carry a connection param
    assert "connection" not in params


def test_dataset_create_inline_with_audit_and_clipboard(patch_client):
    """--keep-track-of-changes + --enable-clipboard-api populate Inline params."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "scoring_rules",
            "--type",
            "Inline",
            "--keep-track-of-changes",
            "--enable-clipboard-api",
            "--import-source",
            "CLIPBOARD",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    params = proj.create_dataset.call_args[1]["params"]
    assert params["keepTrackOfChanges"] is True
    assert params["enableClipboardApi"] is True
    assert params["importSourceType"] == "CLIPBOARD"


def test_dataset_create_inline_invalid_import_source(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "x",
            "--type",
            "Inline",
            "--import-source",
            "BOGUS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid --import-source" in result.output


def test_dataset_create_rejects_inline_flags_on_other_types(patch_client):
    """--keep-track-of-changes on a non-Inline dataset should error."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "x",
            "--type",
            "PostgreSQL",
            "--connection",
            "rds",
            "--keep-track-of-changes",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Inline-dataset flags" in result.output


def test_dataset_create_snowflake_auto_populates_mode_and_table(patch_client):
    """Same fix applies to every SQL subtype (Snowflake, Redshift, ...)."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "sales",
            "--type",
            "Snowflake",
            "--connection",
            "sf_prod",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    params = proj.create_dataset.call_args[1]["params"]
    assert params["mode"] == "table"
    assert params["table"] == "${projectKey}_sales"


def test_dataset_create_postgresql_respects_explicit_definition(patch_client, tmp_path):
    """When --definition is passed, the CLI must NOT auto-populate mode/table."""
    def_file = tmp_path / "def.json"
    def_file.write_text(
        json.dumps(
            {
                "type": "PostgreSQL",
                "params": {"connection": "rds", "mode": "query"},
            }
        )
    )
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "q_only",
            "--type",
            "PostgreSQL",
            "--definition",
            f"@{def_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    params = proj.create_dataset.call_args[1]["params"]
    assert params["mode"] == "query"
    # table should NOT be auto-set when definition was explicit
    assert "table" not in params


def test_dataset_create_filesystem_not_affected_by_sql_defaults(patch_client):
    """Filesystem datasets should NOT get mode/table params."""
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
    # Filesystem goes through new_managed_dataset(), not create_dataset()
    proj = patch_client.get_project("PROJ1")
    proj.new_managed_dataset.assert_called_once_with("fs_ds")


def test_dataset_create_type_sql_prescriptive_license_error(patch_client):
    """--type SQL triggers a DSS license error; the CLI must translate it into
    a prescriptive hint listing the concrete subtypes."""
    proj = patch_client.get_project("PROJ1")
    proj.create_dataset.side_effect = Exception(
        "Your license does not allow you to create a dataset of type SQL"
    )
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "foo",
            "--type",
            "SQL",
            "--connection",
            "rds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "concrete DB subtype" in result.output
    assert "--type PostgreSQL" in result.output
    assert "dku connection list" in result.output


def test_dataset_create_fails_on_conflicting_definition_type(patch_client, tmp_path):
    def_file = tmp_path / "def.json"
    def_file.write_text(json.dumps({"type": "S3", "params": {"connection": "s3_conn"}}))
    result = runner.invoke(
        app,
        [
            "dataset",
            "create",
            "new_ds",
            "--type",
            "SQL",
            "--definition",
            f"@{def_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "conflicts with definition type" in result.output


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
        app, ["dataset", "get-definition", "ds1", "--project", "PROJ1", "-o", "json"]
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


# --- rename ---


def test_dataset_rename(patch_client):
    result = runner.invoke(
        app,
        ["dataset", "rename", "ds1", "--name", "ds1_renamed", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Renamed" in result.output
    assert "ds1_renamed" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.rename.assert_called_once_with("ds1_renamed")


# --- copy ---


def test_dataset_copy(patch_client):
    result = runner.invoke(
        app,
        ["dataset", "copy", "ds1", "--to-project", "PROJ2", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Copied" in result.output
    assert "PROJ2.ds1" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.copy_to.assert_called_once()


def test_dataset_copy_with_name(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "copy",
            "ds1",
            "--to-project",
            "PROJ2",
            "--name",
            "ds1_copy",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "PROJ2.ds1_copy" in result.output


# --- partitions ---


def test_dataset_partitions(patch_client):
    result = runner.invoke(app, ["dataset", "partitions", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "2026-01-01" in result.output
    assert "2026-01-02" in result.output


def test_dataset_partitions_json(patch_client):
    result = runner.invoke(
        app, ["dataset", "partitions", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["partition"] == "2026-01-01"


# --- set-metadata ---


def test_dataset_set_metadata_description(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-metadata",
            "ds1",
            "--description",
            "Customer data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated metadata" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.set_metadata.assert_called_once()
    meta = ds.set_metadata.call_args[0][0]
    assert meta["description"] == "Customer data"


def test_dataset_set_metadata_tags(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-metadata",
            "ds1",
            "--tags",
            "etl,source,v2",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    meta = ds.set_metadata.call_args[0][0]
    assert meta["tags"] == ["etl", "source", "v2"]


def test_dataset_set_metadata_short_desc(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-metadata",
            "ds1",
            "--short-desc",
            "Brief",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    meta = ds.set_metadata.call_args[0][0]
    assert meta["shortDesc"] == "Brief"


def test_dataset_set_metadata_no_args(patch_client):
    result = runner.invoke(
        app, ["dataset", "set-metadata", "ds1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


# --- set-column-description ---


def test_dataset_set_column_description(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-column-description",
            "ds1",
            "col1",
            "First name",
            "col2",
            "Age in years",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated descriptions for 2 column(s)" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.set_definition.assert_called_once()
    ds_def = ds.set_definition.call_args[0][0]
    cols = ds_def["schema"]["columns"]
    assert cols[0]["comment"] == "First name"
    assert cols[1]["comment"] == "Age in years"


def test_dataset_set_column_description_odd_args(patch_client):
    result = runner.invoke(
        app,
        ["dataset", "set-column-description", "ds1", "col1", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "even count" in result.output


def test_dataset_set_column_description_unknown_column(patch_client):
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-column-description",
            "ds1",
            "col1",
            "Known",
            "unknown_col",
            "Missing",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "not in schema" in result.output
    assert "Updated descriptions for 1 column(s)" in result.output


# --- ai-describe ---


def test_dataset_ai_describe(patch_client):
    result = runner.invoke(
        app,
        ["dataset", "ai-describe", "ds1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    assert "Customer transactions" in result.output


def test_dataset_ai_describe_save(patch_client):
    result = runner.invoke(
        app,
        ["dataset", "ai-describe", "ds1", "--save", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "saved" in result.output.lower()
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.generate_ai_description.assert_called_once_with(
        language="english", save_description=True
    )


# --- schema with column descriptions ---


def test_dataset_schema_shows_descriptions(patch_client):
    """Schema command shows description column when comments exist."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_definition.return_value = {
        "schema": {
            "columns": [
                {"name": "col1", "type": "string", "comment": "First name"},
                {"name": "col2", "type": "int", "comment": ""},
            ]
        },
    }
    result = runner.invoke(
        app, ["dataset", "schema", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["description"] == "First name"


# --- info ---


def test_dataset_info_table(patch_client):
    result = runner.invoke(app, ["dataset", "info", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "15,000" in result.output  # row count formatted
    assert "UploadedFiles" in result.output  # dataset type
    assert "csv" in result.output  # format


def test_dataset_info_json(patch_client):
    result = runner.invoke(
        app, ["dataset", "info", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["rows"] == 15000
    assert parsed["size_bytes"] == 2500000
    assert parsed["columns"] == 2
    assert parsed["type"] == "UploadedFiles"
    assert parsed["metrics_computed"] is True


def test_dataset_info_no_metrics(patch_client):
    """When the dataset has never been built, hint points at 'dku dataset build'."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_last_metric_values.side_effect = Exception("No metrics")
    # Ensure get_info() returns no buildEndTime (never built)
    ds.get_info.return_value.get_raw.return_value = {"lastBuild": {}}
    result = runner.invoke(app, ["dataset", "info", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "not computed" in result.output
    assert "dku dataset build" in result.output


def test_dataset_info_stale_metrics_after_build_hints_recompute(patch_client):
    """When the dataset has been built but metrics are stale, hint points at --recompute."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_last_metric_values.side_effect = Exception("No metrics")
    # Mock get_info() to return a recent buildEndTime — ms since epoch
    ds.get_info.return_value.get_raw.return_value = {
        "lastBuild": {"buildEndTime": 1_712_000_000_000, "buildSuccess": True}
    }
    result = runner.invoke(app, ["dataset", "info", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "not computed" in result.output
    assert "--recompute" in result.output
    # The old "dku dataset build" hint must NOT appear for a built dataset
    # (only the --recompute hint should fire).
    assert "dku dataset info ds1 -P PROJ1 --recompute" in result.output


def test_dataset_info_stale_metrics_json_suppresses_hint(patch_client):
    """JSON mode must not emit the stderr hint (keeps programmatic output clean)."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_last_metric_values.side_effect = Exception("No metrics")
    ds.get_info.return_value.get_raw.return_value = {
        "lastBuild": {"buildEndTime": 1_712_000_000_000, "buildSuccess": True}
    }
    result = runner.invoke(
        app, ["dataset", "info", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["rows"] is None
    assert parsed["metrics_computed"] is False
    # No hint in JSON mode
    assert "--recompute" not in result.output


def test_dataset_info_large_dataset_warning(patch_client):
    """Large datasets trigger a warning."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    metrics_mock = ds.get_last_metric_values.return_value
    metrics_mock.get_global_value.side_effect = lambda mid: {
        "records:COUNT_RECORDS": 50_000_000,
        "basic:SIZE": 5_000_000_000,
        "basic:COUNT_FILES": 10,
    }.get(mid, 0)
    result = runner.invoke(app, ["dataset", "info", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Large dataset" in result.output
    assert "High row count" in result.output


def test_dataset_info_partial_metrics(patch_client):
    """When some metrics fail (e.g. row count missing), others still show."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    metrics_mock = ds.get_last_metric_values.return_value

    def _partial_metrics(mid):
        if mid == "records:COUNT_RECORDS":
            raise Exception("No data found for global partition")
        return {"basic:SIZE": 1545633, "basic:COUNT_FILES": 1}.get(mid, 0)

    metrics_mock.get_global_value.side_effect = _partial_metrics
    result = runner.invoke(
        app, ["dataset", "info", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["rows"] is None  # row count failed
    assert parsed["size_bytes"] == 1545633  # size succeeded
    assert parsed["files"] == 1  # files succeeded


def test_dataset_info_recompute_calls_compute_metrics(patch_client):
    """--recompute calls ds.compute_metrics() before reading the cached values."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.compute_metrics.return_value = None
    result = runner.invoke(
        app, ["dataset", "info", "ds1", "--project", "PROJ1", "--recompute"]
    )
    assert result.exit_code == 0
    ds.compute_metrics.assert_called_once_with(
        metric_ids=[
            "records:COUNT_RECORDS",
            "basic:SIZE",
            "basic:COUNT_FILES",
        ]
    )


# --- exists ---


def test_dataset_exists_true(patch_client):
    """Exit code 0 and success message when dataset exists."""
    result = runner.invoke(app, ["dataset", "exists", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "exists" in result.output.lower()
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.exists.assert_called_once()


def test_dataset_exists_false(patch_client):
    """Exit code 1 when dataset does not exist."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.exists.return_value = False
    result = runner.invoke(app, ["dataset", "exists", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_dataset_exists_json_true(patch_client):
    """JSON output returns {exists: true} with exit code 0."""
    result = runner.invoke(
        app, ["dataset", "exists", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["exists"] is True
    assert parsed["name"] == "ds1"
    assert parsed["project"] == "PROJ1"


def test_dataset_exists_json_false(patch_client):
    """JSON output returns {exists: false} with exit code 1."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.exists.return_value = False
    result = runner.invoke(
        app, ["dataset", "exists", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 1
    parsed = json.loads(result.output)
    assert parsed["exists"] is False


def test_dataset_exists_with_env_project(patch_client, monkeypatch):
    """Resolves project from DKU_PROJECT env var."""
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["dataset", "exists", "ds1"])
    assert result.exit_code == 0


# --- usages ---


def test_dataset_usages_table(patch_client):
    """Usages command shows recipes/analyses in table format."""
    result = runner.invoke(app, ["dataset", "usages", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "compute_output" in result.output
    assert "analysis_1" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_usages.assert_called_once()


def test_dataset_usages_json(patch_client):
    """Usages JSON output returns a normalized {type,id,project,name,kind} list.

    Since --include-charts adds INSIGHT and DASHBOARD_TILE rows whose shape
    differs from the raw RECIPE/ANALYSIS rows, we normalize all rows to one
    shape regardless of source — JSON consumers can always filter on `type`.
    """
    result = runner.invoke(
        app, ["dataset", "usages", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["type"] == "RECIPE_INPUT"
    assert parsed[0]["id"] == "compute_output"


def test_dataset_usages_empty(patch_client):
    """Empty usages shows informational message."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_usages.return_value = []
    result = runner.invoke(app, ["dataset", "usages", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "no usages" in result.output.lower()


def test_dataset_usages_empty_json(patch_client):
    """Empty usages in JSON returns empty list."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_usages.return_value = []
    result = runner.invoke(
        app, ["dataset", "usages", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == []


def test_dataset_usages_env_project(patch_client, monkeypatch):
    """Resolves project from DKU_PROJECT env var."""
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["dataset", "usages", "ds1"])
    assert result.exit_code == 0
    assert "compute_output" in result.output


# --- lineage ---


def test_dataset_lineage_table(patch_client):
    """Lineage command shows column relations in table format."""
    result = runner.invoke(
        app,
        ["dataset", "lineage", "ds1", "--column", "revenue", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "raw_input" in result.output
    assert "revenue_raw" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_column_lineage.assert_called_once_with("revenue", max_dataset_count=None)


def test_dataset_lineage_json(patch_client):
    """Lineage JSON output returns raw list from dataikuapi."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "lineage",
            "ds1",
            "--column",
            "revenue",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["inputDataset"] == "PROJ1.raw_input"
    assert parsed[0]["inputColumn"] == "revenue_raw"


def test_dataset_lineage_empty(patch_client):
    """No lineage shows informational message."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_column_lineage.return_value = []
    result = runner.invoke(
        app,
        ["dataset", "lineage", "ds1", "--column", "id", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "no lineage" in result.output.lower()


def test_dataset_lineage_with_max_datasets(patch_client):
    """--max-datasets passes through to dataikuapi."""
    result = runner.invoke(
        app,
        [
            "dataset",
            "lineage",
            "ds1",
            "--column",
            "revenue",
            "--max-datasets",
            "5",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_column_lineage.assert_called_once_with("revenue", max_dataset_count=5)


def test_dataset_lineage_requires_column(patch_client):
    """--column is required."""
    result = runner.invoke(app, ["dataset", "lineage", "ds1", "--project", "PROJ1"])
    assert result.exit_code != 0


# --- detect ---


def test_dataset_detect_table(patch_client):
    """Detect shows format and schema without saving."""
    result = runner.invoke(app, ["dataset", "detect", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "csv" in result.output.lower()
    assert "col1" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.autodetect_settings.assert_called_once_with(infer_storage_types=False)
    ds.autodetect_settings.return_value.save.assert_not_called()


def test_dataset_detect_save(patch_client):
    """--save persists detected settings and shows success message."""
    result = runner.invoke(
        app, ["dataset", "detect", "ds1", "--save", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "saved" in result.output.lower()
    assert "csv" in result.output.lower()
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.autodetect_settings.return_value.save.assert_called_once()


def test_dataset_detect_infer_types(patch_client):
    """--infer-types passes through to autodetect_settings."""
    result = runner.invoke(
        app,
        ["dataset", "detect", "ds1", "--infer-types", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.autodetect_settings.assert_called_once_with(infer_storage_types=True)


def test_dataset_detect_json(patch_client):
    """JSON output returns format_type, format_params, columns."""
    result = runner.invoke(
        app, ["dataset", "detect", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["format_type"] == "csv"
    assert len(parsed["columns"]) == 2
    assert parsed["columns"][0]["name"] == "col1"


def test_dataset_detect_all_string_warning(patch_client):
    """Warns when all columns detected as STRING."""
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.autodetect_settings.return_value.get_raw.return_value = {
        "formatType": "csv",
        "formatParams": {},
        "schema": {
            "columns": [
                {"name": "col1", "type": "string"},
                {"name": "col2", "type": "string"},
            ]
        },
    }
    result = runner.invoke(app, ["dataset", "detect", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "--infer-types" in result.output


# --- zone ---


def test_dataset_zone(patch_client):
    """Shows which zone a dataset belongs to."""
    result = runner.invoke(app, ["dataset", "zone", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Processing" in result.output
    assert "zone1" in result.output


def test_dataset_zone_json(patch_client):
    result = runner.invoke(
        app, ["dataset", "zone", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["zone_id"] == "zone1"
    assert parsed["zone_name"] == "Processing"


# --- share ---


def test_dataset_share(patch_client):
    result = runner.invoke(
        app,
        ["dataset", "share", "ds1", "--zone", "Analytics", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Shared" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.share_to_zone.assert_called_once_with("Analytics")


# --- unshare ---


def test_dataset_unshare(patch_client):
    result = runner.invoke(
        app,
        ["dataset", "unshare", "ds1", "--zone", "Analytics", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Unshared" in result.output
    ds = patch_client.get_project("PROJ1").get_dataset("ds1")
    ds.unshare_from_zone.assert_called_once_with("Analytics")


# --- analyze-column ---


def _wire_worksheet(patch_client, raw_result, dataset_name="ds1"):
    """Configure create_statistics_worksheet → run_computation → get_raw()."""
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset(dataset_name)
    ws = MagicMock()
    result = MagicMock()
    result.get_raw.return_value = raw_result
    ws.run_computation.return_value = result
    ws.delete.return_value = None
    ds.create_statistics_worksheet.return_value = ws
    return ds, ws


def test_dataset_analyze_column_numeric(patch_client):
    raw = {
        "results": [
            {"type": "count", "count": 1000},
            {"type": "count_distinct", "count": 950},
            {
                "type": "grouped",
                "groups": {
                    "type": "anum",
                    "values": ["10", "20"],
                    "hasOthers": True,
                    "hasAllValues": False,
                },
                "results": [{"count": 300}, {"count": 200}],
            },
            {
                "type": "grouped",
                "groups": {"type": "subset", "filter": {"type": "missing"}},
                "results": [{"count": 50}],
            },
            {"type": "mean", "value": 42.5},
            {"type": "std_dev", "value": 7.25},
            {
                "type": "quantiles",
                "quantiles": [
                    {"freq": 0.0, "quantile": 1},
                    {"freq": 0.5, "quantile": 40},
                    {"freq": 1.0, "quantile": 99},
                ],
            },
        ]
    }
    _wire_worksheet(patch_client, raw)
    result = runner.invoke(
        app, ["dataset", "analyze-column", "ds1", "col2", "--project", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    assert "Column Analysis: ds1.col2" in result.output
    assert "1000" in result.output  # total rows
    assert "5.0%" in result.output  # null rate 50/1000
    assert "42.5" in result.output  # mean
    assert "Top 2 Values" in result.output


def test_dataset_analyze_column_numeric_json(patch_client):
    raw = {
        "results": [
            {"type": "count", "count": 200},
            {"type": "count_distinct", "count": 190},
            {
                "type": "grouped",
                "groups": {
                    "type": "anum",
                    "values": ["a"],
                    "hasOthers": False,
                    "hasAllValues": True,
                },
                "results": [{"count": 150}],
            },
            {
                "type": "grouped",
                "groups": {"type": "subset", "filter": {"type": "missing"}},
                "results": [{"count": 10}],
            },
            {"type": "mean", "value": 5.0},
        ]
    }
    _wire_worksheet(patch_client, raw)
    result = runner.invoke(
        app,
        [
            "dataset",
            "analyze-column",
            "ds1",
            "col2",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["row_count"] == 200
    assert parsed["distinct_count"] == 190
    assert parsed["null_count"] == 10
    assert parsed["mean"] == 5.0
    assert parsed["top_values"][0] == {"value": "a", "count": 150}


def test_dataset_analyze_column_string_infers_zero_null(patch_client):
    # String column: full coverage (hasAllValues + top counts == total) → null 0.
    raw = {
        "results": [
            {"type": "count", "count": 100},
            {"type": "count_distinct", "count": 3},
            {
                "type": "grouped",
                "groups": {
                    "type": "anum",
                    "values": ["x", "y", "z"],
                    "hasOthers": False,
                    "hasAllValues": True,
                },
                "results": [{"count": 60}, {"count": 30}, {"count": 10}],
            },
        ]
    }
    _wire_worksheet(patch_client, raw)
    result = runner.invoke(
        app,
        [
            "dataset",
            "analyze-column",
            "ds1",
            "col1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["null_count"] == 0
    # Inference scratch keys are stripped from the string-column payload.
    assert "has_others" not in parsed
    assert "has_all_values" not in parsed


def test_dataset_analyze_column_not_found(patch_client):
    result = runner.invoke(
        app, ["dataset", "analyze-column", "ds1", "nonexistent", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "Column 'nonexistent' not found" in result.output
    assert "dku dataset schema ds1" in result.output


def test_dataset_analyze_column_deletes_worksheet(patch_client):
    raw = {"results": [{"type": "count", "count": 5}]}
    _, ws = _wire_worksheet(patch_client, raw)
    result = runner.invoke(
        app, ["dataset", "analyze-column", "ds1", "col1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    # Temp worksheet must be cleaned up even on the happy path.
    ws.delete.assert_called_once()

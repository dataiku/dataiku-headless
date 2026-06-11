"""Dataset command tests split from tests/commands/test_dataset.py."""

from __future__ import annotations

import json

from tests.commands.dataset.helpers import app, runner
from tests.helpers import strip_ansi


def test_dataset_list_table(patch_client):
    result = runner.invoke(app, ["dataset", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ds1" in result.output


def test_dataset_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "dataset", "list", "--project", "PROJ1"]
    )
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
        app, ["--format", "json", "dataset", "schema", "ds1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "col1"


def test_dataset_get_schema_alias(patch_client):
    """`get-schema` is a hidden alias for `schema` (recurring agent miss —
    reached for by analogy with get-definition)."""
    result = runner.invoke(
        app, ["--format", "json", "dataset", "get-schema", "ds1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "col1"


def test_dataset_head(patch_client):
    result = runner.invoke(app, ["dataset", "head", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_dataset_head_preserves_column_name_case(patch_client, mock_client):
    """`head` must show real column-name case in headers, not upper-cased.

    The table renderer upper-cases headers by default, but for `head` the
    headers ARE dataset column names — and GREL/Prepare formula references are
    case-sensitive. An agent copying an upper-cased 'STATEANSI' into a formula
    when the column is really 'StateANSI' gets silent nulls / dropped rows.
    """
    ds = mock_client.get_project("PROJ1").get_dataset("ds1")
    ds.get_definition.return_value = {
        "schema": {"columns": [{"name": "StateANSI", "type": "string"}]},
    }
    ds.iter_rows.return_value = iter([["6"], ["17"]])
    result = runner.invoke(app, ["dataset", "head", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "StateANSI" in result.output
    assert "STATEANSI" not in result.output


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
            "--format",
            "json",
            "dataset",
            "head",
            "ds1",
            "--columns",
            "col2",
            "--project",
            "PROJ1",
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
    assert result.exit_code == 2
    stripped = strip_ansi(result.output)
    assert "Invalid value" in stripped


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
    assert result.exit_code == 2
    stripped = strip_ansi(result.output)
    assert "Invalid value" in stripped


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

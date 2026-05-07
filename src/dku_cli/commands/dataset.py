"""dku dataset — list, schema, info, head, build, create, upload, delete, clear, get/set-definition, set-schema, set-metadata, set-column-description, ai-describe, rename, copy, partitions, exists, usages, lineage, detect, zone, share, unshare."""

from __future__ import annotations

import time
from pathlib import Path

import typer

from dku_cli.errors import (
    exit_with_error,
    handle_api_error,
    is_already_exists_error,
    is_not_found_error,
)
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS datasets.")


@app.command("list")
def list_datasets(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List datasets in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        datasets = proj.list_datasets()

        data = []
        for ds in datasets:
            data.append(
                {
                    "name": ds.get("name", ""),
                    "type": ds.get("type", ""),
                    "schema_count": str(len(ds.get("schema", {}).get("columns", []))),
                }
            )

        render(
            data,
            ["name", "type", "schema_count"],
            output_format=output,
            title=f"Datasets ({project_key})",
            headers={"name": "NAME", "type": "TYPE", "schema_count": "COLUMNS"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def schema(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show dataset schema."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds_def = ds.get_definition()
        columns = ds_def.get("schema", {}).get("columns", [])

        has_descriptions = any(col.get("comment") for col in columns)
        if has_descriptions:
            data = [
                {
                    "name": col.get("name", ""),
                    "type": col.get("type", ""),
                    "description": col.get("comment", ""),
                }
                for col in columns
            ]
            keys = ["name", "type", "description"]
        else:
            data = [
                {"name": col.get("name", ""), "type": col.get("type", "")}
                for col in columns
            ]
            keys = ["name", "type"]

        render(
            data,
            keys,
            output_format=output,
            title=f"Schema: {dataset_name}",
        )
    except Exception as e:
        handle_api_error(e)


def _format_bytes(size_bytes: int | float) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 0:
        return "unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{int(size_bytes)} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _format_count(n: int | float) -> str:
    """Format large numbers with commas."""
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return str(n)


_SIZE_WARNING_BYTES = 1_000_000_000  # 1 GB
_ROW_WARNING_COUNT = 10_000_000  # 10M rows


@app.command("info")
def info_cmd(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
    recompute: bool = typer.Option(
        False,
        "--recompute",
        "--fresh",
        help="Recompute metrics (row count, size, file count) instead of reading the cached values. Use after a recipe run to avoid stale numbers — DSS does not auto-recompute metrics on build.",
    ),
) -> None:
    """Show dataset metadata: size, row count, type, connection, last build.

    Use this BEFORE pulling data to understand how large a dataset is.
    Warns when datasets are large (>1GB or >10M rows) to prevent
    accidental expensive operations. Pass --recompute after a build to
    refresh row count, size, and file count metrics.

    Example:
      dku dataset info my_data -P PROJ
      dku dataset info my_data -P PROJ -o json
      dku dataset info my_data -P PROJ --recompute
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)

        if recompute:
            if fmt != "json":
                info("Recomputing metrics...")
            try:
                ds.compute_metrics(
                    metric_ids=[
                        "records:COUNT_RECORDS",
                        "basic:SIZE",
                        "basic:COUNT_FILES",
                    ]
                )
            except Exception as exc:
                if fmt != "json":
                    warn(f"Metric recompute failed: {exc}")

        # --- Definition: type, connection, format, columns ---
        ds_def = ds.get_definition()
        ds_type = ds_def.get("type", "unknown")
        params = ds_def.get("params", {})
        connection_name = params.get("connection", params.get("uploadConnection", ""))
        format_type = ds_def.get("formatType", "")
        columns = ds_def.get("schema", {}).get("columns", [])
        managed = ds_def.get("managed", False)
        tags = ds_def.get("tags", [])

        # --- Build info (from get_info) ---
        last_build_time = None
        build_success = None
        try:
            ds_info = ds.get_info()
            raw_info = ds_info.get_raw()
            last_build = raw_info.get("lastBuild", {})
            if last_build.get("buildEndTime"):
                from datetime import datetime, timezone

                ts = last_build["buildEndTime"] / 1000
                last_build_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M UTC"
                )
            build_success = last_build.get("buildSuccess")
        except Exception:
            pass  # get_info may not be available on all dataset types

        # --- Metrics: row count, data size, file count ---
        row_count = None
        data_size_bytes = None
        file_count = None
        metrics_stale = True

        try:
            metrics = ds.get_last_metric_values()
            available_ids = metrics.get_all_ids()

            # Each metric can independently fail (ID exists but no computed
            # value for the global partition), so wrap each individually.
            if "records:COUNT_RECORDS" in available_ids:
                try:
                    row_count = metrics.get_global_value("records:COUNT_RECORDS")
                    metrics_stale = False
                except Exception:
                    pass
            if "basic:SIZE" in available_ids:
                try:
                    data_size_bytes = metrics.get_global_value("basic:SIZE")
                    metrics_stale = False
                except Exception:
                    pass
            if "basic:COUNT_FILES" in available_ids:
                try:
                    file_count = metrics.get_global_value("basic:COUNT_FILES")
                    metrics_stale = False
                except Exception:
                    pass
        except Exception:
            pass  # Metrics may not be computed yet

        # --- Build result ---
        result = {
            "name": dataset_name,
            "type": ds_type,
            "managed": managed,
            "connection": connection_name or "(none)",
            "format": format_type or "(none)",
            "columns": len(columns),
            "rows": _format_count(row_count)
            if row_count is not None
            else "(not computed)",
            "size": _format_bytes(data_size_bytes)
            if data_size_bytes is not None
            else "(not computed)",
            "files": _format_count(file_count) if file_count is not None else "(n/a)",
            "last_build": last_build_time or "(never built)",
            "build_ok": str(build_success)
            if build_success is not None
            else "(unknown)",
            "tags": ", ".join(tags) if tags else "(none)",
        }

        if fmt == "json":
            # JSON output uses raw numeric values for programmatic use
            json_result = {
                "name": dataset_name,
                "type": ds_type,
                "managed": managed,
                "connection": connection_name or None,
                "format": format_type or None,
                "columns": len(columns),
                "rows": int(row_count) if row_count is not None else None,
                "size_bytes": int(data_size_bytes)
                if data_size_bytes is not None
                else None,
                "size_human": _format_bytes(data_size_bytes)
                if data_size_bytes is not None
                else None,
                "files": int(file_count) if file_count is not None else None,
                "last_build": last_build_time,
                "build_success": build_success,
                "tags": tags,
                "metrics_computed": not metrics_stale,
            }
            render_raw(json_result, output_format="json")
        else:
            data = [{"field": k, "value": v} for k, v in result.items()]
            render(
                data,
                ["field", "value"],
                output_format=fmt,
                title=f"Dataset Info: {dataset_name}",
            )

        # --- Warnings for large datasets ---
        if data_size_bytes is not None and data_size_bytes > _SIZE_WARNING_BYTES:
            warn(
                f"Large dataset: {_format_bytes(data_size_bytes)}. "
                "Use --rows/-n with 'head' to limit data pulled. "
                "Building downstream recipes may incur significant compute cost."
            )
        if row_count is not None and row_count > _ROW_WARNING_COUNT:
            warn(
                f"High row count: {_format_count(row_count)} rows. "
                "Consider sampling before transforming. "
                "Use 'dku recipe create-sampling' to create a sample dataset."
            )
        # Stale-metrics hint — skip in JSON mode so the stderr line doesn't
        # interfere with programmatic consumers that check both streams.
        if metrics_stale and fmt != "json":
            if last_build_time is not None:
                # Dataset has been built but metrics are cached (DSS does
                # NOT auto-recompute on build). Direct the agent to --recompute.
                info(
                    f"Metrics are stale — pass --recompute for fresh row count / size / file count: "
                    f"dku dataset info {dataset_name} -P {project_key} --recompute"
                )
            else:
                # Dataset was never successfully built — no metrics to refresh.
                info(
                    "Metrics not yet computed. Run: "
                    f"dku dataset build {dataset_name} -P {project_key} --wait"
                )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def head(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    rows: int = typer.Option(10, "-n", "--rows", help="Number of rows"),
    filter_columns: str = typer.Option(
        None,
        "--columns",
        "-C",
        help="Comma-separated column names to display (default: all). Use to inspect specific columns before transforming.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Preview first rows of a dataset.

    Use --columns to inspect specific columns before creating recipes:
      dku dataset head INPUT --columns "order_date,price" -P PROJ -n 10
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)

        # Get column names from schema
        ds_def = ds.get_definition()
        all_columns = [
            col.get("name", f"col_{i}")
            for i, col in enumerate(ds_def.get("schema", {}).get("columns", []))
        ]

        # Filter columns if requested
        if filter_columns:
            requested = [c.strip() for c in filter_columns.split(",") if c.strip()]
            missing = [c for c in requested if c not in all_columns]
            if missing:
                exit_with_error(
                    f"Column(s) not found: {missing}",
                    code="invalid_column",
                    details=[
                        f"Available columns: {', '.join(all_columns[:20])}"
                        + (
                            f" ... ({len(all_columns)} total)"
                            if len(all_columns) > 20
                            else ""
                        ),
                        f"Check schema: dku dataset schema {dataset_name} -P {project_key}",
                    ],
                )
            display_columns = requested
        else:
            display_columns = all_columns

        # iter_rows() returns lists, not dicts — zip with column names
        data = []
        for i, row in enumerate(ds.iter_rows()):
            if i >= rows:
                break
            full_row = dict(zip(all_columns, row))
            data.append({c: full_row[c] for c in display_columns})

        render(
            data,
            display_columns,
            output_format=output,
            title=f"{dataset_name} (first {rows} rows)",
        )
        # Table rendering truncates columns aggressively once there are more
        # than ~6 on a typical terminal. Hint the agent toward JSON output.
        if output == "table" and len(display_columns) > 6:
            info(
                f"{len(display_columns)} columns — table output truncates. Use "
                f"'-o json' or '--columns col1,col2' for readable output."
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def build(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
    job_type: str = typer.Option(
        None,
        "--type",
        "-t",
        help="Build type: NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD, RECURSIVE_MISSING_ONLY_BUILD",
    ),
    auto_update_schema: bool = typer.Option(
        False,
        "--auto-update-schema",
        help="Auto-update output schemas before each recipe run",
    ),
) -> None:
    """Trigger dataset build.

    Use --type RECURSIVE_BUILD --auto-update-schema to build the entire upstream
    pipeline with automatic schema propagation.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        from dku_cli.output import error, info, success

        # Use job builder when advanced options are specified
        if job_type or auto_update_schema:
            builder = proj.new_job(job_type or "NON_RECURSIVE_FORCED_BUILD")
            builder.with_output(dataset_name)
            if auto_update_schema:
                builder.with_auto_update_schema_before_each_recipe_run(True)
            job = builder.start()
        else:
            ds = proj.get_dataset(dataset_name)
            job = ds.build()

        success(f"Build started for {dataset_name}")
        info(f"Job ID: {job.id}")
        if auto_update_schema:
            info("Auto-update schema: enabled")

        if wait:
            info("Waiting for completion...")
            while True:
                status = job.get_status()
                state = status.get("baseStatus", {}).get("state", "")
                if state in ("DONE", "FAILED", "ABORTED"):
                    break
                time.sleep(2)
            if state == "DONE":
                success("Build completed successfully")
            else:
                error(f"Build finished with state: {state}")
    except Exception as e:
        handle_api_error(e)


# Dataset types that live on a SQL connection. `dku dataset create --type <T> -c <C>`
# for these types should produce a managed, writable `mode: "table"` dataset by
# default — otherwise the dataset comes up as an unmanaged query-mode dataset
# that no recipe can write to. The canonical list of SQL dataset types exposed
# via dataikuapi's concrete type names.
_SQL_DATASET_TYPES = frozenset(
    {
        "PostgreSQL",
        "MySQL",
        "Snowflake",
        "Redshift",
        "BigQuery",
        "Oracle",
        "SQLServer",
        "Vertica",
        "Teradata",
        "Greenplum",
        "Netezza",
        "Synapse",
        "Databricks",
        "Exasol",
        "SAPHANA",
        "Athena",
        "DB2",
    }
)


@app.command()
def create(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    type_name: str = typer.Option(
        "Filesystem",
        "--type",
        "-t",
        help="Dataset type: Filesystem, UploadedFiles, Inline, PostgreSQL, MySQL, Snowflake, Redshift, BigQuery, Oracle, SQLServer, S3, ... Use the concrete DB name for SQL connections — 'SQL' is rejected by the DSS license system on most instances. Inline = editable spreadsheet-like dataset stored in DSS itself (no connection needed). Default: Filesystem",
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help="Connection name (defaults to filesystem_managed for Filesystem; required for SQL/S3; ignored for Inline)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if dataset already exists"
    ),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="Dataset definition JSON. Supported create-time fields: type, params, formatType, formatParams",
    ),
    keep_track_of_changes: bool = typer.Option(
        False,
        "--keep-track-of-changes",
        help="Inline only: store every edit in an audit log (params.keepTrackOfChanges).",
    ),
    enable_clipboard_api: bool = typer.Option(
        False,
        "--enable-clipboard-api",
        help="Inline only: allow paste-in via DSS UI clipboard API (params.enableClipboardApi).",
    ),
    import_source: str | None = typer.Option(
        None,
        "--import-source",
        help="Inline only: seed source — NONE (default), CLIPBOARD, CSV, FILE. Sets params.importSourceType.",
    ),
    catalog: str | None = typer.Option(
        None,
        "--catalog",
        help="Databricks Unity Catalog name. Sets params.catalog (3-level: catalog.schema.table).",
    ),
    view: str | None = typer.Option(
        None,
        "--view",
        help="JobsDB only: live view to expose. METRICS_HISTORY | CHECK_HISTORY | JOBS_HISTORY. Sets params.view.",
    ),
    with_header: bool | None = typer.Option(
        None,
        "--with-header/--no-header",
        help="CSV/TSV: file has a header row. Sets formatParams.parseHeaderRow.",
    ),
    csv_dialect: str | None = typer.Option(
        None,
        "--csv-dialect",
        help="CSV dialect (excel, unix, etc.). Sets formatParams.style.",
    ),
    compress: str | None = typer.Option(
        None,
        "--compress",
        help="File compression for write: NONE | GZIP | BZIP2 | SNAPPY (filesystem-style outputs). Sets params.compress.",
    ),
    parquet_compression: str | None = typer.Option(
        None,
        "--parquet-compression",
        help="Parquet write codec: SNAPPY (default) | UNCOMPRESSED | GZIP | LZO. Sets formatParams.compressionCodec.",
    ),
    parquet_flavor: str | None = typer.Option(
        None,
        "--parquet-flavor",
        help="Parquet flavor: HIVE (default) | SPARK. Sets formatParams.flavor.",
    ),
    parquet_block_size_mb: int | None = typer.Option(
        None,
        "--parquet-block-size-mb",
        help="Parquet block (row-group) size in MB. Sets formatParams.blockSizeMB.",
    ),
    read_temporal_mode: str | None = typer.Option(
        None,
        "--read-temporal-mode",
        help="Parquet timestamp read mode: TIMESTAMP_NTZ | TIMESTAMP_TZ | LEGACY. Sets formatParams.readTemporalMode.",
    ),
    write_bad_data_behavior: str | None = typer.Option(
        None,
        "--write-bad-data-behavior",
        help="SQL write: DISCARD_ROW | NULL_VALUE | FAIL. Sets params.writeBadDataBehavior.",
    ),
    write_batch_size: int | None = typer.Option(
        None,
        "--write-batch-size",
        help="SQL bulk-load batch size. Sets params.writeBatchSize.",
    ),
    table_creation_mode: str | None = typer.Option(
        None,
        "--table-creation-mode",
        help="SQL table-creation behavior: auto | use_existing | fail_if_missing. Sets params.tableCreationMode.",
    ),
    no_drop_on_schema_mismatch: bool = typer.Option(
        False,
        "--no-drop-on-schema-mismatch",
        help="SQL: do NOT drop and recreate the table when the input schema diverges. Sets params.dropOnSchemaMismatch=false.",
    ),
    write_descriptions_as_comment: bool = typer.Option(
        False,
        "--write-descriptions-as-comment",
        help="SQL: emit column descriptions as DB column comments. Sets params.writeDescriptionsAsComment=true.",
    ),
    num_partitions: int | None = typer.Option(
        None,
        "--num-partitions",
        help="SQL/HDFS write parallelism. Sets params.numPartitions.",
    ),
    datetime_notz_read_mode: str | None = typer.Option(
        None,
        "--datetime-notz-read-mode",
        help="SQL date+time-without-tz read interpretation. Sets params.dateTimeNoTZReadMode.",
    ),
    dateonly_read_mode: str | None = typer.Option(
        None,
        "--dateonly-read-mode",
        help="SQL date-only read interpretation. Sets params.dateOnlyReadMode.",
    ),
    dist_style: str | None = typer.Option(
        None,
        "--dist-style",
        help="Redshift distribution style: AUTO | KEY | ALL | EVEN. Sets params.redshiftDistStyle.",
    ),
    dist_key: str | None = typer.Option(
        None,
        "--dist-key",
        help="Redshift KEY-style distribution column. Sets params.redshiftDistKey.",
    ),
    sort_key: str | None = typer.Option(
        None,
        "--sort-key",
        help="Redshift sort-key kind: COMPOUND | INTERLEAVED. Sets params.redshiftSortKey.",
    ),
    sort_key_columns: str | None = typer.Option(
        None,
        "--sort-key-columns",
        help="Redshift sort-key columns (comma-separated). Sets params.redshiftSortKeyColumns[].",
    ),
    use_bigquery_partitioning: bool = typer.Option(
        False,
        "--use-bigquery-partitioning",
        help="BigQuery: enable native time partitioning. Sets params.useBigQueryPartitioning=true.",
    ),
    bigquery_partitioning_type: str | None = typer.Option(
        None,
        "--bigquery-partitioning-type",
        help="BigQuery partitioning type: TIME | INTEGER_RANGE. Sets params.bigQueryPartitioningType.",
    ),
    bigquery_partitioning_period: str | None = typer.Option(
        None,
        "--bigquery-partitioning-period",
        help="BigQuery partitioning period: DAY | HOUR | MONTH | YEAR. Sets params.bigQueryPartitioningPeriod.",
    ),
    require_partition_filter: bool = typer.Option(
        False,
        "--require-partition-filter",
        help="BigQuery: require a partition filter in queries. Sets params.requirePartitionFilter=true.",
    ),
    upload_provider: str | None = typer.Option(
        None,
        "--upload-provider",
        help="UploadedFiles backend: LOCAL | S3 | AZURE | GCS. Sets params.uploadProvider.",
    ),
    metastore_sync: bool = typer.Option(
        False,
        "--metastore-sync",
        help="S3/Azure/GCS: synchronise to the Hive metastore on build. Sets params.metastoreSynchronizationEnabled=true.",
    ),
    metastore_database: str | None = typer.Option(
        None,
        "--metastore-database",
        help="Hive metastore database name. Sets params.metastoreDatabase.",
    ),
    metastore_table: str | None = typer.Option(
        None,
        "--metastore-table",
        help="Hive metastore table name. Sets params.metastoreTable.",
    ),
    include_glob: list[str] | None = typer.Option(
        None,
        "--include-glob",
        help="File-selection include glob (repeatable). Adds to params.filesSelectionRules.includeRules[].",
    ),
    exclude_glob: list[str] | None = typer.Option(
        None,
        "--exclude-glob",
        help="File-selection exclude glob (repeatable). Adds to params.filesSelectionRules.excludeRules[].",
    ),
    explicit_files: list[str] | None = typer.Option(
        None,
        "--explicit-files",
        help="Explicit file path (repeatable). Adds to params.filesSelectionRules.explicitFiles[].",
    ),
    variable_loop: str | None = typer.Option(
        None,
        "--variable-loop",
        help="Variable expansion loop config: literal JSON, @file.json, or '-' stdin. Sets params.variablesExpansionLoopConfig.",
    ),
) -> None:
    """Create a new dataset.

    For SQL dataset types (PostgreSQL, Snowflake, ...), the CLI auto-populates
    `mode: "table"` and `table: "${projectKey}_<name>"` so the dataset is
    immediately writable by downstream recipes. Without this, DSS creates a
    query-mode unmanaged dataset that no recipe can write to. Pass --definition
    with explicit params to opt out of the auto-populate.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        dataset_definition: dict = {}
        if definition:
            dataset_definition = read_json_input(definition) or {}

        definition_type = dataset_definition.get("type")
        if definition_type is not None and definition_type != type_name:
            raise typer.BadParameter(
                f"--type {type_name!r} conflicts with definition type {definition_type!r}",
                param_hint="--type",
            )

        params = dataset_definition.get("params") or {}
        if connection and "connection" not in params:
            params["connection"] = connection

        dataset_type = definition_type or type_name

        # Auto-populate SQL-type defaults so the dataset is immediately
        # writable. Only applies when the user did NOT pass --definition
        # (which is the "I know what I'm doing" opt-out).
        if dataset_type in _SQL_DATASET_TYPES and not definition:
            params.setdefault("mode", "table")
            params.setdefault("table", "${projectKey}_" + dataset_name)
            params.setdefault("tableCreationMode", "auto")

        # Reject Inline-only flags on non-Inline datasets so agents get a clear
        # error instead of a silent payload-shape mismatch.
        if dataset_type != "Inline" and (
            keep_track_of_changes or enable_clipboard_api or import_source is not None
        ):
            exit_with_error(
                "--keep-track-of-changes / --enable-clipboard-api / --import-source "
                "are Inline-dataset flags.",
                code="invalid_argument",
                details=[
                    f"Use --type Inline (got '{dataset_type}'), or drop these flags."
                ],
            )

        format_params: dict = dataset_definition.get("formatParams") or {}

        # Connection-specific params: catalog (Databricks), view (JobsDB).
        if catalog is not None:
            params["catalog"] = catalog
        if view is not None:
            _VALID_JOBSDB_VIEWS = {"METRICS_HISTORY", "CHECK_HISTORY", "JOBS_HISTORY"}
            if view.upper() not in _VALID_JOBSDB_VIEWS:
                exit_with_error(
                    f"Invalid --view '{view}'.",
                    code="invalid_argument",
                    details=[f"Valid: {', '.join(sorted(_VALID_JOBSDB_VIEWS))}"],
                )
            params["view"] = view.upper()

        # CSV/format flags.
        if with_header is not None:
            format_params["parseHeaderRow"] = bool(with_header)
        if csv_dialect is not None:
            format_params["style"] = csv_dialect
        if compress is not None:
            params["compress"] = compress
        if parquet_compression is not None:
            format_params["compressionCodec"] = parquet_compression
        if parquet_flavor is not None:
            format_params["flavor"] = parquet_flavor
        if parquet_block_size_mb is not None:
            format_params["blockSizeMB"] = parquet_block_size_mb
        if read_temporal_mode is not None:
            format_params["readTemporalMode"] = read_temporal_mode

        # SQL write knobs.
        if write_bad_data_behavior is not None:
            params["writeBadDataBehavior"] = write_bad_data_behavior
        if write_batch_size is not None:
            params["writeBatchSize"] = write_batch_size
        if table_creation_mode is not None:
            params["tableCreationMode"] = table_creation_mode
        if no_drop_on_schema_mismatch:
            params["dropOnSchemaMismatch"] = False
        if write_descriptions_as_comment:
            params["writeDescriptionsAsComment"] = True
        if num_partitions is not None:
            params["numPartitions"] = num_partitions
        if datetime_notz_read_mode is not None:
            params["dateTimeNoTZReadMode"] = datetime_notz_read_mode
        if dateonly_read_mode is not None:
            params["dateOnlyReadMode"] = dateonly_read_mode

        # Redshift-specific knobs.
        if dist_style is not None:
            params["redshiftDistStyle"] = dist_style.upper()
        if dist_key is not None:
            params["redshiftDistKey"] = dist_key
        if sort_key is not None:
            params["redshiftSortKey"] = sort_key.upper()
        if sort_key_columns is not None:
            params["redshiftSortKeyColumns"] = [
                c.strip() for c in sort_key_columns.split(",") if c.strip()
            ]

        # BigQuery partitioning.
        if use_bigquery_partitioning:
            params["useBigQueryPartitioning"] = True
        if bigquery_partitioning_type is not None:
            params["bigQueryPartitioningType"] = bigquery_partitioning_type.upper()
        if bigquery_partitioning_period is not None:
            params["bigQueryPartitioningPeriod"] = bigquery_partitioning_period.upper()
        if require_partition_filter:
            params["requirePartitionFilter"] = True

        # UploadedFiles upload provider.
        if upload_provider is not None:
            params["uploadProvider"] = upload_provider.upper()

        # Metastore (S3/Azure/GCS).
        if metastore_sync:
            params["metastoreSynchronizationEnabled"] = True
        if metastore_database is not None:
            params["metastoreDatabase"] = metastore_database
        if metastore_table is not None:
            params["metastoreTable"] = metastore_table

        # File selection (filesystem-style datasets).
        if include_glob or exclude_glob or explicit_files:
            sel = params.setdefault("filesSelectionRules", {})
            if include_glob:
                sel.setdefault("includeRules", []).extend(
                    [{"expr": g} for g in include_glob]
                )
            if exclude_glob:
                sel.setdefault("excludeRules", []).extend(
                    [{"expr": g} for g in exclude_glob]
                )
            if explicit_files:
                sel.setdefault("explicitFiles", []).extend(explicit_files)
            sel.setdefault("mode", "ALL")

        # Variable-expansion loop config (time/wildcard-based file loops).
        if variable_loop is not None:
            params["variablesExpansionLoopConfig"] = read_json_input(variable_loop)

        # Inline datasets (editable spreadsheet-like, stored in DSS itself).
        # No connection needed; the data lives in the dataset definition.
        if dataset_type == "Inline":
            params.pop("connection", None)
            if keep_track_of_changes:
                params.setdefault("keepTrackOfChanges", True)
            if enable_clipboard_api:
                params.setdefault("enableClipboardApi", True)
            if import_source is not None:
                _VALID_INLINE_IMPORT = {"NONE", "CLIPBOARD", "CSV", "FILE"}
                if import_source.upper() not in _VALID_INLINE_IMPORT:
                    exit_with_error(
                        f"Invalid --import-source '{import_source}'.",
                        code="invalid_argument",
                        details=[f"Valid: {', '.join(sorted(_VALID_INLINE_IMPORT))}"],
                    )
                params.setdefault("importSourceType", import_source.upper())

        # UploadedFiles uses "uploadConnection" param, not "connection".
        # Map --connection to the correct param for this type.
        if dataset_type == "UploadedFiles" and "uploadConnection" not in params:
            if connection:
                params["uploadConnection"] = connection
                params.pop("connection", None)
            else:
                # Try common default upload connections
                try:
                    conns = client.list_connections()
                    conn_names = [c for c in conns]
                    # Prefer the first available upload-friendly connection
                    for candidate in ["dataiku-managed-storage", "filesystem_managed"]:
                        if candidate in conn_names:
                            params["uploadConnection"] = candidate
                            break
                    if "uploadConnection" not in params and conn_names:
                        # Fall back to first available connection
                        params["uploadConnection"] = conn_names[0]
                except Exception:
                    pass  # list_connections may require admin — fall through to create attempt

        if dataset_type == "Filesystem":
            if definition:
                error(
                    "Filesystem dataset creation via --definition is not supported yet. "
                    "Create the dataset with --connection first, then use 'dku dataset set-definition' to configure it."
                )
                raise typer.Exit(1)
            if not connection:
                connection = "filesystem_managed"
            builder = proj.new_managed_dataset(dataset_name)
            builder.with_store_into(connection)
            builder.create()
        else:
            try:
                proj.create_dataset(
                    dataset_name,
                    dataset_type,
                    params=params,
                    formatType=dataset_definition.get("formatType"),
                    formatParams=format_params
                    or dataset_definition.get("formatParams"),
                )
            except Exception as create_err:
                msg = str(create_err).lower()
                if dataset_type == "UploadedFiles" and (
                    "connection" in msg or "target" in msg
                ):
                    exit_with_error(
                        "Cannot create UploadedFiles dataset — no upload connection found.",
                        code="connection_required",
                        details=[
                            "Cloud DSS instances require an explicit upload connection.",
                            f"Fix: dku dataset create {dataset_name} --type UploadedFiles --connection <CONNECTION_NAME> -P {project_key}",
                            "Find connections: dku connection list",
                        ],
                    )
                if dataset_type == "SQL" and ("license" in msg and "sql" in msg):
                    exit_with_error(
                        "'--type SQL' is a catch-all name and is rejected by the DSS license system.",
                        code="invalid_type",
                        details=[
                            "Use the concrete DB subtype instead:",
                            "  --type PostgreSQL / --type MySQL / --type Snowflake /",
                            "  --type Redshift / --type BigQuery / --type Oracle / --type SQLServer",
                            "Run 'dku connection list' to see which connection types your instance has.",
                            f"Example: dku dataset create {dataset_name} --type PostgreSQL -c <YOUR_CONN> -P {project_key}",
                        ],
                    )
                raise
        success(
            f"Created dataset '{dataset_name}' (type={dataset_type}) in {project_key}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(
                f"Dataset '{dataset_name}' already exists in {project_key}, skipping create"
            )
            return
        if is_already_exists_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' already exists in {project_key}.",
                code="already_exists",
                details=[
                    "Use --if-not-exists to skip creation when the dataset exists.",
                    f"Or delete first: dku dataset delete {dataset_name} -P {project_key} --yes",
                ],
            )
        handle_api_error(e)


@app.command()
def upload(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(
        help="Dataset name (must be UploadedFiles type)"
    ),
    local_path: Path = typer.Argument(help="Local file to upload"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    no_autodetect: bool = typer.Option(
        False, "--no-autodetect", help="Skip format/schema auto-detection after upload"
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        "--force",
        "-f",
        help="Clear existing files from the dataset before uploading.",
    ),
) -> None:
    """Upload a file to an UploadedFiles dataset and auto-detect format/schema.

    By default, uploading a file with the same name as an existing upload
    fails. Pass --overwrite to clear the dataset first.
    """
    project_key = resolve_project(project)

    if not local_path.exists():
        from dku_cli.output import error

        error(f"File not found: {local_path}")
        raise typer.Exit(1)

    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)

        if overwrite:
            ds.clear()

        with local_path.open("rb") as f:
            ds.uploaded_add_file(f, local_path.name)

        from dku_cli.output import info

        success(f"Uploaded {local_path.name} → {dataset_name}")

        if not no_autodetect:
            info("Auto-detecting format and schema...")
            detected = ds.autodetect_settings(infer_storage_types=True)
            detected.save()
            schema_cols = detected.get_raw().get("schema", {}).get("columns", [])
            success(
                f"Format detected: {detected.get_raw().get('formatType', 'unknown')} ({len(schema_cols)} columns)"
            )
            # Warn if all columns detected as STRING — common with CSV uploads
            # and causes downstream aggregation failures (group/window SUM)
            if schema_cols:
                from dku_cli.output import warn

                string_cols = [c for c in schema_cols if c.get("type") == "string"]
                if len(string_cols) == len(schema_cols):
                    warn(
                        "All columns detected as STRING. Downstream aggregation "
                        "recipes (group, window) may fail on numeric operations. "
                        f"Fix with: dku dataset set-schema {dataset_name} -d "
                        f"@schema.json -P {project_key}"
                    )
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
    drop_data: bool = typer.Option(
        False,
        "--drop-data",
        help="Accepted for symmetry with 'project delete'; dataset delete always removes backing data.",
    ),
) -> None:
    """Delete a dataset.

    Before deleting, scans for recipes that have this dataset as an input or
    output and warns about cascade effects. When recipes consume the dataset
    as input, deleting it will also delete those recipes.
    """
    project_key = resolve_project(project)
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="dataset.delete",
        subject=f"dataset '{dataset_name}' in project {project_key}",
        yes=yes,
        prompt=f"Permanently delete dataset '{dataset_name}' from project {project_key}? This cannot be undone.",
    )
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)

        # Query dependent recipes BEFORE confirmation so the user sees the
        # full blast radius. ds.get_usages() returns a list of dicts with
        # type/objectType and objectId/id fields — format varies slightly
        # across DSS versions, so handle both shapes.
        dependents: list[tuple[str, str]] = []
        try:
            usages = ds.get_usages() or []
            for u in usages:
                usage_type = u.get("type") or u.get("objectType") or ""
                obj_id = u.get("objectId") or u.get("id") or ""
                if not obj_id:
                    continue
                # Only recipes cascade; analyses and models don't block dataset delete
                if "RECIPE" in usage_type.upper():
                    # Try to determine input vs output role from the usage entry
                    role = u.get("objectRole") or u.get("role") or ""
                    reason = (
                        "uses as input"
                        if "INPUT" in role.upper()
                        else "produces"
                        if "OUTPUT" in role.upper()
                        else "depends on"
                    )
                    dependents.append((obj_id, reason))
        except Exception:
            # Non-fatal: if usages query fails, proceed with delete but warn
            warn(
                f"Could not enumerate dependents of '{dataset_name}' — "
                f"cascade effects unknown. Proceeding."
            )

        if dependents:
            warn(
                f"Deleting '{dataset_name}' will also remove "
                f"{len(dependents)} dependent recipe(s):"
            )
            for recipe_id, reason in dependents:
                warn(f"  - {recipe_id} ({reason})")

        if drop_data:
            info(
                "Note: --drop-data is accepted for symmetry with 'project delete'; "
                "dataset delete always removes backing data."
            )

        ds.delete()
        success(f"Deleted dataset '{dataset_name}' from {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def clear(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Clear all data from a dataset."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="dataset.clear",
        subject=f"dataset '{dataset_name}' in project {project_key}",
        yes=yes,
        prompt=f"Wipe all rows from dataset '{dataset_name}' in project {project_key}? Data cannot be recovered.",
    )
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds.clear()
        success(f"Cleared dataset '{dataset_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the full definition of a dataset as JSON."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds_def = ds.get_definition()
        render_raw(ds_def, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Definition JSON (string, @file.json, or '-' for stdin)",
    ),
) -> None:
    """Set the full definition of a dataset from JSON."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        new_def = read_json_input(definition)
        ds.set_definition(new_def)
        success(f"Updated definition for dataset '{dataset_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("set-schema")
def set_schema(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help=(
            "Schema as JSON (string, @file.json, '-' for stdin) OR shorthand "
            "'col type, col type, ...' (e.g. 'id int, name string, amount double')"
        ),
    ),
) -> None:
    """Set the schema of a dataset from JSON or shorthand.

    Accepts either {"columns": [{name, type}, ...]} or a plain
    [{name, type}, ...] array (auto-wrapped). The array form lets you
    round-trip with 'dku dataset schema -o json'.

    Shorthand: pass 'col1 type1, col2 type2' directly to -d for quick
    edits without a temp file. Example:
      dku dataset set-schema my_ds -d 'id int, name string, amount double' -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        current_def = ds.get_definition()
        schema_input = _parse_schema_input(definition)
        current_def["schema"] = schema_input
        ds.set_definition(current_def)
        success(f"Updated schema for dataset '{dataset_name}'")
    except Exception as e:
        handle_api_error(e)


def _parse_schema_input(value: str) -> dict:
    """Parse a schema definition from JSON, file, stdin, or shorthand.

    Shorthand form is 'col type, col type' — e.g. 'id int, amount double'.
    JSON forms accepted: {"columns": [...]}, plain [...] array, @file.json, '-'.
    """
    shorthand = _parse_schema_shorthand(value)
    if shorthand is not None:
        return shorthand
    try:
        schema_input = read_json_input(value)
    except typer.BadParameter as exc:
        raise typer.BadParameter(
            f"{exc}\n--definition accepts: JSON literal, @file.json, '-' for "
            "stdin, OR shorthand 'col1 type1, col2 type2'."
        ) from exc
    if isinstance(schema_input, list):
        return {"columns": schema_input}
    if isinstance(schema_input, dict):
        return schema_input
    raise typer.BadParameter(
        "--definition must be a JSON object, JSON array, or shorthand "
        "'col type, col type'."
    )


def _parse_schema_shorthand(value: str) -> dict | None:
    """Try to parse 'col type, col type' shorthand. Returns None if not shorthand.

    Bails out (returns None) on any structural ambiguity so the caller falls
    through to JSON parsing. Strict matching: every comma-separated chunk must
    be exactly two whitespace-separated tokens.
    """
    if not value:
        return None
    stripped = value.strip()
    # JSON / file / stdin always wins — never try shorthand on those
    if stripped.startswith(("{", "[", "@", '"')) or stripped == "-":
        return None
    cols = []
    for chunk in stripped.split(","):
        parts = chunk.strip().split()
        if len(parts) != 2:
            return None
        name, ctype = parts
        # Reject obviously non-identifier names (basic sanity)
        if not name or any(c in name for c in '{}[]"\\'):
            return None
        cols.append({"name": name, "type": ctype})
    if not cols:
        return None
    return {"columns": cols}


@app.command()
def rename(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Current dataset name"),
    new_name: str = typer.Option(..., "--name", help="New dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Rename a dataset."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds.rename(new_name)
        success(f"Renamed '{dataset_name}' to '{new_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def copy(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Source dataset name"),
    to_project: str = typer.Option(..., "--to-project", help="Target project key"),
    name: str | None = typer.Option(
        None, "--name", help="Name in target project (default: same name)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Copy a dataset to another project."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        new_name = name or dataset_name
        target_ds = client.get_project(to_project).get_dataset(new_name)
        ds.copy_to(target_ds)
        success(f"Copied '{dataset_name}' to {to_project}.{new_name}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def partitions(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List partitions of a dataset."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        parts = ds.list_partitions()
        data = [{"partition": p} for p in parts]
        render(
            data,
            ["partition"],
            output_format=output,
            title=f"Partitions ({dataset_name})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Dataset description"
    ),
    short_desc: str | None = typer.Option(
        None, "--short-desc", help="Short description (shown in dataset list)"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update dataset description, short description, and/or tags.

    Unlike set-definition, this is a targeted update — no JSON needed.
    Use after creating a dataset to document what it contains.
    """
    if description is None and short_desc is None and tags is None:
        error("Provide --description, --short-desc, and/or --tags to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        meta = ds.get_metadata()

        if description is not None:
            meta["description"] = description
        if short_desc is not None:
            meta["shortDesc"] = short_desc
        if tags is not None:
            meta["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        ds.set_metadata(meta)
        success(f"Updated metadata for dataset '{dataset_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-column-description")
def set_column_description(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    columns: list[str] = typer.Argument(
        help='Column-description pairs: col1 "desc1" col2 "desc2"'
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set descriptions on dataset columns.

    Pass alternating column names and descriptions:
      dku dataset set-column-description DS col1 "Revenue total" col2 "Customer ID" -P PROJ

    Column descriptions appear in the schema view and help document data meaning.
    """
    if len(columns) % 2 != 0:
        exit_with_error(
            "Arguments must be column-description pairs (even count).",
            code="invalid_argument",
            details=[
                'Usage: dku dataset set-column-description DS col1 "desc1" col2 "desc2" -P PROJ',
                f"Got {len(columns)} arguments — must be even (column name, description, column name, description, ...).",
            ],
        )
    pairs = dict(zip(columns[0::2], columns[1::2]))
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds_def = ds.get_definition()
        schema_cols = ds_def.get("schema", {}).get("columns", [])

        updated = 0
        for col in schema_cols:
            if col["name"] in pairs:
                col["comment"] = pairs[col["name"]]
                updated += 1

        # Warn on unknown columns
        known_names = {c["name"] for c in schema_cols}
        unknown = set(pairs.keys()) - known_names
        if unknown:
            warn(f"Column(s) not in schema (skipped): {', '.join(sorted(unknown))}")

        ds.set_definition(ds_def)
        success(f"Updated descriptions for {updated} column(s) in '{dataset_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("ai-describe")
def ai_describe(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    language: str = typer.Option(
        "english",
        "--language",
        "-l",
        help="Language (english, french, german, dutch, portuguese, spanish)",
    ),
    save: bool = typer.Option(
        False, "--save", help="Save generated descriptions to the dataset"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Generate AI-powered descriptions for a dataset and its columns.

    Requires 'Generate Metadata' enabled in DSS AI Services admin settings.
    Rate-limited: 1000 requests/day, then throttled (~60s per request).

    Without --save, displays suggestions. With --save, persists to the dataset.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        result = ds.generate_ai_description(language=language, save_description=save)

        if save:
            success(f"AI descriptions saved to dataset '{dataset_name}'")
        else:
            info("AI-generated descriptions (not saved — use --save to persist):")

        render_raw(result, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def exists(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Check whether a dataset exists (exit code 0 = yes, 1 = no).

    Use before creating datasets to avoid duplicates, or in scripts to
    branch on dataset existence.

    Example:
      dku dataset exists my_data -P PROJ && echo "found"
      dku dataset exists my_data -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        found = ds.exists()

        if fmt == "json":
            render_raw(
                {"exists": found, "name": dataset_name, "project": project_key},
                output_format="json",
            )
        else:
            if found:
                success(f"Dataset '{dataset_name}' exists in {project_key}")
            else:
                info(f"Dataset '{dataset_name}' does not exist in {project_key}")

        raise typer.Exit(0 if found else 1)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _scan_insight_consumers(proj, dataset_name: str) -> list[dict]:
    """Walk every insight in the project; return rows for those whose
    `params.datasetSmartName` matches `dataset_name`.

    Closes the recurring deletion-safety question — bare get_usages()
    only returns recipe / analysis / model bindings, not chart-insight
    bindings. Without this, "is this dataset orphaned?" required a
    hand-rolled jq pipeline across two endpoints.
    """
    rows: list[dict] = []
    try:
        insights = proj.list_insights() or []
    except Exception:
        return rows
    for ins in insights:
        iid = ins.get("id", "")
        if not iid:
            continue
        try:
            raw = proj.get_insight(iid).get_settings().get_raw()
        except Exception:
            continue
        params = raw.get("params") or {}
        smart_name = params.get("datasetSmartName") or params.get("datasetName")
        if smart_name and (
            smart_name == dataset_name or smart_name.endswith(f".{dataset_name}")
        ):
            rows.append(
                {
                    "type": "INSIGHT",
                    "id": iid,
                    "project": raw.get("projectKey", ""),
                    "name": raw.get("name", ""),
                    "kind": raw.get("type", ""),
                }
            )
    return rows


def _scan_dashboard_tile_consumers(
    proj, dataset_name: str, insight_ids_using: set[str]
) -> list[dict]:
    """Walk every dashboard's pages[*].grid.tiles[*]; report tiles whose
    `tileParams.insightId` references an insight that consumes the dataset.

    Insight IDs already known to bind the dataset are passed in via
    `insight_ids_using` so we don't refetch each insight. Direct dataset
    bindings on tiles (rare — most tiles route through insights) are also
    surfaced via `tileParams.datasetSmartName` if present.
    """
    rows: list[dict] = []
    try:
        dashboards = proj.list_dashboards() or []
    except Exception:
        return rows
    for d in dashboards:
        did = d.get("id") if isinstance(d, dict) else None
        if not did:
            continue
        try:
            raw = proj.get_dashboard(did).get_settings().get_raw()
        except Exception:
            continue
        for page in raw.get("pages") or []:
            for tile in (page.get("grid") or {}).get("tiles") or []:
                params = tile.get("tileParams") or {}
                ref_iid = params.get("insightId")
                ref_ds = params.get("datasetSmartName") or params.get("datasetName")
                if (ref_iid and ref_iid in insight_ids_using) or (
                    ref_ds
                    and (ref_ds == dataset_name or ref_ds.endswith(f".{dataset_name}"))
                ):
                    rows.append(
                        {
                            "type": "DASHBOARD_TILE",
                            "id": did,
                            "project": raw.get("projectKey", ""),
                            "name": raw.get("name", ""),
                            "kind": tile.get("tileType", ""),
                        }
                    )
                    # Don't double-count if both fields point at it
                    break
    return rows


@app.command()
def usages(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
    include_charts: bool = typer.Option(
        False,
        "--include-charts",
        help="Also scan insights and dashboard tiles for references "
        "(N+1 calls — only for deletion-safety checks).",
    ),
) -> None:
    """Show what recipes, analyses, or models use this dataset.

    Use to investigate the flow graph: which downstream recipes consume
    this dataset, and which upstream recipes produce it.

    Pass --include-charts to ALSO scan every insight (`params.datasetSmartName`)
    and every dashboard tile (`tileParams.insightId` chained to a matching
    insight). This costs O(insights + dashboards) extra API calls but
    closes the deletion-safety question that bare `usages` can't answer.

    Example:
      dku dataset usages my_data -P PROJ
      dku dataset usages my_data -P PROJ --include-charts
      dku dataset usages my_data -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        ds = proj.get_dataset(dataset_name)
        usage_list = ds.get_usages() or []

        rows: list[dict] = []
        for u in usage_list:
            rows.append(
                {
                    "type": u.get("type", u.get("objectType", "")),
                    "id": u.get("objectId", u.get("id", "")),
                    "project": u.get(
                        "objectProjectKey", u.get("projectKey", project_key)
                    ),
                    "name": "",
                    "kind": "",
                }
            )

        if include_charts:
            insight_rows = _scan_insight_consumers(proj, dataset_name)
            rows.extend(insight_rows)
            insight_ids_using = {r["id"] for r in insight_rows}
            rows.extend(
                _scan_dashboard_tile_consumers(proj, dataset_name, insight_ids_using)
            )

        if fmt == "json":
            render_raw(rows, output_format="json")
            return

        if not rows:
            scope = (
                "any recipe, analysis, model, insight, or dashboard tile"
                if include_charts
                else "any recipe, analysis, or model"
            )
            info(
                f"No usages found for dataset '{dataset_name}' in {project_key}. "
                f"This dataset is not referenced by {scope}."
            )
            if not include_charts:
                info(
                    "  Pass --include-charts to also scan insights and "
                    "dashboard tiles before deleting."
                )
            return

        columns = ["type", "id", "name", "kind", "project"]
        render(
            rows,
            columns,
            output_format=fmt,
            title=f"Usages of {dataset_name}",
            headers={
                "type": "TYPE",
                "id": "ID",
                "name": "NAME",
                "kind": "KIND",
                "project": "PROJECT",
            },
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def lineage(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    column: str = typer.Option(..., "--column", "-c", help="Column name to trace"),
    max_datasets: int | None = typer.Option(
        None,
        "--max-datasets",
        help="Maximum number of datasets to query for lineage (default: DSS hard limit)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Trace a column's provenance across the flow graph.

    Shows which upstream datasets and columns feed into the specified
    column, including cross-project lineage.

    Example:
      dku dataset lineage my_data --column revenue -P PROJ
      dku dataset lineage my_data -c customer_id -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        relations = ds.get_column_lineage(column, max_dataset_count=max_datasets)

        if fmt == "json":
            render_raw(relations, output_format="json")
        else:
            if not relations:
                info(
                    f"No lineage found for column '{column}' in {dataset_name}. "
                    "The column may be a source column with no upstream provenance, "
                    "or lineage has not been computed yet."
                )
                return

            data = []
            for rel in relations:
                # Real API returns inputDataset/inputColumn/outputDataset/outputColumn
                data.append(
                    {
                        "source_dataset": rel.get(
                            "inputDataset", rel.get("sourceDataset", "")
                        ),
                        "source_column": rel.get(
                            "inputColumn", rel.get("sourceColumn", "")
                        ),
                        "target_dataset": rel.get(
                            "outputDataset", rel.get("targetDataset", "")
                        ),
                        "target_column": rel.get(
                            "outputColumn", rel.get("targetColumn", "")
                        ),
                    }
                )

            render(
                data,
                [
                    "source_dataset",
                    "source_column",
                    "target_dataset",
                    "target_column",
                ],
                output_format=fmt,
                title=f"Column Lineage: {dataset_name}.{column}",
                headers={
                    "source_dataset": "SOURCE DS",
                    "source_column": "SOURCE COL",
                    "target_dataset": "TARGET DS",
                    "target_column": "TARGET COL",
                },
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def detect(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    save: bool = typer.Option(
        False, "--save", help="Save detected format and schema to the dataset"
    ),
    infer_types: bool = typer.Option(
        False,
        "--infer-types",
        help="Infer storage types (e.g. int vs string) instead of defaulting to string",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Detect format and schema for a dataset.

    Runs DSS auto-detection to discover the format type, format params,
    and column schema. Works for filesystem, SQL, and Elasticsearch datasets.

    Without --save, shows what was detected. With --save, persists to the dataset.

    Example:
      dku dataset detect my_data -P PROJ
      dku dataset detect my_data --save --infer-types -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        detected = ds.autodetect_settings(infer_storage_types=infer_types)

        raw = detected.get_raw()
        format_type = raw.get("formatType", "")
        schema_cols = raw.get("schema", {}).get("columns", [])

        if fmt == "json":
            render_raw(
                {
                    "format_type": format_type,
                    "format_params": raw.get("formatParams", {}),
                    "columns": schema_cols,
                },
                output_format="json",
            )
        else:
            if save:
                success(
                    f"Detected and saved: {format_type} format, "
                    f"{len(schema_cols)} columns for '{dataset_name}'"
                )
            else:
                info(f"Detected format: {format_type} ({len(schema_cols)} columns)")
                info("Run with --save to persist these settings.")

            if schema_cols:
                data = [
                    {"name": c.get("name", ""), "type": c.get("type", "")}
                    for c in schema_cols
                ]
                render(
                    data,
                    ["name", "type"],
                    output_format=fmt,
                    title=f"Detected Schema: {dataset_name}",
                )

            string_cols = [c for c in schema_cols if c.get("type") == "string"]
            if schema_cols and len(string_cols) == len(schema_cols):
                warn(
                    "All columns detected as STRING. Use --infer-types to detect "
                    "numeric/date types, or fix manually with set-schema."
                )
    except ValueError as e:
        exit_with_error(
            str(e),
            code="unsupported_type",
            details=[
                "Dataset type may not support auto-detection.",
                f"Check type: dku dataset info {dataset_name} -P {project_key}",
            ],
        )
    except typer.Exit:
        raise
    except Exception as e:
        msg = str(e)
        if "Format detection failed" in msg or "empty" in msg.lower():
            exit_with_error(
                f"Format detection failed for '{dataset_name}'.",
                code="detection_failed",
                details=[
                    "The dataset may be empty or have no data to detect from.",
                    f"Upload data first: dku dataset upload {dataset_name} FILE -P {project_key}",
                    f"Or set schema manually: dku dataset set-schema {dataset_name} -d @schema.json -P {project_key}",
                ],
            )
        handle_api_error(e)


@app.command()
def zone(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show which flow zone a dataset belongs to.

    Example:
      dku dataset zone my_data -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        # DSS raises NotFoundException when the dataset is in the default zone
        # (no zone membership has been explicitly set). Treat that as success.
        try:
            z = ds.get_zone()
            zone_id = z.id
            zone_name = z.name
        except Exception as e:
            if is_not_found_error(e) and "flow zone" in str(e).lower():
                zone_id = "default"
                zone_name = "Default"
            else:
                raise

        if fmt == "json":
            render_raw(
                {"zone_id": zone_id, "zone_name": zone_name, "dataset": dataset_name},
                output_format="json",
            )
        else:
            success(
                f"Dataset '{dataset_name}' is in zone '{zone_name}' (ID: {zone_id})"
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def share(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    zone_id: str = typer.Option(
        ..., "--zone", "-z", help="Zone name or ID to share to"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Share a dataset to another flow zone.

    Sharing makes the dataset visible in the target zone without moving it.

    Example:
      dku dataset share my_data --zone Analytics -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds.share_to_zone(zone_id)
        success(f"Shared dataset '{dataset_name}' to zone '{zone_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def unshare(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    zone_id: str = typer.Option(
        ..., "--zone", "-z", help="Zone name or ID to unshare from"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Unshare a dataset from a flow zone.

    Example:
      dku dataset unshare my_data --zone Analytics -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds.unshare_from_zone(zone_id)
        success(f"Unshared dataset '{dataset_name}' from zone '{zone_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# dku dataset metrics — list configured probes, compute, fetch values, history.
# ---------------------------------------------------------------------------

metrics_app = typer.Typer(
    help=(
        "Inspect and compute dataset metrics (row count, size, custom SQL probes). "
        "DSS does NOT auto-recompute metrics on build. Run `dku dataset metrics run` "
        "after a recipe rebuild, otherwise downstream checks see stale numbers."
    )
)
app.add_typer(metrics_app, name="metrics")


@metrics_app.command("list")
def metrics_list(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "",
        "--partition",
        help="Partition identifier. 'ALL' for the whole dataset; default reads the non-partitioned partition.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List configured probes and their last computed values.

    Reads the probe list from `dataset.metrics.probes` (the
    `dataset get-definition` view) and joins it with the cached last
    metric values. A row marked '(not computed)' means the probe is
    configured but hasn't run since the last build — fix with
    `dku dataset metrics run`.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        defn = ds.get_definition()
        probes = defn.get("metrics", {}).get("probes", [])

        cached = None
        try:
            cached = ds.get_last_metric_values(partition=partition)
        except Exception:
            cached = None

        rows = []
        seen_ids: set[str] = set()
        if cached is not None:
            for m in cached.get_raw().get("metrics", []):
                meta = m.get("metric", {})
                metric_id = meta.get("id", "")
                seen_ids.add(metric_id)
                last_values = m.get("lastValues") or []
                if last_values:
                    target = last_values[0]
                    for v in last_values:
                        if v.get("partition") in ("NP", "ALL"):
                            target = v
                            break
                    value = target.get("value", "")
                    computed_at = target.get("computed", 0)
                else:
                    value = "(not computed)"
                    computed_at = 0
                rows.append(
                    {
                        "metric_id": metric_id,
                        "type": meta.get("metricType", ""),
                        "value": value,
                        "computed_at": computed_at,
                    }
                )
        for probe in probes:
            ptype = probe.get("type", "")
            if not probe.get("enabled", True):
                continue
            if ptype in ("basic", "records"):
                continue
            probe_id = probe.get("meta", {}).get("name", ptype)
            if probe_id in seen_ids:
                continue
            rows.append(
                {
                    "metric_id": probe_id,
                    "type": ptype,
                    "value": "(not computed)",
                    "computed_at": 0,
                }
            )

        render(
            rows,
            ["metric_id", "type", "value", "computed_at"],
            output_format=output,
            title=f"Metrics: {dataset_name}",
            headers={
                "metric_id": "METRIC ID",
                "type": "TYPE",
                "value": "VALUE",
                "computed_at": "COMPUTED AT",
            },
        )
        if not rows:
            info("No metrics configured. Add probes via the dataset's Metrics tab.")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@metrics_app.command("get")
def metrics_get(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    metric_id: str = typer.Argument(
        help="Metric ID (e.g. records:COUNT_RECORDS, basic:SIZE)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "",
        "--partition",
        help="Partition identifier. 'ALL' for the whole dataset.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the cached value of a single metric.

    Use `dku dataset metrics list` first to find the metric ID. Returns
    `(not computed)` if the probe is configured but hasn't run since the
    last build — re-run with `dku dataset metrics run`.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json", "table"), default="table")
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        cached = ds.get_last_metric_values(partition=partition)
        try:
            data = cached.get_metric_by_id(metric_id)
        except Exception:
            exit_with_error(
                f"Metric '{metric_id}' is not computed for dataset '{dataset_name}'.",
                code="metric_not_found",
                details=[
                    f"List metrics: dku dataset metrics list {dataset_name} -P {project_key}",
                    f"Compute metrics first: dku dataset metrics run {dataset_name} -P {project_key}",
                ],
            )
        if output == "json":
            render_raw(data, output_format="json")
        else:
            last_values = data.get("lastValues") or []
            if not last_values:
                info("(no values computed)")
                return
            rows = []
            for v in last_values:
                rows.append(
                    {
                        "partition": v.get("partition", ""),
                        "value": v.get("value", ""),
                        "data_type": v.get("dataType", ""),
                        "computed_at": v.get("computed", 0),
                    }
                )
            render(
                rows,
                ["partition", "value", "data_type", "computed_at"],
                output_format=output,
                title=f"Metric: {metric_id}",
                headers={
                    "partition": "PARTITION",
                    "value": "VALUE",
                    "data_type": "TYPE",
                    "computed_at": "COMPUTED AT",
                },
            )
    except typer.Exit:
        raise
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@metrics_app.command("run")
def metrics_run(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "",
        "--partition",
        help="Partition identifier. 'ALL' to compute on the whole dataset.",
    ),
    metric_ids: list[str] = typer.Option(
        [],
        "--metric-id",
        help="Restrict computation to these metric IDs (repeatable). Default: every configured probe.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Recompute metrics on the dataset.

    DSS does NOT auto-refresh metric values on rebuild — call this after
    every build that should produce fresh row-count / size numbers.

    Example:
        dku dataset metrics run my_data -P PROJ
        dku dataset metrics run my_data --metric-id records:COUNT_RECORDS -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ids = list(metric_ids) if metric_ids else None
        report = ds.compute_metrics(partition=partition, metric_ids=ids)
        if output == "json":
            render_raw(report, output_format="json")
            return
        success(f"Computed metrics on dataset '{dataset_name}'")
        # compute_metrics() returns {hasResult, aborted, ..., result: {computed,
        # skipped, ...}}. Older shapes flatten to the top level, so check both.
        body = (
            report.get("result") if isinstance(report.get("result"), dict) else report
        )
        computed = body.get("computed") or []
        skipped = body.get("skipped") or []
        errors = body.get("errors") or report.get("errors") or []
        info(
            f"Probes computed: {len(computed)}, skipped: {len(skipped)}, errors: {len(errors)}"
        )
        for err in errors[:5]:
            warn(f"  {err.get('message', err) if isinstance(err, dict) else err}")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@metrics_app.command("history")
def metrics_history(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    metric_id: str = typer.Argument(help="Metric ID (e.g. records:COUNT_RECORDS)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "",
        "--partition",
        help="Partition identifier. 'ALL' for the whole dataset.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the time-series history of a metric value.

    Useful for spotting drift — e.g. tracking `records:COUNT_RECORDS` over
    several builds to confirm a join hasn't started silently dropping rows.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        history = ds.get_metric_history(metric_id, partition=partition)
        render_raw(history, output_format=output)
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


# ---------------------------------------------------------------------------
# dku dataset checks — modern data-quality rules (DSSDataQualityRuleSet).
# ---------------------------------------------------------------------------

checks_app = typer.Typer(
    help=(
        "Inspect and compute data-quality rules. Modern API "
        "(DSSDataQualityRuleSet) — `compute_rules`, `list_rules`, "
        "`get_status`, `get_last_rules_results`. The legacy `runChecks` "
        "endpoint exposed pre-DSS-12 is intentionally NOT wired up here."
    )
)
app.add_typer(checks_app, name="checks")


@checks_app.command("list")
def checks_list(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "NP",
        "--partition",
        help="Partition identifier. Default 'NP' (non-partitioned). 'ALL' for full dataset.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List data-quality rules with their last results.

    Pulls the rule definitions then joins the last run's outcome
    (OK / WARNING / ERROR / EMPTY). Rules with no recent run show
    outcome='(no result)'.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ruleset = ds.get_data_quality_rules()
        rules = ruleset.list_rules(as_type="dict")
        results_by_id: dict[str, object] = {}
        try:
            last_results = ruleset.get_last_rules_results(partition=partition)
            results_by_id = {r.id: r for r in last_results}
        except Exception:
            pass

        rows = []
        for r in rules:
            rid = r.get("id", "")
            outcome = "(no result)"
            message = ""
            if rid in results_by_id:
                outcome = results_by_id[rid].outcome or "(no result)"
                message = results_by_id[rid].message or ""
            rows.append(
                {
                    "id": rid,
                    "name": r.get("displayName", ""),
                    "metric": r.get("metricId", "") or r.get("type", ""),
                    "outcome": outcome,
                    "message": (message[:60] + "…") if len(message) > 60 else message,
                }
            )

        render(
            rows,
            ["id", "name", "metric", "outcome", "message"],
            output_format=output,
            title=f"Data Quality Rules: {dataset_name}",
            headers={
                "id": "ID",
                "name": "NAME",
                "metric": "METRIC",
                "outcome": "OUTCOME",
                "message": "MESSAGE",
            },
        )
        if not rows:
            info("No data-quality rules configured.")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@checks_app.command("status")
def checks_status(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the overall data-quality status of the dataset.

    For partitioned datasets this is the worst result of the last
    computed partitions.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json", "table"), default="table")
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ruleset = ds.get_data_quality_rules()
        try:
            status = ruleset.get_status()
        except Exception as inner:
            # DSS's no-result response is unstructured: sometimes a 404 with the
            # 'There is no result for this dataset' body, sometimes an empty body
            # that surfaces as a JSON-decode error inside dataikuapi. Either way,
            # if the dataset itself exists, treat it as 'no result yet'.
            try:
                ds.get_definition()
                dataset_exists = True
            except Exception:
                dataset_exists = False
            if not dataset_exists:
                if is_not_found_error(inner):
                    exit_with_error(
                        f"Dataset '{dataset_name}' not found in {project_key}.",
                        code="not_found",
                        status=3,
                        details=[f"List datasets: dku dataset list -P {project_key}"],
                    )
                raise
            if output == "json":
                render_raw({"status": "NO_RESULT"}, output_format="json")
                return
            info(
                "No data-quality results yet. Run rules first: "
                f"dku dataset checks run {dataset_name} -P {project_key}"
            )
            return
        if output == "json":
            render_raw(status, output_format="json")
            return
        rows = []
        if isinstance(status, dict):
            for k, v in status.items():
                rows.append({"field": k, "value": str(v)})
        else:
            rows.append({"field": "status", "value": str(status)})
        render(
            rows,
            ["field", "value"],
            output_format=output,
            title=f"Data Quality Status: {dataset_name}",
        )
    except typer.Exit:
        raise
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@checks_app.command("run")
def checks_run(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "NP",
        "--partition",
        help="Partition identifier. Default 'NP' (non-partitioned). 'ALL' for full dataset.",
    ),
    wait: bool = typer.Option(
        False, "--wait", "-w", help="Wait for the rule computation to finish."
    ),
) -> None:
    """Compute every enabled data-quality rule on the dataset.

    Returns a DSSFuture immediately; pass --wait to block until done. After
    completion, fetch results via `dku dataset checks list <DS>`.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ruleset = ds.get_data_quality_rules()
        future = ruleset.compute_rules(partition=partition)
        success(f"Started data-quality computation on '{dataset_name}'")
        if hasattr(future, "job_id") and future.job_id:
            info(f"Future ID: {future.job_id}")
        if wait:
            info("Waiting for computation to finish...")
            future.wait_for_result()
            success("Computation finished")
            info(
                f"Inspect results: dku dataset checks list {dataset_name} -P {project_key}"
            )
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)

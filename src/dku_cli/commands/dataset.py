"""dku dataset — list, schema, info, head, build, create, upload, delete, clear, get/set-definition, set-schema, set-metadata, set-column-description, ai-describe, rename, copy, partitions, exists, usages, lineage, detect, zone, share, unshare."""

from __future__ import annotations

import time
from pathlib import Path

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
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
        help="Dataset type: Filesystem, UploadedFiles, PostgreSQL, MySQL, Snowflake, Redshift, BigQuery, Oracle, SQLServer, S3, ... Use the concrete DB name for SQL connections — 'SQL' is rejected by the DSS license system on most instances. Default: Filesystem",
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help="Connection name (defaults to filesystem_managed for Filesystem; required for SQL/S3)",
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
                    formatParams=dataset_definition.get("formatParams"),
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
        info(
            "Tip: 'dku recipe create --output-ds NAME' auto-creates the output dataset. "
            "You only need 'dku dataset create' for input/source datasets."
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a dataset."""
    project_key = resolve_project(project)
    if not yes:
        confirm = typer.confirm(f"Delete dataset '{dataset_name}' from {project_key}?")
        if not confirm:
            raise typer.Abort()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds.delete()
        success(f"Deleted dataset '{dataset_name}' from {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def clear(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Clear all data from a dataset."""
    project_key = resolve_project(project)
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
        help="Schema JSON (string, @file.json, or '-' for stdin)",
    ),
) -> None:
    """Set the schema of a dataset from JSON.

    Accepts either {"columns": [{name, type}, ...]} or a plain
    [{name, type}, ...] array (auto-wrapped). The array form lets you
    round-trip with 'dku dataset schema -o json'.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        current_def = ds.get_definition()
        schema_input = read_json_input(definition)
        if isinstance(schema_input, list):
            schema_input = {"columns": schema_input}
        current_def["schema"] = schema_input
        ds.set_definition(current_def)
        success(f"Updated schema for dataset '{dataset_name}'")
    except Exception as e:
        handle_api_error(e)


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


@app.command()
def usages(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show what recipes, analyses, or models use this dataset.

    Use to investigate the flow graph: which downstream recipes consume
    this dataset, and which upstream recipes produce it.

    Example:
      dku dataset usages my_data -P PROJ
      dku dataset usages my_data -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        usage_list = ds.get_usages()

        if fmt == "json":
            render_raw(usage_list, output_format="json")
        else:
            if not usage_list:
                info(
                    f"No usages found for dataset '{dataset_name}' in {project_key}. "
                    "This dataset is not referenced by any recipe or analysis."
                )
                return

            data = []
            for u in usage_list:
                data.append(
                    {
                        "type": u.get("type", u.get("objectType", "")),
                        "id": u.get("objectId", u.get("id", "")),
                        "project": u.get(
                            "objectProjectKey", u.get("projectKey", project_key)
                        ),
                    }
                )

            render(
                data,
                ["type", "id", "project"],
                output_format=fmt,
                title=f"Usages of {dataset_name}",
                headers={"type": "TYPE", "id": "ID", "project": "PROJECT"},
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
        z = ds.get_zone()

        if fmt == "json":
            render_raw(
                {"zone_id": z.id, "zone_name": z.name, "dataset": dataset_name},
                output_format="json",
            )
        else:
            success(f"Dataset '{dataset_name}' is in zone '{z.name}' (ID: {z.id})")
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

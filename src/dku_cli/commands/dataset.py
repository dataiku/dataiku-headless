"""dku dataset — list, schema, head, build, create, upload, delete, clear, get/set-definition, set-schema."""

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

        data = [
            {"name": col.get("name", ""), "type": col.get("type", "")}
            for col in columns
        ]

        render(
            data,
            ["name", "type"],
            output_format=output,
            title=f"Schema: {dataset_name}",
        )
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
                        + (f" ... ({len(all_columns)} total)" if len(all_columns) > 20 else ""),
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


@app.command()
def create(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    type_name: str = typer.Option(
        "Filesystem",
        "--type",
        "-t",
        help="Dataset type (Filesystem, UploadedFiles, SQL, S3). Default: Filesystem",
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
    """Create a new dataset."""
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
) -> None:
    """Upload a file to an UploadedFiles dataset and auto-detect format/schema."""
    project_key = resolve_project(project)

    if not local_path.exists():
        from dku_cli.output import error

        error(f"File not found: {local_path}")
        raise typer.Exit(1)

    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)

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
    """Set the schema of a dataset from JSON."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        current_def = ds.get_definition()
        current_def["schema"] = read_json_input(definition)
        ds.set_definition(current_def)
        success(f"Updated schema for dataset '{dataset_name}'")
    except Exception as e:
        handle_api_error(e)

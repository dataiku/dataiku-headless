"""dku connection — list, test, create, get, update, delete, schemas, tables, sync-acls."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import (
    exit_with_error,
    handle_api_error,
    is_not_found_error,
)
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS connections.")


@app.command("list")
def list_connections(
    ctx: typer.Context,
    conn_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by connection type (e.g. Snowflake, PostgreSQL, S3)",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List connections. Use --type to filter by connection type.

    Example:
      dku connection list
      dku connection list --type Snowflake
    """
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)

        if conn_type:
            # Fast path: list_connections_names returns just names filtered by type
            names = client.list_connections_names(conn_type)
            data = [{"name": n, "type": conn_type} for n in names]
        else:
            connections = client.list_connections()
            data = []
            for name, conn in connections.items():
                data.append(
                    {
                        "name": name,
                        "type": conn.get("type", ""),
                        "allow_write": str(conn.get("allowWrite", "")),
                        "allow_managed": str(conn.get("allowManagedDatasets", "")),
                    }
                )

        if conn_type:
            render(
                data,
                ["name", "type"],
                output_format=output,
                title=f"Connections (type: {conn_type})",
                headers={"name": "NAME", "type": "TYPE"},
            )
        else:
            render(
                data,
                ["name", "type", "allow_write", "allow_managed"],
                output_format=output,
                title="Connections",
                headers={
                    "name": "NAME",
                    "type": "TYPE",
                    "allow_write": "WRITABLE",
                    "allow_managed": "MANAGED",
                },
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Connection name"),
    conn_type: str = typer.Option(
        ..., "--type", "-t", help="Connection type (e.g. PostgreSQL, Snowflake)"
    ),
    definition: Optional[str] = typer.Option(
        None,
        "--definition",
        "-d",
        help="Connection params as JSON (literal, @file.json, or - for stdin)",
    ),
) -> None:
    """Create a new connection."""
    try:
        client = get_client_from_ctx(ctx)
        params = read_json_input(definition) or {}
        client.create_connection(name, conn_type, params)

        success(f"Created connection '{name}' (type: {conn_type})")
    except Exception as e:
        handle_api_error(e)


@app.command()
def test(
    ctx: typer.Context,
    connection_name: str = typer.Argument(help="Connection name"),
) -> None:
    """Test a connection.

    Only works on SQL and cloud connections. Filesystem/LLM connections do not
    support test and will report the limitation prescriptively.
    """
    try:
        client = get_client_from_ctx(ctx)
        conn = client.get_connection(connection_name)
        try:
            result = conn.test()
        except Exception as e:
            msg = str(e)
            # "NotImplementedException" is raised for Filesystem etc.
            if "NotImplementedException" in msg or "Not implemented" in msg:
                exit_with_error(
                    f"Connection '{connection_name}' does not support testing.",
                    code="unsupported_operation",
                    status=2,
                    details=[
                        "Test only works on SQL and cloud connections.",
                        f"Inspect instead: dku connection get {connection_name}",
                    ],
                )
            if is_not_found_error(e) or "does not exist" in msg:
                exit_with_error(
                    f"Connection '{connection_name}' does not exist.",
                    code="not_found",
                    status=3,
                    details=[
                        "List connections: dku connection list",
                    ],
                )
            raise
        # DSS returns "connectionOK" (not "ok") for most connection types.
        ok = result.get("connectionOK", result.get("ok", False))
        if ok:
            success(f"Connection '{connection_name}' is working")
        else:
            msg = (
                result.get("errorMessage")
                or result.get("message")
                or result.get("error")
                or "DSS returned connectionOK=false but no diagnostic message"
            )
            exit_with_error(
                f"Connection '{connection_name}' test failed.",
                code="test_failed",
                status=1,
                details=[f"DSS: {msg}"],
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    name: str = typer.Argument(help="Connection name"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get connection details as JSON (admin only)."""
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        conn = client.get_connection(name)
        settings = conn.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(help="Connection name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must match CONNECTION name to proceed (tier-3 cascade).",
    ),
) -> None:
    """Delete a connection (admin only). Tier-3 cascade — orphans all datasets using it."""
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.CASCADE,
        action="connection.delete",
        subject=f"connection '{name}' (orphans every dataset that uses it)",
        yes=yes,
        target_id=name,
        confirm_name=confirm_name,
        prompt=f"Delete connection '{name}'? This orphans every dataset using it.",
    )
    try:
        client = get_client_from_ctx(ctx)
        conn = client.get_connection(name)
        conn.delete()
        success(f"Deleted connection '{name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    name: str = typer.Argument(help="Connection name"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Full connection definition JSON (from 'connection get')",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Confirm overwrite — breaks datasets if wrong"
    ),
) -> None:
    """Replace a connection's full definition (credential rotation, param changes).

    Workflow:
      dku connection get CONN -o json > /tmp/conn.json
      # edit /tmp/conn.json
      dku connection set-definition CONN -d @/tmp/conn.json --yes

    WARNING: Wrong credentials or URL will break EVERY dataset that uses this
    connection until fixed. Prefer editing one field at a time.
    """
    new_def = read_json_input(definition)
    if not isinstance(new_def, dict):
        exit_with_error(
            "Connection definition must be a JSON object.",
            code="connection_bad_payload",
        )
    if not yes:
        info(
            f"Dry run — would replace connection '{name}' definition. "
            "Pass --yes to execute."
        )
        raise typer.Exit(code=0)
    try:
        client = get_client_from_ctx(ctx)
        conn = client.get_connection(name)
        conn.set_definition(new_def)
        success(
            f"Updated connection '{name}'. Run 'dku connection test {name}' to verify."
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def update(
    ctx: typer.Context,
    name: str = typer.Argument(help="Connection name"),
    params: str | None = typer.Option(
        None, "--params", help="JSON patch for params (inline, @file, -)"
    ),
    usable_by: str | None = typer.Option(
        None,
        "--usable-by",
        help="ALL | ALLOWED (restrict to --allowed-groups)",
    ),
    allowed_groups: str | None = typer.Option(
        None, "--allowed-groups", help="Comma-separated group names"
    ),
    description: str | None = typer.Option(
        None, "--description", help="New description"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm changes"),
) -> None:
    """Patch selected fields on an existing connection. Safer than set-definition.

    Example:
      # Rotate Snowflake password
      dku connection update snowflake --params '{"password":"new-secret"}' --yes

      # Restrict to a group
      dku connection update snowflake --usable-by ALLOWED \\
        --allowed-groups data_team,admin --yes
    """
    if all(v is None for v in (params, usable_by, allowed_groups, description)):
        exit_with_error(
            "Nothing to update — pass at least one of --params, --usable-by, "
            "--allowed-groups, --description.",
            code="connection_update_noop",
        )
    if usable_by is not None and usable_by not in {"ALL", "ALLOWED"}:
        exit_with_error(
            f"--usable-by must be ALL or ALLOWED, got '{usable_by}'.",
            code="connection_bad_usable_by",
        )
    params_patch = read_json_input(params) if params else None
    if params_patch is not None and not isinstance(params_patch, dict):
        exit_with_error(
            "--params must be a JSON object.",
            code="connection_bad_params",
        )

    if not yes:
        info(f"Dry run — would update connection '{name}'. Pass --yes to execute.")
        if params_patch:
            info(f"  • params keys: {sorted(params_patch.keys())}")
        if usable_by:
            info(f"  • usableBy: {usable_by}")
        if allowed_groups is not None:
            info(f"  • allowedGroups: {allowed_groups}")
        if description is not None:
            info(f"  • description: {description}")
        raise typer.Exit(code=0)

    try:
        client = get_client_from_ctx(ctx)
        conn = client.get_connection(name)
        current = conn.get_definition()
        if params_patch:
            current.setdefault("params", {}).update(params_patch)
        if usable_by:
            current["usableBy"] = usable_by
        if allowed_groups is not None:
            current["allowedGroups"] = [
                g.strip() for g in allowed_groups.split(",") if g.strip()
            ]
        if description is not None:
            current["description"] = description
        conn.set_definition(current)
        success(f"Updated connection '{name}'. Run 'dku connection test {name}'.")
    except Exception as e:
        handle_api_error(e)


@app.command()
def schemas(
    ctx: typer.Context,
    connection_name: str = typer.Argument(help="Connection name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List schemas/namespaces available in a SQL or Iceberg connection.

    For SQL connections, lists database schemas. For Iceberg connections,
    lists namespaces. Requires project context for API access.

    Use this before 'dku connection tables' to discover what's available.

    Example:
      dku connection schemas my_postgres -P PROJ
      dku connection schemas my_iceberg -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # Try SQL schemas first (most common), fall back to Iceberg namespaces
        schema_list: list = []
        try:
            schema_list = proj.list_sql_schemas(connection_name)
        except Exception:
            try:
                schema_list = proj.list_iceberg_namespaces(connection_name)
            except Exception:
                pass

        if fmt == "json":
            render_raw(schema_list, output_format="json")
        else:
            if not schema_list:
                info(
                    f"No schemas found for connection '{connection_name}'. "
                    "The connection may not be SQL/Iceberg, or you may lack access. "
                    f"Check connection type: dku connection get {connection_name}"
                )
                return

            data = [{"schema": s} for s in schema_list]
            render(
                data,
                ["schema"],
                output_format=fmt,
                title=f"Schemas ({connection_name})",
                headers={"schema": "SCHEMA"},
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def tables(
    ctx: typer.Context,
    connection_name: str = typer.Argument(help="Connection name"),
    schema_name: str | None = typer.Option(
        None,
        "--schema",
        "-s",
        help="Schema/namespace to list tables from (default: all)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List tables available for import in a SQL or Iceberg connection.

    Discovers what tables exist so agents can create datasets with the
    correct table names. Use --schema to narrow results.

    Example:
      dku connection tables my_postgres -P PROJ
      dku connection tables my_postgres --schema public -P PROJ
      dku connection tables my_iceberg --schema my_namespace -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # Try SQL tables first (most common), fall back to Iceberg tables
        table_list: list = []
        try:
            table_list = proj.list_sql_tables(connection_name, schema_name=schema_name)
        except Exception:
            try:
                table_list = proj.list_iceberg_tables(
                    connection_name, namespace=schema_name
                )
            except Exception:
                pass

        if fmt == "json":
            render_raw(table_list, output_format="json")
        else:
            if not table_list:
                hint = f" in schema '{schema_name}'" if schema_name else ""
                info(
                    f"No tables found for connection '{connection_name}'{hint}. "
                    "Try listing schemas first: "
                    f"dku connection schemas {connection_name} -P {project_key}"
                )
                return

            # Normalize keys — SQL returns {schema, table}, Iceberg returns {namespace, table}
            data = []
            for t in table_list:
                scope = t.get("schema") or t.get("namespace") or ""
                data.append({"schema": scope, "table": t.get("table", "")})

            render(
                data,
                ["schema", "table"],
                output_format=fmt,
                title=f"Tables ({connection_name})",
                headers={"schema": "SCHEMA", "table": "TABLE"},
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("sync-acls")
def sync_acls(
    ctx: typer.Context,
    connection_name: str = typer.Argument(help="Connection name"),
    root: bool = typer.Option(
        True,
        "--root/--datasets",
        help="Sync root ACLs (--root) or dataset ACLs (--datasets)",
    ),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for completion"),
) -> None:
    """Sync HDFS ACLs for a connection (User Isolation with DSS-managed ACLs).

    Example:
      dku connection sync-acls hdfs_conn
      dku connection sync-acls hdfs_conn --datasets
    """
    try:
        from dku_cli.output import success

        client = get_client_from_ctx(ctx)
        conn = client.get_connection(connection_name)
        if root:
            future = conn.sync_root_acls()
        else:
            future = conn.sync_datasets_acls()

        if wait:
            future.wait_for_result()
            mode = "root" if root else "datasets"
            success(f"Synced {mode} ACLs for connection '{connection_name}'")
        else:
            success(f"ACL sync started for connection '{connection_name}'")
    except Exception as e:
        handle_api_error(e)

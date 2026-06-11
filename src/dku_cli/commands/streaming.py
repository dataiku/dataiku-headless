"""dku streaming — list, create, get, delete, schema, set-schema for streaming endpoints."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS streaming endpoints.")


@app.command("list")
def list_endpoints(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List streaming endpoints in a project."""
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        items = proj.list_streaming_endpoints()

        data = []
        for item in items:
            data.append(
                {
                    "id": item.id,
                    "type": item.type,
                }
            )

        if fmt == "json":
            render_raw(data, output_format="json")
        else:
            if not data:
                info(f"No streaming endpoints in {project_key}.")
                return
            render(
                data,
                ["id", "type"],
                output_format=fmt,
                title=f"Streaming Endpoints ({project_key})",
                headers={"id": "ID", "type": "TYPE"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Streaming endpoint name"),
    endpoint_type: str = typer.Option(
        ..., "--type", "-t", help="Type: kafka, httpsse, SQS, KDBPlus"
    ),
    connection: str | None = typer.Option(
        None, "--connection", "-c", help="Connection name"
    ),
    topic: str | None = typer.Option(None, "--topic", help="Kafka topic name"),
    url: str | None = typer.Option(None, "--url", help="HTTP SSE URL"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a streaming endpoint.

    Example:
      dku streaming create my_stream --type kafka --connection kafka_conn --topic events -P PROJ
      dku streaming create my_sse --type httpsse --url https://example.com/stream -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        params = {}
        if connection:
            params["connection"] = connection
        if topic:
            params["topic"] = topic
        if url:
            params["url"] = url

        proj.create_streaming_endpoint(name, endpoint_type, params=params)
        success(
            f"Created streaming endpoint '{name}' (type: {endpoint_type}) in {project_key}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    name: str = typer.Argument(help="Streaming endpoint name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get streaming endpoint settings."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        se = proj.get_streaming_endpoint(name)
        settings = se.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(help="Streaming endpoint name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a streaming endpoint."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="streaming.delete",
        subject=f"streaming endpoint '{name}' in {project_key}",
        yes=yes,
        prompt=f"Delete streaming endpoint '{name}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        se = proj.get_streaming_endpoint(name)
        se.delete()
        success(f"Deleted streaming endpoint '{name}' from {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def schema(
    ctx: typer.Context,
    name: str = typer.Argument(help="Streaming endpoint name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show streaming endpoint schema."""
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        se = proj.get_streaming_endpoint(name)
        s = se.get_schema()
        columns = s.get("columns", [])

        if fmt == "json":
            render_raw(s, output_format="json")
        else:
            if not columns:
                info(f"No schema defined for streaming endpoint '{name}'.")
                return
            data = [
                {"name": c.get("name", ""), "type": c.get("type", "")} for c in columns
            ]
            render(
                data,
                ["name", "type"],
                output_format=fmt,
                title=f"Schema: {name}",
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-schema")
def set_schema(
    ctx: typer.Context,
    name: str = typer.Argument(help="Streaming endpoint name"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Schema JSON (string, @file.json, or '-' for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the schema of a streaming endpoint.

    Example:
      dku streaming set-schema my_stream -d '{"columns":[{"name":"id","type":"string"}]}' -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        se = proj.get_streaming_endpoint(name)
        new_schema = read_json_input(definition)
        se.set_schema(new_schema)
        success(f"Updated schema for streaming endpoint '{name}'")
    except Exception as e:
        handle_api_error(e)

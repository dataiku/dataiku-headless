"""dku agent-tool — list, get, run, delete."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS agent tools.")


@app.command("list")
def list_agent_tools(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List agent tools in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tools = proj.list_agent_tools()

        data = []
        for t in tools:
            data.append(
                {
                    "id": t.get("id", ""),
                    "name": t.get("name", ""),
                    "type": t.get("type", ""),
                }
            )

        render(
            data,
            ["id", "name", "type"],
            output_format=output,
            title=f"Agent Tools ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show agent tool settings."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)
        settings = tool.get_settings()
        raw = settings.get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def run(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    input_data: str | None = typer.Option(
        None, "--input", help="Input JSON (string, @file.json, or - for stdin)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Run an agent tool."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)

        input_dict = read_json_input(input_data) or {}
        result = tool.run(input_dict)

        render_raw(result, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete an agent tool."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)
        tool.delete()
        success(f"Deleted agent tool '{tool_id}'")
    except Exception as e:
        handle_api_error(e)

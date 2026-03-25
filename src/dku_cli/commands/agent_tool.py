"""dku agent-tool — list, get, run, create, types, delete."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

# Known built-in agent tool types in DSS.
# The server accepts these as the `type` param in new_agent_tool().
BUILTIN_TOOL_TYPES = {
    "DatasetRowLookup": "Query rows from a dataset by column values",
    "VectorStoreSearch": "Search a knowledge bank (requires --knowledge-bank)",
    "LLMMeshLLMQuery": "Call another LLM or agent via LLM Mesh",
    "PythonFunction": "Custom Python function tool",
    "RetrieveDatasetSchema": "Get the schema of a dataset",
    "SQLQuery": "Execute SQL queries against a connection",
}

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
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Tool name"),
    tool_type: str = typer.Option(..., "--type", "-t", help="Tool type (run 'dku agent-tool types' to list)"),
    knowledge_bank: str | None = typer.Option(
        None, "--knowledge-bank", "--kb",
        help="Knowledge bank ID (required for VectorStoreSearch)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new agent tool.

    Uses the dataikuapi builder pattern (project.new_agent_tool()).
    Run 'dku agent-tool types' to see valid tool types.

    Examples:
      dku agent-tool create my_lookup --type DatasetRowLookup -P PROJ
      dku agent-tool create my_search --type VectorStoreSearch --kb my_kb -P PROJ
      dku agent-tool create my_llm_tool --type LLMMeshLLMQuery -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        builder = proj.new_agent_tool(tool_type, name=name)

        # VectorStoreSearch requires a knowledge bank
        if tool_type == "VectorStoreSearch":
            if knowledge_bank is None:
                from dku_cli.errors import exit_with_error
                exit_with_error(
                    "VectorStoreSearch tools require --knowledge-bank.",
                    code="missing_param",
                    details=[
                        "Example: dku agent-tool create my_search --type VectorStoreSearch --kb my_kb -P PROJ",
                        "List knowledge banks with: dku knowledge list -P PROJ",
                    ],
                )
            builder.with_knowledge_bank(knowledge_bank)

        tool = builder.create()
        success(f"Created agent tool '{name}' (id={tool.id}, type={tool_type})")
    except Exception as e:
        handle_api_error(e)


@app.command()
def types(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List known built-in agent tool types.

    These are the type names accepted by 'dku agent-tool create --type TYPE'.
    DSS may support additional plugin-provided types not listed here.
    """
    output = resolve_output_format(output)
    data = [{"type": t, "description": d} for t, d in BUILTIN_TOOL_TYPES.items()]
    render(data, ["type", "description"], output_format=output, title="Agent Tool Types")


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

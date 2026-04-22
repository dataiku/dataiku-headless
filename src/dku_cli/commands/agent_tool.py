"""dku agent-tool — list, get, create, set-definition, run, types, delete."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    resolve_knowledge_bank,
    resolve_project,
)
from dku_cli.output import render, render_raw, resolve_output_format, success

# Known built-in agent tool types in DSS (verified on DSS 14.4+).
# The server accepts these as the `type` param in new_agent_tool().
# For custom Python tools, create a plugin with python-agent-tools/ and use
# the Custom_agent_tool_<plugin>_<tool> type format.
BUILTIN_TOOL_TYPES = {
    "DatasetRowLookup": "Query rows from a dataset by column values (use --dataset)",
    "VectorStoreSearch": "Search a knowledge bank (use --knowledge-bank)",
    "LLMMeshLLMQuery": "Call another LLM or agent via LLM Mesh (use --llm)",
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
    tool_type: str = typer.Option(
        ..., "--type", "-t", help="Tool type (run 'dku agent-tool types' to list)"
    ),
    knowledge_bank: str | None = typer.Option(
        None,
        "--knowledge-bank",
        "--kb",
        help="Knowledge bank ID (required for VectorStoreSearch)",
    ),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "--ds",
        help="Dataset name for DatasetRowLookup (auto-detects field name per DSS version)",
    ),
    llm: str | None = typer.Option(
        None,
        "--llm",
        help="LLM ID e.g. openai:conn:gpt-4o (sets llmId for LLMMeshLLMQuery)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new agent tool.

    Built-in types: DatasetRowLookup, VectorStoreSearch, LLMMeshLLMQuery.
    For custom Python tools, build a plugin and use Custom_agent_tool_<plugin>_<tool>.
    Run 'dku agent-tool types' to see built-in types.

    Examples:
      dku agent-tool create my_lookup --type DatasetRowLookup --dataset customers -P PROJ
      dku agent-tool create my_search --type VectorStoreSearch --kb my_kb -P PROJ
      dku agent-tool create my_llm --type LLMMeshLLMQuery --llm openai:conn:gpt-4o -P PROJ
      dku agent-tool create "Web Search" --type Custom_agent_tool_google-search-tool_google-search-tool -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        builder = proj.new_agent_tool(tool_type, name=name)

        # VectorStoreSearch requires a knowledge bank
        if tool_type == "VectorStoreSearch":
            if knowledge_bank is None:
                exit_with_error(
                    "VectorStoreSearch tools require --knowledge-bank.",
                    code="missing_param",
                    details=[
                        "Example: dku agent-tool create my_search --type VectorStoreSearch --kb my_kb -P PROJ",
                        "List knowledge banks with: dku knowledge list -P PROJ",
                    ],
                )
            # Resolve name → ID. DSS stores knowledgeBankRef as the KB ID;
            # passing a name silently breaks the tool at runtime.
            kb = resolve_knowledge_bank(proj, knowledge_bank)
            builder.with_knowledge_bank(kb.id)

        tool = builder.create()

        # Post-creation param configuration for built-in types
        if dataset and tool_type == "DatasetRowLookup":
            settings = tool.get_settings()
            # Detect which field the server uses (datasetRef in DSS 14.5+,
            # datasetSmartName in older versions). Write to existing field,
            # or both if fresh tool for version compatibility.
            if "datasetRef" in settings.params:
                settings.params["datasetRef"] = dataset
            elif "datasetSmartName" in settings.params:
                settings.params["datasetSmartName"] = dataset
            else:
                settings.params["datasetSmartName"] = dataset
                settings.params["datasetRef"] = dataset
            settings.save()
        elif dataset:
            exit_with_error(
                f"--dataset is only for DatasetRowLookup tools, not {tool_type}.",
                code="invalid_param",
                details=[
                    f"Example: dku agent-tool create {name} --type DatasetRowLookup --dataset my_ds -P {project_key}",
                ],
            )

        if llm and tool_type == "LLMMeshLLMQuery":
            settings = tool.get_settings()
            settings.params["llmId"] = llm
            settings.save()
        elif llm:
            exit_with_error(
                f"--llm is only for LLMMeshLLMQuery tools, not {tool_type}.",
                code="invalid_param",
                details=[
                    f"Example: dku agent-tool create {name} --type LLMMeshLLMQuery --llm openai:conn:gpt-4o -P {project_key}",
                ],
            )

        success(f"Created agent tool '{name}' (id={tool.id}, type={tool_type})")
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Definition JSON (string, @file.json, or - for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Update agent tool settings (params, config, etc.)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)
        settings = tool.get_settings()
        raw = settings.get_raw()
        updates = read_json_input(definition)
        raw.update(updates)
        settings.save()
        success(f"Updated agent tool '{tool_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def types(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List known built-in agent tool types.

    These are the type names accepted by 'dku agent-tool create --type TYPE'.
    For custom Python tools, build a plugin with python-agent-tools/ and use
    the type format: Custom_agent_tool_<plugin-id>_<tool-folder-name>

    Example: plugin 'my-tools' with tool folder 'web-search' →
      dku agent-tool create "Web Search" --type Custom_agent_tool_my-tools_web-search -P PROJ
    """
    output = resolve_output_format(output)
    data = [{"type": t, "description": d} for t, d in BUILTIN_TOOL_TYPES.items()]
    data.append(
        {
            "type": "Custom_agent_tool_<plugin-id>_<tool-folder>",
            "description": "Plugin-based tool (build a plugin with python-agent-tools/)",
        }
    )
    render(
        data, ["type", "description"], output_format=output, title="Agent Tool Types"
    )


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
        try:
            result = tool.run(input_dict)
        except Exception as e:
            if "NullPointerException" in str(e) or "null" in str(e).lower():
                exit_with_error(
                    f"Agent tool '{tool_id}' failed with a server-side null error.",
                    code="tool_run_error",
                    details=[
                        "If this is a VectorStoreSearch tool, the knowledge bank must be built first.",
                        f"Build it with: dku knowledge build <KB_ID> --wait -P {project_key}",
                        "To check knowledge banks: dku knowledge list -P "
                        + project_key,
                    ],
                )
            if tool_id.startswith("Custom_agent_tool_"):
                exit_with_error(
                    f"Plugin tool '{tool_id}' failed: {e}",
                    code="plugin_tool_error",
                    details=[
                        "Plugin tools may fail when tested directly — presets and "
                        "connections are only resolved inside agent execution context.",
                        f"Test via the agent instead: dku agent test AGENT_ID -P {project_key}",
                    ],
                )
            raise

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

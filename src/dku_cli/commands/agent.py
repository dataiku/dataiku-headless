"""dku agent — list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm, set-metadata, test."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_text_input,
    resolve_agent,
    resolve_project,
    update_taggable_metadata,
)
from dku_cli.output import error, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS agents.")


@app.command("list")
def list_agents(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List agents in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agents = proj.list_agents()

        data = []
        for a in agents:
            data.append(
                {
                    "id": a.get("id", ""),
                    "name": a.get("name", ""),
                }
            )

        render(
            data,
            ["id", "name"],
            output_format=output,
            title=f"Agents ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Agent name"),
    agent_type: str = typer.Option(
        "TOOLS_USING_AGENT",
        "--type",
        "-t",
        help="Agent type: TOOLS_USING_AGENT, PYTHON_AGENT, PLUGIN_AGENT, STRUCTURED_AGENT",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new agent."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = proj.create_agent(name, type=agent_type)
        success(f"Created agent '{name}' (id={agent.id}, type={agent_type})")
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show agent settings. Accepts agent ID or name."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        settings = agent.get_settings()
        raw = settings.get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete an agent. Accepts agent ID or name."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="agent.delete",
        subject=f"agent '{agent_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete agent '{agent_id}' from project {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        agent.delete()
        success(f"Deleted agent '{agent_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("wake-up")
def wake_up(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Wake up an agent. Accepts agent ID or name."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        agent.wake_up()
        success(f"Agent '{agent_id}' woken up")
    except Exception as e:
        handle_api_error(e)


@app.command()
def shutdown(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Shutdown an agent. Accepts agent ID or name."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        agent.shutdown()
        success(f"Agent '{agent_id}' shut down")
    except Exception as e:
        handle_api_error(e)


@app.command()
def status(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show agent status. Accepts agent ID or name."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        status_data = agent.status()
        render_raw(status_data, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("add-tool")
def add_tool(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    tool_id: str = typer.Option(..., "--tool", help="Tool ID to add"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a tool to an agent's active version. Accepts agent ID or name."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        settings = agent.get_settings()

        # Resolve the active version ID
        active_ver_id = settings.active_version
        if active_ver_id is None:
            version_ids = settings.get_version_ids()
            if not version_ids:
                from dku_cli.output import error

                error("Agent has no versions.")
                raise typer.Exit(1)
            active_ver_id = version_ids[0]

        # Try dataikuapi's version settings API (works for TOOLS_USING_AGENT only)
        ver_settings = settings.get_version_settings(active_ver_id)
        try:
            ver_settings.add_tool(tool_id)
        except (ValueError, AttributeError):
            # Structured agent — add tool to raw settings directly.
            # Use agent type (not key presence) — newly-created STRUCTURED_AGENT
            # may lack the structuredAgentSettings key.
            ver_raw = ver_settings.get_raw()
            agent_raw = settings.get_raw()
            cfg_key = (
                "structuredAgentSettings"
                if agent_raw.get("type") == "STRUCTURED_AGENT"
                else "toolsUsingAgentSettings"
            )
            if cfg_key not in ver_raw:
                ver_raw[cfg_key] = {}
            tools = ver_raw[cfg_key].setdefault("tools", [])
            tools.append({"toolRef": tool_id})
        settings.save()
        success(f"Added tool '{tool_id}' to agent '{agent_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("set-prompt")
def set_prompt(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    prompt: str = typer.Option(
        ...,
        "--prompt",
        help="System prompt: literal string, @file.txt, or '-' for stdin",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the system prompt for an agent's active version. Accepts agent ID or name.

    Examples:
      dku agent set-prompt my_agent --prompt "You are a helpful analyst." -P PROJ
      dku agent set-prompt my_agent --prompt @system_prompt.txt -P PROJ
      echo "You are an analyst." | dku agent set-prompt my_agent --prompt - -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        prompt_text = read_text_input(prompt)
        settings = agent.get_settings()

        # Resolve the active version ID
        active_ver_id = settings.active_version
        if active_ver_id is None:
            version_ids = settings.get_version_ids()
            if not version_ids:
                from dku_cli.output import error

                error("Agent has no versions.")
                raise typer.Exit(1)
            active_ver_id = version_ids[0]

        # Detect agent settings key using agent type (not key presence —
        # newly-created STRUCTURED_AGENT may lack the key).
        ver_settings = settings.get_version_settings(active_ver_id)
        raw = ver_settings.get_raw()
        agent_raw = settings.get_raw()
        if agent_raw.get("type") == "STRUCTURED_AGENT":
            cfg_key = "structuredAgentSettings"
            prompt_field = "systemPromptAppend"
        else:
            cfg_key = "toolsUsingAgentSettings"
            prompt_field = "systemPrompt"
        if cfg_key not in raw:
            raw[cfg_key] = {}
        raw[cfg_key][prompt_field] = prompt_text
        settings.save()
        success(
            f"Set system prompt on agent '{agent_id}' ({len(prompt_text)} chars, field={prompt_field})"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("set-llm")
def set_llm(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    llm_id: str = typer.Option(
        ..., "--llm-id", help="LLM ID to set (e.g. 'openai:conn:gpt-4o')"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the LLM for an agent's active version. Accepts agent ID or name.

    This performs a GET → modify llmId → PUT cycle, preserving existing tools and prompt.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        settings = agent.get_settings()

        # Resolve the active version ID
        active_ver_id = settings.active_version
        if active_ver_id is None:
            version_ids = settings.get_version_ids()
            if not version_ids:
                from dku_cli.output import error

                error("Agent has no versions.")
                raise typer.Exit(1)
            active_ver_id = version_ids[0]

        # Try dataikuapi's property setter (works for TOOLS_USING_AGENT only)
        ver_settings = settings.get_version_settings(active_ver_id)
        try:
            ver_settings.llm_id = llm_id
        except (ValueError, AttributeError):
            # Structured agent — dataikuapi property raises ValueError.
            # Use agent type (not key presence) — newly-created STRUCTURED_AGENT
            # may lack the structuredAgentSettings key.
            ver_raw = ver_settings.get_raw()
            agent_raw = settings.get_raw()
            if agent_raw.get("type") == "STRUCTURED_AGENT":
                ver_raw.setdefault("structuredAgentSettings", {})["llmId"] = llm_id
            else:
                ver_raw.setdefault("toolsUsingAgentSettings", {})["llmId"] = llm_id
        settings.save()
        success(f"Set LLM '{llm_id}' on agent '{agent_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def test(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    query: str = typer.Argument(help="Test query to send to the agent"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(
        None, "-o", "--output", help="Output format (text or json)"
    ),
) -> None:
    """Send a test query to an agent and display the response.

    ALWAYS test agents after creation or modification. Send at least one
    representative query to verify the agent works end-to-end before
    considering it complete.

    Examples:
      dku agent test my_agent "What is the refund policy?" -P PROJ
      dku agent test my_agent "Summarize the latest report" -P PROJ -o json
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("text", "json"), default="text")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)

        # agent.as_llm() returns a DSSLLM handle via get_llm("agent:<id>")
        llm_handle = agent.as_llm()
        completion = llm_handle.new_completion()
        completion.with_message(query)
        result = completion.execute()

        if output == "json":
            detail = {
                "agent_id": agent.id,
                "query": query,
                "response": result.text,
                "success": result.success,
            }
            print(json.dumps(detail, indent=2, default=str))
        else:
            print(result.text)
    except Exception as e:
        handle_api_error(e)


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    agent_ref: str = typer.Argument(help="Agent ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Agent description"
    ),
    short_desc: str | None = typer.Option(
        None, "--short-desc", help="Short description"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update agent description, short description, and/or tags.

    Accepts agent ID or name. No JSON needed — updates metadata fields directly.
    """
    if description is None and short_desc is None and tags is None:
        error("Provide --description, --short-desc, and/or --tags to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_ref)
        settings = agent.get_settings()
        update_taggable_metadata(settings, description, short_desc, tags)
        success(f"Updated metadata for agent '{agent_ref}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

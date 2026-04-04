"""dku agent-hub — list, config, set-config, list-agents, add-agent, remove-agent, set-agent, set-llm, start, stop."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS Agent Hub instances.")

_HUB_TYPE = "agent-hub"


def _resolve_hub(ctx: typer.Context, project_key: str, hub_id: str | None):
    """Find the AgentHub webapp and return (webapp, config dict).

    If hub_id is provided, uses it directly. Otherwise auto-detects by scanning
    project webapps for type containing 'agent-hub'.
    """
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)

    if hub_id:
        webapp = proj.get_webapp(hub_id)
        settings = webapp.get_settings()
        raw = settings.get_raw()
        return webapp, raw.get("config", {})

    # Auto-detect
    webapps = proj.list_webapps()
    hubs = [w for w in webapps if _HUB_TYPE in w.get("type", "")]

    if len(hubs) == 0:
        exit_with_error(
            f"No Agent Hub webapp found in project {project_key}.",
            code="not_found",
            details=[
                "Agent Hub is a plugin webapp — create it in the DSS UI first.",
                "Go to: Project > Web Apps > New Web App > Agent Hub",
            ],
        )
    if len(hubs) > 1:
        hub_list = [f"  {h.get('id', '')} ({h.get('name', '')})" for h in hubs]
        exit_with_error(
            f"Multiple Agent Hub webapps found in {project_key}. Use --hub to specify one.",
            code="ambiguous",
            details=["Available hubs:", *hub_list],
        )

    webapp = proj.get_webapp(hubs[0].get("id", ""))
    settings = webapp.get_settings()
    raw = settings.get_raw()
    return webapp, raw.get("config", {})


def _save_config(webapp, config: dict) -> None:
    """Write the config dict back to the webapp definition."""
    settings = webapp.get_settings()
    raw = settings.get_raw()
    raw["config"] = config
    settings.save()


@app.command("list")
def list_hubs(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List Agent Hub instances in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapps = proj.list_webapps()

        data = []
        for w in webapps:
            if _HUB_TYPE in w.get("type", ""):
                data.append(
                    {
                        "id": w.get("id", ""),
                        "name": w.get("name", ""),
                    }
                )

        render(
            data,
            ["id", "name"],
            output_format=output,
            title=f"Agent Hubs ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def config(
    ctx: typer.Context,
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show Agent Hub configuration."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        _, cfg = _resolve_hub(ctx, project_key, hub)
        render_raw(cfg, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-config")
def set_config(
    ctx: typer.Context,
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Config JSON — merges into current. String, @file.json, or '-' for stdin.",
    ),
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Update Agent Hub configuration from JSON (shallow merge).

    Get current config first: dku agent-hub config -P PROJ -o json

    Examples:
      dku agent-hub set-config -d '{"enable_quick_agents": true}' -P PROJ
      dku agent-hub set-config -d @hub_config.json -P PROJ
    """
    project_key = resolve_project(project)
    try:
        webapp, cfg = _resolve_hub(ctx, project_key, hub)
        updates = read_json_input(definition)
        cfg.update(updates)
        _save_config(webapp, cfg)
        success("Updated Agent Hub configuration")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-agents")
def list_agents(
    ctx: typer.Context,
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List enterprise agents configured in an Agent Hub."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        _, cfg = _resolve_hub(ctx, project_key, hub)
        agents = cfg.get("tool_agent_configurations", [])

        data = []
        for a in agents:
            desc = a.get("tool_agent_description", "")
            data.append(
                {
                    "agent_id": a.get("agent_id", ""),
                    "name": a.get("tool_agent_display_name", ""),
                    "description": desc[:80] + "..." if len(desc) > 80 else desc,
                    "stories": str(a.get("enable_stories", False)),
                }
            )

        render(
            data,
            ["agent_id", "name", "description", "stories"],
            output_format=output,
            title="Enterprise Agents",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-agent")
def add_agent(
    ctx: typer.Context,
    agent_id: str = typer.Option(
        ...,
        "--agent-id",
        help="Agent reference (PROJECT:agent:ID). Find with: dku agent list -P PROJ -o json",
    ),
    name: str = typer.Option(..., "--name", "-n", help="Display name in the Hub"),
    description: str = typer.Option(
        ...,
        "--description",
        help="Description used by LLM for routing (required for orchestration)",
    ),
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an enterprise agent to the Agent Hub.

    The agent must already exist in a DSS project. Use dku agent list -P PROJ
    to find agent IDs, then pass the full reference as PROJECT:agent:ID.
    """
    project_key = resolve_project(project)
    try:
        webapp, cfg = _resolve_hub(ctx, project_key, hub)

        # Check not already present
        agents_ids = cfg.setdefault("agents_ids", [])
        if agent_id in agents_ids:
            warn(f"Agent '{agent_id}' is already in this Agent Hub, skipping")
            return

        # Add to agents_ids
        agents_ids.append(agent_id)

        # Extract project key from agent_id and add to projects_keys
        parts = agent_id.split(":")
        if len(parts) >= 1:
            agent_project = parts[0]
            projects_keys = cfg.setdefault("projects_keys", [])
            if agent_project not in projects_keys:
                projects_keys.append(agent_project)

        # Add to tool_agent_configurations
        configs = cfg.setdefault("tool_agent_configurations", [])
        configs.append(
            {
                "agent_id": agent_id,
                "tool_agent_display_name": name,
                "tool_agent_description": description,
                "agent_system_instructions": "",
                "agent_example_queries": [],
                "enable_stories": False,
            }
        )

        _save_config(webapp, cfg)
        success(f"Added agent '{name}' ({agent_id}) to Agent Hub")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-agent")
def remove_agent(
    ctx: typer.Context,
    agent_id: str = typer.Option(
        ...,
        "--agent-id",
        help="Agent reference to remove (PROJECT:agent:ID)",
    ),
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Remove an enterprise agent from the Agent Hub."""
    project_key = resolve_project(project)
    try:
        webapp, cfg = _resolve_hub(ctx, project_key, hub)

        agents_ids = cfg.get("agents_ids", [])
        if agent_id not in agents_ids:
            available = [
                f"  {a.get('agent_id', '')} ({a.get('tool_agent_display_name', '')})"
                for a in cfg.get("tool_agent_configurations", [])
            ]
            exit_with_error(
                f"Agent '{agent_id}' not found in this Agent Hub.",
                code="not_found",
                details=["Available agents:", *available] if available else [],
            )

        # Remove from agents_ids
        agents_ids.remove(agent_id)

        # Remove from tool_agent_configurations
        configs = cfg.get("tool_agent_configurations", [])
        cfg["tool_agent_configurations"] = [
            c for c in configs if c.get("agent_id") != agent_id
        ]

        _save_config(webapp, cfg)
        success(f"Removed agent '{agent_id}' from Agent Hub")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-agent")
def set_agent(
    ctx: typer.Context,
    agent_id: str = typer.Option(
        ..., "--agent-id", help="Agent reference (PROJECT:agent:ID)"
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="New display name"),
    description: str | None = typer.Option(
        None, "--description", help="New description"
    ),
    examples: str | None = typer.Option(
        None,
        "--examples",
        help='Example queries as JSON array, e.g. \'["Q4 sales?", "Revenue by region"]\'',
    ),
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Update an enterprise agent's display configuration.

    Only provided fields are updated. Get current config:
      dku agent-hub list-agents -P PROJ -o json
    """
    project_key = resolve_project(project)
    try:
        webapp, cfg = _resolve_hub(ctx, project_key, hub)

        configs = cfg.get("tool_agent_configurations", [])
        target = None
        for c in configs:
            if c.get("agent_id") == agent_id:
                target = c
                break

        if target is None:
            available = [
                f"  {c.get('agent_id', '')} ({c.get('tool_agent_display_name', '')})"
                for c in configs
            ]
            exit_with_error(
                f"Agent '{agent_id}' not found in this Agent Hub.",
                code="not_found",
                details=["Available agents:", *available] if available else [],
            )

        if name is not None:
            target["tool_agent_display_name"] = name
        if description is not None:
            target["tool_agent_description"] = description
        if examples is not None:
            try:
                parsed = json.loads(examples)
                if not isinstance(parsed, list):
                    raise ValueError("Expected a JSON array")
                target["agent_example_queries"] = parsed
            except (json.JSONDecodeError, ValueError):
                exit_with_error(
                    "Invalid --examples: must be a JSON array.",
                    code="invalid_input",
                    details=[
                        'Example: --examples \'["What are Q4 sales?", "Show revenue"]\'',
                    ],
                )

        _save_config(webapp, cfg)
        success(f"Updated agent '{agent_id}' configuration")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-llm")
def set_llm(
    ctx: typer.Context,
    llm_id: str = typer.Argument(
        help="LLM ID for orchestration (e.g. openai:conn:gpt-4o). Find with: dku llm list"
    ),
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the orchestrating LLM for the Agent Hub.

    This LLM handles multi-agent routing and must support tool calling.
    """
    project_key = resolve_project(project)
    try:
        webapp, cfg = _resolve_hub(ctx, project_key, hub)
        cfg["default_llm_id"] = llm_id
        _save_config(webapp, cfg)
        success(f"Set Agent Hub LLM to '{llm_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def start(
    ctx: typer.Context,
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Start or restart the Agent Hub backend."""
    project_key = resolve_project(project)
    try:
        webapp, _ = _resolve_hub(ctx, project_key, hub)
        webapp.start_or_restart_backend()
        success("Agent Hub backend started")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def stop(
    ctx: typer.Context,
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Stop the Agent Hub backend."""
    project_key = resolve_project(project)
    try:
        webapp, _ = _resolve_hub(ctx, project_key, hub)
        webapp.stop_backend()
        success("Agent Hub backend stopped")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)

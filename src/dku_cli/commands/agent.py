"""dku agent — list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm, set-prompt, set-metadata, test, list-versions, create-version, set-active-version."""

from __future__ import annotations

import copy
import json
import time

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_text_input,
    resolve_agent,
    resolve_project,
    update_taggable_metadata,
)
from dku_cli.output import (
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage DSS agents.")


# ── Version helpers ─────────────────────────────────────────────────────


def _next_version_id(versions: list) -> str:
    """Pick the next `vN` version id by inspecting existing ids."""
    nums: list[int] = []
    for v in versions:
        vid = v.get("versionId", "")
        if vid.startswith("v"):
            try:
                nums.append(int(vid[1:]))
            except ValueError:
                pass
    return f"v{max(nums) + 1 if nums else 1}"


def _deep_copy_version(settings, source_vid: str | None = None) -> tuple[dict, str]:
    """Deep-copy a version into a new version dict appended to raw['versions'].

    Source defaults to the agent's active version. Returns (new_version_dict, new_vid).
    The new dict is a live reference inside raw['versions'] — mutate it then call
    settings.save() to persist. Caller activates via saved_model.set_active_version()
    (setting raw['activeVersion'] alone is not persisted).
    """
    raw = settings.get_raw()
    versions = raw.get("versions", [])
    if not versions:
        error("Agent has no versions to copy from.")
        raise typer.Exit(1)

    src_vid = source_vid or raw.get("activeVersion") or versions[0]["versionId"]
    source = next((v for v in versions if v.get("versionId") == src_vid), None)
    if source is None:
        error(
            f"Version '{src_vid}' not found. Use `dku agent list-versions` to list available versions."
        )
        raise typer.Exit(1)

    new_vid = _next_version_id(versions)
    new_version = copy.deepcopy(source)
    new_version["versionId"] = new_vid
    now_ms = int(time.time() * 1000)
    tag = {
        "versionNumber": 0,
        "lastModifiedBy": {"login": "api"},
        "lastModifiedOn": now_ms,
    }
    new_version["versionTag"] = tag
    new_version["creationTag"] = dict(tag)
    versions.append(new_version)
    return new_version, new_vid


def _resolve_target_version_raw(
    settings, *, new_version: bool, source_vid: str | None = None
) -> tuple[dict, str | None]:
    """Return (version_raw_dict, new_vid_or_None).

    When new_version is True: deep-copies the source (or active) version, appends it,
    returns the new dict + new id. When False: returns the active version's raw dict
    + None, matching legacy in-place behavior.
    """
    if new_version:
        return _deep_copy_version(settings, source_vid=source_vid)

    active_ver_id = settings.active_version
    if active_ver_id is None:
        version_ids = settings.get_version_ids()
        if not version_ids:
            error("Agent has no versions.")
            raise typer.Exit(1)
        active_ver_id = version_ids[0]
    return settings.get_version_settings(active_ver_id).get_raw(), None


def _activate_version(proj, agent_id: str, new_vid: str) -> None:
    """Flip the active version. Uses saved_model API — setting activeVersion in raw is not persisted."""
    proj.get_saved_model(agent_id).set_active_version(new_vid)


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


@app.command("list-versions")
def list_versions(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List versions of an agent. Active version is marked."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        raw = agent.get_settings().get_raw()
        active = raw.get("activeVersion")
        data = [
            {
                "version_id": v.get("versionId", ""),
                "active": "✓" if v.get("versionId") == active else "",
            }
            for v in raw.get("versions", [])
        ]
        render(
            data,
            ["version_id", "active"],
            output_format=output,
            title=f"Agent versions ({agent_id})",
            headers={"version_id": "VERSION", "active": "ACTIVE"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-version")
def create_version(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    source: str | None = typer.Option(
        None, "--from", help="Source version ID to copy from (default: active version)"
    ),
    activate: bool = typer.Option(
        False, "--activate", help="Make the new version active after creation"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new agent version by deep-copying an existing one.

    Preferred over `set-prompt` / `set-llm` / `add-tool` in-place edits when you
    want a reversible change. The new version inherits prompt, LLM, and tools
    from the source — modify it next with `--new-version`-aware mutators.

    Examples:
      dku agent create-version my_agent -P PROJ
      dku agent create-version my_agent --from v1 --activate -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        settings = agent.get_settings()
        _, new_vid = _deep_copy_version(settings, source_vid=source)
        settings.save()
        if activate:
            _activate_version(proj, agent.id, new_vid)
        suffix = " (now active)" if activate else ""
        success(f"Created version '{new_vid}' on agent '{agent_id}'{suffix}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-active-version")
def set_active_version(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    version_id: str = typer.Argument(help="Version ID to activate (e.g. v2)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Make a specific agent version active.

    Setting `activeVersion` in raw settings does not persist — this command
    uses the saved-model API which is the only path that actually flips the
    active version on the server.

    Examples:
      dku agent set-active-version my_agent v2 -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        existing = [
            v.get("versionId")
            for v in agent.get_settings().get_raw().get("versions", [])
        ]
        if version_id not in existing:
            error(
                f"Version '{version_id}' not found on agent '{agent_id}'. "
                f"Existing: {', '.join(existing) if existing else '(none)'}"
            )
            raise typer.Exit(1)
        _activate_version(proj, agent.id, version_id)
        success(f"Active version of agent '{agent_id}' set to '{version_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-tool")
def add_tool(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    tool_id: str = typer.Option(..., "--tool", help="Tool ID to add"),
    new_version: bool = typer.Option(
        False,
        "--new-version",
        help="Create a new agent version with this change instead of mutating active in place",
    ),
    activate: bool = typer.Option(
        False,
        "--activate",
        help="Activate the new version after creation (requires --new-version)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a tool to an agent's active version. Accepts agent ID or name.

    Pass --new-version to create a fresh version with the added tool (reversible).
    Without it, the active version is mutated in place.
    """
    if activate and not new_version:
        error("--activate requires --new-version.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        settings = agent.get_settings()

        # Only TOOLS_USING_AGENT (Simple Visual Agent) reads a flat tool list from
        # toolsUsingAgentSettings.tools. Structured/Python/plugin agents reference
        # tools elsewhere (structured agents compose them inside blocks), so writing
        # here would silently no-op. Fail loudly instead, matching the SDK's own
        # ValueError("Only valid for Simple Visual Agents").
        if settings.type != "TOOLS_USING_AGENT":
            error(
                f"Cannot add a tool to agent '{agent_id}': add-tool only supports "
                f"TOOLS_USING_AGENT (Simple Visual Agent), but this agent is "
                f"{settings.type}."
            )
            if settings.type == "STRUCTURED_AGENT":
                info(
                    "Structured agents attach tools inside blocks. Configure tools "
                    "in the agent's blocks via the DSS UI."
                )
            raise typer.Exit(1)

        if new_version:
            ver_raw, new_vid = _deep_copy_version(settings)
            ver_raw.setdefault("toolsUsingAgentSettings", {}).setdefault(
                "tools", []
            ).append({"toolRef": tool_id})
            settings.save()
            if activate:
                _activate_version(proj, agent.id, new_vid)
            suffix = " (now active)" if activate else ""
            success(
                f"Added tool '{tool_id}' to agent '{agent_id}' as version '{new_vid}'{suffix}"
            )
            return

        # Legacy in-place behavior
        active_ver_id = settings.active_version
        if active_ver_id is None:
            version_ids = settings.get_version_ids()
            if not version_ids:
                error("Agent has no versions.")
                raise typer.Exit(1)
            active_ver_id = version_ids[0]

        # Idempotency check — bail early if the tool is already attached.
        ver_settings = settings.get_version_settings(active_ver_id)
        ver_raw = ver_settings.get_raw()
        existing_tools = (
            ver_raw.get("toolsUsingAgentSettings", {}).get("tools", []) or []
        )
        if any(t.get("toolRef") == tool_id for t in existing_tools):
            info(
                f"Tool '{tool_id}' already attached to agent '{agent_id}' — no change."
            )
            return

        ver_settings.add_tool(tool_id)
        settings.save()
        success(f"Added tool '{tool_id}' to agent '{agent_id}'")
    except typer.Exit:
        raise
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
    new_version: bool = typer.Option(
        False,
        "--new-version",
        help="Create a new agent version with this prompt instead of mutating active in place",
    ),
    activate: bool = typer.Option(
        False,
        "--activate",
        help="Activate the new version after creation (requires --new-version)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the system prompt for an agent's active version. Accepts agent ID or name.

    Pass --new-version to publish the prompt as a fresh version (reversible).
    Without it, the active version is mutated in place.

    Examples:
      dku agent set-prompt my_agent --prompt "You are a helpful analyst." -P PROJ
      dku agent set-prompt my_agent --prompt @system_prompt.txt --new-version --activate -P PROJ
      echo "You are an analyst." | dku agent set-prompt my_agent --prompt - -P PROJ
    """
    if activate and not new_version:
        error("--activate requires --new-version.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        prompt_text = read_text_input(prompt)
        settings = agent.get_settings()
        agent_raw = settings.get_raw()

        target_ver_raw, new_vid = _resolve_target_version_raw(
            settings, new_version=new_version
        )

        # Detect agent settings key using agent type (not key presence —
        # newly-created STRUCTURED_AGENT may lack the key).
        # Both STRUCTURED_AGENT and TOOLS_USING_AGENT use `systemPromptAppend`
        # on DSS 14.5+. Writing to `systemPrompt` on TOOLS_USING_AGENT silently
        # fails — the agent runtime ignores it and runs with an empty prompt.
        if agent_raw.get("type") == "STRUCTURED_AGENT":
            cfg_key = "structuredAgentSettings"
        else:
            cfg_key = "toolsUsingAgentSettings"
        prompt_field = "systemPromptAppend"
        target_ver_raw.setdefault(cfg_key, {})[prompt_field] = prompt_text
        settings.save()
        if new_version and activate:
            _activate_version(proj, agent.id, new_vid)

        if new_version:
            suffix = " (now active)" if activate else ""
            success(
                f"Set system prompt on agent '{agent_id}' as version '{new_vid}'{suffix} "
                f"({len(prompt_text)} chars, field={prompt_field})"
            )
        else:
            success(
                f"Set system prompt on agent '{agent_id}' ({len(prompt_text)} chars, field={prompt_field})"
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-llm")
def set_llm(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID or name"),
    llm_id: str = typer.Option(
        ..., "--llm-id", help="LLM ID to set (e.g. 'openai:conn:gpt-4o')"
    ),
    new_version: bool = typer.Option(
        False,
        "--new-version",
        help="Create a new agent version with this LLM instead of mutating active in place",
    ),
    activate: bool = typer.Option(
        False,
        "--activate",
        help="Activate the new version after creation (requires --new-version)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the LLM for an agent's active version. Accepts agent ID or name.

    Pass --new-version to publish the LLM change as a fresh version (reversible).
    Without it, the active version is mutated in place (GET → modify llmId → PUT),
    preserving existing tools and prompt.
    """
    if activate and not new_version:
        error("--activate requires --new-version.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
        settings = agent.get_settings()
        agent_raw = settings.get_raw()

        if new_version:
            ver_raw, new_vid = _deep_copy_version(settings)
            cfg_key = (
                "structuredAgentSettings"
                if agent_raw.get("type") == "STRUCTURED_AGENT"
                else "toolsUsingAgentSettings"
            )
            ver_raw.setdefault(cfg_key, {})["llmId"] = llm_id
            settings.save()
            if activate:
                _activate_version(proj, agent.id, new_vid)
            suffix = " (now active)" if activate else ""
            success(
                f"Set LLM '{llm_id}' on agent '{agent_id}' as version '{new_vid}'{suffix}"
            )
            return

        # Legacy in-place behavior
        active_ver_id = settings.active_version
        if active_ver_id is None:
            version_ids = settings.get_version_ids()
            if not version_ids:
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
            if agent_raw.get("type") == "STRUCTURED_AGENT":
                ver_raw.setdefault("structuredAgentSettings", {})["llmId"] = llm_id
            else:
                ver_raw.setdefault("toolsUsingAgentSettings", {})["llmId"] = llm_id
        settings.save()
        success(f"Set LLM '{llm_id}' on agent '{agent_id}'")
    except typer.Exit:
        raise
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

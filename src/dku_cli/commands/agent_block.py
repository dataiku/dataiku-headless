"""dku agent-block — list, get, add, remove, connect, disconnect, set-start, set-mode, get-graph, set-graph."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    resolve_agent,
    resolve_project,
)
from dku_cli.output import render, render_raw, resolve_output_format, success, warn

app = typer.Typer(help="Manage visual agent block graphs.")

# ---------------------------------------------------------------------------
# Known block types — warn on unknown, don't block
# ---------------------------------------------------------------------------

_KNOWN_BLOCK_TYPES = frozenset(
    {
        "SET_STATE_ENTRIES",
        "LLM_REQUEST",
        "ROUTING",
        "MANUAL_TOOL_CALL",
        "MANDATORY_TOOL_CALL",
        "PARALLEL",
        "FOR_EACH",
        "PYTHON_CODE",
        "REFLECTION",
        "DELEGATE_TO_OTHER_AGENT",
        "GENERATE_ARTIFACT",
        # DSS 13.x names
        "EMIT_OUTPUT",
        "STANDARD_REACT",
        # DSS 14.5+ names
        "CORE_LOOP",
        "GENERATE_OUTPUT",
        # DSS 14.5+ additional types
        "CUSTOM",
        "CONTEXT_COMPRESSION",
        "SET_SCRATCHPAD_ENTRIES",
        "EDIT_LAST_USER_MESSAGE",
    }
)

# ---------------------------------------------------------------------------
# Agent settings key detection (DSS version-agnostic)
# ---------------------------------------------------------------------------

_STRUCTURED_KEY = "structuredAgentSettings"
_SIMPLE_KEY = "toolsUsingAgentSettings"

# Block types that use defaultNextBlock instead of nextBlock
_DEFAULT_NEXT_BLOCK_TYPES = frozenset({"STANDARD_REACT", "CORE_LOOP"})

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_version_id(settings, version_flag: str | None) -> str:
    """Resolve version: --version flag → active_version → first version."""
    if version_flag:
        return version_flag
    active = settings.active_version
    if active:
        return active
    ids = settings.get_version_ids()
    if not ids:
        exit_with_error("Agent has no versions.", code="no_versions", status=1)
    return ids[0]


def _get_version_data(raw: dict, version_id: str) -> dict:
    """Return the version dict matching version_id."""
    for v in raw["versions"]:
        if v["versionId"] == version_id:
            return v
    exit_with_error(f"Version '{version_id}' not found.", code="not_found", status=3)


def _get_agent_settings(raw: dict, version_id: str) -> dict:
    """Get the agent settings dict for a version, auto-detecting the correct key.

    STRUCTURED_AGENT uses structuredAgentSettings (DSS 14.5+).
    TOOLS_USING_AGENT uses toolsUsingAgentSettings.

    Uses raw["type"] for detection — newly-created STRUCTURED_AGENT may lack
    the structuredAgentSettings key, so key-presence checks are unreliable.
    """
    ver = _get_version_data(raw, version_id)
    if raw.get("type") == "STRUCTURED_AGENT":
        return ver.setdefault(_STRUCTURED_KEY, {})
    if _SIMPLE_KEY in ver:
        return ver[_SIMPLE_KEY]
    # Fallback: create simple agent settings
    ver[_SIMPLE_KEY] = {}
    return ver[_SIMPLE_KEY]


def _get_settings_key(raw: dict) -> str:
    """Return the correct settings key based on agent type."""
    if raw.get("type") == "STRUCTURED_AGENT":
        return _STRUCTURED_KEY
    return _SIMPLE_KEY


def _find_block(agent_cfg: dict, block_id: str) -> dict | None:
    """Find a block by ID. Returns None if not found."""
    for b in agent_cfg.get("blocks", []):
        if b.get("id") == block_id:
            return b
    return None


def _find_dangling_refs(blocks: list[dict], removed_id: str) -> list[tuple[str, str]]:
    """Return [(block_id, field_name)] for blocks referencing removed_id."""
    refs = []
    for b in blocks:
        bid = b.get("id", "?")
        # Direct nextBlock fields
        for field in (
            "nextBlock",
            "defaultNextBlock",
            "defaultNextBlockIfNoClauseMatch",
        ):
            if b.get(field) == removed_id:
                refs.append((bid, field))
        # PARALLEL.blockIds
        if removed_id in b.get("blockIds", []):
            refs.append((bid, "blockIds"))
        # FOR_EACH.blockIdToRepeat
        if b.get("blockIdToRepeat") == removed_id:
            refs.append((bid, "blockIdToRepeat"))
        # ROUTING clauses
        for clause in b.get("clausesBasedDecisions", []):
            if clause.get("nextBlock") == removed_id:
                refs.append((bid, "clausesBasedDecisions[].nextBlock"))
        # STANDARD_REACT exitConditions
        for cond in b.get("exitConditions", []):
            if cond.get("nextBlock") == removed_id:
                refs.append((bid, "exitConditions[].nextBlock"))
    return refs


def _fetch_settings(
    ctx: typer.Context, agent_id: str, project: str | None, version: str | None
):
    """Common fetch pattern: returns (settings, raw, agent_cfg, version_id).

    agent_cfg is the agent settings dict (structuredAgentSettings or
    toolsUsingAgentSettings), auto-detected from the version data.
    """
    project_key = resolve_project(project)
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    agent = resolve_agent(proj, agent_id)
    settings = agent.get_settings()
    raw = settings.get_raw()
    version_id = _resolve_version_id(settings, version)
    agent_cfg = _get_agent_settings(raw, version_id)
    return settings, raw, agent_cfg, version_id


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("list")
def list_blocks(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List blocks in an agent's block graph."""
    output = resolve_output_format(output)
    try:
        settings, raw, agent_cfg, version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        # On DSS 14.5+, blocks live in structuredAgentSettings with no explicit
        # mode field — presence of blocks means block-graph mode is active.
        has_blocks = bool(agent_cfg.get("blocks"))
        if not has_blocks:
            warn(f"Agent '{agent_id}' has no blocks yet.")

        blocks = agent_cfg.get("blocks", [])
        starting = agent_cfg.get("startingBlockId")

        data = []
        for b in blocks:
            bid = b.get("id", "")
            data.append(
                {
                    "id": bid,
                    "type": b.get("type", ""),
                    "next_block": b.get("nextBlock", ""),
                    "start": "*" if bid == starting else "",
                }
            )

        render(
            data,
            ["id", "type", "next_block", "start"],
            output_format=output,
            title=f"Blocks in {agent_id}",
            headers={
                "id": "ID",
                "type": "TYPE",
                "next_block": "NEXT_BLOCK",
                "start": "START",
            },
        )
    except Exception as e:
        handle_api_error(e)


@app.command("get")
def get_block(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    block_id: str = typer.Argument(help="Block ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show a single block definition."""
    output = resolve_output_format(output)
    try:
        settings, raw, agent_cfg, version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        block = _find_block(agent_cfg, block_id)
        if block is None:
            exit_with_error(
                f"Block '{block_id}' not found in agent '{agent_id}'.",
                code="not_found",
                status=3,
            )

        render_raw(block, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("add")
def add_block(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    block_json: str = typer.Option(
        ..., "--block", "-b", help="Block JSON (string, @file.json, or - for stdin)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
    set_start: bool = typer.Option(
        False, "--set-start", help="Set this block as the starting block"
    ),
) -> None:
    """Add a block to the agent's block graph."""
    try:
        new_block = read_json_input(block_json)
        if not new_block:
            exit_with_error(
                "Block JSON cannot be empty.", code="invalid_input", status=1
            )

        block_id = new_block.get("id")
        if not block_id:
            exit_with_error(
                "Block JSON must have an 'id' field.", code="invalid_input", status=1
            )

        block_type = new_block.get("type")
        if not block_type:
            exit_with_error(
                "Block JSON must have a 'type' field.", code="invalid_input", status=1
            )

        if block_type not in _KNOWN_BLOCK_TYPES:
            warn(
                f"Unknown block type '{block_type}'. Known: {', '.join(sorted(_KNOWN_BLOCK_TYPES))}"
            )

        settings, raw, agent_cfg, version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        # Ensure blocks list exists (on DSS 14.5+ mode is implicit, not a field)
        if "blocks" not in agent_cfg or agent_cfg["blocks"] is None:
            agent_cfg["blocks"] = []

        # Check duplicate ID
        if _find_block(agent_cfg, block_id) is not None:
            exit_with_error(
                f"Block '{block_id}' already exists in agent '{agent_id}'.",
                code="already_exists",
                status=1,
            )

        agent_cfg["blocks"].append(new_block)

        # Set as starting block if requested or if it's the first block
        if set_start or (
            len(agent_cfg["blocks"]) == 1 and not agent_cfg.get("startingBlockId")
        ):
            agent_cfg["startingBlockId"] = block_id

        settings.save()
        success(f"Added block '{block_id}' (type={block_type}) to agent '{agent_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("remove")
def remove_block(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    block_id: str = typer.Argument(help="Block ID to remove"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
) -> None:
    """Remove a block from the agent's block graph."""
    try:
        settings, raw, agent_cfg, version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        blocks = agent_cfg.get("blocks", [])
        original_len = len(blocks)
        agent_cfg["blocks"] = [b for b in blocks if b.get("id") != block_id]

        if len(agent_cfg["blocks"]) == original_len:
            exit_with_error(
                f"Block '{block_id}' not found in agent '{agent_id}'.",
                code="not_found",
                status=3,
            )

        # Warn if starting block was removed
        if agent_cfg.get("startingBlockId") == block_id:
            agent_cfg["startingBlockId"] = None
            warn(
                f"Removed starting block '{block_id}'. Set a new one: dku agent-block set-start {agent_id} <BLOCK_ID>"
            )

        # Warn about dangling references
        dangling = _find_dangling_refs(agent_cfg["blocks"], block_id)
        for ref_bid, ref_field in dangling:
            warn(
                f"Block '{ref_bid}' references removed block '{block_id}' via {ref_field}"
            )

        settings.save()
        success(f"Removed block '{block_id}' from agent '{agent_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("connect")
def connect_blocks(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    from_id: str = typer.Option(..., "--from", help="Source block ID"),
    to_id: str = typer.Option(..., "--to", help="Target block ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
) -> None:
    """Connect two blocks (set nextBlock on source)."""
    try:
        settings, raw, agent_cfg, version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        source = _find_block(agent_cfg, from_id)
        if source is None:
            exit_with_error(
                f"Source block '{from_id}' not found.", code="not_found", status=3
            )

        target = _find_block(agent_cfg, to_id)
        if target is None:
            exit_with_error(
                f"Target block '{to_id}' not found.", code="not_found", status=3
            )

        block_type = source.get("type", "")
        if block_type == "PYTHON_CODE":
            exit_with_error(
                f"Cannot wire PYTHON_CODE blocks with 'connect' — nextBlock is ignored by DSS. "
                f'Declare \'validNextBlocksFromCode: ["{to_id}"]\' in the block JSON and yield NextBlock("{to_id}") '
                f"from process(). Use 'dku agent-block set-graph' to push the full graph.",
                code="unsupported_block_type",
                status=1,
            )

        if block_type in _DEFAULT_NEXT_BLOCK_TYPES:
            source["defaultNextBlock"] = to_id
        else:
            source["nextBlock"] = to_id

        settings.save()
        success(f"Connected '{from_id}' -> '{to_id}' in agent '{agent_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("disconnect")
def disconnect_block(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    block_id: str = typer.Argument(help="Block ID to disconnect"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
) -> None:
    """Disconnect a block (remove nextBlock, making it terminal)."""
    try:
        settings, raw, agent_cfg, version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        block = _find_block(agent_cfg, block_id)
        if block is None:
            exit_with_error(
                f"Block '{block_id}' not found.", code="not_found", status=3
            )

        block_type = block.get("type", "")
        if block_type == "PYTHON_CODE":
            exit_with_error(
                "Cannot disconnect PYTHON_CODE blocks with 'disconnect' — nextBlock is ignored by DSS. "
                "Remove 'validNextBlocksFromCode' and the NextBlock() yield from process(). "
                "Use 'dku agent-block set-graph' to push the full graph.",
                code="unsupported_block_type",
                status=1,
            )
        if block_type in _DEFAULT_NEXT_BLOCK_TYPES:
            block.pop("defaultNextBlock", None)
        else:
            block.pop("nextBlock", None)
        settings.save()
        success(f"Disconnected block '{block_id}' (now terminal) in agent '{agent_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("set-start")
def set_start(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    block_id: str = typer.Argument(help="Block ID to set as starting block"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
) -> None:
    """Set the starting block of the agent's block graph."""
    try:
        settings, raw, agent_cfg, version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        if _find_block(agent_cfg, block_id) is None:
            exit_with_error(
                f"Block '{block_id}' not found in agent '{agent_id}'.",
                code="not_found",
                status=3,
            )

        agent_cfg["startingBlockId"] = block_id
        settings.save()
        success(f"Set starting block to '{block_id}' in agent '{agent_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("set-mode")
def set_mode(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    mode: str = typer.Argument(help="Mode: SIMPLE or BLOCKS_GRAPH"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
) -> None:
    """Switch agent mode between SIMPLE and BLOCKS_GRAPH."""
    if mode not in ("SIMPLE", "BLOCKS_GRAPH"):
        exit_with_error(
            f"Invalid mode '{mode}'. Must be SIMPLE or BLOCKS_GRAPH.",
            code="invalid_input",
            status=1,
        )
    try:
        settings, raw, agent_cfg, version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        agent_cfg["mode"] = mode

        if mode == "BLOCKS_GRAPH":
            if not agent_cfg.get("blocks"):
                agent_cfg["blocks"] = []
        elif mode == "SIMPLE" and agent_cfg.get("blocks"):
            warn("Existing blocks will be preserved but inactive in SIMPLE mode.")

        settings.save()
        success(f"Set mode to '{mode}' for agent '{agent_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("get-graph")
def get_graph(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Dump the full block graph definition (auto-detects settings key)."""
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        settings, raw, agent_cfg, version_id = _fetch_settings(
            ctx, agent_id, project, version
        )
        render_raw(agent_cfg, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-graph")
def set_graph(
    ctx: typer.Context,
    agent_id: str = typer.Argument(help="Agent ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Full graph JSON (string, @file.json, or - for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
) -> None:
    """Replace the full block graph definition (auto-detects settings key)."""
    try:
        new_agent_cfg = read_json_input(definition)
        if not new_agent_cfg:
            exit_with_error(
                "Definition JSON cannot be empty.", code="invalid_input", status=1
            )

        project_key = resolve_project(project)
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = proj.get_agent(agent_id)
        settings = agent.get_settings()
        raw = settings.get_raw()
        version_id = _resolve_version_id(settings, version)

        # Write to the correct settings key for this agent type
        version_data = _get_version_data(raw, version_id)
        key = _get_settings_key(raw)
        version_data[key] = new_agent_cfg

        settings.save()
        block_count = len(new_agent_cfg.get("blocks", []))
        mode = new_agent_cfg.get("mode", "unknown")
        success(
            f"Updated block graph for agent '{agent_id}' (mode={mode}, blocks={block_count})"
        )
    except Exception as e:
        handle_api_error(e)

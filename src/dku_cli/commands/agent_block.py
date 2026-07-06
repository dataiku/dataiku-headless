"""dku agent-block — list, get, add, remove, connect, disconnect, set-start, set-mode, get-graph, set-graph."""

from __future__ import annotations

import typer

from dku_cli.enums import AgentBlockMode
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
        exit_with_error("Agent has no versions.", status=1)
    return ids[0]


def _get_version_data(raw: dict, version_id: str) -> dict:
    """Return the version dict matching version_id."""
    for v in raw["versions"]:
        if v["versionId"] == version_id:
            return v
    exit_with_error(f"Version '{version_id}' not found.", status=3)


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


def _display_next_block(b: dict) -> str:
    """Get display value for next block, with defaultNextBlock fallback."""
    nb = b.get("nextBlock")
    if nb:
        return nb
    if b.get("type") in _DEFAULT_NEXT_BLOCK_TYPES:
        dnb = b.get("defaultNextBlock")
        if dnb:
            return f"{dnb} (default)"
    return ""


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


def _validate_routing_block(block: dict) -> list[str]:
    """Validate a ROUTING block for common pitfalls. Returns list of error messages."""
    errors = []
    if block.get("type") != "ROUTING":
        return errors

    clauses = block.get("clausesBasedDecisions", [])
    for i, clause_entry in enumerate(clauses):
        clause = clause_entry.get("clause", {})
        if clause.get("type") == "EXPRESSION":
            expr_obj = clause.get("expression", {})
            expr_str = (
                expr_obj.get("expression", "") if isinstance(expr_obj, dict) else ""
            )
            if not expr_str or not expr_str.strip():
                errors.append(
                    f"ROUTING block '{block.get('id', '?')}' clause {i} has an EMPTY CEL expression. "
                    "This causes 'Micro-CEL Evaluation Error: unexpected EOF while parsing'. "
                    'Set a valid expression like: state["intent"] == "billing"'
                )
    return errors


def _validate_set_state_entries_block(block: dict) -> list[str]:
    """Validate SET_STATE_ENTRIES / SET_SCRATCHPAD_ENTRIES for empty CEL values."""
    errors = []
    if block.get("type") not in ("SET_STATE_ENTRIES", "SET_SCRATCHPAD_ENTRIES"):
        return errors
    for i, entry in enumerate(block.get("entriesToSet", [])):
        value = entry.get("value")
        if isinstance(value, str) and not value.strip():
            errors.append(
                f"{block.get('type')} block '{block.get('id', '?')}' entry {i} "
                f"(key='{entry.get('key', '?')}') has an EMPTY CEL value. "
                "This causes 'Micro-CEL Evaluation Error: unexpected EOF'. "
                'Use a CEL literal: "\'\'" (empty string), "0" (number), or "[]" (empty list).'
            )
    return errors


def _validate_output_key(block: dict) -> list[str]:
    """Validate that SAVE_TO_STATE/SAVE_TO_SCRATCHPAD blocks have an output key."""
    errors = []
    output_mode = block.get("outputMode", "")
    if output_mode not in ("SAVE_TO_STATE", "SAVE_TO_SCRATCHPAD"):
        return errors
    has_key = (
        block.get("outputKey")
        or block.get("outputStateKey")
        or block.get("outputScratchpadKey")
    )
    if not has_key:
        target = "state" if "STATE" in output_mode else "scratchpad"
        errors.append(
            f"Block '{block.get('id', '?')}' (type={block.get('type', '?')}) has "
            f"outputMode={output_mode} but no output key. "
            f'LLM output will be lost. Add "outputKey": "my_field" to save to {target}.'
        )
    return errors


def _normalize_blocks(blocks: list[dict]) -> list[str]:
    """Apply silent-failure fixes in-place. Returns warnings about what was fixed.

    1. PYTHON_CODE without `functionName` → inject `"functionName": "process"` when the
       code defines `def process(`. DSS 14.5.1+ NPEs with a bare 'functionName' KeyError
       before any block runs if this field is missing.
    2. Legacy `outputScratchpadKey` / `outputStateKey` → rename to `outputKey`. DSS
       14.5+ rejects both legacy fields — `SAVE_TO_STATE` with `outputStateKey` NPEs at
       runtime with `RequestFailedException: 'outputKey'` (verified live on 14.6).
    3. LLM_REQUEST `systemPrompt` → rename to `systemPromptAfterHistory`. DSS
       silently ignores `systemPrompt` on LLM_REQUEST (verified live: the block
       runs with default behavior and the prompt never reaches the model).
    """
    warnings: list[str] = []
    for block in blocks:
        bid = block.get("id", "?")

        # Fix 1: PYTHON_CODE auto-inject functionName="process"
        if block.get("type") == "PYTHON_CODE" and not block.get("functionName"):
            code = block.get("code", "") or ""
            if "def process(" in code:
                block["functionName"] = "process"
                warnings.append(
                    f"Block '{bid}' (PYTHON_CODE) was missing functionName; "
                    "auto-injected functionName='process'. DSS 14.5.1+ requires this field."
                )

        # Fix 2: rename legacy outputScratchpadKey / outputStateKey -> outputKey
        for legacy_field in ("outputScratchpadKey", "outputStateKey"):
            if legacy_field not in block:
                continue
            if "outputKey" not in block:
                block["outputKey"] = block.pop(legacy_field)
                warnings.append(
                    f"Block '{bid}' used legacy '{legacy_field}'; renamed to 'outputKey'. "
                    "DSS 14.5+ rejects the legacy field."
                )
            else:
                # Both present — drop the legacy one to avoid confusion downstream.
                block.pop(legacy_field)
                warnings.append(
                    f"Block '{bid}' had both 'outputKey' and legacy '{legacy_field}'; "
                    "dropped the legacy field."
                )

        # Fix 3: LLM_REQUEST systemPrompt -> systemPromptAfterHistory
        if block.get("type") == "LLM_REQUEST" and "systemPrompt" in block:
            if "systemPromptAfterHistory" not in block:
                block["systemPromptAfterHistory"] = block.pop("systemPrompt")
                warnings.append(
                    f"Block '{bid}' (LLM_REQUEST) used 'systemPrompt', which DSS "
                    "silently ignores on this block type; renamed to "
                    "'systemPromptAfterHistory'."
                )
            else:
                block.pop("systemPrompt")
                warnings.append(
                    f"Block '{bid}' (LLM_REQUEST) had both 'systemPromptAfterHistory' "
                    "and 'systemPrompt'; dropped 'systemPrompt' (DSS ignores it on "
                    "this block type)."
                )

        warnings.extend(_fix_legacy_block_fields(block, bid))
    return warnings


def _fix_legacy_block_fields(block: dict, bid: str) -> list[str]:
    """Relocate/flag legacy block fields DSS silently ignores (#228)."""
    warnings: list[str] = []

    # `responseFormat` at the block root is ignored; DSS reads the JSON-output
    # constraint from completionSettings.
    if "responseFormat" in block:
        settings = block.setdefault("completionSettings", {})
        if isinstance(settings, dict) and "responseFormat" not in settings:
            settings["responseFormat"] = block.pop("responseFormat")
            warnings.append(
                f"Block '{bid}' had a top-level 'responseFormat', which DSS "
                "ignores; moved it under 'completionSettings.responseFormat'."
            )
        else:
            block.pop("responseFormat")
            warnings.append(
                f"Block '{bid}' had a top-level 'responseFormat' that DSS "
                "ignores; dropped it (completionSettings.responseFormat already set)."
            )

    # Legacy `clauses` -> `clausesBasedDecisions`. The shape differs across DSS
    # versions, so don't silently transform — warn loudly and name the field.
    if "clauses" in block and "clausesBasedDecisions" not in block:
        block.pop("clauses")
        warnings.append(
            f"Block '{bid}' used legacy 'clauses', which DSS ignores; "
            "routing decisions go in 'clausesBasedDecisions' (a list of "
            "{condition, nextBlock}). The 'clauses' value was dropped — "
            "re-add it under 'clausesBasedDecisions'."
        )
    return warnings


# Block types that require an LLM to function
_LLM_BLOCK_TYPES = frozenset(
    {
        "STANDARD_REACT",
        "CORE_LOOP",
        "LLM_REQUEST",
        "MANDATORY_TOOL_CALL",
        "REFLECTION",
        "EDIT_LAST_USER_MESSAGE",
    }
)


def _validate_llm_blocks(block: dict) -> list[str]:
    """Warn when LLM-dependent blocks lack llmId (warning, not error)."""
    warnings = []
    if block.get("type") not in _LLM_BLOCK_TYPES:
        return warnings
    if not block.get("llmId"):
        warnings.append(
            f"Block '{block.get('id', '?')}' (type={block.get('type')}) has no llmId. "
            "On DSS 14.5+, each LLM block needs its own llmId or it fails with "
            "'Please select a valid LLM'. Discover models: dku llm list -P PROJ"
        )
    return warnings


def _validate_blocks(blocks: list[dict]) -> list[str]:
    """Validate all blocks. Returns list of error messages."""
    errors = []
    for block in blocks:
        errors.extend(_validate_routing_block(block))
        errors.extend(_validate_set_state_entries_block(block))
        errors.extend(_validate_output_key(block))
    return errors


def _collect_block_warnings(blocks: list[dict]) -> list[str]:
    """Collect non-fatal warnings across all blocks."""
    warnings: list[str] = []
    for block in blocks:
        warnings.extend(_validate_llm_blocks(block))
    return warnings


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
) -> None:
    """List blocks in an agent's block graph."""
    output = resolve_output_format()
    try:
        _, _, agent_cfg, _ = _fetch_settings(ctx, agent_id, project, version)

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
                    "next_block": _display_next_block(b),
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
) -> None:
    """Show a single block definition."""
    output = resolve_output_format()
    try:
        _, _, agent_cfg, _ = _fetch_settings(ctx, agent_id, project, version)

        block = _find_block(agent_cfg, block_id)
        if block is None:
            exit_with_error(
                f"Block '{block_id}' not found in agent '{agent_id}'.",
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
            exit_with_error("Block JSON cannot be empty.", status=1)

        block_id = new_block.get("id")
        if not block_id:
            exit_with_error("Block JSON must have an 'id' field.", status=1)

        block_type = new_block.get("type")
        if not block_type:
            exit_with_error("Block JSON must have a 'type' field.", status=1)

        if block_type not in _KNOWN_BLOCK_TYPES:
            warn(
                f"Unknown block type '{block_type}'. Known: {', '.join(sorted(_KNOWN_BLOCK_TYPES))}"
            )

        settings, raw, agent_cfg, _version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        # Block addition to non-STRUCTURED agents — blocks silently vanish
        agent_type = raw.get("type", "")
        if agent_type != "STRUCTURED_AGENT":
            exit_with_error(
                f"Agent '{agent_id}' is type '{agent_type}', not STRUCTURED_AGENT. "
                "Block graphs require STRUCTURED_AGENT — blocks silently vanish on other types.",
                details=[
                    "Fix: dku agent create NAME --type STRUCTURED_AGENT -P PROJ",
                    "Then add blocks to the new agent instead.",
                ],
            )

        # Ensure blocks list exists (on DSS 14.5+ mode is implicit, not a field)
        if "blocks" not in agent_cfg or agent_cfg["blocks"] is None:
            agent_cfg["blocks"] = []

        # Silent-failure fixes: inject functionName on PYTHON_CODE, rename
        # outputScratchpadKey -> outputKey. Warn loudly so agents see the fix.
        for w in _normalize_blocks([new_block]):
            warn(w)

        # Validate block — routing CEL, SET_STATE_ENTRIES CEL, SAVE_TO_STATE output key
        block_errors = _validate_blocks([new_block])
        if block_errors:
            exit_with_error(
                block_errors[0],
                status=1,
            )

        # Non-fatal warnings (e.g. LLM blocks without llmId on DSS 14.5+)
        for w in _collect_block_warnings([new_block]):
            warn(w)

        # Check duplicate ID
        if _find_block(agent_cfg, block_id) is not None:
            exit_with_error(
                f"Block '{block_id}' already exists in agent '{agent_id}'.",
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a block from the agent's block graph."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="agent_block.remove",
        subject=f"block '{block_id}' from agent '{agent_id}' in {project_key}",
        yes=yes,
        prompt=f"Remove block '{block_id}' from agent '{agent_id}'?",
    )
    try:
        settings, _raw, agent_cfg, _version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        blocks = agent_cfg.get("blocks", [])
        original_len = len(blocks)
        agent_cfg["blocks"] = [b for b in blocks if b.get("id") != block_id]

        if len(agent_cfg["blocks"]) == original_len:
            exit_with_error(
                f"Block '{block_id}' not found in agent '{agent_id}'.",
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
        settings, _raw, agent_cfg, _version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        source = _find_block(agent_cfg, from_id)
        if source is None:
            exit_with_error(f"Source block '{from_id}' not found.", status=3)

        target = _find_block(agent_cfg, to_id)
        if target is None:
            exit_with_error(f"Target block '{to_id}' not found.", status=3)

        block_type = source.get("type", "")
        if block_type == "PYTHON_CODE":
            exit_with_error(
                f"Cannot wire PYTHON_CODE blocks with 'connect' — nextBlock is ignored by DSS. "
                f'Declare \'validNextBlocksFromCode: ["{to_id}"]\' in the block JSON and yield NextBlock("{to_id}") '
                f"from process(). Use 'dku agent-block set-graph' to push the full graph.",
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
        settings, _raw, agent_cfg, _version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        block = _find_block(agent_cfg, block_id)
        if block is None:
            exit_with_error(f"Block '{block_id}' not found.", status=3)

        block_type = block.get("type", "")
        if block_type == "PYTHON_CODE":
            exit_with_error(
                "Cannot disconnect PYTHON_CODE blocks with 'disconnect' — nextBlock is ignored by DSS. "
                "Remove 'validNextBlocksFromCode' and the NextBlock() yield from process(). "
                "Use 'dku agent-block set-graph' to push the full graph.",
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
        settings, _raw, agent_cfg, _version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        if _find_block(agent_cfg, block_id) is None:
            exit_with_error(
                f"Block '{block_id}' not found in agent '{agent_id}'.",
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
    mode: AgentBlockMode = typer.Argument(
        case_sensitive=False, help="Mode: SIMPLE or BLOCKS_GRAPH"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    version: str | None = typer.Option(
        None, "--version", help="Version ID (default: active)"
    ),
) -> None:
    """Switch agent mode between SIMPLE and BLOCKS_GRAPH."""
    try:
        settings, _raw, agent_cfg, _version_id = _fetch_settings(
            ctx, agent_id, project, version
        )

        agent_cfg["mode"] = mode.value

        if mode == AgentBlockMode.BLOCKS_GRAPH:
            if not agent_cfg.get("blocks"):
                agent_cfg["blocks"] = []
        elif mode == AgentBlockMode.SIMPLE and agent_cfg.get("blocks"):
            warn("Existing blocks will be preserved but inactive in SIMPLE mode.")

        settings.save()
        warn(
            "On DSS ≥14.5 the mode is derived from block presence, not this field — "
            "this setting may have no effect."
        )
        success(f"Set mode to '{mode.value}' for agent '{agent_id}'")
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
) -> None:
    """Dump the full block graph definition (auto-detects settings key)."""
    output = resolve_output_format()
    try:
        _, _, agent_cfg, _ = _fetch_settings(ctx, agent_id, project, version)
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
            exit_with_error("Definition JSON cannot be empty.", status=1)

        # Silent-failure fixes: inject functionName on PYTHON_CODE, rename
        # outputScratchpadKey -> outputKey. Warn loudly so agents see the fix.
        all_blocks = new_agent_cfg.get("blocks", [])
        for w in _normalize_blocks(all_blocks):
            warn(w)

        # Validate all blocks before saving
        block_errors = _validate_blocks(all_blocks)
        if block_errors:
            exit_with_error(
                block_errors[0],
                status=1,
                details=block_errors[1:] if len(block_errors) > 1 else None,
            )

        # Non-fatal warnings (e.g. LLM blocks without llmId on DSS 14.5+)
        for w in _collect_block_warnings(all_blocks):
            warn(w)

        project_key = resolve_project(project)
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        agent = resolve_agent(proj, agent_id)
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

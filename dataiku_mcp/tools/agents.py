"""Tools for creating and managing Dataiku DSS Agents."""

import copy
import time
from typing import Any

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, is_empty, omit_empty
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.validation import require_non_empty_string


def _get_version(raw, version_id=""):
    """Get a specific version or the active version from agent settings."""
    versions = raw.get("versions", [])
    if version_id:
        for v in versions:
            if v.get("versionId") == version_id:
                return v
        return None
    active_id = raw.get("activeVersion")
    for v in versions:
        if v.get("versionId") == active_id:
            return v
    return versions[0] if versions else None


def _get_tua(version):
    """Get the toolsUsingAgentSettings from a version (TOOLS_USING_AGENT type)."""
    return version.setdefault("toolsUsingAgentSettings", {})


def _get_sa(version):
    """Get the structuredAgentSettings from a version (STRUCTURED_AGENT type)."""
    return version.setdefault("structuredAgentSettings", {})


# ---------------------------------------------------------------------------
# Agent CRUD
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_agents(
    project_key: str,
    ctx: Context,
) -> str:
    """List the agents in the project."""
    project_key = require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing agents in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        agents = project.list_agents()
        result = []
        for a in agents:
            result.append(
                {
                    "id": a.get("id", ""),
                    "name": a.get("name", ""),
                    "type": a.get("type", ""),
                }
            )
        return columnar(result, ["id", "name", "type"])

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_agent_settings(
    project_key: str,
    agent_id: str,
    ctx: Context,
    version_id: str = "",
) -> str:
    """Get the agent's full settings (version details vary by agent type).

    Args:
        version_id: Optional version ID (defaults to the active version)
    """
    project_key = require_non_empty_string(project_key, "project_key")
    agent_id = require_non_empty_string(agent_id, "agent_id")
    await ctx.info(f"Getting settings for agent '{agent_id}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        agent = project.get_agent(agent_id)
        settings = agent.get_settings()
        raw = settings.get_raw()

        result = {
            "id": raw.get("id", agent_id),
            "name": raw.get("name", ""),
            "type": raw.get("type", ""),
        }

        version = _get_version(raw, version_id)
        if version:
            agent_type = raw.get("type", "")
            if agent_type == "STRUCTURED_AGENT":
                sa = _get_sa(version)
                ver = {
                    "versionId": version.get("versionId", ""),
                    "blocks": sa.get("blocks", []),
                    "entryBlockId": sa.get("startingBlockId", ""),
                }
            elif agent_type == "PYTHON_AGENT":
                pas = version.get("pythonAgentSettings", {})
                code_env = pas.get("codeEnvSelection", {})
                ver = {
                    "versionId": version.get("versionId", ""),
                    "code": version.get("code", ""),
                    "code_env_mode": code_env.get("envMode", ""),
                    "code_env_name": code_env.get("envName", ""),
                    # keep false boolean (carries information)
                    "supports_image_inputs": pas.get("supportsImageInputs", False),
                }
            else:
                tua = _get_tua(version)
                ver = {
                    "versionId": version.get("versionId", ""),
                    "mode": tua.get("mode", ""),
                    "llmId": tua.get("llmId", ""),
                    "systemPrompt": tua.get("systemPromptAppend", ""),
                    "tools": tua.get("tools", []),
                    "blocks": tua.get("blocks", []),
                    "entryBlockId": tua.get("startingBlockId", ""),
                }
            # LEVER 4: omit empty version fields (keeps False / 0)
            result["version"] = omit_empty(ver)
        elif version_id:
            available_versions = [v.get("versionId") for v in raw.get("versions", [])]
            raise ValueError(
                f"Version '{version_id}' not found for agent '{agent_id}'. "
                f"Available versions: {available_versions}"
            )

        # LEVER 4: omit empty top-level fields (keeps False / 0)
        result = omit_empty(result)
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_agent(
    project_key: str,
    agent_name: str,
    agent_type: str,
    ctx: Context,
) -> str:
    """Create a new agent and return its ID.

    Args:
        agent_name: Display name for the agent
        agent_type: One of TOOLS_USING_AGENT, STRUCTURED_AGENT, or PYTHON_AGENT
    """
    project_key = require_non_empty_string(project_key, "project_key")
    agent_name = require_non_empty_string(agent_name, "agent_name")
    agent_type = require_non_empty_string(agent_type, "agent_type")
    await ctx.info(f"Creating agent '{agent_name}' ({agent_type}) in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        agent = project.create_agent(agent_name, agent_type)
        raw = agent.get_settings().get_raw()
        return {
            "agent_id": raw.get("id", ""),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def update_agent_settings(
    project_key: str,
    agent_id: str,
    ctx: Context,
    version_id: str = "",
    llm_id: str | None = None,
    system_prompt: str | None = None,
    tool_ids: list[str] | None = None,
    blocks: list[dict[str, Any]] | None = None,
    entry_block_id: str | None = None,
    pre_turn_block_ids: list[str] | None = None,
    post_turn_block_ids: list[str] | None = None,
    code: str | None = None,
    code_env_name: str | None = None,
    supports_image_inputs: bool | None = None,
) -> str:
    """Update version-level agent settings. Only provided fields are changed.

    Args:
        version_id: Version to update (defaults to active version)
        llm_id: LLM identifier (TOOLS_USING_AGENT)
        system_prompt: System prompt (TOOLS_USING_AGENT)
        tool_ids: Full replacement tool list (TOOLS_USING_AGENT)
        blocks: Full replacement blocks list (STRUCTURED_AGENT)
        entry_block_id: Entry block ID (STRUCTURED_AGENT)
        pre_turn_block_ids: Block IDs to run before every turn (STRUCTURED_AGENT)
        post_turn_block_ids: Block IDs to run after every turn (STRUCTURED_AGENT)
        code: Python source code (PYTHON_AGENT)
        code_env_name: Name of the code environment (PYTHON_AGENT)
        supports_image_inputs: Whether the agent accepts image inputs (PYTHON_AGENT)
    """
    project_key = require_non_empty_string(project_key, "project_key")
    agent_id = require_non_empty_string(agent_id, "agent_id")
    await ctx.info(f"Updating agent '{agent_id}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        agent = project.get_agent(agent_id)
        settings = agent.get_settings()
        raw = settings.get_raw()

        version = _get_version(raw, version_id)
        if not version:
            raise ValueError(
                f"No version found to update for agent '{agent_id}'"
                + (f" with version_id '{version_id}'" if version_id else "")
            )

        agent_type = raw.get("type", "")
        is_structured = agent_type == "STRUCTURED_AGENT"
        settings_dict = _get_sa(version) if is_structured else _get_tua(version)
        updated = []

        if code is not None:
            if agent_type != "PYTHON_AGENT":
                raise ValueError("'code' can only be set on PYTHON_AGENT agents")
            version["code"] = code
            updated.append("code")

        if code_env_name is not None:
            if agent_type != "PYTHON_AGENT":
                raise ValueError(
                    "'code_env_name' can only be set on PYTHON_AGENT agents"
                )
            pas = version.setdefault("pythonAgentSettings", {})
            pas["codeEnvSelection"] = {
                "envMode": "EXPLICIT_ENV",
                "envName": code_env_name,
            }
            updated.append("code_env_name")

        if supports_image_inputs is not None:
            if agent_type != "PYTHON_AGENT":
                raise ValueError(
                    "'supports_image_inputs' can only be set on PYTHON_AGENT agents"
                )
            pas = version.setdefault("pythonAgentSettings", {})
            pas["supportsImageInputs"] = supports_image_inputs
            updated.append("supports_image_inputs")

        if llm_id is not None:
            settings_dict["llmId"] = llm_id
            updated.append("llm_id")
        if system_prompt is not None:
            settings_dict["systemPromptAppend"] = system_prompt
            updated.append("system_prompt")
        if tool_ids is not None:
            settings_dict["tools"] = [
                {"toolRef": tid, "disabled": False} for tid in tool_ids
            ]
            updated.append("tools")
        if blocks is not None:
            settings_dict["blocks"] = blocks
            if blocks and not settings_dict.get("startingBlockId"):
                settings_dict["startingBlockId"] = blocks[0]["id"]
            updated.append("blocks")
        if entry_block_id is not None:
            settings_dict["startingBlockId"] = entry_block_id
            updated.append("entry_block_id")
        if pre_turn_block_ids is not None:
            settings_dict["preTurnBlockIds"] = pre_turn_block_ids
            updated.append("pre_turn_block_ids")
        if post_turn_block_ids is not None:
            settings_dict["postTurnBlockIds"] = post_turn_block_ids
            updated.append("post_turn_block_ids")

        settings.save()

        result = {
            "updated_fields": updated,
        }
        # LEVER 4: omit empty updated_fields (keeps False / 0)
        return omit_empty(result)

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_agent_versions(
    project_key: str,
    agent_id: str,
    ctx: Context,
) -> str:
    """List all versions of an agent, indicating which is active."""
    project_key = require_non_empty_string(project_key, "project_key")
    agent_id = require_non_empty_string(agent_id, "agent_id")
    await ctx.info(f"Listing versions for agent '{agent_id}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        agent = project.get_agent(agent_id)
        settings = agent.get_settings()
        active_id = settings.active_version
        result = [
            {"versionId": v, "active": v == active_id}
            for v in settings.get_version_ids()
        ]
        return columnar(result, ["versionId", "active"])

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_agent_version(
    project_key: str,
    agent_id: str,
    version_id: str,
    ctx: Context,
    duplicate_of: str | None = None,
) -> str:
    """Create a new version of an agent.

    Args:
        version_id: Identifier for the new version (e.g. "v2")
        duplicate_of: Version ID to copy settings from; omit for an empty version
    """
    project_key = require_non_empty_string(project_key, "project_key")
    agent_id = require_non_empty_string(agent_id, "agent_id")
    version_id = require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Creating version '{version_id}' for agent '{agent_id}' in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        agent = project.get_agent(agent_id)
        settings = agent.get_settings()
        raw = settings.get_raw()

        existing_ids = settings.get_version_ids()
        if version_id in existing_ids:
            raise ValueError(
                f"Version '{version_id}' already exists on agent '{agent_id}'"
            )

        if duplicate_of:
            if duplicate_of not in existing_ids:
                raise ValueError(
                    f"Source version '{duplicate_of}' not found. Available: {existing_ids}"
                )
            source_raw = settings.get_version_settings(duplicate_of).get_raw()
            new_version = copy.deepcopy(source_raw)
        else:
            new_version = {}

        new_version["versionId"] = version_id
        now_ms = int(time.time() * 1000)
        tag = {
            "versionNumber": 0,
            "lastModifiedBy": {"login": "api"},
            "lastModifiedOn": now_ms,
        }
        new_version["versionTag"] = tag
        new_version["creationTag"] = dict(tag)
        raw.setdefault("versions", []).append(new_version)
        settings.save()
        return {"version_id": version_id}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_active_agent_version(
    project_key: str,
    agent_id: str,
    version_id: str,
    ctx: Context,
) -> str:
    """Set the active version of an agent.

    Args:
        version_id: Version ID to make active (must already exist)
    """
    project_key = require_non_empty_string(project_key, "project_key")
    agent_id = require_non_empty_string(agent_id, "agent_id")
    version_id = require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Setting active version to '{version_id}' for agent '{agent_id}' in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        agent = project.get_agent(agent_id)
        settings = agent.get_settings()
        existing_ids = settings.get_version_ids()
        if version_id not in existing_ids:
            raise ValueError(
                f"Version '{version_id}' not found. Available: {existing_ids}"
            )
        # Agents are backed by saved models; setting activeVersion in raw is not
        # persisted by the agent PUT endpoint — use the saved-model activation API.
        project.get_saved_model(agent_id).set_active_version(version_id)
        return {"active_version": version_id}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def delete_agent(
    project_key: str,
    agent_id: str,
    ctx: Context,
) -> str:
    """Delete the agent."""
    project_key = require_non_empty_string(project_key, "project_key")
    agent_id = require_non_empty_string(agent_id, "agent_id")
    await ctx.info(f"Deleting agent '{agent_id}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        agent = project.get_agent(agent_id)
        agent.delete()
        return {}

    return compact_json(await run_blocking(_run))


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_agent(
    project_key: str,
    agent_id: str,
    message: str,
    ctx: Context,
) -> str:
    """Send a message to an agent and return its response (non-streaming)."""
    project_key = require_non_empty_string(project_key, "project_key")
    agent_id = require_non_empty_string(agent_id, "agent_id")
    message = require_non_empty_string(message, "message")
    await ctx.info(f"Running agent '{agent_id}' with message: {message[:80]}...")

    def _run():
        client = get_dss_client()
        project = client.get_project(project_key)
        agent = project.get_agent(agent_id)

        llm = agent.as_llm()
        completion = llm.new_completion()
        completion.with_message(message, role="user")
        response = completion.execute()

        result = {
            "success": response.success,
            "text": response.text,
        }
        # LEVER 4: omit empty text (keep success bool — carries information)
        if is_empty(result["text"]):
            del result["text"]

        # Include a lightweight tool call summary (name only — full results are too large)
        if response.tool_calls:
            result["tools_called"] = [
                tc.get("function", {}).get("name", str(tc))
                if isinstance(tc, dict)
                else str(tc)
                for tc in response.tool_calls
            ]

        return result

    return compact_json(await run_blocking(_run))


# ---------------------------------------------------------------------------
# Agent tools (project-level tools that agents can use)
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_agent_tools(
    project_key: str,
    ctx: Context,
) -> str:
    """List the agent tools available in the project."""
    project_key = require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing agent tools in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        tools = project.list_agent_tools()
        result = []
        for t in tools:
            result.append(
                {
                    "id": t.get("id", ""),
                    "name": t.get("name", ""),
                    "type": t.get("type", ""),
                    "description": t.get("description", ""),
                }
            )
        return columnar(result, ["id", "name", "type", "description"])

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_agent_tool_settings(
    project_key: str,
    tool_id: str,
    ctx: Context,
) -> str:
    """Get the full settings of an agent tool."""
    project_key = require_non_empty_string(project_key, "project_key")
    tool_id = require_non_empty_string(tool_id, "tool_id")
    await ctx.info(f"Getting settings for agent tool '{tool_id}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        tool = project.get_agent_tool(tool_id)
        settings = tool.get_settings()
        return settings.get_raw()

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_agent_tool(
    project_key: str,
    tool_type: str,
    tool_name: str,
    tool_id: str,
    ctx: Context,
    config: dict[str, Any] | None = None,
) -> str:
    """Create an agent tool in the project.

    Args:
        tool_type: Tool type (e.g. DatasetRowLookup, VectorStoreSearch)
        tool_name: Display name for the tool
        tool_id: Unique identifier for the tool
        config: Type-specific configuration dict
    """
    project_key = require_non_empty_string(project_key, "project_key")
    tool_type = require_non_empty_string(tool_type, "tool_type")
    tool_name = require_non_empty_string(tool_name, "tool_name")
    tool_id = require_non_empty_string(tool_id, "tool_id")
    await ctx.info(
        f"Creating agent tool '{tool_name}' ({tool_type}) in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        creator = project.new_agent_tool(tool_type, tool_name, tool_id)
        tool = creator.create()

        if config:
            settings = tool.get_settings()
            raw = settings.get_raw()
            raw.update(config)
            settings.save()

        return {}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_agent_tool_settings(
    project_key: str,
    tool_id: str,
    new_settings,
    ctx: Context,
) -> str:
    """Set the full settings of an agent tool.

    Args:
        new_settings: A modified version of the object returned by get_agent_tool_settings
    """
    project_key = require_non_empty_string(project_key, "project_key")
    tool_id = require_non_empty_string(tool_id, "tool_id")
    settings_obj = _coerce_json_object(new_settings, "new_settings")
    await ctx.info(f"Updating agent tool '{tool_id}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        tool = project.get_agent_tool(tool_id)
        settings = tool.get_settings()
        raw = (
            settings.get_raw()
        )  # reference to current.data — mutate in-place for save()
        raw.clear()
        raw.update(settings_obj)
        settings.save()
        return {}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def delete_agent_tool(
    project_key: str,
    tool_id: str,
    ctx: Context,
) -> str:
    """Delete the agent tool."""
    project_key = require_non_empty_string(project_key, "project_key")
    tool_id = require_non_empty_string(tool_id, "tool_id")
    await ctx.info(f"Deleting agent tool '{tool_id}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        tool = project.get_agent_tool(tool_id)
        tool.delete()
        return {}

    return compact_json(await run_blocking(_run))

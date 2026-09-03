# Copyright 2026 Dataiku
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Inspection tools for Dataiku Agents."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import require_non_empty_string


def _get_version(raw, version_id=""):
    versions = raw.get("versions", [])
    if version_id:
        for version in versions:
            if version.get("versionId") == version_id:
                return version
        return None
    active_id = raw.get("activeVersion")
    for version in versions:
        if version.get("versionId") == active_id:
            return version
    return versions[0] if versions else None


def _get_tua(version):
    return version.setdefault("toolsUsingAgentSettings", {})


def _get_sa(version):
    return version.setdefault("structuredAgentSettings", {})


@mcp.tool()
async def list_agents(project_key: str, ctx: Context) -> str:
    """List the agents in the project."""
    project_key = require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing agents in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        agents = project.list_agents()
        result = []
        for agent in agents:
            result.append(
                {
                    "id": agent.get("id", ""),
                    "name": agent.get("name", ""),
                    "type": agent.get("type", ""),
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
    """Get an agent's full settings; version details vary by agent type."""
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
            result["version"] = omit_empty(ver)
        elif version_id:
            available_versions = [v.get("versionId") for v in raw.get("versions", [])]
            raise ValueError(
                f"Version '{version_id}' not found for agent '{agent_id}'. "
                f"Available versions: {available_versions}"
            )

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
            {"versionId": version_id, "active": version_id == active_id}
            for version_id in settings.get_version_ids()
        ]
        return columnar(result, ["versionId", "active"])

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_agent_tools(project_key: str, ctx: Context) -> str:
    """List the agent tools available in the project."""
    project_key = require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing agent tools in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        tools = project.list_agent_tools()
        result = []
        for tool in tools:
            result.append(
                {
                    "id": tool.get("id", ""),
                    "name": tool.get("name", ""),
                    "type": tool.get("type", ""),
                    "description": tool.get("description", ""),
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
        return tool.get_settings().get_raw()

    return compact_json(await run_blocking(_run))

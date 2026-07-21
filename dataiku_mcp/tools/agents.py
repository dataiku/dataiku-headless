"""Inspection tools for Dataiku DSS Agents."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string


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

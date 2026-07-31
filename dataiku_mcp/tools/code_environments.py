"""Dataiku code environment discovery tools."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.auth import get_dss_client


@mcp.tool()
async def list_code_envs(ctx: Context) -> str:
    """List all code environments available on the Dataiku instance, each with its name and language."""
    await ctx.info("Listing Dataiku code environments...")
    envs = await run_blocking(lambda: get_dss_client().list_code_envs())
    result = [
        {
            "name": e.get("envName") or e.get("name", ""),
            "language": e.get("envLang") or e.get("language", ""),
            "type": e.get("deploymentMode") or e.get("type", ""),
        }
        for e in envs
    ]
    return compact_json({"code_envs": columnar(result, ["name", "language", "type"])})

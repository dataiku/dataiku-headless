"""Instance management tools for switching between Dataiku instances."""

from dataclasses import asdict
from fastmcp import Context

from .. import config, mcp
from .utils.serialization import columnar, compact_json, omit_empty


@mcp.tool()
async def list_instances(ctx: Context) -> str:
    """List the configured Dataiku instances (name, URL, description, active flag)."""
    instances = config.get_instances()
    current_instance_name = config.get_current_instance_name()

    # Note: caution to not include inst.api_key in tool return value
    result = []
    for name, inst in instances.items():
        result.append(
            {
                "name": name,
                "url": inst.url,
                "description": inst.description,
                "active": name == current_instance_name,
            }
        )
    return compact_json(columnar(result, ["name", "url", "description", "active"]))


@mcp.tool()
async def switch_instance(name: str, ctx: Context) -> str:
    """Switch the active Dataiku instance.

    The switch affects only tool calls made *after* this returns. A call already
    in flight — notably a long-running Cobuild turn — keeps running against the
    instance it was started on; it is never retargeted mid-flight.

    Args:
        name: Instance name (run list_instances() to retrieve all available instance names).
    """
    await ctx.info(f"Switching to instance '{name}'...")
    info = config.switch_instance(name)
    return compact_json(info)


@mcp.tool()
async def get_current_instance(ctx: Context) -> str:
    """Return the active Dataiku instance (name, URL, description; API key omitted)."""

    # Strip api_key from return value
    current_instance = asdict(config.get_current_instance())
    current_instance.pop("api_key", None)

    result = omit_empty(current_instance)
    return compact_json(result)

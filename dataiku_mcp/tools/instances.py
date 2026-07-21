"""Instance management tools for switching between Dataiku instances."""

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

    Callers that already captured an instance/client snapshot keep it. A caller
    that has not resolved its client yet observes the new active instance.

    Args:
        name: Instance name (run list_instances() to retrieve all available instance names).
    """
    await ctx.info(f"Switching to instance '{name}'...")
    info = config.switch_instance(name)
    return compact_json(info)


@mcp.tool()
async def get_current_instance(ctx: Context) -> str:
    """Return the active Dataiku instance (name, URL, description; API key omitted)."""

    # Return only the public connection identity. ``source`` may contain a local
    # config path and the TLS flag is an operational detail, so neither belongs
    # in a model-visible response.
    current_instance = config.get_current_instance()
    result = omit_empty(
        {
            "name": current_instance.name,
            "url": current_instance.url,
            "description": current_instance.description,
        }
    )
    return compact_json(result)

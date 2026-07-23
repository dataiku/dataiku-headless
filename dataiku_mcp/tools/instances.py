"""Instance management tools for switching between Dataiku instances."""

import asyncio
import secrets
from dataclasses import asdict

from fastmcp import Context

from .. import config, mcp
from ..setup_server import SESSION_LIFETIME_SECONDS, start_setup_server
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
    """Switch the active Dataiku instance. All subsequent tool calls will use this instance.

    Args:
        name: Instance name (run list_instances() to retrieve all available instance names).
    """
    await ctx.info(f"Switching to instance '{name}'...")
    info = config.switch_instance(name)
    return compact_json(info)


@mcp.tool()
async def delete_instance(name: str, ctx: Context) -> str:
    """Delete a Dataiku instance from ~/.dataiku/config.json.

    Only instances stored in the config file can be deleted. An instance defined
    through environment variables must be removed by unsetting DKU_DSS_URL.

    Args:
        name: Instance name (run list_instances() to see available names).
    """
    await ctx.info(f"Deleting instance '{name}'...")
    info = config.delete_instance(name)
    return compact_json(info)


@mcp.tool()
async def get_current_instance(ctx: Context) -> str:
    """Get the active Dataiku instance configuration."""

    # Strip api_key from return value
    current_instance = asdict(config.get_current_instance())
    current_instance.pop("api_key", None)

    result = omit_empty(current_instance)
    return compact_json(result)


@mcp.tool()
async def configure_instance(ctx: Context) -> str:
    """Connect a Dataiku instance. Use when no instance is configured, or to add another.

    Opens a local browser page for the user to enter the instance URL and API key,
    saved to ~/.dataiku/config.json (0600).
    """
    client_params = ctx.session.client_params
    elicitation_capability = (
        client_params.capabilities.elicitation if client_params else None
    )
    supports_url_elicitation = bool(
        elicitation_capability and elicitation_capability.url is not None
    )

    if not supports_url_elicitation:
        await ctx.info(
            "This MCP client does not advertise URL elicitation; opening the "
            "local configuration page directly."
        )
        session = start_setup_server()
        return compact_json(
            {
                "interaction_mode": "direct_local_url",
                "setup_url": session.url,
                "browser_opened": session.browser_opened,
                "expires_in_seconds": SESSION_LIFETIME_SECONDS,
                "next_step": "Open setup_url if the browser did not open automatically.",
            }
        )

    await ctx.info("Requesting permission to open the Dataiku configuration page...")
    session = start_setup_server(open_browser=False)
    elicitation_id = secrets.token_urlsafe(18)
    elicitation = await ctx.session.elicit_url(
        message=(
            "Open the local Dataiku configuration page to save an instance URL "
            "and API key securely."
        ),
        url=session.url,
        elicitation_id=elicitation_id,
        related_request_id=ctx.request_id,
    )

    if elicitation.action != "accept":
        # Some clients advertise URL elicitation but decline the request because
        # the capability is gated behind an unreleased feature flag (e.g. Codex,
        # openai/codex#29344). Fall back to opening the local setup page directly.
        fallback = start_setup_server()
        return compact_json(
            {
                "interaction_mode": "direct_local_url",
                "elicitation_status": elicitation.action,
                "setup_url": fallback.url,
                "browser_opened": fallback.browser_opened,
                "expires_in_seconds": SESSION_LIFETIME_SECONDS,
                "next_step": (
                    "The in-app prompt was declined or is unsupported by this "
                    "client; open setup_url to finish configuring Dataiku."
                ),
            }
        )

    await asyncio.to_thread(
        session.completed.wait,
        SESSION_LIFETIME_SECONDS + 1,
    )
    if session.result is None:
        session.close()
        return compact_json(
            {
                "interaction_mode": "mcp_url_elicitation",
                "status": "expired" if session.expired else "incomplete",
            }
        )

    await ctx.session.send_elicit_complete(
        elicitation_id,
        related_request_id=ctx.request_id,
    )
    session.close()
    return compact_json(
        {
            "interaction_mode": "mcp_url_elicitation",
            "status": "configured",
            "instance": session.result,
        }
    )

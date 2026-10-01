# Copyright 2026 Dataiku SAS
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

"""Instance management tools for switching between Dataiku instances."""

import asyncio
import secrets
from dataclasses import asdict
from typing import Annotated

from fastmcp import Context
from pydantic import Field

from ..auth import get_dss_client
from ..config import request, stdio
from ..executors import run_blocking
from ..server import DSS_INDEPENDENT_TOOL_TAG, mcp
from ..setup_server import SESSION_LIFETIME_SECONDS, start_setup_server
from .utils.serialization import columnar, compact_json, omit_empty

InstanceName = Annotated[
    str, Field(description="A configured instance name, from list_instances.")
]


@mcp.tool(
    title="List Dataiku Instances",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
    tags={DSS_INDEPENDENT_TOOL_TAG},
)
async def list_instances(ctx: Context) -> str:
    """See which Dataiku instances are configured and which one is active."""
    instances = request.get_instances()
    try:
        current_instance_name = request.get_pinned_instance().name
    except ValueError:
        current_instance_name = ""

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


@mcp.tool(
    title="Switch Dataiku Instance",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    tags={DSS_INDEPENDENT_TOOL_TAG},
)
async def switch_instance(name: InstanceName, ctx: Context) -> str:
    """Retarget every later tool call at a different configured instance."""
    await ctx.info(f"Switching to instance '{name}'...")
    info = await run_blocking(request.set_current_instance, name)
    return compact_json(info)


@mcp.tool(
    title="Delete Dataiku Instance",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    tags={DSS_INDEPENDENT_TOOL_TAG},
)
async def delete_instance(name: InstanceName, ctx: Context) -> str:
    """Forget a stored instance's local config; one set via DKU_DSS_URL cannot be deleted."""
    if request.is_http_request():
        raise ValueError(
            "Instances are platform-managed in HTTP mode and cannot be deleted."
        )
    await ctx.info(f"Deleting instance '{name}'...")
    info = await run_blocking(stdio.delete_instance_from_config, name)
    return compact_json(info)


@mcp.tool(
    title="Get Current Instance",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_current_instance(ctx: Context) -> str:
    """Confirm which instance is active, whether it can be reached, and its version."""

    # Strip api_key from return value
    current_instance = asdict(request.get_pinned_instance())
    current_instance.pop("api_key", None)
    current_instance["connection_status"] = "failed"
    try:
        client = get_dss_client()
        version = await run_blocking(
            lambda: client.get_instance_info().raw.get("dssVersion") or ""
        )
    except Exception:
        pass
    else:
        current_instance["connection_status"] = "connected"
        current_instance["dataiku_version"] = version

    result = omit_empty(current_instance)
    return compact_json(result)


@mcp.tool(
    title="Configure Dataiku Instance",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    tags={DSS_INDEPENDENT_TOOL_TAG},
)
async def configure_instance(ctx: Context) -> str:
    """Connect a Dataiku instance, prompting the user in a local browser for its URL and key."""
    if request.is_http_request():
        raise ValueError(
            "Instances are platform-managed in HTTP mode and cannot be configured."
        )
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

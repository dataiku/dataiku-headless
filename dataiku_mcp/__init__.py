"""Dataiku MCP server package.

Exposes Dataiku operations through FastMCP tools.
"""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams

load_dotenv(Path(__file__).parent.parent / ".env")

from . import config, config_mcp  # noqa: E402
from .tools.utils.async_executor import run_blocking  # noqa: E402
from .tools.utils.auth import exchange_http_token  # noqa: E402


_INSTANCE_PROFILE_TOOLS = {
    "list_instances",
    "switch_instance",
    "delete_instance",
    "get_current_instance",
    "configure_instance",
}


def _http_auth() -> JWTVerifier:
    settings = config.get_http_auth_settings()
    return JWTVerifier(
        jwks_uri=settings["jwks_uri"],
        issuer=settings["issuer"],
        audience=settings["audience"],
        required_scopes=[settings["scope"]],
    )


def _tool_name(context: MiddlewareContext[CallToolRequestParams]) -> str:
    message = context.message
    return getattr(message, "name", "") or getattr(
        getattr(message, "params", None), "name", ""
    )


class InstancePinningMiddleware(Middleware):
    """Pin the active Dataiku instance for each MCP tool call."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, Any],
    ) -> Any:
        access_token = get_access_token()
        identity_token = None
        delegated_token = None
        if access_token is not None:
            claims = access_token.claims
            identity_token = config.bind_http_identity(
                str(claims.get("iss", "")), str(claims.get("sub", ""))
            )

        token = config.pin_current_instance()
        try:
            if (
                access_token is not None
                and _tool_name(context) not in _INSTANCE_PROFILE_TOOLS
            ):
                delegated = await run_blocking(exchange_http_token, access_token.token)
                delegated_token = config.set_http_dss_token(delegated)
            return await call_next(context)
        finally:
            if delegated_token is not None:
                config.reset_http_dss_token(delegated_token)
            config.reset_pinned_instance(token)
            if identity_token is not None:
                config.reset_http_identity(identity_token)


# Create MCP instance
mcp = FastMCP("Dataiku", middleware=[InstancePinningMiddleware()])

config.initialize_current_instance()

# Import all modules to register tools and resources
from .tools import (  # noqa: F401,E402
    agent_reviews,
    agents,
    cobuild,
    code_environments,
    connections,
    cross_project_sharing,
    dashboards,
    data_collections,
    data_quality,
    datasets,
    evaluation_stores,
    flow,
    general_settings,
    groups,
    insights,
    instances,
    jobs,
    licensing,
    llms_and_knowledge_banks,
    managed_folders,
    project_folders,
    project_libraries,
    projects,
    recipes,
    scenarios,
    semantic_models,
    users,
    webapps,
    wikis,
)
from .tools.machine_learning import (  # noqa: F401,E402
    analyses,
    saved_models,
)


def run_server():
    """Run the MCP server in stdio mode."""
    config_mcp.logger.info("Starting Dataiku MCP server (stdio)")
    mcp.run(transport="stdio")


def run_http_server(settings_path: Path | None = None):
    """Run the MCP server with authenticated Streamable HTTP transport."""
    config.set_http_config_path(settings_path)
    settings = config.get_http_server_settings()
    mcp.auth = _http_auth()
    config_mcp.logger.info("Starting Dataiku MCP server (streamable HTTP)")
    mcp.run(transport="streamable-http", **settings)


__all__ = ["mcp", "run_server", "run_http_server"]

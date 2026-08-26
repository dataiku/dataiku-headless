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

from . import config_mcp  # noqa: E402
from .auth import exchange_http_token  # noqa: E402
from .config import http, request, stdio  # noqa: E402


# These tools only manage MCP-local instance preferences. They must never create
# a DSS client, so HTTP requests for them deliberately skip token exchange.
HTTP_LOCAL_ONLY_TOOL_NAMES = frozenset(
    {
        "list_instances",
        "switch_instance",
        "delete_instance",
        "get_current_instance",
        "configure_instance",
    }
)


def _http_auth() -> JWTVerifier:
    settings = http.get_auth_settings()
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


class RequestContextMiddleware(Middleware):
    """Bind request identity, active instance, and delegated DSS credentials."""

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
            identity_token = request.bind_http_identity(
                str(claims.get("iss", "")), str(claims.get("sub", ""))
            )

        pinned_instance_token = None
        try:
            pinned_instance_token = request.pin_current_instance()
            if (
                access_token is not None
                and _tool_name(context) not in HTTP_LOCAL_ONLY_TOOL_NAMES
            ):
                delegated = await exchange_http_token(access_token.token)
                delegated_token = request.set_http_dss_token(delegated)
            return await call_next(context)
        finally:
            if delegated_token is not None:
                request.reset_http_dss_token(delegated_token)
            if pinned_instance_token is not None:
                request.reset_pinned_instance(pinned_instance_token)
            if identity_token is not None:
                request.reset_http_identity(identity_token)


# Create MCP instance
mcp = FastMCP("Dataiku", middleware=[RequestContextMiddleware()])

stdio.initialize_current_instance()

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


def run_stdio_server():
    """Run the MCP server in stdio mode."""
    config_mcp.logger.info("Starting Dataiku MCP server (stdio)")
    mcp.run(transport="stdio")


def run_http_server(settings_path: Path | None = None):
    """Run the MCP server with authenticated Streamable HTTP transport."""
    http.set_settings_path(settings_path)
    settings = http.get_server_settings()
    mcp.auth = _http_auth()
    config_mcp.logger.info("Starting Dataiku MCP server (streamable HTTP)")
    mcp.run(transport="streamable-http", **settings)


__all__ = ["mcp", "run_stdio_server", "run_http_server"]

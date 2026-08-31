"""FastMCP server construction, request middleware, and transport startup."""

import logging
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams

from .auth import exchange_http_token
from .config import http, request, stdio

logger = logging.getLogger("dataiku-mcp")


# Tools with this tag only manage MCP-local state and never create a DSS client.
DSS_INDEPENDENT_TOOL_TAG = "dss-independent"


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


async def _tool_requires_dss_token(
    context: MiddlewareContext[CallToolRequestParams],
) -> bool:
    fastmcp_context = context.fastmcp_context
    if fastmcp_context is None:
        return True

    tool = await fastmcp_context.fastmcp.get_tool(_tool_name(context))
    return tool is None or DSS_INDEPENDENT_TOOL_TAG not in tool.tags


class RequestContextMiddleware(Middleware):
    """Bind request identity, active instance, and delegated DSS credentials."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, Any],
    ) -> Any:
        http_identity_reset_token = None
        delegated_token_reset_token = None
        pinned_instance_reset_token = None

        incoming_access_token = get_access_token()
        if incoming_access_token is not None:
            claims = incoming_access_token.claims
            http_identity_reset_token = request.bind_http_identity(
                str(claims.get("iss", "")), str(claims.get("sub", ""))
            )

        try:
            pinned_instance_reset_token = request.pin_current_instance()
            if incoming_access_token is not None and await _tool_requires_dss_token(context):
                delegated_dss_token = await exchange_http_token(incoming_access_token.token)
                delegated_token_reset_token = request.bind_http_dss_token(delegated_dss_token)
            return await call_next(context)
        finally:
            if delegated_token_reset_token is not None:
                request.reset_http_dss_token(delegated_token_reset_token)
            if pinned_instance_reset_token is not None:
                request.reset_pinned_instance(pinned_instance_reset_token)
            if http_identity_reset_token is not None:
                request.reset_http_identity(http_identity_reset_token)


mcp = FastMCP("Dataiku", middleware=[RequestContextMiddleware()])


def run_stdio_server():
    """Run the MCP server in stdio mode."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Dataiku MCP server (stdio)")
    stdio.initialize_current_instance()
    mcp.run(transport="stdio")


def run_http_server(settings_path: Path | None = None):
    """Run the MCP server with authenticated Streamable HTTP transport."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Dataiku MCP server (streamable HTTP)")
    http.set_settings_path(settings_path)
    settings = http.get_server_settings()
    mcp.auth = _http_auth()
    mcp.run(transport="streamable-http", **settings)

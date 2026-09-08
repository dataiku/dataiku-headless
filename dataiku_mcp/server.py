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

"""FastMCP server construction, request middleware, and transport startup."""

import logging
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth import MultiAuth
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams

from .auth import exchange_http_token
from .config import http, request, stdio

logger = logging.getLogger("dataiku-mcp")


# Tools with this tag only manage MCP-local state and never create a DSS client.
DSS_INDEPENDENT_TOOL_TAG = "dss-independent"


def _http_auth() -> JWTVerifier | MultiAuth:
    auth_settings = http.get_auth_settings()
    direct_token_verifier = JWTVerifier(
        jwks_uri=auth_settings.jwks_uri,
        issuer=auth_settings.issuer,
        audience=auth_settings.required_audience,
        required_scopes=[auth_settings.required_scope],
    )
    if auth_settings.provider == "entra":
        interactive_enabled = auth_settings.interactive_login
    else:
        interactive_enabled = auth_settings.interactive_login is not None
    if not interactive_enabled:
        return direct_token_verifier

    server_settings = http.get_server_settings()
    if auth_settings.provider == "entra":
        interactive_provider = AzureProvider(
            client_id=auth_settings.client_id,
            client_secret=auth_settings.client_secret,
            tenant_id=auth_settings.tenant_id,
            required_scopes=[auth_settings.required_scope],
            base_url=server_settings.public_url,
            token_issuer=auth_settings.issuer,
        )
    else:
        interactive_settings = auth_settings.interactive_login
        interactive_provider = OIDCProxy(
            config_url=(
                f"{auth_settings.issuer.rstrip('/')}/.well-known/openid-configuration"
            ),
            client_id=interactive_settings.client_id,
            client_secret=interactive_settings.client_secret,
            token_verifier=direct_token_verifier,
            base_url=server_settings.public_url,
            forward_resource=False,
        )
    return MultiAuth(server=interactive_provider, verifiers=direct_token_verifier)


async def _tool_requires_dss_token(
    context: MiddlewareContext[CallToolRequestParams],
) -> bool:
    fastmcp_context = context.fastmcp_context
    if fastmcp_context is None:
        return True

    tool = await fastmcp_context.fastmcp.get_tool(context.message.name)
    return tool is None or DSS_INDEPENDENT_TOOL_TAG not in tool.tags


class RequestContextMiddleware(Middleware):
    """Bind request identity, active instance, and delegated DSS credentials."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, Any],
    ) -> Any:
        http_identity_reset_token = None
        dss_token_reset_token = None
        pinned_instance_reset_token = None

        access_token = get_access_token()
        if access_token is not None:
            claims = access_token.claims
            http_identity_reset_token = request.bind_http_identity(
                str(claims.get("iss", "")), str(claims.get("sub", ""))
            )

        try:
            pinned_instance_reset_token = request.pin_current_instance()
            if access_token is not None and await _tool_requires_dss_token(context):
                dss_token = await exchange_http_token(access_token.token)
                dss_token_reset_token = request.bind_http_dss_token(dss_token)
            return await call_next(context)
        finally:
            if dss_token_reset_token is not None:
                request.reset_http_dss_token(dss_token_reset_token)
            if pinned_instance_reset_token is not None:
                request.reset_pinned_instance(pinned_instance_reset_token)
            if http_identity_reset_token is not None:
                request.reset_http_identity(http_identity_reset_token)


mcp = FastMCP("Dataiku", middleware=[RequestContextMiddleware()])


def run_stdio_server(settings_path: Path | None = None):
    """Run the MCP server in stdio mode."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Dataiku MCP server (stdio)")
    stdio.set_settings_path(settings_path)
    stdio.initialize_config()
    mcp.run(transport="stdio")


def run_http_server(settings_path: Path | None = None):
    """Run the MCP server with authenticated Streamable HTTP transport."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Dataiku MCP server (streamable HTTP)")
    http.set_settings_path(settings_path)
    http.initialize_config()
    server_settings = http.get_server_settings()
    mcp.auth = _http_auth()
    mcp.run(
        transport="streamable-http",
        host=server_settings.host,
        port=server_settings.port,
        path=server_settings.path,
    )

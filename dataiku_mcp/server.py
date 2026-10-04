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

"""FastMCP server construction, request middleware, and stdio startup."""

import logging
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams

from .config import request, stdio

logger = logging.getLogger("dataiku-mcp")


class RequestContextMiddleware(Middleware):
    """Pin the active instance for the duration of each tool call."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, Any],
    ) -> Any:
        token = request.pin_current_instance()
        try:
            return await call_next(context)
        finally:
            request.reset_pinned_instance(token)


mcp = FastMCP("Dataiku", middleware=[RequestContextMiddleware()])


def run_stdio_server(settings_path: Path | None = None):
    """Run the MCP server in stdio mode."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Dataiku MCP server (stdio)")
    stdio.set_settings_path(settings_path)
    stdio.initialize_config()
    mcp.run(transport="stdio")

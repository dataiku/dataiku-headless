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

"""Dataiku MCP server package.

Exposes Dataiku operations through FastMCP tools.
"""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams

load_dotenv(Path(__file__).parent.parent / ".env")

from . import config, config_mcp  # noqa: E402


class InstancePinningMiddleware(Middleware):
    """Pin the active Dataiku instance for each MCP tool call."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, Any],
    ) -> Any:
        token = config.pin_current_instance()
        try:
            return await call_next(context)
        finally:
            config.reset_pinned_instance(token)


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


__all__ = ["mcp", "run_server"]

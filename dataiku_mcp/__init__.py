"""Dataiku MCP server package.

Exposes Dataiku DSS operations through FastMCP tools.
"""

from typing import Literal
from pathlib import Path
from dotenv import load_dotenv

from fastmcp import FastMCP
from fastmcp.server.transforms.search import BM25SearchTransform

load_dotenv(Path(__file__).parent.parent / ".env")

# Create MCP instance
mcp = FastMCP("Dataiku DSS")

# Load MCP server and DSS instance configuration
from . import (  # noqa: E402
    config,
    config_mcp,
)
config.load_dss_instances()

# Import all modules to register tools and resources
from .tools import (  # noqa: F401,E402
    agent_reviews,
    agents,
    code_environments,
    cobuild,
    connections,
    cross_project_sharing,
    dashboards,
    data_collections,
    data_quality,
    datasets,
    evaluation_stores,
    flow,
    insights,
    instances,
    jobs,
    llms_and_knowledge_banks,
    managed_folders,
    project_libraries,
    projects,
    recipes,
    scenarios,
    semantic_models,
    webapps,
    wikis,
)
from .tools.machine_learning import (  # noqa: F401,E402
    analyses,
    saved_models,
)

# Detect Transport mode, and enable/disable tools based on mode
Transport = Literal["stdio", "streamable-http"]
transport: Transport

raw_transport = config_mcp.DKU_MCP_TRANSPORT.strip().lower()
if raw_transport == "stdio":
    transport = "stdio"
elif raw_transport == "streamable-http":
    transport = "streamable-http"
else:
    raise ValueError(
        f"Invalid DKU_MCP_TRANSPORT '{config_mcp.DKU_MCP_TRANSPORT}'. "
        f"Allowed values: ['stdio', 'streamable-http']"
    )

if transport == "stdio":
    mcp.local_provider.remove_tool("create_upload_dataset_from_rows")
elif transport == "streamable-http":
    mcp.local_provider.remove_tool("create_upload_dataset")
    mcp.local_provider.remove_tool("switch_instance")
    mcp.local_provider.remove_tool("list_instances")

if config_mcp.DKU_MCP_COBUILD_MODE == "FULL":
    for tool_name in sorted(config_mcp.FULL_COBUILD_DISABLED_TOOLS):
        mcp.local_provider.remove_tool(tool_name)

# Configure MCP search mode
if config_mcp.DKU_MCP_TOOL_EXPOSURE == "search":
    mcp.add_transform(
        BM25SearchTransform(
            max_results=config_mcp.DKU_MCP_SEARCH_MAX_RESULTS,
            always_visible=config_mcp.DKU_MCP_SEARCH_ALWAYS_VISIBLE,
        )
    )
    config_mcp.logger.info(
        "Enabled MCP search tool exposure mode with max_results=%s always_visible=%s",
        config_mcp.DKU_MCP_SEARCH_MAX_RESULTS,
        config_mcp.DKU_MCP_SEARCH_ALWAYS_VISIBLE,
    )


def run_server():
    """Run the MCP server."""
    config_mcp.logger.info("Starting Dataiku MCP server with transport=%s", transport)
    mcp.run(transport=transport)


__all__ = ["mcp", "run_server"]

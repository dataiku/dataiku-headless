"""Dataiku MCP server package.

Exposes Dataiku operations through FastMCP tools.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv(Path(__file__).parent.parent / ".env")

# Create MCP instance
mcp = FastMCP("Dataiku")

# Load MCP server and Dataiku instance configuration
from . import (  # noqa: E402
    config,
    config_mcp,
)

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

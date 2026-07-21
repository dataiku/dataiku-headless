"""Dataiku MCP server package.

Exposes Dataiku DSS operations through FastMCP tools.
"""

from typing import Literal
from dotenv import load_dotenv

from fastmcp import FastMCP

from . import config

# Resolve user configuration at runtime. Installed packages must not look for a
# user-owned .env beside their site-packages source tree.
load_dotenv(config.resolve_dotenv_path())

# Create MCP instance
mcp = FastMCP("Dataiku DSS")

# Load MCP server and DSS instance configuration
from . import config_mcp  # noqa: E402
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
    object_settings,
    project_audit,
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

# Detect transport mode. The registered catalog is fixed; the sole runtime
# difference is whether a tool requires a path on the MCP server's filesystem.
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
    # Under HTTP the caller is remote. A filepath/local_path argument would name
    # the server's filesystem, so no server-file-reading tool is exposed.
    mcp.local_provider.remove_tool("create_upload_dataset")
    mcp.local_provider.remove_tool("upload_file_to_managed_folder")
    mcp.local_provider.remove_tool("write_project_library_file")
    mcp.local_provider.remove_tool("switch_instance")
    mcp.local_provider.remove_tool("list_instances")


def run_server():
    """Run the MCP server."""
    config_mcp.logger.info("Starting Dataiku MCP server with transport=%s", transport)
    mcp.run(transport=transport)


__all__ = ["mcp", "run_server"]

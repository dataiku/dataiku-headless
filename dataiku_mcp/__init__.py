"""Dataiku MCP server package.

Exposes Dataiku DSS operations through FastMCP tools.
"""

from typing import Literal
from dotenv import load_dotenv

from fastmcp import FastMCP

# config is side-effect-free at import; it owns the $DKU_CONFIG_DIR -> cwd ->
# ~/.config/dataiku-headless search order for both config.json and .env. The
# package directory is never consulted — for installed copies (uvx/pip) it sits
# beside site-packages, where no user configuration lives.
from . import config

load_dotenv(config.resolve_dotenv_path())

# Create MCP instance
mcp = FastMCP("Dataiku DSS")

# Load MCP server and DSS instance configuration
from . import config_mcp  # noqa: E402

config.load_dss_instances()

# Import all modules to register tools and resources
from .tools import (  # noqa: F401,E402
    agents,
    code_environments,
    cobuild,
    connections,
    cross_project_sharing,
    data_collections,
    data_quality,
    datasets,
    flow,
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
)
from .tools.machine_learning import (  # noqa: F401,E402
    analyses,
    saved_models,
)

# Detect Transport mode, and enable/disable tools based on mode.
#
# Transport-gating rule: no tool that reads the *server's* local filesystem on
# behalf of a caller is exposed over streamable-http. Under HTTP the caller is
# remote, so a filepath argument would let it read arbitrary server-side files.
# Every filepath/local_path-taking tool is therefore removed under HTTP:
#   * create_upload_dataset            (reads a server-local ``filepath``)
#   * upload_file_to_managed_folder    (reads a server-local ``local_path``)
#   * write_project_library_file       (reads a server-local ``filepath``)
# The rows-based ``create_upload_dataset_from_rows`` (no server file read) is the
# HTTP-safe alternative, so under stdio it is removed in favor of the file tool.
# ``switch_instance`` / ``list_instances`` are stdio-only multi-instance controls.
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
    # No server-filesystem-reading tool is exposed over HTTP.
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

"""Dataiku MCP server package.

Exposes Dataiku operations through FastMCP tools.
"""

from .server import mcp, run_http_server, run_stdio_server

# Import all modules to register tools and resources
from .tools import (  # noqa: F401
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
from .tools.machine_learning import (  # noqa: F401
    analyses,
    saved_models,
)


__all__ = ["mcp", "run_stdio_server", "run_http_server"]

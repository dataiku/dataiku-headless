"""Project exploration, listing, and limited creation tools."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)


@mcp.tool(
    title="Count projects",
    annotations={
        "title": "Count projects",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def count_projects(ctx: Context) -> str:
    """Count projects on the Dataiku instance without listing project metadata."""
    await ctx.info("Counting Dataiku projects...")
    project_keys = await run_blocking(lambda: get_dss_client().list_project_keys())
    return compact_json({"project_count": len(project_keys)})


@mcp.tool()
async def list_projects(ctx: Context, search: str = "") -> str:
    """List the projects on the Dataiku instance."""
    await ctx.info("Listing Dataiku projects...")
    raw_projects = await run_blocking(lambda: get_dss_client().list_projects())
    projects = [
        {
            "projectKey": project["projectKey"],
            "name": project.get("name", ""),
            "shortDesc": project.get("shortDesc", ""),
        }
        for project in raw_projects
    ]
    if search:
        q = search.lower()
        projects = [
            project
            for project in projects
            if q in project["projectKey"].lower()
            or q in project["name"].lower()
            or q in project["shortDesc"].lower()
        ]
    return compact_json(
        {"projects": columnar(projects, ["projectKey", "name", "shortDesc"])}
    )


@mcp.tool()
async def create_project(
    project_key: str,
    name: str,
    ctx: Context,
    short_desc: str = "",
) -> str:
    """Create a new project on the Dataiku instance."""
    project_key = _require_non_empty_string(project_key, "project_key")
    name = _require_non_empty_string(name, "name")
    await ctx.info(f"Creating project '{project_key}'...")

    def _run():
        client = get_dss_client()
        auth_info = client.get_auth_info()
        owner = auth_info.get("authIdentifier", "")
        client.create_project(project_key, name, owner=owner, description=short_desc)
        return omit_empty({"projectKey": project_key, "name": name, "owner": owner})

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_project_metadata(project_key: str, ctx: Context) -> str:
    """Get project metadata: label, descriptions, tags, and checklists."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Fetching metadata for project {project_key}...")
    metadata = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_metadata()
    )
    return compact_json(metadata)


@mcp.tool()
async def get_project_variables(project_key: str, ctx: Context) -> str:
    """Get the project variables as {'standard': {...}, 'local': {...}}."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Fetching variables for project {project_key}...")
    variables = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_variables()
    )
    return compact_json(variables)


@mcp.tool()
async def set_project_variables(
    project_key: str,
    variables: dict | str,
    ctx: Context,
) -> str:
    """Set the project variables.

    Args:
        variables: A modified version of the object returned by get_project_variables
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    variables_obj = _coerce_json_object(variables, "variables")
    await ctx.info(f"Updating variables for project {project_key}...")

    def _run():
        get_dss_client().get_project(project_key).set_variables(variables_obj)

    await run_blocking(_run)
    return compact_json({"project_key": project_key})

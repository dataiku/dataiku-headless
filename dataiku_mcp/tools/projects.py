"""Project exploration, listing, and metadata tools."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)


@mcp.tool()
async def count_projects(ctx: Context) -> str:
    """Count projects on the Dataiku instance without listing project metadata."""
    await ctx.info("Counting Dataiku projects...")

    project_keys = await run_blocking(lambda: get_dss_client().list_project_keys())
    return compact_json({"project_count": len(project_keys)})


@mcp.tool()
async def list_projects(ctx: Context, search: str = "") -> str:
    """List the projects on the Dataiku instance.

    Args:
        search: Case-insensitive substring filter matched against project key, name, or description
    """
    await ctx.info("Listing Dataiku projects...")

    raw_projects = await run_blocking(lambda: get_dss_client().list_projects())

    projects = [
        {
            "projectKey": p["projectKey"],
            "name": p.get("name", ""),
            "shortDesc": p.get("shortDesc", ""),
        }
        for p in raw_projects
    ]

    if search:
        q = search.lower()
        projects = [
            p for p in projects
            if q in p["projectKey"].lower()
            or q in p["name"].lower()
            or q in p["shortDesc"].lower()
        ]

    return compact_json(
        {
            "projects": columnar(projects, ["projectKey", "name", "shortDesc"]),
        }
    )


@mcp.tool()
async def create_project(
    project_key: str,
    name: str,
    ctx: Context,
    short_desc: str = "",
) -> str:
    """Create a new project on the Dataiku instance.

    Args:
        project_key: Uppercase identifier, e.g. "MY_PROJECT"
        name: Display name for the project
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    name = _require_non_empty_string(name, "name")

    await ctx.info(f"Creating project '{project_key}'...")

    def _run():
        client = get_dss_client()
        auth_info = client.get_auth_info()
        owner = auth_info.get("authIdentifier", "")
        client.create_project(project_key, name, owner=owner, description=short_desc)
        result = {
            "projectKey": project_key,
            "name": name,
            "owner": owner,
        }
        # Lever 4: omit fields whose value carries no information (None/""/[]/{}).
        # Keeps False and 0 since those are not equal to any empty sentinel.
        return omit_empty(result)

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_project_metadata(project_key: str, ctx: Context) -> str:
    """Get the project metadata: label, short/long description, tags, and checklists."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Fetching metadata for project {project_key}...")

    metadata = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_metadata()
    )
    return compact_json(metadata)


@mcp.tool()
async def set_project_metadata(project_key: str, metadata, ctx: Context) -> str:
    """Set the project metadata.

    Args:
        metadata: A modified version of the object returned by get_project_metadata
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    metadata_obj = _coerce_json_object(metadata, "metadata")
    await ctx.info(f"Updating metadata for project {project_key}...")

    def _run():
        get_dss_client().get_project(project_key).set_metadata(metadata_obj)

    await run_blocking(_run)
    return compact_json({"project_key": project_key})


@mcp.tool()
async def get_project_variables(project_key: str, ctx: Context) -> str:
    """Get the project variables as {"standard": {...}, "local": {...}}. Standard variables are exported with bundles; local variables stay instance-specific."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Fetching variables for project {project_key}...")

    variables = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_variables()
    )
    return compact_json(variables)


@mcp.tool()
async def set_project_variables(project_key: str, variables, ctx: Context) -> str:
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

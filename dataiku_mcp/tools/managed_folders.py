"""Managed folder inspection plus file upload."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)


@mcp.tool()
async def list_managed_folders(project_key: str, ctx: Context) -> str:
    """List the managed folders in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing managed folders in {project_key}...")

    managed_folders = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_managed_folders()
    )
    serialized = []
    for folder_info in managed_folders:
        serialized.append(
            {
                "id": folder_info.get("id"),
                "name": folder_info.get("name"),
                "type": folder_info.get("type"),
                "connection": folder_info.get("params", {}).get("connection"),
                "path": folder_info.get("params", {}).get("path"),
            }
        )
    return compact_json(
        {
            "folders": columnar(
                serialized, ["id", "name", "type", "connection", "path"]
            )
        }
    )


@mcp.tool()
async def get_managed_folder_contents(
    project_key: str,
    folder_id: str,
    ctx: Context,
    max_items: int = 200,
) -> str:
    """List files inside a managed folder."""
    project_key = _require_non_empty_string(project_key, "project_key")
    folder_id = _require_non_empty_string(folder_id, "folder_ref")
    max_items = min(_require_positive_int(max_items, "max_items"), 1000)
    await ctx.info(
        f"Loading managed folder contents for '{folder_id}' in {project_key} "
        f"(max_items={max_items})..."
    )

    def _run():
        folder = get_dss_client().get_project(project_key).get_managed_folder(folder_id)
        folder_info = folder.get_definition()
        folder_items = folder.list_contents().get("items", [])
        serialized_items = [
            {
                "path": item.get("path"),
                "size": item.get("size"),
                "last_modified": item.get("lastModified"),
            }
            for item in folder_items[:max_items]
        ]
        result = omit_empty(
            {
                "folder_id": folder_info.get("id"),
                "folder_name": folder_info.get("name"),
            }
        )
        result["items"] = columnar(serialized_items, ["path", "size", "last_modified"])
        if len(folder_items) > max_items:
            result["truncated"] = True
            result["total_items"] = len(folder_items)
        else:
            result["truncated"] = False
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_managed_folder_info(
    project_key: str,
    folder_id: str,
    ctx: Context,
) -> str:
    """Get a managed folder's id, name, type, connection, and path."""
    project_key = _require_non_empty_string(project_key, "project_key")
    folder_id = _require_non_empty_string(folder_id, "folder_ref")
    await ctx.info(f"Loading managed folder info for '{folder_id}' in {project_key}...")

    folder_info = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_managed_folder(folder_id)
            .get_settings()
            .get_raw()
        )
    )
    result = omit_empty(
        {
            "folder_id": folder_info.get("id"),
            "folder_name": folder_info.get("name"),
            "type": folder_info.get("type"),
            "connection": folder_info.get("params", {}).get("connection"),
            "path": folder_info.get("params", {}).get("path"),
        }
    )
    return compact_json(result)


@mcp.tool()
async def upload_file_to_managed_folder(
    project_key: str,
    folder_id: str,
    target_path: str,
    ctx: Context,
    local_path: str,
) -> str:
    """Upload a local file to a path inside a managed folder, replacing any existing file."""
    project_key = _require_non_empty_string(project_key, "project_key")
    folder_id = _require_non_empty_string(folder_id, "folder_id")
    target_path = _require_non_empty_string(target_path, "target_path")
    local_path = _require_non_empty_string(local_path, "local_path")
    await ctx.info(
        f"Uploading to managed folder '{folder_id}' in {project_key} at "
        f"'{target_path}' from local file '{local_path}'..."
    )

    def _run():
        folder = get_dss_client().get_project(project_key).get_managed_folder(folder_id)
        with open(local_path, "rb") as handle:
            folder.put_file(target_path, handle)
        return omit_empty(
            {
                "folder_id": folder_id,
                "target_path": target_path,
                "local_path": local_path,
            }
        )

    return compact_json(await run_blocking(_run))

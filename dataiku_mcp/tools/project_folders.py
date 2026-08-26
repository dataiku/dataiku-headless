"""Project folder inspection and management tools."""

from fastmcp import Context

from .. import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)

_ROOT_FOLDER_ID = "ROOT"


def _resolve_project_folder(client, folder_id: str):
    normalized = _require_non_empty_string(folder_id, "folder_id")
    if normalized == _ROOT_FOLDER_ID:
        return client.get_root_project_folder()
    return client.get_project_folder(normalized)


def _serialize_project_folder(folder) -> dict:
    parent = folder.get_parent()
    children = folder.list_child_folders()
    return {
        "folder_id": folder.id,
        "name": folder.name or "",
        "path": folder.get_path(),
        "parent_id": parent.id if parent is not None else None,
        "project_count": len(folder.list_project_keys()),
        "child_folders": [
            {"folder_id": child.id, "name": child.name or ""} for child in children
        ],
    }


def _walk_project_folders(client, folder_id: str) -> list[dict]:
    folder = _resolve_project_folder(client, folder_id)
    rows = [_serialize_project_folder(folder)]
    for child in folder.list_child_folders():
        rows.extend(_walk_project_folders(client, child.id))
    return rows


@mcp.tool()
async def list_project_folders(ctx: Context) -> str:
    """List all project folders with their paths and immediate child folders."""
    await ctx.info("Listing Dataiku project folders...")

    def _run():
        client = get_dss_client()
        return _walk_project_folders(client, _ROOT_FOLDER_ID)

    folders = await run_blocking(_run)
    return compact_json(
        {
            "folders": columnar(
                folders,
                [
                    "folder_id",
                    "name",
                    "path",
                    "parent_id",
                    "project_count",
                    "child_folders",
                ],
            )
        }
    )


@mcp.tool()
async def get_project_folder(folder_id: str, ctx: Context) -> str:
    """Get one project folder with its immediate child folders and projects."""
    folder_id = _require_non_empty_string(folder_id, "folder_id")
    await ctx.info(f"Loading project folder {folder_id}...")

    def _run():
        client = get_dss_client()
        folder = _resolve_project_folder(client, folder_id)
        parent = folder.get_parent()
        return {
            "folder_id": folder.id,
            "name": folder.name or "",
            "path": folder.get_path(),
            "parent_id": parent.id if parent is not None else None,
            "child_folders": [
                {
                    "folder_id": child.id,
                    "name": child.name or "",
                    "path": child.get_path(),
                }
                for child in folder.list_child_folders()
            ],
            "projects": [
                {
                    "projectKey": project.project_key,
                    "name": (metadata := project.get_metadata()).get("label")
                    or metadata.get("name")
                    or "",
                    "shortDesc": metadata.get("shortDesc") or "",
                }
                for project in folder.list_projects()
            ],
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_project_folder(
    parent_folder_id: str,
    name: str,
    ctx: Context,
) -> str:
    """Create a project folder under a parent project folder."""
    parent_folder_id = _require_non_empty_string(parent_folder_id, "parent_folder_id")
    name = _require_non_empty_string(name, "name")
    await ctx.info(f"Creating project folder '{name}' under {parent_folder_id}...")

    def _run():
        client = get_dss_client()
        parent_folder = _resolve_project_folder(client, parent_folder_id)
        folder = parent_folder.create_sub_folder(name)
        parent = folder.get_parent()
        return {
            "folder_id": folder.id,
            "name": folder.name or "",
            "path": folder.get_path(),
            "parent_id": parent.id if parent is not None else None,
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def move_project_to_folder(
    project_key: str,
    destination_folder_id: str,
    ctx: Context,
) -> str:
    """Move a project into a project folder."""
    project_key = _require_non_empty_string(project_key, "project_key")
    destination_folder_id = _require_non_empty_string(
        destination_folder_id, "destination_folder_id"
    )
    await ctx.info(f"Moving project {project_key} to folder {destination_folder_id}...")

    def _run():
        client = get_dss_client()
        project = client.get_project(project_key)
        destination_folder = _resolve_project_folder(client, destination_folder_id)
        project.move_to_folder(destination_folder)
        return {
            "project_key": project_key,
            "destination_folder_id": destination_folder.id,
            "destination_path": destination_folder.get_path(),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def delete_project_folder(folder_id: str, ctx: Context) -> str:
    """Delete an empty project folder."""
    folder_id = _require_non_empty_string(folder_id, "folder_id")
    await ctx.info(f"Deleting project folder {folder_id}...")

    def _run():
        client = get_dss_client()
        folder = _resolve_project_folder(client, folder_id)
        if folder.get_parent() is None:
            raise ValueError("Cannot delete the root project folder")
        folder.delete()
        return {"folder_id": folder.id, "deleted": True}

    return compact_json(await run_blocking(_run))

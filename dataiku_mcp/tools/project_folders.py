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

"""Project folder inspection and management tools."""

from typing import Annotated

from fastmcp import Context
from pydantic import Field

from ..server import mcp
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


@mcp.tool(
    title="List Project Folders",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_project_folders(ctx: Context) -> str:
    """Map how the instance's projects are organized into folders."""
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


@mcp.tool(
    title="Get Project Folder",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_project_folder(folder_id: str, ctx: Context) -> str:
    """See what one project folder directly contains."""
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


@mcp.tool(
    title="Create Project Folder",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_project_folder(
    parent_folder_id: Annotated[
        str,
        Field(
            description="ROOT for the top level, else a folder id from list_project_folders."
        ),
    ],
    name: str,
    ctx: Context,
) -> str:
    """Add a folder to organize projects under an existing parent folder."""
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


@mcp.tool(
    title="Move Project to Folder",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def move_project_to_folder(
    project_key: str,
    destination_folder_id: str,
    ctx: Context,
) -> str:
    """Reorganize where a project sits in the folder hierarchy."""
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


@mcp.tool(
    title="Delete Project Folder",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def delete_project_folder(folder_id: str, ctx: Context) -> str:
    """Remove a project folder, which must already be empty."""
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

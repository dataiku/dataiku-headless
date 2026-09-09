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

"""Managed folder creation, inspection, and file upload."""

from typing import Annotated

from fastmcp import Context
from pydantic import Field

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)


@mcp.tool(
    title="Create Managed Folder",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_managed_folder(
    project_key: str,
    name: str,
    connection: Annotated[
        str, Field(description="Dataiku connection that will store the folder's files.")
    ],
    ctx: Context,
    folder_type: Annotated[
        str | None,
        Field(
            description="Storage type, e.g. Filesystem or S3. Inferred from the connection when omitted."
        ),
    ] = None,
) -> str:
    """Create an empty managed folder, to hold files a project needs."""
    project_key = _require_non_empty_string(project_key, "project_key")
    name = _require_non_empty_string(name, "name")
    connection = _require_non_empty_string(connection, "connection")
    if folder_type is not None:
        folder_type = _require_non_empty_string(folder_type, "folder_type")
    await ctx.info(f"Creating managed folder '{name}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        folder = project.create_managed_folder(
            name,
            folder_type=folder_type,
            connection_name=connection,
        )
        folder_info = folder.get_settings().get_raw()
        return omit_empty(
            {
                "folder_id": folder_info.get("id"),
                "folder_name": folder_info.get("name"),
                "type": folder_info.get("type"),
                "connection": folder_info.get("params", {}).get("connection"),
                "path": folder_info.get("params", {}).get("path"),
            }
        )

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="List Managed Folders",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_managed_folders(project_key: str, ctx: Context) -> str:
    """Find a project's managed folders and their IDs."""
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
        {"folders": columnar(serialized, ["id", "name", "type", "connection", "path"])}
    )


@mcp.tool(
    title="Get Managed Folder Contents",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_managed_folder_contents(
    project_key: str,
    folder_id: str,
    ctx: Context,
    max_items: Annotated[
        int, Field(description="Files listed before truncating.")
    ] = 200,
) -> str:
    """See which files a managed folder holds, with their sizes and paths."""
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


@mcp.tool(
    title="Get Managed Folder Info",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_managed_folder_info(
    project_key: str,
    folder_id: str,
    ctx: Context,
) -> str:
    """Read where a managed folder stores its files."""
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


@mcp.tool(
    title="Upload File to Managed Folder",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def upload_file_to_managed_folder(
    project_key: str,
    folder_id: str,
    target_path: Annotated[
        str, Field(description="Destination path inside the managed folder.")
    ],
    ctx: Context,
    local_path: Annotated[
        str, Field(description="Source path on the machine running this server.")
    ],
) -> str:
    """Put a local file into a managed folder, replacing whatever is at that path."""
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

"""Managed folder operations for creating and inspecting folder assets."""

from fastmcp import Context

from .. import config, mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.auth import get_dss_client
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)


@mcp.tool()
async def create_managed_folder(
    project_key: str,
    folder_name: str,
    ctx: Context,
    connection_name: str | None = None,
) -> str:
    """Create a new managed folder in the project.

    Args:
        connection_name: Connection to store the managed folder on
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    folder_name = _require_non_empty_string(folder_name, "folder_name")
    connection_name = connection_name or config.get_current_instance().default_folder_connection
    connection_name = _require_non_empty_string(connection_name, "connection_name")

    await ctx.info(
        f"Creating managed folder '{folder_name}' in {project_key} on connection '{connection_name}'..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        managed_folder = project.create_managed_folder(
            name=folder_name,
            connection_name=connection_name,
        )
        return managed_folder.get_settings().get_raw()

    folder_info = await run_blocking(_run)

    result = {
        "folder_id": folder_info["id"],
        "folder_name": folder_info["name"],
        "type": folder_info["type"],
        "connection": connection_name,
        "path": folder_info.get("params", {}).get("path", ""),
    }
    # LEVER 4: omit empty-valued fields (keeps False / 0)
    result = omit_empty(result)
    return compact_json(result)


@mcp.tool()
async def list_managed_folders(project_key: str, ctx: Context) -> str:
    """List the managed folders in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing managed folders in {project_key}...")

    managed_folders = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_managed_folders()
    )

    serialized_managed_folders = []
    for folder_info in managed_folders:
        row = {
            "id": folder_info.get("id"),
            "name": folder_info.get("name"),
            "type": folder_info.get("type"),
            "connection": folder_info.get("params", {}).get("connection"),
            "path": folder_info.get("params", {}).get("path"),
        }
        serialized_managed_folders.append(row)

    return compact_json({
            "folders": columnar(
                serialized_managed_folders,
                ["id", "name", "type", "connection", "path"],
            ),
        })


@mcp.tool()
async def delete_managed_folder(
    project_key: str,
    folder_id: str,
    ctx: Context,
) -> str:
    """Delete a managed folder from the flow. Does not delete the folder's contents on storage."""
    project_key = _require_non_empty_string(project_key, "project_key")
    folder_id = _require_non_empty_string(folder_id, "folder_id")
    await ctx.info(f"Deleting managed folder '{folder_id}' in {project_key}...")

    def _run():
        folder = get_dss_client().get_project(project_key).get_managed_folder(folder_id)
        folder_name = folder.get_definition().get("name")
        folder.delete()
        return folder_name

    folder_name = await run_blocking(_run)

    result = {
        "folder_name": folder_name,
    }
    # LEVER 4: omit empty-valued fields (keeps False / 0)
    result = omit_empty(result)
    return compact_json(result)


@mcp.tool()
async def get_managed_folder_contents(
    project_key: str,
    folder_id: str,
    ctx: Context,
    max_items: int = 200,
) -> str:
    """List files inside a managed folder (path, size, last modified).

    Args:
        max_items: Maximum number of file entries to return (max 1000)
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    folder_id = _require_non_empty_string(folder_id, "folder_ref")
    max_items = _require_positive_int(max_items, "max_items")
    max_items = min(max_items, 1000)

    await ctx.info(
        f"Loading managed folder contents for '{folder_id}' in {project_key} (max_items={max_items})..."
    )

    def _run():
        folder = get_dss_client().get_project(project_key).get_managed_folder(folder_id)
        folder_info = folder.get_definition()
        folder_items = folder.list_contents().get("items", [])

        serialized_items = []
        for item in folder_items[:max_items]:
            serialized_items.append(
                {
                    "path": item.get("path"),
                    "size": item.get("size"),
                    "last_modified": item.get("lastModified"),
                }
            )

        result = {
            "folder_id": folder_info.get("id"),
            "folder_name": folder_info.get("name"),
        }
        # LEVER 4: omit empty-valued scalar identity fields (keeps False / 0).
        # Note: the columnar `items` block and the `truncated` boolean are added
        # AFTER this filter so they are never dropped (columnar untouched; False kept).
        result = omit_empty(result)

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

    def _run():
        project = get_dss_client().get_project(project_key)
        managed_folder = project.get_managed_folder(folder_id)
        return managed_folder.get_settings().get_raw()

    folder_info = await run_blocking(_run)

    result = {
        "folder_id": folder_info.get("id"),
        "folder_name": folder_info.get("name"),
        "type": folder_info.get("type"),
        "connection": folder_info.get("params", {}).get("connection"),
        "path": folder_info.get("params", {}).get("path"),
    }
    # LEVER 4: omit empty-valued fields (keeps False / 0)
    result = omit_empty(result)
    return compact_json(result)


@mcp.tool()
async def create_files_in_folder_dataset(
    project_key: str,
    folder_id: str,
    dataset_name: str,
    ctx: Context,
    files_selection: dict | None = None,
) -> str:
    """Create a dataset of type FilesInFolder that reads its files from a managed folder.

    Runs autodetect after creation to initialize the format and schema. Autodetect
    failures are non-fatal: the dataset is still created and returned, but format
    and schema may need manual configuration.

    Args:
        files_selection: Optional filesSelectionRules object controlling which files are read.
            When omitted, all files in the folder are read.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    folder_id = _require_non_empty_string(folder_id, "folder_id")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")

    await ctx.info(
        f"Creating FilesInFolder dataset '{dataset_name}' from folder '{folder_id}' in {project_key}..."
    )

    def _run():
        folder = get_dss_client().get_project(project_key).get_managed_folder(folder_id)
        ds = folder.create_dataset_from_files(dataset_name)

        if files_selection is not None:
            settings = ds.get_settings()
            settings.get_raw().setdefault("params", {})["filesSelectionRules"] = files_selection
            settings.save()

        detected_format = None
        detected_columns = None
        autodetect_warning = None
        try:
            detected = ds.autodetect_settings(infer_storage_types=True)
            raw = detected.get_raw()
            detected.save()
            detected_format = raw.get("formatType")
            detected_columns = [
                c.get("name") for c in raw.get("schema", {}).get("columns", [])
            ]
        except Exception as exc:
            autodetect_warning = str(exc)

        result = omit_empty({
            "dataset_name": dataset_name,
            "folder_id": folder_id,
            "detected_format": detected_format,
        })
        result["columns"] = detected_columns
        if autodetect_warning:
            result["autodetect_warning"] = (
                f"Autodetect failed: {autodetect_warning}. "
                "Format and schema may need manual configuration."
            )
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def upload_file_to_managed_folder(
    project_key: str,
    folder_id: str,
    target_path: str,
    ctx: Context,
    local_path: str,
) -> str:
    """Upload a local file to a path inside a managed folder, replacing any existing file.

    Args:
        local_path: Local source file path to upload.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    folder_id = _require_non_empty_string(folder_id, "folder_id")
    target_path = _require_non_empty_string(target_path, "target_path")
    local_path = _require_non_empty_string(local_path, "local_path")

    await ctx.info(
        f"Uploading to managed folder '{folder_id}' in {project_key} at '{target_path}' "
        f"from local file '{local_path}'..."
    )

    def _run():
        folder = get_dss_client().get_project(project_key).get_managed_folder(folder_id)

        with open(local_path, "rb") as handle:
            folder.put_file(target_path, handle)

        result = {
            "folder_id": folder_id,
            "target_path": target_path,
            "local_path": local_path,
        }
        return omit_empty(result)

    return compact_json(await run_blocking(_run))

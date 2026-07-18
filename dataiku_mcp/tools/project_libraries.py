"""Project library operations for Dataiku DSS.

This module intentionally keeps the surface small:

1. Read and manage files and folders in the per-project library tree.
2. Surface external (git-imported) libraries that contribute files to the
   same tree.
"""

import os

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.auth import get_dss_client
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)

DEFAULT_LIST_MAX_ITEMS = 500
DEFAULT_LIST_MAX_DEPTH = 20
DEFAULT_READ_MAX_BYTES = 200_000


def _normalize_library_path(path: str) -> str:
    """Normalize a library path to a leading-slash, no-trailing-slash form."""
    stripped = path.strip()
    if not stripped:
        raise ValueError("path must be a non-empty string")
    normalized = "/" + stripped.strip("/")
    return "/" if normalized == "/" else normalized.rstrip("/")


def _safe_get_folder(library, path: str):
    """Return the folder at ``path``, or None if it doesn't exist or is a file."""
    try:
        return library.get_folder(path)
    except Exception as e:
        if "is a file" in str(e):
            return None
        raise


def _safe_get_file(library, path: str):
    """Return the file at ``path``, or None if it doesn't exist or is a folder."""
    try:
        return library.get_file(path)
    except Exception as e:
        if "is a folder" in str(e):
            return None
        raise


def _ensure_parent_folder(library, file_path: str):
    """Walk ``file_path``, creating any missing intermediate folders."""
    parts = [p for p in file_path.strip("/").split("/") if p]
    if not parts:
        raise ValueError("path must include a file name")
    basename = parts[-1]
    folder = library.root
    for component in parts[:-1]:
        existing = folder.get_child(component)
        if existing is None:
            folder = folder.add_folder(component)
        elif existing.children is None:
            raise ValueError(
                f"Path component '{component}' is a file, expected a folder"
            )
        else:
            folder = existing
    return folder, basename


def _read_local_file_bytes(filepath: str) -> bytes:
    """Load upload content from a readable local file."""
    filepath = _require_non_empty_string(filepath, "filepath")
    if not os.path.exists(filepath):
        raise ValueError(f"Local file not found: {filepath}")
    if not os.path.isfile(filepath):
        raise ValueError(f"Local path is not a file: {filepath}")
    if not os.access(filepath, os.R_OK):
        raise ValueError(f"Local file is not readable: {filepath}")
    with open(filepath, "rb") as f:
        return f.read()


def _load_external_libraries(project) -> tuple[list[dict], str | None]:
    """Load external-library config with explicit error signaling."""
    try:
        payload = project.get_project_git().list_libraries() or {}
        entries = []
        for local_path, ref in ((payload.get("gitReferences") or {}) or {}).items():
            entries.append(
                {
                    "local_path": local_path.strip("/"),
                    "normalized_path": _normalize_library_path(local_path),
                    "remote": ref.get("remote") or ref.get("repository"),
                    "checkout": ref.get("checkout"),
                    "path_in_repo": ref.get("pathInGitRepository")
                    or ref.get("remotePath")
                    or "",
                }
            )
        return sorted(entries, key=lambda entry: entry["local_path"]), None
    except Exception as e:
        return [], (
            "External library configuration is unavailable. Check whether the "
            "caller has permission to inspect external libraries and whether "
            "project git/external-library support is available on this project "
            f"or DSS instance. Details: {str(e).strip()}"
        )


def _match_external_library(item_path: str, external_libraries: list[dict]) -> str | None:
    """Return the external library local path that owns ``item_path``, if any."""
    normalized = _normalize_library_path(item_path)
    matches = []
    for entry in external_libraries:
        prefix = entry["normalized_path"]
        if normalized == prefix or normalized.startswith(prefix + "/"):
            matches.append(entry)
    if not matches:
        return None
    return max(matches, key=lambda entry: len(entry["normalized_path"]))["local_path"]


def _walk_library_tree(
    folder,
    prefix: str,
    external_libraries: list[dict],
    source: str,
    external_config_available: bool,
    max_items: int,
    max_depth: int,
) -> tuple[list[dict], bool]:
    """Flatten a library folder into ``(items, truncated)`` filtered by source.

    Bounded on two axes so a deep or huge library tree cannot produce an
    unbounded payload: at most ``max_items`` matching entries, and descent no
    deeper than ``max_depth`` levels below ``folder``. ``truncated`` is True when
    either bound clipped the walk.
    """
    items: list[dict] = []
    state = {"truncated": False}

    def _walk(node, node_prefix: str, depth: int) -> None:
        for item in node.list():
            if len(items) >= max_items:
                state["truncated"] = True
                return
            item_path = (node_prefix + "/" + item.name).replace("//", "/")
            is_folder = item.children is not None
            external_library = (
                _match_external_library(item_path, external_libraries)
                if external_config_available
                else None
            )
            item_source = (
                "external"
                if external_library is not None
                else ("internal" if external_config_available else "unknown")
            )

            if source in {"all", item_source}:
                entry = {
                    "path": item_path,
                    "type": "folder" if is_folder else "file",
                    "source": item_source,
                }
                if external_library is not None:
                    entry["external_library"] = external_library
                items.append(entry)

            if is_folder:
                if depth + 1 > max_depth:
                    state["truncated"] = True
                    continue
                _walk(item, item_path, depth + 1)
                if len(items) >= max_items:
                    state["truncated"] = True
                    return

    _walk(folder, prefix, 1)
    return items, state["truncated"]


@mcp.tool()
async def list_project_library(
    project_key: str,
    ctx: Context,
    path: str = "/",
    source: str = "all",
    include_external_metadata: bool = False,
    max_items: int = DEFAULT_LIST_MAX_ITEMS,
    max_depth: int = DEFAULT_LIST_MAX_DEPTH,
) -> str:
    """List project library contents, optionally filtering to internal or external items.

    Bounded: at most ``max_items`` entries (default 500) and ``max_depth`` levels
    of descent (default 20). When either bound clips the walk the payload carries
    ``truncated: true`` alongside the applied ``max_items``/``max_depth``.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    path = _normalize_library_path(path or "/")
    source = source.strip().lower() or "all"
    if source not in {"all", "internal", "external"}:
        raise ValueError("source must be one of: all, internal, external")
    max_items = _require_positive_int(max_items, "max_items")
    max_depth = _require_positive_int(max_depth, "max_depth")
    await ctx.info(
        f"Listing project library {project_key} from {path} (source={source}, "
        f"max_items={max_items}, max_depth={max_depth})..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        library = project.get_library()
        folder = library.root if path == "/" else _safe_get_folder(library, path)
        if folder is None:
            raise ValueError(f"Folder not found: {path}")
        external_libraries, external_error = _load_external_libraries(project)
        external_config_available = external_error is None
        if not external_config_available and source != "all":
            raise ValueError(
                "External library configuration is unavailable, so source filtering "
                f"for '{source}' cannot be evaluated. Details: {external_error}"
            )
        prefix = "" if path == "/" else path.rstrip("/")
        walked, tree_truncated = _walk_library_tree(
            folder,
            prefix,
            external_libraries,
            source,
            external_config_available,
            max_items,
            max_depth,
        )
        payload = {
            "path": path,
            "source": source,
            "items": columnar(
                walked,
                ["path", "type", "source", "external_library"],
            ),
        }
        if tree_truncated:
            payload["truncated"] = True
            payload["max_items"] = max_items
            payload["max_depth"] = max_depth
        if not external_config_available:
            payload["external_libraries_available"] = False
            payload["warning"] = (
                "External library configuration is unavailable; item sources are "
                "reported as 'unknown'."
            )
        if include_external_metadata:
            if not external_config_available:
                raise ValueError(
                    "External library metadata is unavailable. "
                    f"Details: {external_error}"
                )
            payload["external_libraries"] = columnar(
                [
                    {
                        "local_path": entry["local_path"],
                        "remote": entry["remote"],
                        "checkout": entry["checkout"],
                        "path_in_repo": entry["path_in_repo"],
                    }
                    for entry in external_libraries
                ],
                ["local_path", "remote", "checkout", "path_in_repo"],
            )
        return payload

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def read_project_library_file(
    project_key: str,
    path: str,
    ctx: Context,
    max_bytes: int = DEFAULT_READ_MAX_BYTES,
) -> str:
    """Read a text file from the project library, bounded to ``max_bytes``.

    The DSS API returns the whole file, so the cap is applied to the *returned*
    content (default 200_000 bytes, measured UTF-8). When the file is larger the
    payload is clipped on a byte boundary and carries ``truncated: true`` with the
    total and returned byte counts.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    path = _normalize_library_path(path)
    max_bytes = _require_positive_int(max_bytes, "max_bytes")
    await ctx.info(
        f"Reading project library file {path} in {project_key} (max_bytes={max_bytes})..."
    )

    def _run():
        library = get_dss_client().get_project(project_key).get_library()
        if _safe_get_folder(library, path) is not None:
            raise ValueError(f"Path is a folder: {path}")
        file = _safe_get_file(library, path)
        if file is None:
            raise ValueError(f"File not found: {path}")
        content = file.read()
        encoded = content.encode("utf-8")
        total_bytes = len(encoded)
        result = {"path": path, "content": content}
        if total_bytes > max_bytes:
            # Clip on a byte boundary; drop any partial trailing multibyte char.
            clipped = encoded[:max_bytes].decode("utf-8", errors="ignore")
            result["content"] = clipped
            result["truncated"] = True
            result["max_bytes"] = max_bytes
            result["bytes_total"] = total_bytes
            result["bytes_returned"] = len(clipped.encode("utf-8"))
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def write_project_library_file(
    project_key: str,
    path: str,
    filepath: str,
    ctx: Context,
    overwrite: bool = False,
) -> str:
    """Create or update a project library file from a local file upload."""
    project_key = _require_non_empty_string(project_key, "project_key")
    path = _normalize_library_path(path)
    filepath = _require_non_empty_string(filepath, "filepath")
    await ctx.info(f"Uploading local file {filepath} to project library {path} in {project_key}...")

    def _run():
        local_bytes = _read_local_file_bytes(filepath)
        library = get_dss_client().get_project(project_key).get_library()
        if _safe_get_folder(library, path) is not None:
            raise ValueError(f"Path already exists as a folder: {path}")
        file = _safe_get_file(library, path)
        if file is not None:
            if not overwrite:
                raise ValueError(
                    f"File '{path}' already exists. Pass overwrite=True to replace it."
                )
            if file.read(as_type="bytes") == local_bytes:
                return {
                    "path": path,
                    "action": "unchanged",
                }
            file.write(local_bytes)
            return {
                "path": path,
                "action": "updated",
            }

        parent, basename = _ensure_parent_folder(library, path)
        new_file = parent.add_file(basename)
        new_file.write(local_bytes)
        return {
            "path": path,
            "action": "created",
        }

    return compact_json(await run_blocking(_run))

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

"""Project library operations for Dataiku.

This module intentionally keeps the surface small:

1. Manage files and folders in the per-project library tree.
2. Search and validate Python library files.
3. Configure external (git-imported) libraries that contribute files to the
   same tree.
"""

import ast
import fnmatch
import os
import re

from fastmcp import Context

from ..server import mcp
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from ..auth import get_dss_client
from .utils.validation import require_non_empty_string as _require_non_empty_string


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


def _resolve_item(library, path: str):
    """Return the folder or file at ``path``, or None if it doesn't exist."""
    folder = _safe_get_folder(library, path)
    if folder is not None:
        return folder
    return _safe_get_file(library, path)


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
            f"or Dataiku instance. Details: {str(e).strip()}"
        )


def _match_external_library(
    item_path: str, external_libraries: list[dict]
) -> str | None:
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
) -> list[dict]:
    """Flatten a library folder into a list of items filtered by source."""
    items = []
    for item in folder.list():
        item_path = (prefix + "/" + item.name).replace("//", "/")
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
            items.extend(
                _walk_library_tree(
                    item,
                    item_path,
                    external_libraries,
                    source,
                    external_config_available,
                )
            )
    return items


def _ast_validate_python(content: str) -> dict:
    """Run ``ast.parse`` on ``content`` and extract its imports."""
    import_columns = [
        "module",
        "imported_name",
        "alias",
        "line",
        "from",
        "relative_level",
    ]
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        syntax_error = {
            "message": str(e.msg),
            "line": e.lineno,
            "column": e.offset,
            "text": (e.text or "").rstrip(),
        }
        syntax_error = omit_empty(syntax_error)
        return {
            "syntax_error": syntax_error,
            "imports": columnar([], import_columns),
        }

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    {
                        "module": alias.name,
                        "imported_name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                        "from": False,
                        "relative_level": 0,
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                full = f"{module}.{alias.name}" if module else alias.name
                imports.append(
                    {
                        "module": full,
                        "imported_name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                        "from": True,
                        "relative_level": node.level,
                    }
                )
    return {
        "imports": columnar(imports, import_columns),
    }


@mcp.tool()
async def list_project_library(
    project_key: str,
    ctx: Context,
    path: str = "/",
    source: str = "all",
    include_external_metadata: bool = False,
) -> str:
    """List project library contents, optionally filtering to internal or external items."""
    project_key = _require_non_empty_string(project_key, "project_key")
    path = _normalize_library_path(path or "/")
    source = source.strip().lower() or "all"
    if source not in {"all", "internal", "external"}:
        raise ValueError("source must be one of: all, internal, external")
    await ctx.info(
        f"Listing project library {project_key} from {path} (source={source})..."
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
        payload = {
            "path": path,
            "source": source,
            "items": columnar(
                _walk_library_tree(
                    folder,
                    prefix,
                    external_libraries,
                    source,
                    external_config_available,
                ),
                ["path", "type", "source", "external_library"],
            ),
        }
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
) -> str:
    """Read a text file from the project library."""
    project_key = _require_non_empty_string(project_key, "project_key")
    path = _normalize_library_path(path)
    await ctx.info(f"Reading project library file {path} in {project_key}...")

    def _run():
        library = get_dss_client().get_project(project_key).get_library()
        if _safe_get_folder(library, path) is not None:
            raise ValueError(f"Path is a folder: {path}")
        file = _safe_get_file(library, path)
        if file is None:
            raise ValueError(f"File not found: {path}")
        return {
            "path": path,
            "content": file.read(),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def search_project_library(
    project_key: str,
    query: str,
    ctx: Context,
    path: str = "/",
    is_regex: bool = False,
    case_insensitive: bool = False,
    file_glob: str = "",
    max_matches: int = 200,
) -> str:
    """Search project library files using substring or regex matching."""
    project_key = _require_non_empty_string(project_key, "project_key")
    query = _require_non_empty_string(query, "query")
    path = _normalize_library_path(path or "/")
    if max_matches < 1 or max_matches > 5000:
        raise ValueError("max_matches must be between 1 and 5000")
    await ctx.info(
        f"Searching project library {project_key} under {path} for "
        f"{'regex' if is_regex else 'substring'} '{query}'..."
    )

    flags = re.IGNORECASE if case_insensitive else 0
    if is_regex:
        try:
            regex = re.compile(query, flags)
        except re.error as e:
            raise ValueError(f"Invalid regex: {e}") from e
    else:
        regex = re.compile(re.escape(query), flags)

    glob_re = re.compile(fnmatch.translate(file_glob)) if file_glob else None

    def _run():
        project = get_dss_client().get_project(project_key)
        library = project.get_library()
        folder = library.root if path == "/" else _safe_get_folder(library, path)
        if folder is None:
            raise ValueError(f"Folder not found: {path}")
        external_libraries, external_error = _load_external_libraries(project)
        external_config_available = external_error is None
        prefix = "" if path == "/" else path.rstrip("/")

        matches = []
        truncated = False
        for entry in _walk_library_tree(
            folder,
            prefix,
            external_libraries,
            "all",
            external_config_available,
        ):
            if entry["type"] != "file":
                continue
            if glob_re is not None and not glob_re.match(entry["path"]):
                continue
            file = library.get_file(entry["path"])
            if file is None:
                continue
            try:
                text = file.read()
            except Exception:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(
                        {
                            "path": entry["path"],
                            "line": lineno,
                            "text": line[:500],
                        }
                    )
                    if len(matches) >= max_matches:
                        truncated = True
                        return {
                            "path": path,
                            "matches": columnar(matches, ["path", "line", "text"]),
                            "truncated": truncated,
                            **(
                                {
                                    "external_libraries_available": False,
                                    "warning": (
                                        "External library configuration is unavailable; "
                                        "search results may include both internal and "
                                        "external-backed files without distinction."
                                    ),
                                }
                                if not external_config_available
                                else {}
                            ),
                        }
        return {
            "path": path,
            "matches": columnar(matches, ["path", "line", "text"]),
            "truncated": truncated,
            **(
                {
                    "external_libraries_available": False,
                    "warning": (
                        "External library configuration is unavailable; search "
                        "results may include both internal and external-backed "
                        "files without distinction."
                    ),
                }
                if not external_config_available
                else {}
            ),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def validate_project_library_file(
    project_key: str,
    path: str,
    ctx: Context,
    content: str | None = None,
) -> str:
    """Validate a project library file, with Python AST parsing for ``.py`` files."""
    project_key = _require_non_empty_string(project_key, "project_key")
    path = _normalize_library_path(path)
    await ctx.info(f"Validating project library file {path} in {project_key}...")

    is_python = path.lower().endswith(".py")

    if content is None:

        def _read():
            library = get_dss_client().get_project(project_key).get_library()
            if _safe_get_folder(library, path) is not None:
                raise ValueError(f"Path is a folder: {path}")
            file = _safe_get_file(library, path)
            if file is None:
                raise ValueError(f"File not found: {path}")
            return file.read()

        content = await run_blocking(_read)

    base = {
        "path": path,
        "language": "python"
        if is_python
        else (path.rsplit(".", 1)[-1].lower() if "." in path else "unknown"),
    }
    if not is_python:
        return compact_json(
            {**base, "is_valid": True, "checks_skipped": "non-python file"}
        )

    return compact_json({**base, **_ast_validate_python(content)})


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
    await ctx.info(
        f"Uploading local file {filepath} to project library {path} in {project_key}..."
    )

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

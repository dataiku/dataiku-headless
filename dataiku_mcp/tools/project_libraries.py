"""Project library operations for Dataiku DSS.

This module intentionally keeps the surface small:

1. Manage files and folders in the per-project library tree.
2. Search and validate Python library files.
3. Configure external (git-imported) libraries that contribute files to the
   same tree.
"""

import ast
import fnmatch
import os
import time

import regex

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import bounded_compact_json, columnar, omit_empty
from .utils.auth import get_dss_client
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)


_DEFAULT_LIST_ITEMS = 500
_MAX_LIST_ITEMS = 2_000
_DEFAULT_VISITED_NODES = 2_000
_MAX_VISITED_NODES = 10_000
_DEFAULT_LIBRARY_DEPTH = 20
_MAX_LIBRARY_DEPTH = 50
_DEFAULT_READ_BYTES = 200_000
_MAX_FILE_BYTES = 1_000_000
_MAX_RESPONSE_BYTES = 1_000_000
_MAX_LIBRARY_PATH_CHARACTERS = 4_096
_DEFAULT_SEARCH_FILES = 200
_MAX_SEARCH_FILES = 1_000
_MAX_EXTERNAL_LIBRARIES = 1_000
_MAX_QUERY_CHARACTERS = 500
_MAX_GLOB_CHARACTERS = 500
_REGEX_MATCH_TIMEOUT_SECONDS = 0.05
_SEARCH_TIME_BUDGET_SECONDS = 5.0


def _bounded_positive_int(value: int, field_name: str, hard_max: int) -> int:
    """Validate a positive integer without silently weakening its requested bound."""
    value = _require_positive_int(value, field_name)
    if value > hard_max:
        raise ValueError(f"'{field_name}' must be <= {hard_max}")
    return value


def _read_library_bytes(file) -> bytes:
    """Read a library file as bytes and reject unexpected SDK return types."""
    raw = file.read(as_type="bytes")
    if not isinstance(raw, bytes):
        raise ValueError("DSS returned a non-byte project library payload")
    return raw


def _decode_utf8_prefix(raw: bytes, max_bytes: int) -> tuple[str, int, bool]:
    """Decode at most ``max_bytes`` without returning a split UTF-8 code point."""
    truncated = len(raw) > max_bytes
    prefix = raw[:max_bytes]
    try:
        return prefix.decode("utf-8"), len(prefix), truncated
    except UnicodeDecodeError as exc:
        # A byte cap can cut through the final code point. Remove only that
        # incomplete suffix; malformed UTF-8 elsewhere is still an error.
        if truncated and exc.end == len(prefix):
            prefix = prefix[: exc.start]
            try:
                return prefix.decode("utf-8"), len(prefix), True
            except UnicodeDecodeError:
                pass
        raise ValueError("Project library file is not valid UTF-8 text") from exc


def _normalize_library_path(path: str) -> str:
    """Normalize a library path to a leading-slash, no-trailing-slash form."""
    stripped = path.strip()
    if not stripped:
        raise ValueError("path must be a non-empty string")
    normalized = "/" + stripped.strip("/")
    normalized = "/" if normalized == "/" else normalized.rstrip("/")
    if len(normalized) > _MAX_LIBRARY_PATH_CHARACTERS:
        raise ValueError(
            f"path must be <= {_MAX_LIBRARY_PATH_CHARACTERS} characters"
        )
    return normalized


def _tool_json(payload) -> str:
    """Serialize a project-library result under the shared hard ceiling."""
    return bounded_compact_json(payload, _MAX_RESPONSE_BYTES)


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
        references = (payload.get("gitReferences") or {}) or {}
        if len(references) > _MAX_EXTERNAL_LIBRARIES:
            return [], (
                "External library configuration exceeds the supported "
                f"{_MAX_EXTERNAL_LIBRARIES}-entry classification limit."
            )
        entries = []
        for local_path, ref in references.items():
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
    except Exception as exc:
        return [], (
            "External library configuration is unavailable. Check whether the "
            "caller has permission to inspect external libraries and whether "
            "project git/external-library support is available on this project "
            f"or DSS instance ({type(exc).__name__})."
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
    max_visited_nodes: int,
    max_depth: int,
    deadline: float | None = None,
) -> dict:
    """Flatten a library tree with independent output, work, and depth limits.

    ``visited_nodes`` counts every inspected node, including entries filtered out
    by ``source``. This distinction matters: limiting only returned matches lets a
    selective filter walk an arbitrarily large tree.
    """
    items: list[dict] = []
    visited_nodes = 0
    truncation_reasons: set[str] = set()
    stack = [
        (item, prefix, 1)
        for item in reversed(folder.list())
    ]

    while stack:
        if deadline is not None and time.monotonic() >= deadline:
            truncation_reasons.add("search_time_budget")
            break
        if visited_nodes >= max_visited_nodes:
            truncation_reasons.add("max_visited_nodes")
            break

        item, parent_prefix, depth = stack.pop()
        visited_nodes += 1
        item_path = (parent_prefix + "/" + item.name).replace("//", "/")
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
            if len(items) >= max_items:
                truncation_reasons.add("max_items")
                break
            entry = {
                "path": item_path,
                "type": "folder" if is_folder else "file",
                "source": item_source,
            }
            if external_library is not None:
                entry["external_library"] = external_library
            items.append(entry)

        if is_folder:
            children = item.list()
            if children and depth >= max_depth:
                truncation_reasons.add("max_depth")
            elif children:
                stack.extend(
                    (child, item_path, depth + 1)
                    for child in reversed(children)
                )

    return {
        "items": items,
        "visited_nodes": visited_nodes,
        "truncated": bool(truncation_reasons),
        "truncation_reasons": sorted(truncation_reasons),
    }


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
    max_items: int = _DEFAULT_LIST_ITEMS,
    max_visited_nodes: int = _DEFAULT_VISITED_NODES,
    max_depth: int = _DEFAULT_LIBRARY_DEPTH,
) -> str:
    """List a bounded project-library tree.

    ``max_items`` bounds returned rows. ``max_visited_nodes`` independently
    bounds all inspected nodes, including rows excluded by ``source``.
    ``max_depth`` bounds traversal below ``path``. The result states whether it
    was truncated and why, so a partial inventory cannot look complete.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    path = _normalize_library_path(path or "/")
    source = source.strip().lower() or "all"
    if source not in {"all", "internal", "external"}:
        raise ValueError("source must be one of: all, internal, external")
    max_items = _bounded_positive_int(max_items, "max_items", _MAX_LIST_ITEMS)
    max_visited_nodes = _bounded_positive_int(
        max_visited_nodes, "max_visited_nodes", _MAX_VISITED_NODES
    )
    max_depth = _bounded_positive_int(max_depth, "max_depth", _MAX_LIBRARY_DEPTH)
    client = get_dss_client()
    await ctx.info(f"Listing project library {project_key} from {path} (source={source})...")

    def _run():
        project = client.get_project(project_key)
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
        walk = _walk_library_tree(
            folder,
            prefix,
            external_libraries,
            source,
            external_config_available,
            max_items,
            max_visited_nodes,
            max_depth,
        )
        payload = {
            "path": path,
            "source": source,
            "items": columnar(
                walk["items"],
                ["path", "type", "source", "external_library"],
            ),
            "returned_items": len(walk["items"]),
            "visited_nodes": walk["visited_nodes"],
            "truncated": walk["truncated"],
            "truncation_reasons": walk["truncation_reasons"],
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

    return _tool_json(await run_blocking(_run))


@mcp.tool()
async def read_project_library_file(
    project_key: str,
    path: str,
    ctx: Context,
    max_bytes: int = _DEFAULT_READ_BYTES,
) -> str:
    """Read bounded UTF-8 text from a project-library file.

    The payload reports the full byte size, returned byte count, and whether the
    content was clipped. ``max_bytes`` has a hard 1 MB ceiling.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    path = _normalize_library_path(path)
    max_bytes = _bounded_positive_int(max_bytes, "max_bytes", _MAX_FILE_BYTES)
    client = get_dss_client()
    await ctx.info(f"Reading project library file {path} in {project_key}...")

    def _run():
        library = client.get_project(project_key).get_library()
        if _safe_get_folder(library, path) is not None:
            raise ValueError(f"Path is a folder: {path}")
        file = _safe_get_file(library, path)
        if file is None:
            raise ValueError(f"File not found: {path}")
        raw = _read_library_bytes(file)
        content, returned_bytes, truncated = _decode_utf8_prefix(raw, max_bytes)
        return {
            "path": path,
            "content": content,
            "size_bytes": len(raw),
            "returned_bytes": returned_bytes,
            "truncated": truncated,
        }

    return _tool_json(await run_blocking(_run))


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
    max_files: int = _DEFAULT_SEARCH_FILES,
    max_visited_nodes: int = _DEFAULT_VISITED_NODES,
    max_depth: int = _DEFAULT_LIBRARY_DEPTH,
    max_file_bytes: int = _DEFAULT_READ_BYTES,
) -> str:
    """Search bounded project-library text using substring or timed regex matching.

    Traversal, attempted reads, bytes accepted per file, matches returned, tree
    depth, per-regex execution, and cooperative processing time all have
    independent limits. Partial searches report explicit truncation reasons.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    query = _require_non_empty_string(query, "query")
    path = _normalize_library_path(path or "/")
    max_matches = _bounded_positive_int(max_matches, "max_matches", 1_000)
    max_files = _bounded_positive_int(max_files, "max_files", _MAX_SEARCH_FILES)
    max_visited_nodes = _bounded_positive_int(
        max_visited_nodes, "max_visited_nodes", _MAX_VISITED_NODES
    )
    max_depth = _bounded_positive_int(max_depth, "max_depth", _MAX_LIBRARY_DEPTH)
    max_file_bytes = _bounded_positive_int(
        max_file_bytes, "max_file_bytes", _MAX_FILE_BYTES
    )
    if len(query) > _MAX_QUERY_CHARACTERS:
        raise ValueError(f"'query' must be <= {_MAX_QUERY_CHARACTERS} characters")
    if len(file_glob) > _MAX_GLOB_CHARACTERS:
        raise ValueError(
            f"'file_glob' must be <= {_MAX_GLOB_CHARACTERS} characters"
        )
    client = get_dss_client()
    await ctx.info(
        f"Searching project library {project_key} under {path} for "
        f"a {'regex' if is_regex else 'substring'} match..."
    )

    flags = regex.IGNORECASE if case_insensitive else 0
    if is_regex:
        try:
            pattern = regex.compile(query, flags)
        except regex.error as exc:
            raise ValueError(f"Invalid regex: {exc}") from exc
    else:
        pattern = regex.compile(regex.escape(query), flags)

    glob_pattern = regex.compile(fnmatch.translate(file_glob)) if file_glob else None

    def _run():
        started = time.monotonic()
        deadline = started + _SEARCH_TIME_BUDGET_SECONDS
        project = client.get_project(project_key)
        library = project.get_library()
        folder = library.root if path == "/" else _safe_get_folder(library, path)
        if folder is None:
            raise ValueError(f"Folder not found: {path}")
        external_libraries, external_error = _load_external_libraries(project)
        external_config_available = external_error is None
        prefix = "" if path == "/" else path.rstrip("/")
        walk = _walk_library_tree(
            folder,
            prefix,
            external_libraries,
            "all",
            external_config_available,
            max_visited_nodes,
            max_visited_nodes,
            max_depth,
            deadline,
        )

        matches = []
        files_attempted = 0
        files_read = 0
        files_searched = 0
        skipped_files = {
            "oversized": 0,
            "non_utf8": 0,
            "unreadable": 0,
        }
        truncation_reasons = set(walk["truncation_reasons"])
        stop = False
        for entry in walk["items"]:
            if entry["type"] != "file":
                continue
            if glob_pattern is not None and not glob_pattern.match(entry["path"]):
                continue
            if files_attempted >= max_files:
                truncation_reasons.add("max_files")
                break
            if time.monotonic() - started >= _SEARCH_TIME_BUDGET_SECONDS:
                truncation_reasons.add("search_time_budget")
                break
            files_attempted += 1
            try:
                file = library.get_file(entry["path"])
                if file is None:
                    skipped_files["unreadable"] += 1
                    continue
                raw = _read_library_bytes(file)
            except Exception:
                skipped_files["unreadable"] += 1
                continue
            files_read += 1
            if len(raw) > max_file_bytes:
                skipped_files["oversized"] += 1
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                skipped_files["non_utf8"] += 1
                continue
            files_searched += 1
            for lineno, line in enumerate(text.splitlines(), start=1):
                remaining = _SEARCH_TIME_BUDGET_SECONDS - (time.monotonic() - started)
                if remaining <= 0:
                    truncation_reasons.add("search_time_budget")
                    stop = True
                    break
                try:
                    matched = pattern.search(
                        line,
                        timeout=min(_REGEX_MATCH_TIMEOUT_SECONDS, remaining),
                    )
                except TimeoutError:
                    truncation_reasons.add("regex_timeout")
                    stop = True
                    break
                if matched:
                    matches.append(
                        {
                            "path": entry["path"],
                            "line": lineno,
                            "text": line[:500],
                        }
                    )
                    if len(matches) >= max_matches:
                        truncation_reasons.add("max_matches")
                        stop = True
                        break
            if stop:
                break

        for reason, count in skipped_files.items():
            if count:
                truncation_reasons.add(f"{reason}_files")

        payload = {
            "path": path,
            "matches": columnar(matches, ["path", "line", "text"]),
            "visited_nodes": walk["visited_nodes"],
            "files_attempted": files_attempted,
            "files_read": files_read,
            "files_searched": files_searched,
            "skipped_files": skipped_files,
            "truncated": bool(truncation_reasons),
            "truncation_reasons": sorted(truncation_reasons),
        }
        if not external_config_available:
            payload["external_libraries_available"] = False
            payload["warning"] = (
                "External library configuration is unavailable; search results "
                "may include both internal and external-backed files without "
                "distinction."
            )
        return payload

    return _tool_json(await run_blocking(_run))


@mcp.tool()
async def validate_project_library_file(
    project_key: str,
    path: str,
    ctx: Context,
    content: str | None = None,
    max_bytes: int = _MAX_FILE_BYTES,
) -> str:
    """Validate a bounded project-library file, parsing Python with ``ast``."""
    project_key = _require_non_empty_string(project_key, "project_key")
    path = _normalize_library_path(path)
    max_bytes = _bounded_positive_int(max_bytes, "max_bytes", _MAX_FILE_BYTES)
    client = get_dss_client()
    await ctx.info(f"Validating project library file {path} in {project_key}...")

    is_python = path.lower().endswith(".py")

    if content is None:

        def _read():
            library = client.get_project(project_key).get_library()
            if _safe_get_folder(library, path) is not None:
                raise ValueError(f"Path is a folder: {path}")
            file = _safe_get_file(library, path)
            if file is None:
                raise ValueError(f"File not found: {path}")
            raw = _read_library_bytes(file)
            if len(raw) > max_bytes:
                raise ValueError(
                    f"Project library file exceeds the {max_bytes}-byte validation limit"
                )
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    "Project library file is not valid UTF-8 text"
                ) from exc

        content = await run_blocking(_read)
    else:
        try:
            content_bytes = content.encode("utf-8")
        except AttributeError as exc:
            raise ValueError("'content' must be a string or null") from exc
        if len(content_bytes) > max_bytes:
            raise ValueError(
                f"Provided content exceeds the {max_bytes}-byte validation limit"
            )

    base = {
        "path": path,
        "language": "python"
        if is_python
        else (path.rsplit(".", 1)[-1].lower() if "." in path else "unknown"),
    }
    if not is_python:
        return _tool_json(
            {**base, "is_valid": True, "checks_skipped": "non-python file"}
        )

    validation = await run_blocking(_ast_validate_python, content)
    return _tool_json(
        {**base, "is_valid": "syntax_error" not in validation, **validation}
    )


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
    client = get_dss_client()
    await ctx.info(f"Uploading local file {filepath} to project library {path} in {project_key}...")

    def _run():
        local_bytes = _read_local_file_bytes(filepath)
        library = client.get_project(project_key).get_library()
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

    return _tool_json(await run_blocking(_run))

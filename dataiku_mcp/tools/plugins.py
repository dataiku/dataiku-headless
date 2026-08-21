"""Dataiku plugin discovery, lifecycle, deployment, and code environment tools."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)

_MAX_LIST_LIMIT = 100
_FUTURE_POLL_INTERVAL_SECONDS = 2
# Dataiku embeds a Java stack trace and pre-rendered HTML in operation results.
_NOISY_RESULT_KEYS = {
    "detailedMessageHTML",
    "installationError",
    "messages",
    "stackTrace",
    "stackTraceStr",
}


def _plugin_id(metadata: dict) -> str:
    return str(metadata.get("id", ""))


def _plugin_version(metadata: dict) -> str:
    return str(metadata.get("version", ""))


def _plugin_is_dev(metadata: dict) -> bool:
    # DSS 15 sends ``isDev``; ``dev`` is read first for older instances.
    value = metadata.get("dev")
    if value is None:
        value = metadata.get("isDev", False)
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _list_plugin_metadata(client) -> list[Any]:
    return list(client.list_plugins())


def _find_plugin_metadata(client, plugin_id: str) -> Any:
    for metadata in _list_plugin_metadata(client):
        if _plugin_id(metadata) == plugin_id:
            return metadata
    raise ValueError(f"Plugin '{plugin_id}' is not installed")


def _ensure_plugin_absent(client, plugin_id: str) -> None:
    if any(
        _plugin_id(metadata) == plugin_id for metadata in _list_plugin_metadata(client)
    ):
        raise ValueError(
            f"Plugin '{plugin_id}' is already installed. Use an update tool instead."
        )


def _get_installed_plugin(client, plugin_id: str):
    _find_plugin_metadata(client, plugin_id)
    return client.get_plugin(plugin_id)


def _plugin_config(raw_settings: Any) -> dict:
    """Return a plugin's config section; DSS omits it when nothing is configured."""
    config = raw_settings.get("config")
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ValueError("Dataiku returned plugin config in an unexpected format")
    return config


def _configured_keys(config: dict) -> list[str]:
    return sorted(str(key) for key in config)


def _plugin_details(client, plugin_id: str) -> dict[str, Any]:
    metadata = _find_plugin_metadata(client, plugin_id)
    raw_settings = client.get_plugin(plugin_id).get_settings().get_raw()
    return {
        "id": plugin_id,
        "version": _plugin_version(metadata),
        "dev": _plugin_is_dev(metadata),
        "code_env_name": raw_settings.get("codeEnvName") or None,
        "configured_keys": _configured_keys(_plugin_config(raw_settings)),
    }


def _instance_missing_types(raw: dict) -> dict[str, Any]:
    """Summarize DSS's unresolvable component types.

    ``listUsages`` returns these for the whole instance, identically for every
    plugin, so they signal that usage analysis may be incomplete rather than naming
    usages of the plugin that was asked about.
    """
    missing = raw.get("missingTypes") or []
    return {
        "count": len(missing),
        "types": sorted({str(item.get("missingType", "")) for item in missing}),
    }


def _plugin_operation_result(operation: str, result: Any) -> Any:
    """Raise on a failed operation and strip stack traces from what is returned.

    Dataiku answers some plugin operations with ``hasResult`` and ``success: false``
    instead of an HTTP error, so a completed future is not a successful one. The
    failure payload embeds a Java stack trace, which never belongs in a response.
    """
    if not isinstance(result, dict):
        return result
    # Only the top-level flag. A nested ``messages.success`` means "a success-level
    # message was emitted" and is false on operations that plainly succeeded.
    if result.get("success") is False:
        error = result.get("installationError") or {}
        detail = (
            error.get("message") or result.get("errorMessage") or "no reason reported"
        )
        code = error.get("code")
        raise RuntimeError(
            f"Dataiku reported {operation} as failed: {detail}"
            + (f" ({code})" if code else "")
        )
    return omit_empty(
        {key: value for key, value in result.items() if key not in _NOISY_RESULT_KEYS}
    )


def _delete_refusal(plugin_id: str, usage_raw: dict, force: bool, err) -> ValueError:
    """Explain a refused deletion using the analysis already in hand.

    Dataiku also refuses ``force=False`` when any component type is unresolvable
    anywhere on the instance, which has nothing to do with the plugin being deleted.
    Saying so keeps the caller from reading every refusal as "this plugin is in use".
    """
    if force:
        return ValueError(
            f"Dataiku refused to delete plugin '{plugin_id}' even with force=true: {err}"
        )
    usage_count = len(usage_raw.get("usages", []))
    if usage_count:
        reason = f"it reports {usage_count} usage(s) of this plugin"
    else:
        missing = _instance_missing_types(usage_raw)
        reason = (
            f"it reports no usage of this plugin, but {missing['count']} component "
            "type(s) are unresolvable elsewhere on the instance, so it cannot confirm "
            "the analysis is complete"
        )
    return ValueError(
        f"Dataiku refused to delete plugin '{plugin_id}': {reason} ({err}). Re-run "
        "with force=true only when deleting it regardless is intended."
    )


def _future_id(future) -> str | None:
    """Return the future's DSS job ID, or None when DSS already has the result.

    DSS omits ``jobId`` when it finished the operation before answering; the result
    then travels in the future's state and ``wait_for_result`` returns it without
    polling. Such a response reports success, so callers complete instead of
    handing back an identity that does not exist.
    """
    return getattr(future, "job_id", None) or None


async def _future_result(operation: str, future) -> Any:
    """Wait for a DSS future, releasing the executor worker between polls.

    ``DSSFuture.wait_for_result`` blocks its thread in a backoff loop, which would
    hold one of the few general workers for a whole plugin install or code-env
    build. Polling matches ``jobs.py`` and ``scenarios.py``.
    """
    if _future_id(future) is None:
        # DSS already answered with the result; there is nothing to poll.
        return _plugin_operation_result(
            operation, await run_blocking(future.wait_for_result)
        )
    while not (await run_blocking(future.get_state)).get("hasResult"):
        await asyncio.sleep(_FUTURE_POLL_INTERVAL_SECONDS)
    return _plugin_operation_result(operation, await run_blocking(future.get_result))


def _future_started(operation: str, future_id: str, plugin_id: str) -> dict[str, Any]:
    return {
        "status": f"{operation}_started",
        "plugin_id": plugin_id,
        "future_id": future_id,
        "hint": (
            "Use get_future_status(future_id, fetch_result=true) to follow this "
            "operation. Do not start a duplicate operation while it is running."
        ),
    }


async def _finish_or_return_future(
    client,
    plugin_id: str,
    operation: str,
    future,
    wait_for_completion: bool,
) -> dict[str, Any]:
    future_id = _future_id(future)
    if not wait_for_completion and future_id is not None:
        return _future_started(operation, future_id, plugin_id)
    result = await _future_result(operation, future)
    return {
        "status": f"{operation}_completed",
        "plugin": await run_blocking(_plugin_details, client, plugin_id),
        "result": result,
    }


def _find_plugin_json_member(archive: ZipFile) -> str | None:
    files = [name for name in archive.namelist() if not name.endswith("/")]
    if "plugin.json" in files:
        return "plugin.json"
    nested = [
        name for name in files if name.count("/") == 1 and name.endswith("/plugin.json")
    ]
    top_level_dirs = {name.split("/", 1)[0] for name in files if "/" in name}
    loose_files = [name for name in files if "/" not in name]
    if len(nested) == 1 and len(top_level_dirs) == 1 and not loose_files:
        return nested[0]
    return None


def _validate_archive_members(archive: ZipFile) -> None:
    seen_paths = set()
    for member in archive.infolist():
        normalized_name = member.filename.replace("\\", "/")
        path = PurePosixPath(normalized_name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or (path.parts and path.parts[0].endswith(":"))
        ):
            raise ValueError(
                f"Plugin archive contains an unsafe path: '{member.filename}'"
            )
        if normalized_name in seen_paths:
            raise ValueError(
                f"Plugin archive contains a duplicate path: '{member.filename}'"
            )
        seen_paths.add(normalized_name)
        if any(part.startswith(".") for part in path.parts):
            raise ValueError(
                f"Plugin archive contains a hidden path component: '{member.filename}'"
            )
        if stat.S_ISLNK(member.external_attr >> 16):
            raise ValueError(
                f"Plugin archive contains a symbolic link: '{member.filename}'"
            )


def _read_archive_plugin_id(archive_path: Path) -> tuple[str, str | None]:
    try:
        with ZipFile(archive_path) as archive:
            _validate_archive_members(archive)
            member = _find_plugin_json_member(archive)
            if member is None:
                raise ValueError(
                    "Plugin archive must contain plugin.json at its root or under "
                    "one unambiguous top-level directory"
                )
            with archive.open(member) as plugin_file:
                metadata = json.load(plugin_file)
    except json.JSONDecodeError as exc:
        raise ValueError("plugin.json is not valid JSON") from exc
    except OSError as exc:
        raise ValueError(f"Could not read plugin archive '{archive_path}'") from exc
    plugin_id = str(metadata.get("id", "")).strip()
    if not plugin_id:
        raise ValueError(f"'{member}' does not declare a plugin 'id'")
    wrapper = member.rsplit("/", 1)[0] if "/" in member else None
    return plugin_id, wrapper


@contextmanager
def _temp_zip_path() -> Iterator[Path]:
    """Yield a fresh temp .zip path, unlinking it if the caller raises."""
    file_descriptor, temp_name = tempfile.mkstemp(suffix=".zip")
    os.close(file_descriptor)
    path = Path(temp_name)
    try:
        yield path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _zip_plugin_directory(directory: Path) -> Path:
    if not (directory / "plugin.json").is_file():
        raise ValueError(f"Plugin directory '{directory}' does not contain plugin.json")
    with _temp_zip_path() as archive_path:
        with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
            for root, directory_names, file_names in os.walk(directory):
                root_path = Path(root)
                for directory_name in sorted(directory_names):
                    child = root_path / directory_name
                    if directory_name.startswith("."):
                        raise ValueError(
                            f"Plugin directory contains a hidden path component: '{child}'"
                        )
                    if child.is_symlink():
                        raise ValueError(
                            f"Plugin directory contains a symbolic link: '{child}'"
                        )
                for file_name in sorted(file_names):
                    file = root_path / file_name
                    if file_name.startswith("."):
                        raise ValueError(
                            f"Plugin directory contains a hidden path component: '{file}'"
                        )
                    if file.is_symlink():
                        raise ValueError(
                            f"Plugin directory contains a symbolic link: '{file}'"
                        )
                    archive.write(file, file.relative_to(directory))
        return archive_path


def _flatten_archive(archive_path: Path, wrapper: str) -> Path:
    prefix = f"{wrapper}/"
    with _temp_zip_path() as flattened_path:
        with ZipFile(archive_path) as source, ZipFile(flattened_path, "w") as target:
            for info in source.infolist():
                if info.is_dir() or not info.filename.startswith(prefix):
                    continue
                stripped = ZipInfo(
                    info.filename[len(prefix) :], date_time=info.date_time
                )
                stripped.external_attr = info.external_attr
                stripped.compress_type = info.compress_type
                with source.open(info) as member:
                    target.writestr(stripped, member.read())
        return flattened_path


@contextmanager
def _prepared_plugin_archive(local_path: str) -> Iterator[tuple[Path, str]]:
    path = Path(_require_non_empty_string(local_path, "local_path"))
    if not path.exists():
        raise ValueError(f"Local plugin path does not exist: '{path}'")
    if path.is_symlink():
        raise ValueError(f"Local plugin path must not be a symbolic link: '{path}'")
    temporary_paths: list[Path] = []
    try:
        if path.is_dir():
            archive_path = _zip_plugin_directory(path)
            temporary_paths.append(archive_path)
        elif path.is_file() and path.suffix.casefold() == ".zip":
            archive_path = path
        else:
            raise ValueError("'local_path' must be a plugin directory or ZIP archive")

        plugin_id, wrapper = _read_archive_plugin_id(archive_path)
        if wrapper is not None:
            flattened_path = _flatten_archive(archive_path, wrapper)
            temporary_paths.append(flattened_path)
            archive_path = flattened_path
        yield archive_path, plugin_id
    finally:
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)


@mcp.tool()
async def list_plugins(
    ctx: Context,
    search: str = "",
    dev: bool | None = None,
    offset: int = 0,
    limit: int = 10,
) -> str:
    """List installed Dataiku plugins with optional ID and development-status filters.

    Args:
        search: Case-insensitive substring of the plugin ID. Defaults to every plugin.
        dev: Filter to development plugins (``true``) or store- and archive-installed
            plugins (``false``). Defaults to both.
        offset: Zero-based offset within the matching plugins.
        limit: Maximum plugins to return. Values above 100 are capped at 100.
    """
    search = search.strip()
    offset = _require_non_negative_int(offset, "offset")
    limit = min(_require_positive_int(limit, "limit"), _MAX_LIST_LIMIT)
    await ctx.info("Listing installed Dataiku plugins...")

    metadata = await run_blocking(lambda: _list_plugin_metadata(get_dss_client()))
    plugins = [
        {
            "id": _plugin_id(item),
            "version": _plugin_version(item),
            "dev": _plugin_is_dev(item),
        }
        for item in metadata
    ]
    if search:
        query = search.casefold()
        plugins = [item for item in plugins if query in item["id"].casefold()]
    if dev is not None:
        plugins = [item for item in plugins if item["dev"] is dev]
    plugins.sort(key=lambda item: (item["id"].casefold(), item["id"]))
    matched_plugins = len(plugins)
    page = plugins[offset : offset + limit]
    next_offset = offset + len(page)
    if next_offset >= matched_plugins:
        next_offset = None
    return compact_json(
        {
            "matched_plugins": matched_plugins,
            "returned_plugins": len(page),
            "next_offset": next_offset,
            "plugins": columnar(page, ["id", "version", "dev"]),
        }
    )


@mcp.tool()
async def get_plugin(plugin_id: str, ctx: Context) -> str:
    """Get one installed plugin's version, development status, code env, and configured keys."""
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    await ctx.info(f"Getting Dataiku plugin '{plugin_id}'...")
    return compact_json(
        {
            "plugin": await run_blocking(
                lambda: _plugin_details(get_dss_client(), plugin_id)
            )
        }
    )


@mcp.tool()
async def list_plugin_usages(
    plugin_id: str,
    ctx: Context,
    project_key: str | None = None,
) -> str:
    """List projects and objects that use components from an installed plugin.

    Args:
        project_key: Restrict the analysis to one project. Defaults to every project.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    if project_key is not None:
        project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing usages of Dataiku plugin '{plugin_id}'...")

    def _run():
        client = get_dss_client()
        return (
            _get_installed_plugin(client, plugin_id)
            .list_usages(project_key=project_key)
            .get_raw()
        )

    raw = await run_blocking(_run)
    usages = [
        {
            "project_key": usage.get("projectKey"),
            "object_type": usage.get("objectType"),
            "object_id": usage.get("objectId"),
            "element_kind": usage.get("elementKind"),
            "element_type": usage.get("elementType"),
        }
        for usage in raw.get("usages", [])
    ]
    return compact_json(
        {
            "plugin_id": plugin_id,
            "usage_count": len(usages),
            "usages": columnar(
                usages,
                [
                    "project_key",
                    "object_type",
                    "object_id",
                    "element_kind",
                    "element_type",
                ],
            ),
            "instance_missing_types": _instance_missing_types(raw),
        }
    )


@mcp.tool()
async def update_plugin_settings(
    plugin_id: str,
    config: dict[str, Any],
    ctx: Context,
) -> str:
    """Merge structured config values into an installed plugin's settings and verify the saved values.

    Args:
        config: Settings to merge by key. Unlisted keys keep their current values.
            Saved values are verified by a fresh read but never echoed back, because
            plugin configuration commonly holds credentials.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    if not config:
        raise ValueError("'config' must contain at least one setting")
    await ctx.info(f"Updating settings for Dataiku plugin '{plugin_id}'...")

    def _run():
        client = get_dss_client()
        settings = _get_installed_plugin(client, plugin_id).get_settings()
        settings.get_raw().setdefault("config", {}).update(config)
        settings.save()
        saved_config = _plugin_config(
            client.get_plugin(plugin_id).get_settings().get_raw()
        )
        mismatches = sorted(
            key for key, value in config.items() if saved_config.get(key) != value
        )
        if mismatches:
            raise RuntimeError(
                f"Dataiku did not persist plugin settings for keys: {mismatches}"
            )
        return {
            "plugin_id": plugin_id,
            "updated_keys": sorted(config),
            "configured_keys": _configured_keys(saved_config),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def install_plugin_from_store(
    plugin_id: str,
    ctx: Context,
    wait_for_completion: bool = False,
) -> str:
    """Install a plugin from the Dataiku plugin store.

    Args:
        wait_for_completion: Wait for Dataiku to finish and return the resulting
            plugin state. Defaults to returning a future ID to follow with
            ``get_future_status``.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    await ctx.info(f"Installing Dataiku plugin '{plugin_id}' from the store...")

    def _inspect_and_start():
        client = get_dss_client()
        _ensure_plugin_absent(client, plugin_id)
        return client, client.install_plugin_from_store(plugin_id)

    client, future = await run_blocking(_inspect_and_start)
    return compact_json(
        await _finish_or_return_future(
            client, plugin_id, "plugin_install", future, wait_for_completion
        )
    )


@mcp.tool()
async def update_plugin_from_store(
    plugin_id: str,
    ctx: Context,
    wait_for_completion: bool = False,
) -> str:
    """Update an installed plugin from the Dataiku plugin store.

    Args:
        wait_for_completion: Wait for Dataiku to finish and return the resulting
            plugin state. Defaults to returning a future ID to follow with
            ``get_future_status``.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    await ctx.info(f"Updating Dataiku plugin '{plugin_id}' from the store...")

    def _inspect_and_start():
        client = get_dss_client()
        return client, _get_installed_plugin(client, plugin_id).update_from_store()

    client, future = await run_blocking(_inspect_and_start)
    return compact_json(
        await _finish_or_return_future(
            client, plugin_id, "plugin_update", future, wait_for_completion
        )
    )


@mcp.tool()
async def delete_plugin(
    plugin_id: str,
    ctx: Context,
    force: bool = False,
) -> str:
    """Delete an installed plugin after inspecting its usages.

    Args:
        force: Delete even though the plugin is in use or its usage analysis failed.
            Defaults to letting Dataiku refuse an in-use plugin.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    await ctx.info(f"Deleting Dataiku plugin '{plugin_id}' (force={force})...")

    def _inspect_and_start():
        client = get_dss_client()
        metadata = _find_plugin_metadata(client, plugin_id)
        plugin = client.get_plugin(plugin_id)  # metadata above already proved it exists
        usage_raw = plugin.list_usages().get_raw()
        try:
            future = plugin.delete(force=force)
        except DataikuException as err:
            raise _delete_refusal(plugin_id, usage_raw, force, err) from None
        return client, metadata, usage_raw, future

    client, metadata, usage_raw, future = await run_blocking(_inspect_and_start)
    await _future_result("plugin_deletion", future)
    remaining = await run_blocking(lambda: _list_plugin_metadata(client))
    if any(_plugin_id(item) == plugin_id for item in remaining):
        raise RuntimeError(f"Dataiku still reports plugin '{plugin_id}' after deletion")
    return compact_json(
        {
            "plugin_id": plugin_id,
            "version": _plugin_version(metadata),
            "deleted": True,
            "force": force,
            "usage_count_before_delete": len(usage_raw.get("usages", [])),
            "instance_missing_types_before_delete": _instance_missing_types(usage_raw),
        }
    )


@mcp.tool()
async def install_plugin_from_local_path(local_path: str, ctx: Context) -> str:
    """Install a plugin from a user-supplied local directory or ZIP archive.

    Args:
        local_path: Directory containing ``plugin.json``, or a ZIP holding it at the
            root or inside one unambiguous top-level directory. Hidden paths and
            symbolic links are rejected.
    """
    await ctx.info(f"Installing a Dataiku plugin from local path '{local_path}'...")

    def _run():
        client = get_dss_client()
        with _prepared_plugin_archive(local_path) as (archive_path, plugin_id):
            _ensure_plugin_absent(client, plugin_id)
            with archive_path.open("rb") as archive:
                client.install_plugin_from_archive(archive)
        return _plugin_details(client, plugin_id)

    return compact_json(
        {"status": "plugin_install_completed", "plugin": await run_blocking(_run)}
    )


@mcp.tool()
async def update_plugin_from_local_path(
    plugin_id: str,
    local_path: str,
    ctx: Context,
) -> str:
    """Update an installed plugin from a matching user-supplied local directory or ZIP archive.

    Args:
        local_path: Directory containing ``plugin.json``, or a ZIP holding it at the
            root or inside one unambiguous top-level directory. Its declared plugin
            ID must match ``plugin_id``.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    await ctx.info(
        f"Updating Dataiku plugin '{plugin_id}' from local path '{local_path}'..."
    )

    def _run():
        client = get_dss_client()
        plugin = _get_installed_plugin(client, plugin_id)
        with _prepared_plugin_archive(local_path) as (archive_path, archive_plugin_id):
            if archive_plugin_id != plugin_id:
                raise ValueError(
                    f"Archive plugin ID '{archive_plugin_id}' does not match '{plugin_id}'"
                )
            with archive_path.open("rb") as archive:
                plugin.update_from_zip(archive)
        return _plugin_details(client, plugin_id)

    return compact_json(
        {"status": "plugin_update_completed", "plugin": await run_blocking(_run)}
    )


@mcp.tool()
async def create_plugin_code_env(
    plugin_id: str,
    ctx: Context,
    python_interpreter: str | None = None,
    conda: bool = False,
    force: bool = False,
    wait_for_completion: bool = False,
) -> str:
    """Create a managed code environment for an installed plugin.

    Dataiku creates the environment without binding it to the plugin, so bind it with
    ``set_plugin_code_env`` afterwards. Until it is bound, a further call here creates
    another environment rather than reporting the existing one.

    Args:
        python_interpreter: Dataiku interpreter constant such as ``PYTHON311``.
            Defaults to the interpreter the plugin declares.
        conda: Build with conda instead of virtualenv and pip.
        force: Create another managed environment even though one is already bound to
            the plugin. Defaults to reporting the existing binding and creating
            nothing.
        wait_for_completion: Wait for Dataiku to finish and return the resulting
            plugin state. Defaults to returning a future ID to follow with
            ``get_future_status``.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    if python_interpreter is not None:
        python_interpreter = _require_non_empty_string(
            python_interpreter, "python_interpreter"
        )
    await ctx.info(f"Creating a code environment for Dataiku plugin '{plugin_id}'...")
    client = await run_blocking(get_dss_client)

    def _inspect_and_start():
        plugin = _get_installed_plugin(client, plugin_id)
        bound_env = plugin.get_settings().get_raw().get("codeEnvName")
        if bound_env and not force:
            return plugin, bound_env, None
        return (
            plugin,
            bound_env,
            plugin.create_code_env(python_interpreter=python_interpreter, conda=conda),
        )

    plugin, bound_env, future = await run_blocking(_inspect_and_start)
    if future is None:
        return compact_json(
            {
                "status": "plugin_code_env_already_bound",
                "plugin_id": plugin_id,
                "bound_code_env_name": bound_env,
                "created": False,
                "hint": (
                    "Use update_plugin_code_env to rebuild this environment, or set "
                    "force=true only when a separate managed environment is intended."
                ),
            }
        )
    future_id = _future_id(future)
    if not wait_for_completion and future_id is not None:
        return compact_json(
            _future_started("plugin_code_env_creation", future_id, plugin_id)
        )
    result = await _future_result("plugin_code_env_creation", future)
    saved = await run_blocking(lambda: plugin.get_settings().get_raw())
    created_name = result.get("envName") if isinstance(result, dict) else None
    bound_name = saved.get("codeEnvName")
    payload = {
        "status": "plugin_code_env_creation_completed",
        "plugin_id": plugin_id,
        "created_code_env_name": created_name,
        "bound_code_env_name": bound_name,
    }
    if created_name and not bound_name:
        payload["hint"] = (
            f"Dataiku created '{created_name}' without binding it. Call "
            "set_plugin_code_env to bind it; until then another "
            "create_plugin_code_env call creates a second environment."
        )
    return compact_json(payload)


@mcp.tool()
async def set_plugin_code_env(
    plugin_id: str,
    code_env_name: str,
    ctx: Context,
) -> str:
    """Assign an existing code environment to an installed plugin and verify the binding.

    Args:
        code_env_name: Name of an existing code environment, from ``list_code_envs``.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    code_env_name = _require_non_empty_string(code_env_name, "code_env_name")
    await ctx.info(
        f"Assigning code environment '{code_env_name}' to Dataiku plugin '{plugin_id}'..."
    )

    def _run():
        client = get_dss_client()
        settings = _get_installed_plugin(client, plugin_id).get_settings()
        settings.set_code_env(code_env_name)
        settings.save()
        saved_name = (
            client.get_plugin(plugin_id).get_settings().get_raw().get("codeEnvName")
        )
        if saved_name != code_env_name:
            raise RuntimeError(
                f"Dataiku did not persist code environment '{code_env_name}' "
                f"for plugin '{plugin_id}'"
            )
        return {"plugin_id": plugin_id, "code_env_name": saved_name}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def update_plugin_code_env(
    plugin_id: str,
    ctx: Context,
    wait_for_completion: bool = False,
) -> str:
    """Rebuild the managed code environment currently bound to an installed plugin.

    Args:
        wait_for_completion: Wait for Dataiku to finish and return the resulting
            plugin state. Defaults to returning a future ID to follow with
            ``get_future_status``.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    await ctx.info(f"Updating the code environment for Dataiku plugin '{plugin_id}'...")
    client = await run_blocking(get_dss_client)

    def _inspect_and_start():
        plugin = _get_installed_plugin(client, plugin_id)
        code_env_name = plugin.get_settings().get_raw().get("codeEnvName")
        if not code_env_name:
            raise ValueError(
                f"Plugin '{plugin_id}' has no bound code environment to update"
            )
        return plugin, code_env_name, plugin.update_code_env()

    plugin, code_env_name, future = await run_blocking(_inspect_and_start)
    future_id = _future_id(future)
    if not wait_for_completion and future_id is not None:
        result = _future_started("plugin_code_env_update", future_id, plugin_id)
        result["code_env_name"] = code_env_name
        return compact_json(result)
    await _future_result("plugin_code_env_update", future)
    saved_name = await run_blocking(
        lambda: plugin.get_settings().get_raw().get("codeEnvName")
    )
    if saved_name != code_env_name:
        raise RuntimeError(
            f"Plugin '{plugin_id}' code environment binding changed during its update"
        )
    return compact_json(
        {
            "status": "plugin_code_env_update_completed",
            "plugin_id": plugin_id,
            "code_env_name": saved_name,
        }
    )

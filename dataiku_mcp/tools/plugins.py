"""Dataiku plugin discovery and Store lifecycle tools."""

from __future__ import annotations

import asyncio
from typing import Any

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


def _plugin_details(client, plugin_id: str) -> dict[str, Any]:
    metadata = _find_plugin_metadata(client, plugin_id)
    return {
        "id": plugin_id,
        "version": _plugin_version(metadata),
        "dev": _plugin_is_dev(metadata),
    }


def _ensure_plugin_absent(client, plugin_id: str) -> None:
    if any(
        _plugin_id(metadata) == plugin_id for metadata in _list_plugin_metadata(client)
    ):
        raise ValueError(
            f"Plugin '{plugin_id}' is already installed. Use update_plugin_from_store."
        )


def _plugin_operation_result(operation: str, result: Any) -> Any:
    if not isinstance(result, dict):
        return result
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


def _future_id(future) -> str | None:
    return getattr(future, "job_id", None) or None


async def _future_result(operation: str, future) -> Any:
    if _future_id(future) is None:
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


@mcp.tool()
async def list_plugins(
    ctx: Context,
    search: str = "",
    dev: bool | None = None,
    offset: int = 0,
    limit: int = 10,
) -> str:
    """List installed Dataiku plugins with optional ID and development-status filters."""
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
async def install_plugin_from_store(
    plugin_id: str,
    ctx: Context,
    wait_for_completion: bool = False,
) -> str:
    """Install a plugin from the Dataiku Plugin Store."""
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    await ctx.info(f"Installing Dataiku plugin '{plugin_id}' from the Store...")

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
    """Update an installed plugin from the Dataiku Plugin Store."""
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    await ctx.info(f"Updating Dataiku plugin '{plugin_id}' from the Store...")

    def _inspect_and_start():
        client = get_dss_client()
        _find_plugin_metadata(client, plugin_id)
        return client, client.get_plugin(plugin_id).update_from_store()

    client, future = await run_blocking(_inspect_and_start)
    return compact_json(
        await _finish_or_return_future(
            client, plugin_id, "plugin_update", future, wait_for_completion
        )
    )

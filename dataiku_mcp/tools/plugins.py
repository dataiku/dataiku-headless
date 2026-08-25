"""Dataiku plugin discovery and Store lifecycle tools."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.errors import safe_error_text as _safe_error_text
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)

_MAX_LIST_LIMIT = 100
_PLUGIN_COLUMNS = ["id", "version", "dev"]
_FUTURE_POLL_INTERVAL_SECONDS = 2
DEFAULT_WAIT_TIMEOUT_SECONDS = 50
MAX_INLINE_WAIT_SECONDS = 3600
_NOISY_RESULT_KEYS = {
    "detailedMessageHTML",
    "installationError",
    "messages",
    "stackTrace",
    "stackTraceStr",
}
_FOLLOW_HINT = (
    "Use get_future_status(future_id, fetch_result=true) to follow this operation. "
    "Do not start a duplicate operation while it is running."
)


def _plugin_row(metadata: dict) -> dict[str, Any]:
    return {
        "id": str(metadata.get("id", "")),
        "version": str(metadata.get("version", "")),
        # GET /plugins/ is untyped in dataikuapi and DSS has used both spellings for
        # this flag; read either rather than guessing which one this instance sends.
        "dev": bool(metadata.get("isDev", metadata.get("dev", False))),
    }


def _installed_plugin(client, plugin_id: str) -> dict[str, Any] | None:
    """Return the installed plugin's row, or None when it is not installed."""
    for metadata in client.list_plugins():
        if str(metadata.get("id", "")) == plugin_id:
            return _plugin_row(metadata)
    return None


def _validate_wait_timeout(timeout_seconds: int) -> int:
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")
    if timeout_seconds > MAX_INLINE_WAIT_SECONDS:
        raise ValueError(f"'timeout_seconds' must be <= {MAX_INLINE_WAIT_SECONDS}")
    return timeout_seconds


def _plugin_operation_result(operation: str, result: dict) -> dict:
    """Shape a completed operation result, raising when Dataiku reports a failure."""
    error = result.get("installationError") or {}
    if result.get("success") is False or error:
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


async def _future_result(
    operation: str, future, timeout_seconds: int
) -> tuple[bool, dict | None]:
    """Poll ``future`` to a result within ``timeout_seconds``. Returns (timed_out, result)."""
    if future.job_id is None:
        # Dataiku answered inline; the result already sits in the future's state.
        return False, _plugin_operation_result(
            operation, await run_blocking(future.wait_for_result)
        )
    deadline = time.monotonic() + timeout_seconds
    while True:
        if (await run_blocking(future.peek_state)).get("hasResult"):
            return False, _plugin_operation_result(
                operation, await run_blocking(future.get_result)
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True, None
        await asyncio.sleep(min(_FUTURE_POLL_INTERVAL_SECONDS, remaining))


async def _run_store_operation(
    plugin_id: str,
    operation: str,
    wait_for_completion: bool,
    timeout_seconds: int,
    start,
) -> str:
    """Start a Store operation via ``start(client)`` and either hand back its future or follow it."""

    def _inspect_and_start():
        client = get_dss_client()
        return client, start(client)

    try:
        client, future = await run_blocking(_inspect_and_start)
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Dataiku did not return a handle for {operation} of '{plugin_id}'. Inspect "
            "list_plugins before retrying because the request may have reached Dataiku."
        ) from exc

    future_id = future.job_id
    if not wait_for_completion and future_id is not None:
        return compact_json(
            {
                "status": f"{operation}_started",
                "plugin_id": plugin_id,
                "future_id": future_id,
                "hint": _FOLLOW_HINT,
            }
        )

    try:
        timed_out, result = await _future_result(operation, future, timeout_seconds)
    except RuntimeError:
        raise
    except Exception as exc:
        return compact_json(
            {
                "status": f"{operation}_poll_failed",
                "plugin_id": plugin_id,
                **({"future_id": future_id} if future_id is not None else {}),
                "error_type": type(exc).__name__,
                "error": _safe_error_text(exc),
                "hint": (
                    f"The {operation} started but polling it failed. Keep this "
                    "future_id and inspect it with get_future_status, then confirm "
                    "with list_plugins; do not start a replacement operation."
                ),
            }
        )

    if timed_out:
        return compact_json(
            {
                "status": f"{operation}_still_running",
                "plugin_id": plugin_id,
                "future_id": future_id,
                "hint": (
                    f"Still running after {timeout_seconds}s. This is not a failure. "
                    + _FOLLOW_HINT
                ),
            }
        )

    payload: dict[str, Any] = {
        "status": f"{operation}_completed",
        "plugin_id": plugin_id,
        "result": result,
    }
    plugin = await run_blocking(_installed_plugin, client, plugin_id)
    if plugin is None:
        payload["hint"] = (
            "Dataiku reported success but the plugin is not listed yet; it may need an "
            "instance restart. Confirm the installed version with list_plugins."
        )
    else:
        payload["plugin"] = plugin
    return compact_json(payload)


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

    metadata = await run_blocking(lambda: get_dss_client().list_plugins())
    plugins = [_plugin_row(item) for item in metadata]
    total_plugins = len(plugins)
    if search:
        query = search.casefold()
        plugins = [item for item in plugins if query in item["id"].casefold()]
    if dev is not None:
        plugins = [item for item in plugins if item["dev"] is dev]
    plugins.sort(key=lambda item: (item["id"].casefold(), item["id"]))
    matched_plugins = len(plugins)
    page = plugins[offset : offset + limit]
    returned_plugins = len(page)
    return compact_json(
        {
            "total_plugins": total_plugins,
            "matched_plugins": matched_plugins,
            "returned_plugins": returned_plugins,
            "next_offset": (
                offset + returned_plugins
                if offset + returned_plugins < matched_plugins
                else None
            ),
            "plugins": columnar(page, _PLUGIN_COLUMNS),
        }
    )


@mcp.tool()
async def install_plugin_from_store(
    plugin_id: str,
    ctx: Context,
    wait_for_completion: bool = False,
    timeout_seconds: int = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> str:
    """Install a plugin from the Dataiku Plugin Store.

    Args:
        plugin_id: Identifier of the Store plugin to install.
        wait_for_completion: If true, wait up to timeout_seconds for the install to finish; if false, start it and return the future_id.
        timeout_seconds: Max time for the inline wait when wait_for_completion=true. This is a soft timeout checked between status polls.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    timeout_seconds = _validate_wait_timeout(timeout_seconds)
    await ctx.info(f"Installing Dataiku plugin '{plugin_id}' from the Store...")

    def _start(client):
        if _installed_plugin(client, plugin_id) is not None:
            raise ValueError(
                f"Plugin '{plugin_id}' is already installed. "
                "Use update_plugin_from_store."
            )
        return client.install_plugin_from_store(plugin_id)

    return await _run_store_operation(
        plugin_id, "plugin_install", wait_for_completion, timeout_seconds, _start
    )


@mcp.tool()
async def update_plugin_from_store(
    plugin_id: str,
    ctx: Context,
    wait_for_completion: bool = False,
    timeout_seconds: int = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> str:
    """Update an installed plugin from the Dataiku Plugin Store.

    Args:
        plugin_id: Identifier of the installed plugin to update.
        wait_for_completion: If true, wait up to timeout_seconds for the update to finish; if false, start it and return the future_id.
        timeout_seconds: Max time for the inline wait when wait_for_completion=true. This is a soft timeout checked between status polls.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    timeout_seconds = _validate_wait_timeout(timeout_seconds)
    await ctx.info(f"Updating Dataiku plugin '{plugin_id}' from the Store...")

    def _start(client):
        if _installed_plugin(client, plugin_id) is None:
            raise ValueError(f"Plugin '{plugin_id}' is not installed")
        return client.get_plugin(plugin_id).update_from_store()

    return await _run_store_operation(
        plugin_id, "plugin_update", wait_for_completion, timeout_seconds, _start
    )

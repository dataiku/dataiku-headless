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

"""Dataiku instance plugin discovery, update, and deletion tools."""

from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.errors import dataiku_message
from .utils.parsing import parse_json_object
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_int_in_range as _require_int_in_range,
    require_non_empty_string as _require_non_empty_string,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)

_SOURCES = {"store", "local_path"}
_SEARCH_MODES = {"partial", "exact"}
_MAX_TIMEOUT_SECONDS = 3600
# Store updates unpack an archive; code-environment rebuilds also install dependencies.
_DEFAULT_TIMEOUT_SECONDS = 120
_MIN_POLL_INTERVAL_SECONDS = 2
_MAX_POLL_INTERVAL_SECONDS = 30
# A refusal needs to show that the plugin is in use and roughly where, not an
# exhaustive manifest; the full list stays available from Dataiku.
_MAX_REPORTED_USAGES = 50
# Excluded to keep the uploaded archive small, not as a security boundary.
_SKIPPED_DIRECTORY_NAMES = {".git", "__pycache__"}
_MANIFEST_NAME = "plugin.json"
# Noun phrases for error prose, keyed by the machine-readable operation name.
_OPERATION_NOUNS = {
    "update": "update",
    "delete": "deletion",
    "rebuild_code_env": "code environment rebuild",
}
_FOLLOW_HINT = (
    "Follow it with get_future_status(future_id, fetch_result=true). Do not start a "
    "duplicate operation while it is running."
)
_USAGE_COLUMNS = [
    "projectKey",
    "objectType",
    "objectId",
    "elementKind",
    "elementType",
]

_SUMMARY_COLUMNS = ["id", "version", "dev", "label", "deprecated"]
_DETAIL_COLUMNS = [
    *_SUMMARY_COLUMNS,
    "description",
    "author",
    "tags",
    "category",
    "support_level",
    "license",
    "code_env_name",
]


def _serialize_summary(raw: dict) -> dict:
    """Map one entry of Dataiku's installed-plugin listing to the MCP summary."""
    meta = raw.get("meta") or {}
    return {
        "id": raw.get("id", ""),
        "version": raw.get("version", ""),
        "dev": bool(raw.get("isDev", False)),
        "label": meta.get("label", ""),
        "deprecated": bool(meta.get("deprecated", False)),
    }


def _serialize_details(raw: dict, settings_raw: dict) -> dict:
    """Add catalog metadata and the bound code environment to a plugin summary.

    Plugin-level ``config``, ``presets``, and ``parameterSets`` are deliberately never
    read out: they routinely hold credentials, and parameter names are not a secrecy
    boundary either.
    """
    meta = raw.get("meta") or {}
    return {
        **_serialize_summary(raw),
        "description": meta.get("description", ""),
        "author": meta.get("author", ""),
        "tags": meta.get("tags") or [],
        "category": meta.get("category"),
        "support_level": meta.get("supportLevel"),
        "license": meta.get("licenseInfo", ""),
        "code_env_name": settings_raw.get("codeEnvName") or None,
    }


def _matches(raw: dict, query: str) -> bool:
    """Match a query against the identifiers a user is likely to know a plugin by."""
    meta = raw.get("meta") or {}
    values = [raw.get("id", ""), meta.get("label", ""), *(meta.get("tags") or [])]
    return any(query in str(value).casefold() for value in values)


def _installed_plugin(client, plugin_id: str) -> dict:
    """Return one installed plugin's raw listing entry, or raise with the near misses."""
    listing = client.list_plugins()
    for raw in listing:
        if raw.get("id") == plugin_id:
            return raw
    similar = sorted(
        str(raw.get("id", ""))
        for raw in listing
        if plugin_id.casefold() in str(raw.get("id", "")).casefold()
    )
    message = f"Plugin '{plugin_id}' is not installed on this instance."
    if similar:
        message += f" Installed ids containing that text: {similar}."
    raise ValueError(message)


def _find_manifest_member(archive: ZipFile) -> str:
    """Locate plugin.json at the ZIP root or inside a single wrapper directory.

    Dataiku plugin exports put it at the root; a GitHub "Download ZIP" wraps
    everything in one repository directory.
    """
    names = [name for name in archive.namelist() if not name.endswith("/")]
    if _MANIFEST_NAME in names:
        return _MANIFEST_NAME
    nested = [
        name
        for name in names
        if name.count("/") == 1 and name.endswith(f"/{_MANIFEST_NAME}")
    ]
    if len(nested) == 1:
        return nested[0]
    raise ValueError(
        f"Plugin ZIP must contain {_MANIFEST_NAME} at its root or inside exactly one "
        "top-level directory"
    )


def _read_manifest_id(manifest_bytes: bytes) -> str:
    manifest = parse_json_object(manifest_bytes.decode("utf-8"), _MANIFEST_NAME)
    return _require_non_empty_string(
        str(manifest.get("id", "")), f"{_MANIFEST_NAME} 'id'"
    )


def _archive_from_directory(directory: Path) -> tuple[io.BytesIO, str]:
    manifest = directory / _MANIFEST_NAME
    if not manifest.is_file():
        raise ValueError(
            f"Plugin directory '{directory}' does not contain {_MANIFEST_NAME} at its root"
        )
    plugin_id = _read_manifest_id(manifest.read_bytes())
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as target:
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(directory)
            if _SKIPPED_DIRECTORY_NAMES.intersection(relative.parts):
                continue
            if path.is_file():
                target.write(path, relative)
    buffer.seek(0)
    return buffer, plugin_id


def _archive_from_zip(zip_path: Path) -> tuple[io.BytesIO, str]:
    try:
        with ZipFile(zip_path) as source:
            member = _find_manifest_member(source)
            plugin_id = _read_manifest_id(source.read(member))
            if member == _MANIFEST_NAME:
                return io.BytesIO(zip_path.read_bytes()), plugin_id
            # Dataiku expects plugin.json at the archive root, so drop the wrapper.
            prefix = member[: -len(_MANIFEST_NAME)]
            buffer = io.BytesIO()
            with ZipFile(buffer, "w") as target:
                for name in source.namelist():
                    if name.endswith("/") or not name.startswith(prefix):
                        continue
                    target.writestr(name[len(prefix) :], source.read(name))
    except BadZipFile as exc:
        raise ValueError(f"'{zip_path}' is not a readable ZIP archive") from exc
    buffer.seek(0)
    return buffer, plugin_id


def _local_target(plugin_id: str | None, local_path: str) -> tuple[io.BytesIO, str]:
    """Build an uploadable plugin ZIP and resolve which plugin it targets.

    The archive's own manifest names the target, so a caller-supplied ``plugin_id`` is
    only ever an assertion about it.
    """
    path = Path(local_path).expanduser()
    if path.is_dir():
        buffer, archive_id = _archive_from_directory(path)
    elif path.is_file():
        buffer, archive_id = _archive_from_zip(path)
    else:
        raise ValueError(f"'local_path' does not exist: {local_path}")
    if plugin_id is not None and plugin_id != archive_id:
        raise ValueError(
            f"'plugin_id' is '{plugin_id}' but {_MANIFEST_NAME} declares '{archive_id}'"
        )
    # requests names the multipart part from the stream's `name`; Dataiku's upload
    # endpoints expect a filename to be present.
    buffer.name = f"{archive_id}.zip"
    return buffer, archive_id


def _resolve_source(
    source: str, plugin_id: str | None, local_path: str | None
) -> tuple[str | None, str | None]:
    """Validate ``source`` and the argument that source requires."""
    _require_allowed_value(source, "source", _SOURCES)
    if source == "store":
        if local_path is not None:
            raise ValueError("'local_path' applies only to source='local_path'")
        return _require_non_empty_string(plugin_id or "", "plugin_id"), None
    local_path = _require_non_empty_string(local_path or "", "local_path")
    if plugin_id is not None:
        plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    return plugin_id, local_path


def _is_terminal(state: dict) -> bool:
    """Whether Dataiku has stopped working on a future.

    ``hasResult`` is the SDK's own completion predicate, and it also covers the case
    where Dataiku answered inline with the result already in the start response. An
    absent liveness flag is not evidence of completion, so polling continues.
    """
    if state.get("hasResult", False) or state.get("aborted", False):
        return True
    return "alive" in state and not state["alive"]


async def _wait_for_future(future, timeout_seconds: int) -> tuple[bool, dict]:
    """Poll a Dataiku future until it stops running or the inline budget runs out.

    The interval scales with the budget, so a ten-minute code-environment build is not
    polled three hundred times while short waits stay responsive.
    """
    interval = min(
        max(_MIN_POLL_INTERVAL_SECONDS, timeout_seconds // 60),
        _MAX_POLL_INTERVAL_SECONDS,
    )
    deadline = time.monotonic() + timeout_seconds
    state = future.state or {}
    while not _is_terminal(state):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True, state
        await asyncio.sleep(min(interval, remaining))
        state = await run_blocking(future.get_state)
    return False, state


def _action_failure(result: dict) -> str | None:
    """Return the failure message an update or delete result reports.

    Dataiku answers a failed plugin action with HTTP 200 and ``success: false``, so an
    absent transport error is not evidence of success. Only the message is surfaced;
    the accompanying stack trace is not.
    """
    if result.get("success") is not False:
        return None
    error = result.get("installationError") or result.get("error") or {}
    return error.get("message") or "Dataiku reported no error detail."


def _report_failure(result: dict) -> str | None:
    """Return the failure message a nested Dataiku ``messages`` report carries.

    Code-environment actions carry no top-level ``success`` flag, so a missing one must
    not be read as success. That nested report's own ``success`` field is not an
    operation-success flag either: a successful environment creation returns
    ``messages.success: false`` alongside an INFO-only ``INFO_CODEENV_IMPORT_OK`` entry.
    Only ``error`` and ``fatal`` separate a real failure from that.
    """
    messages = result.get("messages") or {}
    if not (messages.get("error") or messages.get("fatal")):
        return None
    reported = [
        str(item.get("message") or item.get("details") or item.get("title") or "")
        for item in messages.get("messages") or []
        if item.get("severity") == "ERROR"
    ]
    return "; ".join(filter(None, reported)) or "Dataiku reported no error detail."


def _terminal_result(operation: str, plugin_id: str, state: dict) -> dict:
    """Return a finished future's result, raising when it never produced one."""
    noun = _OPERATION_NOUNS[operation]
    if state.get("aborted", False):
        raise RuntimeError(f"Dataiku aborted the {noun} of plugin '{plugin_id}'.")
    if not state.get("hasResult", False):
        raise RuntimeError(
            f"Dataiku stopped the {noun} of plugin '{plugin_id}' without reporting a "
            "result. Inspect the plugin before retrying."
        )
    return state.get("result") or {}


def _successful_result(operation: str, plugin_id: str, state: dict) -> dict:
    """Return a completed action's result, raising when Dataiku reports it failed."""
    result = _terminal_result(operation, plugin_id, state)
    detail = _action_failure(result)
    if detail:
        noun = _OPERATION_NOUNS[operation]
        message = (
            f"Dataiku reported the {noun} of plugin '{plugin_id}' failed: {detail}"
        )
        raise RuntimeError(message)
    return result


def _build_outcome(result: dict, code_env_name: str) -> dict:
    """Report a code-environment build outcome instead of discarding the environment.

    The environment exists by this point, so a failed dependency install is reported
    alongside its name rather than raised: the fix is to correct the plugin's
    specification and rebuild, not to create another environment.
    """
    detail = _report_failure(result)
    if detail is None:
        return {"status": "completed", "code_env_name": code_env_name}
    return {
        "status": "failed",
        "code_env_name": code_env_name,
        "error": detail,
        "hint": (
            "The environment exists but its dependencies did not install. Fix the "
            "plugin's code-env specification, then run "
            "update_plugin(rebuild_code_env=true)."
        ),
    }


def _in_flight(operation: str, plugin_id: str, future, started: bool) -> dict:
    """Describe an operation Dataiku is still working on.

    The raw future state is deliberately left out: the caller is routed to
    ``get_future_status``, which exists to return it on demand.
    """
    return {
        "status": "started" if started else "still_running",
        "operation": operation,
        "plugin_id": plugin_id,
        "future_id": future.job_id,
        "hint": _FOLLOW_HINT,
    }


def _reload_flags(result: dict) -> dict:
    return {
        "needs_reload": bool(result.get("needsReload", False)),
        "needs_restart": bool(result.get("needsRestart", False)),
    }


async def _run_plugin_action(
    operation: str,
    plugin_id: str,
    future,
    wait_for_completion: bool,
    timeout_seconds: int,
) -> tuple[dict | None, dict]:
    """Drive one plugin future to a reportable outcome.

    Returns ``(result, payload)``. ``result`` is None when the action is still in
    flight and ``payload`` describes how to follow it; otherwise ``payload`` carries
    the reload flags of a verified success.
    """
    if not wait_for_completion and future.job_id:
        return None, _in_flight(operation, plugin_id, future, started=True)
    timed_out, state = await _wait_for_future(future, timeout_seconds)
    if timed_out:
        return None, _in_flight(operation, plugin_id, future, started=False)
    result = _successful_result(operation, plugin_id, state)
    return result, {
        "status": "completed",
        "operation": operation,
        "plugin_id": plugin_id,
        **_reload_flags(result),
    }


@mcp.tool(
    title="List Installed Plugins",
    description="Find installed plugins and inspect their metadata before an update or deletion.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_plugins(
    ctx: Context,
    search: str = "",
    search_mode: str = "partial",
    dev: bool | None = None,
    deprecated: bool | None = None,
    include_details: bool = False,
    offset: int = 0,
    limit: int = 10,
) -> str:
    """List the plugins installed on the Dataiku instance.

    Args:
        search: Matches plugin id, label, and tags. Defaults to every plugin.
        search_mode: ``partial`` for case-insensitive matching, or ``exact`` to
            retrieve one plugin by its exact id. Ignored when ``search`` is empty.
        dev: Keep only development plugins (true) or only regular ones (false).
        deprecated: Keep only deprecated plugins (true) or only current ones (false).
        include_details: Add catalog metadata and the bound code environment name.
            Reads one plugin's settings per returned row, so pair it with ``search``
            rather than listing every plugin in detail. Needs administrator or
            plugin-developer permission.
        offset: Zero-based offset within the matching plugins.
        limit: Maximum plugins to return. Values above 100 are capped at 100.
    """
    search = search.strip()
    if search:
        search_mode = _require_allowed_value(search_mode, "search_mode", _SEARCH_MODES)
    offset = _require_non_negative_int(offset, "offset")
    limit = min(_require_positive_int(limit, "limit"), 100)
    await ctx.info("Listing installed Dataiku plugins...")

    def _run():
        client = get_dss_client()
        listing = client.list_plugins()
        matched = listing
        if search and search_mode == "exact":
            matched = [raw for raw in matched if raw.get("id") == search]
        elif search:
            query = search.casefold()
            matched = [raw for raw in matched if _matches(raw, query)]
        if dev is not None:
            matched = [raw for raw in matched if bool(raw.get("isDev", False)) is dev]
        if deprecated is not None:
            matched = [
                raw
                for raw in matched
                if bool((raw.get("meta") or {}).get("deprecated", False)) is deprecated
            ]
        matched = sorted(matched, key=lambda raw: str(raw.get("id", "")).casefold())
        page = matched[offset : offset + limit]
        if include_details:
            rows = [
                _serialize_details(
                    raw, client.get_plugin(raw["id"]).get_settings().get_raw()
                )
                for raw in page
            ]
        else:
            rows = [_serialize_summary(raw) for raw in page]
        return len(listing), len(matched), rows

    total, matched, rows = await run_blocking(_run)
    returned = len(rows)
    return compact_json(
        {
            "total_plugins": total,
            "matched_plugins": matched,
            "returned_plugins": returned,
            "next_offset": offset + returned if offset + returned < matched else None,
            "plugins": columnar(
                rows, _DETAIL_COLUMNS if include_details else _SUMMARY_COLUMNS
            ),
        }
    )


@mcp.tool(
    title="Update Plugin",
    description="Update an installed plugin from the store or a local archive, optionally rebuilding its bound environment.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": True,
    },
)
async def update_plugin(
    source: str,
    ctx: Context,
    plugin_id: str | None = None,
    local_path: str | None = None,
    rebuild_code_env: bool = False,
    wait_for_completion: bool = True,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Update an installed plugin in place.

    Requires administrator or plugin-developer permission. A store update needs the
    plugin to have come from the store. Set ``rebuild_code_env`` after a change to the
    plugin's dependencies; it rebuilds the bound environment from the plugin's own
    specification and is reported separately under ``code_env_rebuild``, because the
    plugin update has already landed by then.

    Args:
        source: ``store`` to update from the Dataiku plugin store, or ``local_path``
            to upload a newer version from this machine.
        plugin_id: Installed plugin id. Required for ``store``. For ``local_path`` the
            target is the id declared in plugin.json, and this argument, if given, must
            match it.
        local_path: Plugin directory containing plugin.json at its root, or a plugin
            ZIP. Required for ``local_path``.
        rebuild_code_env: Rebuild the plugin's bound code environment after the update.
        wait_for_completion: Wait up to timeout_seconds for a verified outcome. When
            false, return a future_id to follow instead, unless Dataiku already
            answered with a completed result. Ignored while ``rebuild_code_env`` is
            true, which needs the update to have completed.
        timeout_seconds: Inline wait budget for each stage, checked between polls.
    """
    plugin_id, local_path = _resolve_source(source, plugin_id, local_path)
    timeout_seconds = _require_int_in_range(
        timeout_seconds, "timeout_seconds", 1, _MAX_TIMEOUT_SECONDS
    )
    if rebuild_code_env:
        wait_for_completion = True
    await ctx.info(f"Updating Dataiku plugin from {source}...")

    def _start():
        if source == "store":
            client = get_dss_client()
            _installed_plugin(client, plugin_id)
            return client, plugin_id, client.get_plugin(plugin_id).update_from_store()
        archive, archive_id = _local_target(plugin_id, local_path)
        client = get_dss_client()
        _installed_plugin(client, archive_id)
        plugin = client.get_plugin(archive_id)
        return client, archive_id, plugin.start_update_from_zip(archive)

    client, resolved_id, future = await run_blocking(_start)
    result, payload = await _run_plugin_action(
        "update", resolved_id, future, wait_for_completion, timeout_seconds
    )
    if result is None:
        in_flight = {**payload, "source": source}
        if rebuild_code_env:
            # A rebuild needs the update to have landed, so it never started. Saying
            # so keeps the caller from reading its absence as a completed rebuild.
            in_flight["code_env_rebuild"] = {
                "status": "not_started",
                "reason": "The update has not completed, and a rebuild needs it to.",
                "hint": (
                    "Follow the update to completion, then call "
                    "update_plugin(rebuild_code_env=true) again."
                ),
            }
        return compact_json(in_flight)
    plugin = await run_blocking(
        lambda: _serialize_summary(_installed_plugin(client, resolved_id))
    )
    response = {**payload, "source": source, "plugin": plugin}
    if rebuild_code_env:
        response["code_env_rebuild"] = await _rebuild_code_env(
            client, resolved_id, timeout_seconds
        )
    return compact_json(omit_empty(response))


async def _rebuild_code_env(client, plugin_id: str, timeout_seconds: int) -> dict:
    """Rebuild a plugin's bound code environment, reporting rather than raising.

    The plugin update has already landed when this runs, so a rebuild problem is
    reported alongside the successful update instead of discarding it.
    """

    def _start():
        plugin = client.get_plugin(plugin_id)
        bound = plugin.get_settings().get_raw().get("codeEnvName")
        return bound, plugin.update_code_env() if bound else None

    bound, future = await run_blocking(_start)
    if not bound:
        return {
            "status": "skipped",
            "reason": "No code environment is bound to this plugin.",
            "hint": (
                "Check the plugin requirements and set up its code environment in the "
                "Dataiku UI if needed. An unbound environment does not establish "
                "whether the plugin needs one."
            ),
        }
    timed_out, state = await _wait_for_future(future, timeout_seconds)
    if timed_out:
        return {
            "status": "still_running",
            "code_env_name": bound,
            "future_id": future.job_id,
            "hint": _FOLLOW_HINT,
        }
    result = _terminal_result("rebuild_code_env", plugin_id, state)
    return _build_outcome(result, bound)


def _unresolved_components_refusal(plugin_id: str, reason: str) -> dict:
    """Refuse a deletion Dataiku will not perform until it can resolve the plugin.

    Dataiku raises this from the usage analysis and from the delete endpoint itself,
    and it is the usual state for a plugin installed or updated since the last backend
    reload. Its own wording says the deletion may be forced, which is exactly what the
    ``force`` flag is for.
    """
    return {
        "status": "refused",
        "operation": "delete",
        "plugin_id": plugin_id,
        "deleted": False,
        "error": "Dataiku could not resolve this plugin's components.",
        "reason": reason,
        "hint": (
            "Reloading the Dataiku backend clears the common case, a plugin installed "
            "or updated since the last reload. Otherwise pass force=true to delete "
            "without the usage check."
        ),
    }


@mcp.tool(
    title="Delete Plugin",
    description="Remove an installed plugin after checking whether its components are in use.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    },
)
async def delete_plugin(
    plugin_id: str,
    ctx: Context,
    force: bool = False,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Delete an installed plugin, refusing while its components are still in use.

    Requires administrator or plugin-developer permission. Usages are checked first and
    deletion is refused with ``deleted: false`` when any are found. ``force=true``
    deletes anyway, which breaks every listed object. Do not infer that deletion
    happened until ``deleted`` is true.

    Args:
        plugin_id: Installed plugin id.
        force: Delete despite usages or a failed usage analysis.
        timeout_seconds: Inline wait budget, checked between polls.
    """
    plugin_id = _require_non_empty_string(plugin_id, "plugin_id")
    timeout_seconds = _require_int_in_range(
        timeout_seconds, "timeout_seconds", 1, _MAX_TIMEOUT_SECONDS
    )
    await ctx.info(f"Deleting Dataiku plugin '{plugin_id}'...")

    def _inspect():
        client = get_dss_client()
        _installed_plugin(client, plugin_id)
        plugin = client.get_plugin(plugin_id)
        try:
            raw = plugin.list_usages().get_raw()
        except Exception as exc:
            # Dataiku raises here when it cannot resolve the plugin's component types,
            # the same condition its delete endpoint enforces.
            return plugin, None, None, dataiku_message(exc)
        usages = raw.get("usages") or []
        # Dataiku reports unresolvable component types for the whole instance here,
        # most of them unrelated to this plugin.
        unresolvable = [
            item
            for item in raw.get("missingTypes") or []
            if item.get("pluginId") == plugin_id
        ]
        return plugin, usages, unresolvable, None

    plugin, usages, unresolvable, analysis_error = await run_blocking(_inspect)
    if analysis_error is not None and not force:
        if "may be forced" not in analysis_error:
            raise RuntimeError(
                f"Dataiku could not analyze usages of plugin '{plugin_id}': "
                f"{analysis_error}"
            )
        return compact_json(_unresolved_components_refusal(plugin_id, analysis_error))
    if (usages or unresolvable) and not force:
        return compact_json(
            omit_empty(
                {
                    "status": "refused",
                    "operation": "delete",
                    "plugin_id": plugin_id,
                    "deleted": False,
                    "error": "Plugin cannot be deleted because it is still in use.",
                    "usage_count": len(usages),
                    "usages": columnar(usages[:_MAX_REPORTED_USAGES], _USAGE_COLUMNS),
                    "unresolvable_components": unresolvable,
                    "hint": (
                        "Remove or replace every listed object, then retry. Pass "
                        "force=true only to delete anyway and break them."
                    ),
                }
            )
        )

    try:
        future = await run_blocking(lambda: plugin.delete(force=force))
    except Exception as exc:
        # Dataiku enforces the same resolvability check on the delete endpoint, so
        # this is reachable even when the usage analysis itself came back clean.
        message = dataiku_message(exc)
        if force or "may be forced" not in message:
            raise
        return compact_json(_unresolved_components_refusal(plugin_id, message))
    timed_out, state = await _wait_for_future(future, timeout_seconds)
    if timed_out:
        return compact_json(
            {**_in_flight("delete", plugin_id, future, started=False), "deleted": False}
        )
    result = _successful_result("delete", plugin_id, state)
    return compact_json(
        {
            "status": "completed",
            "operation": "delete",
            "plugin_id": plugin_id,
            "deleted": True,
            "forced": force,
            **_reload_flags(result),
        }
    )

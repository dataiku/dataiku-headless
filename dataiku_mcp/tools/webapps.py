"""WebApp creation, inspection, settings, and backend lifecycle tools."""

import copy

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
)

WEBAPP_SECRET_REDACTION = "__DATAIKU_REDACTED__"
_PRESERVED_SENSITIVE_KEYS = {"apiKey"}
_SUPPORTED_WEBAPP_TYPES = {"STANDARD", "BOKEH", "DASH", "STREAMLIT", "SHINY"}


def _redact_webapp_settings(raw_settings: dict) -> dict:
    redacted = copy.deepcopy(raw_settings)
    for key in _PRESERVED_SENSITIVE_KEYS:
        if key in redacted:
            redacted[key] = WEBAPP_SECRET_REDACTION
    return redacted


def _restore_preserved_sensitive_fields(
    current_settings: dict, proposed_settings: dict
) -> dict:
    restored = copy.deepcopy(proposed_settings)
    for key in _PRESERVED_SENSITIVE_KEYS:
        if key not in current_settings:
            continue
        if key not in restored or restored[key] == WEBAPP_SECRET_REDACTION:
            restored[key] = current_settings[key]
    return restored


def _serialize_webapp_list_item(item: dict) -> dict:
    created_by = item.get("createdBy") or {}
    modified_by = item.get("lastModifiedBy") or {}

    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "type": item.get("type"),
        "backend_running": item.get("backendRunning", False),
        "tags": item.get("tags", []),
        "created_on": item.get("createdOn"),
        "created_by": created_by.get("login"),
        "last_modified_on": item.get("lastModifiedOn"),
        "last_modified_by": modified_by.get("login"),
    }


@mcp.tool()
async def create_webapp(
    project_key: str,
    webapp_name: str,
    ctx: Context,
    webapp_type: str = "STANDARD",
) -> str:
    """Create a new native code WebApp in the project.

    Args:
        webapp_type: One of STANDARD, BOKEH, DASH, STREAMLIT, or SHINY
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    webapp_name = _require_non_empty_string(webapp_name, "webapp_name")
    webapp_type = _require_allowed_value(
        _require_non_empty_string(webapp_type, "webapp_type").upper(),
        "webapp_type",
        _SUPPORTED_WEBAPP_TYPES,
    )

    await ctx.info(
        f"Creating {webapp_type} WebApp '{webapp_name}' in {project_key}..."
    )

    def _run():
        webapp = get_dss_client().get_project(project_key).create_webapp(
            webapp_name,
            webapp_type=webapp_type,
        )
        return webapp.get_settings().get_raw()

    created = await run_blocking(_run)

    return compact_json({
            "settings": _redact_webapp_settings(created),
        })


@mcp.tool()
async def list_webapps(project_key: str, ctx: Context) -> str:
    """List the WebApps in the project with type and backend status."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing WebApps in {project_key}...")

    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_webapps()
    )

    webapps = [_serialize_webapp_list_item(dict(item)) for item in items]

    return compact_json({
            "webapps": columnar(
                webapps,
                [
                    "id",
                    "name",
                    "type",
                    "backend_running",
                    "tags",
                    "created_on",
                    "created_by",
                    "last_modified_on",
                    "last_modified_by",
                ],
            ),
        })


@mcp.tool()
async def get_webapp_settings(
    project_key: str,
    webapp_id: str,
    ctx: Context,
) -> str:
    """Get the full WebApp settings dict. Sensitive top-level fields (e.g. apiKey) are redacted in the returned payload."""
    project_key = _require_non_empty_string(project_key, "project_key")
    webapp_id = _require_non_empty_string(webapp_id, "webapp_id")
    await ctx.info(f"Loading settings for WebApp {webapp_id} in {project_key}...")

    raw = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_webapp(webapp_id)
            .get_settings()
            .get_raw()
        )
    )

    return compact_json(_redact_webapp_settings(raw))


@mcp.tool()
async def set_webapp_settings(
    project_key: str,
    webapp_id: str,
    new_settings,
    ctx: Context,
) -> str:
    """Set the full WebApp settings. Sensitive fields (e.g. apiKey) left as the redaction sentinel or omitted are preserved from the current values.

    Args:
        new_settings: A modified version of the object returned by get_webapp_settings
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    webapp_id = _require_non_empty_string(webapp_id, "webapp_id")
    new_settings_obj = _coerce_json_object(new_settings, "new_settings")

    await ctx.info(f"Replacing settings for WebApp {webapp_id} in {project_key}...")

    def _run():
        webapp = get_dss_client().get_project(project_key).get_webapp(webapp_id)
        settings = webapp.get_settings()
        current_raw = settings.get_raw()

        restored = _restore_preserved_sensitive_fields(current_raw, new_settings_obj)
        restored["id"] = webapp_id
        restored["projectKey"] = project_key
        settings.data = restored
        settings.save()
        return settings.get_raw()

    updated = await run_blocking(_run)

    return compact_json({
            "settings": _redact_webapp_settings(updated),
        })


@mcp.tool()
async def get_webapp_state(
    project_key: str,
    webapp_id: str,
    ctx: Context,
) -> str:
    """Get the WebApp's backend state."""
    project_key = _require_non_empty_string(project_key, "project_key")
    webapp_id = _require_non_empty_string(webapp_id, "webapp_id")
    await ctx.info(f"Loading backend state for WebApp {webapp_id} in {project_key}...")

    def _run():
        webapp = get_dss_client().get_project(project_key).get_webapp(webapp_id)
        state = webapp.get_state()
        result = {
            "backend_running": state.running,
            "state": state.state,
        }
        return omit_empty(result)

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def restart_webapp_backend(
    project_key: str,
    webapp_id: str,
    ctx: Context,
    wait_for_completion: bool = True,
) -> str:
    """Start or restart the WebApp backend.

    Args:
        wait_for_completion: If true, wait for the restart to finish; if false, return the future ID immediately
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    webapp_id = _require_non_empty_string(webapp_id, "webapp_id")
    await ctx.info(
        f"Restarting WebApp backend {webapp_id} in {project_key} "
        f"(wait_for_completion={wait_for_completion})..."
    )

    def _start():
        return (
            get_dss_client()
            .get_project(project_key)
            .get_webapp(webapp_id)
            .start_or_restart_backend()
        )

    future = await run_blocking(_start)

    if not wait_for_completion:
        return compact_json({
                "status": "webapp_backend_restart_started",
                "future_id": future.job_id,
            })

    def _wait():
        result = future.wait_for_result()
        state = (
            get_dss_client()
            .get_project(project_key)
            .get_webapp(webapp_id)
            .get_state()
        )
        waited = {
            "future_result": result,
            "backend_running": state.running,
            "state": state.state,
        }
        return omit_empty(waited)

    completed = await run_blocking(_wait)

    return compact_json({
            "status": "webapp_backend_restart_completed",
            "future_id": future.job_id,
            **completed,
        })


@mcp.tool()
async def stop_webapp_backend(
    project_key: str,
    webapp_id: str,
    ctx: Context,
) -> str:
    """Stop the WebApp backend."""
    project_key = _require_non_empty_string(project_key, "project_key")
    webapp_id = _require_non_empty_string(webapp_id, "webapp_id")
    await ctx.info(f"Stopping WebApp backend {webapp_id} in {project_key}...")

    def _run():
        webapp = get_dss_client().get_project(project_key).get_webapp(webapp_id)
        webapp.stop_backend()
        state = webapp.get_state()
        result = {
            "backend_running": state.running,
            "state": state.state,
        }
        return omit_empty(result)

    result = await run_blocking(_run)

    return compact_json(result)


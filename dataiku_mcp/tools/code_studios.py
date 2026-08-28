"""Dataiku Code Studio template and lifecycle tools."""

import copy

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client, require_admin
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string as _require_non_empty_string

_REDACTED = "__DATAIKU_REDACTED__"
_SENSITIVE_KEY_PARTS = ("password", "secret", "token", "apikey", "api_key")
_TEMPLATE_COLUMNS = ["id", "name", "description", "built"]
_STUDIO_COLUMNS = ["id", "name", "template_id", "owner", "state"]


def _redact_sensitive(value):
    """Recursively redact credential values while preserving configuration shape."""
    if isinstance(value, dict):
        return {
            key: (
                _REDACTED
                if any(part in key.casefold() for part in _SENSITIVE_KEY_PARTS)
                else _redact_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _deep_merge(existing: dict, patch: dict) -> dict:
    """Apply a JSON-object patch without dropping unrelated template settings."""
    merged = copy.deepcopy(existing)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _template_summary(raw: dict) -> dict:
    return {
        "id": raw.get("id", ""),
        "name": raw.get("name", raw.get("label", "")),
        "description": raw.get("description", raw.get("desc", "")),
        "built": raw.get("built", raw.get("isBuilt", False)),
    }


def _studio_summary(raw: dict, state: str | None = None) -> dict:
    return {
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "template_id": raw.get("templateId", ""),
        "owner": raw.get("owner", raw.get("ownerLogin", "")),
        "state": state if state is not None else raw.get("state"),
    }


def _studio_list_item_summary(item) -> dict:
    """Serialize the narrower list-item object returned by the DSS SDK."""
    if isinstance(item, dict):
        return _studio_summary(item)
    return {
        "id": item.id,
        "name": item.name,
        "template_id": item.template_id,
        "owner": item.owner,
        "state": None,
    }


@mcp.tool()
async def list_code_studio_templates(ctx: Context) -> str:
    """List Code Studio templates. Requires Dataiku administrator access."""
    await require_admin()
    await ctx.info("Listing Code Studio templates...")
    templates = await run_blocking(
        lambda: get_dss_client()._perform_json("GET", "/admin/code-studios/")
    )
    rows = [_template_summary(raw) for raw in templates]
    return compact_json({"code_studio_templates": columnar(rows, _TEMPLATE_COLUMNS)})


@mcp.tool()
async def get_code_studio_template_settings(template_id: str, ctx: Context) -> str:
    """Get Code Studio template settings with credential values redacted.

    Requires Dataiku administrator access. Use this result to identify the settings
    to patch; redacted credential values are intentionally not reusable.
    """
    template_id = _require_non_empty_string(template_id, "template_id")
    await require_admin()
    await ctx.info(f"Loading Code Studio template {template_id}...")
    raw = await run_blocking(
        lambda: get_dss_client()._perform_json(
            "GET", f"/admin/code-studios/{template_id}"
        )
    )
    return compact_json(_redact_sensitive(raw))


@mcp.tool()
async def update_code_studio_template(
    template_id: str,
    settings_patch: dict,
    ctx: Context,
) -> str:
    """Patch Code Studio template settings, preserving settings not supplied.

    Requires Dataiku administrator access. This does not build the template; call
    build_code_studio_template after a successful update.
    """
    template_id = _require_non_empty_string(template_id, "template_id")
    if not isinstance(settings_patch, dict) or not settings_patch:
        raise ValueError("'settings_patch' must be a non-empty object")
    await require_admin()
    await ctx.info(f"Updating Code Studio template {template_id}...")

    def _run():
        client = get_dss_client()
        current = client._perform_json("GET", f"/admin/code-studios/{template_id}")
        updated = _deep_merge(current, settings_patch)
        client._perform_json("PUT", f"/admin/code-studios/{template_id}", body=updated)

    await run_blocking(_run)
    return compact_json({"template_id": template_id, "updated": True})


@mcp.tool()
async def build_code_studio_template(
    template_id: str,
    ctx: Context,
    disable_docker_cache: bool = False,
) -> str:
    """Start a Code Studio template image build. Requires administrator access."""
    template_id = _require_non_empty_string(template_id, "template_id")
    await require_admin()
    await ctx.info(f"Starting build for Code Studio template {template_id}...")
    await run_blocking(
        lambda: get_dss_client()._perform_empty(
            "POST",
            f"/admin/code-studios/{template_id}/build",
            body={"disableDockerCache": disable_docker_cache},
        )
    )
    return compact_json(
        {
            "template_id": template_id,
            "status": "build_requested",
            "hint": "The DSS build endpoint returns no future ID. Start or inspect a Code Studio after the image build completes.",
        }
    )


@mcp.tool()
async def list_code_studios(project_key: str, ctx: Context) -> str:
    """List Code Studios in a project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing Code Studios in {project_key}...")
    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_code_studios()
    )
    rows = [_studio_list_item_summary(item) for item in items]
    return compact_json({"code_studios": columnar(rows, _STUDIO_COLUMNS)})


@mcp.tool()
async def get_code_studio(project_key: str, code_studio_id: str, ctx: Context) -> str:
    """Get Code Studio settings and current runtime status."""
    project_key = _require_non_empty_string(project_key, "project_key")
    code_studio_id = _require_non_empty_string(code_studio_id, "code_studio_id")
    await ctx.info(f"Loading Code Studio {code_studio_id} in {project_key}...")

    def _run():
        studio = (
            get_dss_client().get_project(project_key).get_code_studio(code_studio_id)
        )
        return {
            "settings": _redact_sensitive(studio.get_settings().get_raw()),
            "status": _redact_sensitive(studio.get_status().get_raw()),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_code_studio(
    project_key: str, name: str, template_id: str, ctx: Context
) -> str:
    """Create a stopped Code Studio in a project from an existing template."""
    project_key = _require_non_empty_string(project_key, "project_key")
    name = _require_non_empty_string(name, "name")
    template_id = _require_non_empty_string(template_id, "template_id")
    await ctx.info(f"Creating Code Studio {name} in {project_key}...")

    def _run():
        studio = (
            get_dss_client()
            .get_project(project_key)
            .create_code_studio(name, template_id)
        )
        return _studio_summary(studio.get_settings().get_raw())

    return compact_json(await run_blocking(_run))


async def _change_code_studio_state(
    project_key: str, code_studio_id: str, ctx: Context, action: str
) -> str:
    project_key = _require_non_empty_string(project_key, "project_key")
    code_studio_id = _require_non_empty_string(code_studio_id, "code_studio_id")
    await ctx.info(
        f"{action.capitalize()}ing Code Studio {code_studio_id} in {project_key}..."
    )

    def _run():
        studio = (
            get_dss_client().get_project(project_key).get_code_studio(code_studio_id)
        )
        future = studio.restart() if action == "start" else studio.stop()
        return getattr(future, "job_id", None)

    future_id = await run_blocking(_run)
    return compact_json(
        {
            "project_key": project_key,
            "code_studio_id": code_studio_id,
            "status": f"{action}_requested",
            "future_id": future_id,
        }
    )


@mcp.tool()
async def start_code_studio(project_key: str, code_studio_id: str, ctx: Context) -> str:
    """Start or restart a Code Studio without waiting for readiness."""
    return await _change_code_studio_state(project_key, code_studio_id, ctx, "start")


@mcp.tool()
async def stop_code_studio(project_key: str, code_studio_id: str, ctx: Context) -> str:
    """Stop a Code Studio without waiting for completion."""
    return await _change_code_studio_state(project_key, code_studio_id, ctx, "stop")

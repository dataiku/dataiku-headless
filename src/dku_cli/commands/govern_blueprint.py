"""dku govern-blueprint — list, get, list-versions, get-version, fields."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import render, render_raw, resolve_output_format

app = typer.Typer(
    help="Manage Govern blueprints. Use 'fields' subcommand to discover field schemas for artifact creation."
)


@app.command("list")
def list_blueprints(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all Govern blueprints."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        blueprints = govern.list_blueprints()
        data = []
        for item in blueprints:
            raw = item.get_raw()
            bp = raw.get("blueprint", raw)
            data.append(
                {
                    "id": bp.get("id", ""),
                    "name": bp.get("name", ""),
                    "icon": bp.get("icon", ""),
                }
            )
        render(
            data,
            ["id", "name", "icon"],
            output_format=output,
            title="Govern Blueprints",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(
        help="Blueprint ID (e.g. bp.system.govern_project)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get a blueprint definition."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        bp = govern.get_blueprint(blueprint_id)
        defn = bp.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-versions")
def list_versions(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List versions of a blueprint."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        bp = govern.get_blueprint(blueprint_id)
        versions = bp.list_versions()
        data = []
        for item in versions:
            raw = item.get_raw()
            bv = raw.get("blueprintVersion", raw)
            vid = bv.get("id", {})
            trace = raw.get("blueprintVersionTrace", {})
            data.append(
                {
                    "version_id": vid.get("versionId", "")
                    if isinstance(vid, dict)
                    else str(vid),
                    "name": bv.get("name", ""),
                    "status": trace.get("status", ""),
                }
            )
        render(
            data,
            ["version_id", "name", "status"],
            output_format=output,
            title=f"Versions of {blueprint_id}",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-version")
def get_version(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID (e.g. bv.system.default)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get a blueprint version definition."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        bp = govern.get_blueprint(blueprint_id)
        ver = bp.get_version(version_id)
        defn = ver.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


def _resolve_active_version(govern, blueprint_id: str) -> str:
    """Find the ACTIVE version ID for a blueprint, falling back to the first version."""
    bp = govern.get_blueprint(blueprint_id)
    versions = bp.list_versions()
    for item in versions:
        raw = item.get_raw()
        trace = raw.get("blueprintVersionTrace", {})
        if trace.get("status") == "ACTIVE":
            bv = raw.get("blueprintVersion", raw)
            vid = bv.get("id", {})
            return vid.get("versionId", "") if isinstance(vid, dict) else str(vid)
    # Fallback: first version
    if versions:
        raw = versions[0].get_raw()
        bv = raw.get("blueprintVersion", raw)
        vid = bv.get("id", {})
        return vid.get("versionId", "") if isinstance(vid, dict) else str(vid)
    return "bv.system.default"


@app.command()
def fields(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(
        help="Blueprint ID (e.g. bp.system.govern_project)"
    ),
    version_id: Optional[str] = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List fields for a blueprint with type, list/scalar, required, and valid categories.

    Shows the field schema agents and scripts need to construct artifact definitions.
    DATE fields accept ISO 8601 strings (e.g. "2025-01-15T00:00:00.000Z").
    REFERENCE fields accept artifact IDs (e.g. "ar.123").
    List fields (marked with * in LIST column) must be JSON arrays, even for a single value.
    """
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        if not version_id:
            version_id = _resolve_active_version(govern, blueprint_id)
        bp = govern.get_blueprint(blueprint_id)
        ver = bp.get_version(version_id)
        defn = ver.get_definition()
        raw = defn.get_raw()
        field_defs = raw.get("fieldDefinitions", {})

        data = []
        for field_id, fd in field_defs.items():
            is_list = "listConfig" in fd
            source = fd.get("sourceType", "")
            # Skip COMPUTE fields — agents can't set them
            if source == "COMPUTE":
                continue
            categories = fd.get("categories", [])
            if categories:
                if output == "json":
                    cat_display = ", ".join(categories)
                elif len(categories) > 10:
                    cat_display = (
                        ", ".join(categories[:10]) + f" ... ({len(categories)} total)"
                    )
                else:
                    cat_display = ", ".join(categories)
            else:
                cat_display = ""
            allowed_bps = fd.get("allowedBlueprints", [])
            if allowed_bps and not cat_display:
                cat_display = "refs: " + ", ".join(allowed_bps)
            data.append(
                {
                    "field": field_id,
                    "type": fd.get("fieldType", ""),
                    "list": "*" if is_list else "",
                    "required": "*" if fd.get("required") else "",
                    "label": fd.get("label", ""),
                    "values": cat_display,
                }
            )

        render(
            data,
            ["field", "type", "list", "required", "label", "values"],
            output_format=output,
            title=f"Fields for {blueprint_id} ({version_id})",
            headers={
                "field": "FIELD ID",
                "type": "TYPE",
                "list": "LIST",
                "required": "REQ",
                "label": "LABEL",
                "values": "CATEGORIES / ALLOWED REFS",
            },
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)

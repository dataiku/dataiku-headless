"""dku govern-blueprint — list, get, list-versions, get-version."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import render, render_raw, resolve_output_format

app = typer.Typer(help="Manage Govern blueprints.")


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

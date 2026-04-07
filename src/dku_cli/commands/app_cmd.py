"""dku app — list, get, list-instances, create-instance."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS apps and instances.")


@app.command("list")
def list_apps(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all apps on the DSS instance."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        items = client.list_apps(as_type="listitems")

        data = []
        for item in items:
            data.append(
                {
                    "app_id": item.get("appId", ""),
                    "label": item.get("label", ""),
                    "project_key": item.get("projectKey", ""),
                }
            )

        render(
            data, ["app_id", "label", "project_key"], output_format=output, title="Apps"
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    app_id: str = typer.Argument(help="App ID (e.g. PROJECT_MYAPP)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get app manifest/details."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        app_handle = client.get_app(app_id)
        manifest = app_handle.get_manifest()
        raw = manifest.get_raw()

        if output == "json":
            render_raw(raw, output_format=output)
        else:
            total_tiles = sum(
                len(s.get("tiles", [])) for s in raw.get("homepageSections", [])
            )
            data = [
                {"field": "App ID", "value": app_id},
                {"field": "Label", "value": raw.get("label", "")},
                {"field": "Description", "value": raw.get("shortDesc", "")},
                {"field": "Homepage", "value": str(raw.get("useAppHomepage", False))},
                {"field": "Tiles", "value": str(total_tiles)},
                {
                    "field": "Permission",
                    "value": raw.get("instantiationPermission", ""),
                },
            ]
            render(
                data, ["field", "value"], output_format="table", title=f"App: {app_id}"
            )
    except Exception as e:
        handle_api_error(e)


@app.command("list-instances")
def list_instances(
    ctx: typer.Context,
    app_id: str = typer.Argument(help="App ID (e.g. PROJECT_MYAPP)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List instances of an app."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        app_handle = client.get_app(app_id)
        instances = app_handle.list_instances()

        data = []
        for inst in instances:
            data.append({"project_key": inst.get("projectKey", "")})

        render(
            data,
            ["project_key"],
            output_format=output,
            title=f"Instances of {app_id}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-instance")
def create_instance(
    ctx: typer.Context,
    app_id: str = typer.Argument(help="App ID (e.g. PROJECT_MYAPP)"),
    instance_key: str = typer.Option(
        ..., "--key", "-k", help="Project key for the new instance"
    ),
    instance_name: str = typer.Option(
        ..., "--name", "-n", help="Display name for the new instance"
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for instance creation (default: true)"
    ),
) -> None:
    """Create a new app instance."""
    try:
        client = get_client_from_ctx(ctx)
        app_handle = client.get_app(app_id)
        result = app_handle.create_instance(instance_key, instance_name, wait=wait)

        if wait:
            success(
                f"Created app instance '{instance_key}' (project: {result.project_key})"
            )
        else:
            success(f"Instance creation started for '{instance_key}'")
    except Exception as e:
        handle_api_error(e)

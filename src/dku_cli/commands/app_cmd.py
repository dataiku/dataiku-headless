"""dku app — list, get, create-instance, list-instances, manifest."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS applications (app templates and instances).")


@app.command("list")
def list_apps(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all applications (app templates)."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        items = client.list_apps()

        data = []
        for item in items:
            try:
                # dataikuapi DSSAppListItem stores raw data in _data
                # (no public accessor for appId/label on list items)
                app_id = item._data.get("appId", "")
                label = item._data.get("label", "")
            except AttributeError:
                app_id = getattr(item, "app_id", str(item))
                label = ""
            data.append({"id": app_id, "label": label})

        if fmt == "json":
            render_raw(data, output_format="json")
        else:
            if not data:
                info("No applications found.")
                return
            render(
                data,
                ["id", "label"],
                output_format=fmt,
                title="Applications",
                headers={"id": "ID", "label": "LABEL"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    app_id: str = typer.Argument(help="App ID (format: PROJECT_<key>)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get app manifest (definition)."""
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        application = client.get_app(app_id)
        manifest = application.get_manifest()
        render_raw(manifest.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("list-instances")
def list_instances(
    ctx: typer.Context,
    app_id: str = typer.Argument(help="App ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List instances of an application.

    Example:
      dku app list-instances PROJECT_MYAPP
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        application = client.get_app(app_id)
        instances = application.list_instances()

        if fmt == "json":
            render_raw(instances, output_format="json")
        else:
            if not instances:
                info(f"No instances of app '{app_id}'.")
                return

            data = []
            for inst in instances:
                data.append(
                    {
                        "project_key": inst.get("projectKey", ""),
                        "name": inst.get("name", ""),
                    }
                )
            render(
                data,
                ["project_key", "name"],
                output_format=fmt,
                title=f"Instances ({app_id})",
                headers={"project_key": "PROJECT KEY", "name": "NAME"},
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-instance")
def create_instance(
    ctx: typer.Context,
    app_id: str = typer.Argument(help="App ID to instantiate"),
    instance_key: str = typer.Option(
        ..., "--key", "-k", help="Project key for the new instance (must be unique)"
    ),
    instance_name: str = typer.Option(
        ..., "--name", "-n", help="Display name for the new instance"
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for instance creation"
    ),
) -> None:
    """Create a new instance of an application.

    Example:
      dku app create-instance PROJECT_MYAPP --key MYAPP_PROD --name "Production Instance"
    """
    try:
        client = get_client_from_ctx(ctx)
        application = client.get_app(app_id)

        if wait:
            instance = application.create_instance(
                instance_key, instance_name, wait=True
            )
            success(
                f"Created app instance '{instance_name}' "
                f"(project: {instance.project_key}) from '{app_id}'"
            )
        else:
            application.create_instance(instance_key, instance_name, wait=False)
            success(
                f"Instance creation started for '{instance_name}' (project: {instance_key})"
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

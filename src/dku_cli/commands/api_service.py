"""dku api-service — list, create, get, create-package, list-packages."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS API services.")


@app.command("list")
def list_api_services(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List API services in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        services = proj.list_api_services()

        data = []
        for s in services:
            data.append(
                {
                    "id": s.get("id", "") if isinstance(s, dict) else str(s),
                }
            )

        render(
            data,
            ["id"],
            output_format=output,
            title=f"API Services ({project_key})",
            headers={"id": "ID"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create")
def create_api_service(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new API service."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        proj.create_api_service(service_id)
        success(f"Created API service '{service_id}' in project {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("get")
def get_api_service(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get API service settings."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        service = proj.get_api_service(service_id)
        raw = service.get_settings().get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("create-package")
def create_package(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new package for an API service."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        service = proj.get_api_service(service_id)
        service.create_package()
        success(f"Created package for API service '{service_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("list-packages")
def list_packages(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List packages for an API service."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        service = proj.get_api_service(service_id)
        packages = service.list_packages()

        data = []
        for p in packages:
            data.append(
                {
                    "id": p.get("id", "") if isinstance(p, dict) else str(p),
                    "created_on": p.get("createdOn", "") if isinstance(p, dict) else "",
                }
            )

        render(
            data,
            ["id", "created_on"],
            output_format=output,
            title=f"Packages ({service_id})",
            headers={"id": "ID", "created_on": "CREATED"},
        )
    except Exception as e:
        handle_api_error(e)

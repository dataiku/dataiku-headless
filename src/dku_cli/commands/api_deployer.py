"""dku api-deployer — manage API Deployer infras, services, and deployments."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage API Deployer infras, services, and deployments.")


@app.command("list-infras")
def list_infras(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List API Deployer infrastructures."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_apideployer()
        infras = deployer.list_infras(as_objects=False)

        data = []
        for infra in infras:
            info = infra.get("infraBasicInfo", infra)
            data.append(
                {
                    "id": info.get("id", ""),
                    "type": info.get("type", ""),
                }
            )

        render(
            data,
            ["id", "type"],
            output_format=output,
            title="API Deployer Infras",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("list-services")
def list_services(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List API Deployer services."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_apideployer()
        services = deployer.list_services(as_objects=False)

        data = []
        for svc in services:
            info = svc.get("serviceBasicInfo", svc)
            data.append({"id": info.get("id", "")})

        render(
            data,
            ["id"],
            output_format=output,
            title="API Deployer Services",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("get-service")
def get_service(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="Service ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show API Deployer service settings."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_apideployer()
        svc = deployer.get_service(service_id)
        raw = svc.get_settings().get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("list-deployments")
def list_deployments(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List API Deployer deployments."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_apideployer()
        deployments = deployer.list_deployments(as_objects=False)

        data = []
        for dep in deployments:
            info = dep.get("deploymentBasicInfo", dep)
            data.append(
                {
                    "id": info.get("id", ""),
                    "service_id": info.get("serviceId", ""),
                    "infra_id": info.get("infraId", ""),
                }
            )

        render(
            data,
            ["id", "service_id", "infra_id"],
            output_format=output,
            title="API Deployer Deployments",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-deployment")
def create_deployment(
    ctx: typer.Context,
    deployment_id: str = typer.Option(..., "--id", help="Deployment ID"),
    service_id: str = typer.Option(..., "--service-id", help="Service ID"),
    infra_id: str = typer.Option(..., "--infra-id", help="Infrastructure ID"),
    version: str = typer.Option(..., "--version", help="Service version to deploy"),
) -> None:
    """Create a new API Deployer deployment."""
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_apideployer()
        deployer.create_deployment(deployment_id, service_id, infra_id, version)
        success(
            f"Created deployment '{deployment_id}' (service={service_id}, infra={infra_id}, version={version})"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("get-deployment")
def get_deployment(
    ctx: typer.Context,
    deployment_id: str = typer.Argument(help="Deployment ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show API Deployer deployment settings."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_apideployer()
        dep = deployer.get_deployment(deployment_id)
        raw = dep.get_settings().get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("update-deployment")
def update_deployment(
    ctx: typer.Context,
    deployment_id: str = typer.Argument(help="Deployment ID"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for update to complete"
    ),
) -> None:
    """Update (push) an API Deployer deployment."""
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_apideployer()
        dep = deployer.get_deployment(deployment_id)
        future = dep.start_update()
        if wait:
            future.wait_for_result()
            success(f"Updated deployment '{deployment_id}'")
        else:
            success(f"Update started for deployment '{deployment_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("delete-deployment")
def delete_deployment(
    ctx: typer.Context,
    deployment_id: str = typer.Argument(help="Deployment ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete an API Deployer deployment."""
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="api_deployer.delete_deployment",
        subject=f"API deployment '{deployment_id}'",
        yes=yes,
        prompt=f"Delete API deployment '{deployment_id}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_apideployer()
        dep = deployer.get_deployment(deployment_id)
        dep.delete()
        success(f"Deleted deployment '{deployment_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("deployment-status")
def deployment_status(
    ctx: typer.Context,
    deployment_id: str = typer.Argument(help="Deployment ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show API Deployer deployment status."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_apideployer()
        dep = deployer.get_deployment(deployment_id)
        status = dep.get_light_status()
        render_raw(status, output_format=output)
    except Exception as e:
        handle_api_error(e)

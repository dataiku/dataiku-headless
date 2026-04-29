"""dku project-deployer — manage Project Deployer infras, projects, and deployments."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage Project Deployer infras, projects, and deployments.")


@app.command("list-infras")
def list_infras(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List Project Deployer infrastructures."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_projectdeployer()
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
            title="Project Deployer Infras",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("list-projects")
def list_projects(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List Project Deployer published projects."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_projectdeployer()
        projects = deployer.list_projects(as_objects=False)

        data = []
        for p in projects:
            info = p.get("projectBasicInfo", p)
            data.append({"id": info.get("id", "")})

        render(
            data,
            ["id"],
            output_format=output,
            title="Project Deployer Projects",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("list-deployments")
def list_deployments(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List Project Deployer deployments."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_projectdeployer()
        deployments = deployer.list_deployments(as_objects=False)

        data = []
        for dep in deployments:
            info = dep.get("deploymentBasicInfo", dep)
            data.append(
                {
                    "id": info.get("id", ""),
                    "project_id": info.get("projectKey", ""),
                    "infra_id": info.get("infraId", ""),
                }
            )

        render(
            data,
            ["id", "project_id", "infra_id"],
            output_format=output,
            title="Project Deployer Deployments",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-deployment")
def create_deployment(
    ctx: typer.Context,
    deployment_id: str = typer.Option(..., "--id", help="Deployment ID"),
    project_id: str = typer.Option(..., "--project-id", help="Project ID"),
    infra_id: str = typer.Option(..., "--infra-id", help="Infrastructure ID"),
    bundle_id: str = typer.Option(..., "--bundle-id", help="Bundle ID to deploy"),
) -> None:
    """Create a new Project Deployer deployment."""
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_projectdeployer()
        deployer.create_deployment(deployment_id, project_id, infra_id, bundle_id)
        success(
            f"Created deployment '{deployment_id}' (project={project_id}, infra={infra_id}, bundle={bundle_id})"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("get-deployment")
def get_deployment(
    ctx: typer.Context,
    deployment_id: str = typer.Argument(help="Deployment ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show Project Deployer deployment settings."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_projectdeployer()
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
    """Update (push) a Project Deployer deployment."""
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_projectdeployer()
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
    """Delete a Project Deployer deployment."""
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="project_deployer.delete_deployment",
        subject=f"project deployment '{deployment_id}'",
        yes=yes,
        prompt=f"Delete project deployment '{deployment_id}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_projectdeployer()
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
    """Show Project Deployer deployment status."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        deployer = client.get_projectdeployer()
        dep = deployer.get_deployment(deployment_id)
        status = dep.get_light_status()
        render_raw(status, output_format=output)
    except Exception as e:
        handle_api_error(e)

"""dku api-service — list, create, get, create-package, list-packages, add-endpoint, list-endpoints, publish-package, delete-package."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, locked_settings, resolve_project
from dku_cli.output import (
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage DSS API services.")


@app.command("list")
def list_api_services(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List API services in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        hint(f"dku api-service get {service_id} -P {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("get")
def get_api_service(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get API service settings."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
    package_id: str = typer.Option(
        ..., "--package", help="Package version ID to create (e.g. v1)"
    ),
    release_notes: str | None = typer.Option(
        None,
        "--release-notes",
        help="Release notes describing changes in this package",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new package (version) for an API service.

    The package ID is the version identifier you choose (e.g. v1, v2).
    Required by the DSS server — without it the package cannot be created.

    Example:
      dku api-service create-package myservice --package v1 -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        service = proj.get_api_service(service_id)
        service.create_package(package_id, release_notes=release_notes)
        success(
            f"Created package '{package_id}' for API service '{service_id}' "
            f"in {project_key}"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("list-packages")
def list_packages(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List packages for an API service."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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


_ENDPOINT_TYPES = {
    "prediction": "STD_PREDICTION",
    "clustering": "STD_CLUSTERING",
    "forecasting": "STD_FORECAST",
    "causal": "STD_CAUSAL_PREDICTION",
}


@app.command("add-endpoint")
def add_endpoint(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    endpoint_id: str = typer.Option(..., "--endpoint", "-e", help="Endpoint ID"),
    model_id: str = typer.Option(
        ..., "--model", "-m", help="Saved model ID deployed in the Flow"
    ),
    endpoint_type: str = typer.Option(
        "prediction",
        "--type",
        "-t",
        help="Endpoint type: prediction, clustering, forecasting, causal",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a typed endpoint to an API service.

    Supported types: prediction, clustering, forecasting, causal.
    The model must be a saved model deployed in the project Flow.

    Example:
      dku api-service add-endpoint myservice -e predict_churn -m model1 -P PROJ
      dku api-service add-endpoint myservice -e forecast -m ts_model -t forecasting -P PROJ
    """
    project_key = resolve_project(project)
    ep_type_lower = endpoint_type.lower()
    if ep_type_lower not in _ENDPOINT_TYPES:
        exit_with_error(
            f"Unknown endpoint type: '{endpoint_type}'",
            details=[
                f"Supported types: {', '.join(_ENDPOINT_TYPES.keys())}",
                "Example: dku api-service add-endpoint SVC -e ep1 -m model1 -t prediction -P PROJ",
            ],
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        service = proj.get_api_service(service_id)
        with locked_settings(
            client, project_key, "api-service", service_id, service.get_settings
        ) as settings:
            if ep_type_lower == "prediction":
                settings.add_prediction_endpoint(endpoint_id, model_id)
            elif ep_type_lower == "clustering":
                settings.add_clustering_endpoint(endpoint_id, model_id)
            elif ep_type_lower == "forecasting":
                settings.add_forecasting_endpoint(endpoint_id, model_id)
            elif ep_type_lower == "causal":
                settings.add_causal_prediction_endpoint(endpoint_id, model_id)

        success(
            f"Added {endpoint_type} endpoint '{endpoint_id}' "
            f"(model: {model_id}) to API service '{service_id}'"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-endpoints")
def list_endpoints(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List endpoints of an API service.

    Example:
      dku api-service list-endpoints myservice -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        service = proj.get_api_service(service_id)
        settings = service.get_settings()
        endpoints = settings.endpoints

        if fmt == "json":
            render_raw(endpoints, output_format="json")
        else:
            if not endpoints:
                info(
                    f"No endpoints in API service '{service_id}'. "
                    f"Add one: dku api-service add-endpoint {service_id} "
                    f"-e my_endpoint -m MODEL_ID -P {project_key}"
                )
                return

            data = []
            for ep in endpoints:
                data.append(
                    {
                        "id": ep.get("id", ""),
                        "type": ep.get("type", ""),
                        "model": ep.get("modelRef", ""),
                    }
                )
            render(
                data,
                ["id", "type", "model"],
                output_format=fmt,
                title=f"Endpoints ({service_id})",
                headers={"id": "ID", "type": "TYPE", "model": "MODEL"},
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("publish-package")
def publish_package(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    package_id: str = typer.Option(..., "--package", help="Package ID to publish"),
    published_service_id: str | None = typer.Option(
        None,
        "--published-service",
        help="Published service ID on API Deployer (default: same as service ID)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Publish a package to the API Deployer.

    Creates or updates the published service on the API Deployer.

    Example:
      dku api-service publish-package myservice --package v1 -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        service = proj.get_api_service(service_id)
        service.publish_package(package_id, published_service_id=published_service_id)
        target = published_service_id or service_id
        success(
            f"Published package '{package_id}' from '{service_id}' "
            f"to API Deployer (service: {target})"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("delete-package")
def delete_package(
    ctx: typer.Context,
    service_id: str = typer.Argument(help="API service ID"),
    package_id: str = typer.Option(..., "--package", help="Package ID to delete"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a package from an API service.

    Example:
      dku api-service delete-package myservice --package v1 -P PROJ --yes
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="api_service.delete_package",
        subject=f"package '{package_id}' from API service '{service_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete package '{package_id}' from API service '{service_id}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        service = proj.get_api_service(service_id)
        service.delete_package(package_id)
        success(f"Deleted package '{package_id}' from API service '{service_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

"""dku model-comparison — list, create, get, add-model, remove-model, delete."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import (
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage DSS model comparisons.")


@app.command("list")
def list_comparisons(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List model comparisons in a project."""
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        comparisons = proj.list_model_comparisons()

        data = []
        for c in comparisons:
            settings = c.get_settings()
            raw = settings.get_raw()
            data.append(
                {
                    "id": c.comparison_id,
                    "name": raw.get("displayName", ""),
                    "type": raw.get("modelTaskType", raw.get("predictionType", "")),
                }
            )

        if fmt == "json":
            render_raw(data, output_format="json")
        else:
            if not data:
                info(f"No model comparisons in {project_key}.")
                return
            render(
                data,
                ["id", "name", "type"],
                output_format=fmt,
                title=f"Model Comparisons ({project_key})",
                headers={"id": "ID", "name": "NAME", "type": "TYPE"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Name for the comparison"),
    prediction_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="BINARY_CLASSIFICATION, REGRESSION, MULTICLASS, TIMESERIES_FORECAST, CAUSAL_BINARY_CLASSIFICATION, CAUSAL_REGRESSION",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new model comparison.

    Example:
      dku model-comparison create "Churn Models" -t BINARY_CLASSIFICATION -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mc = proj.create_model_comparison(name, prediction_type)

        if fmt == "json":
            render_raw(
                {"id": mc.id, "name": name, "project": project_key},
                output_format="json",
            )
        else:
            success(f"Created model comparison '{name}' (ID: {mc.id}) in {project_key}")
            hint(f"dku model-comparison get {mc.id} -P {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    comparison_id: str = typer.Argument(help="Comparison ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get model comparison settings."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mc = proj.get_model_comparison(comparison_id)
        settings = mc.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("add-model")
def add_model(
    ctx: typer.Context,
    comparison_id: str = typer.Argument(help="Comparison ID"),
    full_id: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Full model ID (saved model version, lab model, or model evaluation)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a model to a comparison.

    Example:
      dku model-comparison add-model MEC_ID --model S-PROJ-modelId-v1 -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mc = proj.get_model_comparison(comparison_id)
        settings = mc.get_settings()
        settings.add_compared_item(full_id)
        settings.save()
        success(f"Added model '{full_id}' to comparison '{comparison_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-model")
def remove_model(
    ctx: typer.Context,
    comparison_id: str = typer.Argument(help="Comparison ID"),
    full_id: str = typer.Option(..., "--model", "-m", help="Full model ID to remove"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a model from a comparison.

    Example:
      dku model-comparison remove-model MEC_ID --model S-PROJ-modelId-v1 -P PROJ --yes
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="model_comparison.remove_model",
        subject=f"model '{full_id}' from comparison '{comparison_id}' in {project_key}",
        yes=yes,
        prompt=f"Remove model '{full_id}' from comparison '{comparison_id}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mc = proj.get_model_comparison(comparison_id)
        settings = mc.get_settings()
        settings.remove_compared_item(full_id)
        settings.save()
        success(f"Removed model '{full_id}' from comparison '{comparison_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    comparison_id: str = typer.Argument(help="Comparison ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a model comparison."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="model_comparison.delete",
        subject=f"model comparison '{comparison_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete model comparison '{comparison_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mc = proj.get_model_comparison(comparison_id)
        mc.delete()
        success(f"Deleted model comparison '{comparison_id}' from {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

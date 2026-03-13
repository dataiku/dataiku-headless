"""dku model — list, get, versions."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, resolve_output_format

app = typer.Typer(help="Manage DSS saved models.")


@app.command("list")
def list_models(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List saved models in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        models = proj.list_saved_models()

        data = []
        for m in models:
            data.append({
                "id": m.get("id", ""),
                "name": m.get("name", ""),
                "type": m.get("type", ""),
            })

        render(
            data,
            ["id", "name", "type"],
            output_format=output,
            title=f"Saved Models ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show saved model details."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        settings = model.get_settings()
        raw = settings.get_raw()
        active = model.get_active_version()

        if output == "json":
            detail = {
                "id": model_id,
                "name": raw.get("name", ""),
                "type": raw.get("type", ""),
                "active_version": active.get("id", "") if active else None,
            }
            print(json.dumps(detail, indent=2, default=str))
        else:
            data = [
                {"field": "ID", "value": model_id},
                {"field": "Name", "value": raw.get("name", "")},
                {"field": "Type", "value": raw.get("type", "")},
                {"field": "Active version", "value": active.get("id", "") if active else "(none)"},
            ]
            render(data, ["field", "value"], output_format=output, title=f"Model: {model_id}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def versions(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List versions of a saved model."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        vers = model.list_versions()

        data = []
        for v in vers:
            data.append({
                "id": v.get("id", ""),
                "active": str(v.get("active", False)),
                "algorithm": v.get("snippet", {}).get("algorithm", ""),
            })

        render(
            data,
            ["id", "active", "algorithm"],
            output_format=output,
            title=f"Model Versions: {model_id}",
        )
    except Exception as e:
        handle_api_error(e)

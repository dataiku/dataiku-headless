"""dku model — list, get, versions, set-active-version, metrics, delete-version, delete, usages, set-metadata."""

from __future__ import annotations

import json
from typing import List

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_not_found_error
from dku_cli.helpers import (
    get_client_from_ctx,
    resolve_project,
    update_taggable_metadata,
)
from dku_cli.output import error, render, render_raw, resolve_output_format, success

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
            data.append(
                {
                    "id": m.get("id", ""),
                    "name": m.get("name", ""),
                    "type": m.get("type", ""),
                }
            )

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
                {
                    "field": "Active version",
                    "value": active.get("id", "") if active else "(none)",
                },
            ]
            render(
                data,
                ["field", "value"],
                output_format=output,
                title=f"Model: {model_id}",
            )
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
            data.append(
                {
                    "id": v.get("id", ""),
                    "active": str(v.get("active", False)),
                    "algorithm": v.get("snippet", {}).get("algorithm", ""),
                }
            )

        render(
            data,
            ["id", "active", "algorithm"],
            output_format=output,
            title=f"Model Versions: {model_id}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("set-active-version")
def set_active_version(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    version_id: str = typer.Argument(help="Version ID to activate"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the active version of a saved model.

    After activation, downstream prediction recipes and API endpoints use this version.
    Use 'dku model versions MODEL_ID' to see available version IDs.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        model.set_active_version(version_id)
        success(f"Activated version {version_id} on model {model_id}")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                "Version or model not found.",
                details=[
                    f"List available versions: dku model versions {model_id} -P {project_key}",
                ],
                code="not_found",
                status=3,
            )
        handle_api_error(e)


@app.command()
def metrics(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    version_id: str = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show performance metrics for a model version.

    Defaults to the active version. Use --version to inspect a specific one.
    Returns metrics like AUC, accuracy, precision, recall, F1, RMSE, MAE
    depending on model type.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)

        if version_id is None:
            active = model.get_active_version()
            if active is None:
                exit_with_error(
                    "No active version on this model.",
                    details=[
                        f"List versions: dku model versions {model_id} -P {project_key}",
                        f"Activate one: dku model set-active-version {model_id} VERSION_ID -P {project_key}",
                    ],
                    code="no_active_version",
                )
            version_id = active["id"]

        details = model.get_version_details(version_id)
        perf = details.get_performance_metrics()

        if output == "json":
            print(json.dumps(perf, indent=2, default=str))
        else:
            data = [
                {"metric": k, "value": v}
                for k, v in perf.items()
                if not isinstance(v, (dict, list))
            ]
            render(
                data,
                ["metric", "value"],
                output_format=output,
                title=f"Metrics: {model_id} (version {version_id})",
            )
    except SystemExit:
        raise
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                "Model or version not found.",
                details=[
                    f"List versions: dku model versions {model_id} -P {project_key}",
                ],
                code="not_found",
                status=3,
            )
        handle_api_error(e)


@app.command("delete-version")
def delete_version(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    version: List[str] = typer.Option(
        ..., "--version", "-v", help="Version ID(s) to delete (repeatable)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete one or more versions from a saved model.

    Pass --version multiple times to delete several at once.
    Use 'dku model versions MODEL_ID' to see available version IDs.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        model.delete_versions(list(version))
        success(f"Deleted {len(version)} version(s) from model {model_id}")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                "Model or version not found.",
                details=[
                    f"List versions: dku model versions {model_id} -P {project_key}",
                ],
                code="not_found",
                status=3,
            )
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a saved model.

    Use 'dku model list' to see available model IDs.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = proj.get_saved_model(model_id)
        sm.delete()
        success(f"Deleted saved model '{model_id}'")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Model '{model_id}' not found.",
                details=[
                    f"List models: dku model list -P {project_key}",
                ],
                code="not_found",
                status=3,
            )
        handle_api_error(e)


@app.command()
def usages(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show where a saved model is used (recipes, endpoints, etc.)."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = proj.get_saved_model(model_id)
        usage_list = sm.get_usages()
        render_raw(usage_list, output_format=output)
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Model '{model_id}' not found.",
                details=[
                    f"List models: dku model list -P {project_key}",
                ],
                code="not_found",
                status=3,
            )
        handle_api_error(e)


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Model description"
    ),
    short_desc: str | None = typer.Option(
        None, "--short-desc", help="Short description"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update saved model description, short description, and/or tags.

    No JSON needed — updates metadata fields directly.
    """
    if description is None and short_desc is None and tags is None:
        error("Provide --description, --short-desc, and/or --tags to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        settings = model.get_settings()
        update_taggable_metadata(settings, description, short_desc, tags)
        success(f"Updated metadata for model '{model_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

"""dku evaluation-store — manage model evaluation stores."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS model evaluation stores.")


@app.command("list")
def list_stores(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List model evaluation stores in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        stores = proj.list_model_evaluation_stores()

        # stores are objects with .id property, not dicts
        data = [{"id": s.id} for s in stores]

        render(
            data,
            ["id"],
            output_format=output,
            title=f"Evaluation Stores ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Name for the evaluation store"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if a store with this name already exists"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new model evaluation store."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.create_model_evaluation_store(name)
        result = {"id": store.id}
        render_raw(result, output)
        success(f"Created evaluation store {store.id}")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            success(f"Evaluation store '{name}' already exists, skipping.")
            return
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show evaluation store settings."""
    project_key = resolve_project(project)
    resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        raw = store.get_settings().get_raw()
        print(json.dumps(raw, indent=2, default=str))
    except Exception as e:
        handle_api_error(e)


@app.command()
def evaluations(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List evaluations in a model evaluation store."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        evals = store.list_model_evaluations()

        # DSSModelEvaluation objects have .evaluation_id
        data = [{"evaluation_id": e.evaluation_id} for e in evals]

        render(
            data,
            ["evaluation_id"],
            output_format=output,
            title=f"Evaluations ({store_id})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def latest(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the latest evaluation in a store."""
    project_key = resolve_project(project)
    resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        ev = store.get_latest_model_evaluation()

        if ev is None:
            exit_with_error(
                "No evaluations in this store.",
                details=[
                    f"Build the store first: dku evaluation-store build {store_id} -P {project_key}",
                ],
            )

        result = {"evaluation_id": ev.evaluation_id}
        full_info = ev.get_full_info()
        if hasattr(full_info, "get_raw"):
            result["info"] = full_info.get_raw()
        render_raw(result, "json")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def build(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for build to complete"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Build a model evaluation store.

    Runs the evaluation pipeline and waits for completion by default.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        job = store.build(wait=wait)
        if wait:
            success(f"Build complete for evaluation store {store_id} (job: {job.id})")
        else:
            success(
                f"Build started. Check progress: dku job status {job.id} -P {project_key}"
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a model evaluation store."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        store.delete()
        success(f"Deleted evaluation store {store_id}")
    except Exception as e:
        handle_api_error(e)

"""dku analysis — manage visual analyses."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS visual analyses (lab).")


@app.command("list")
def list_analyses(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List visual analyses in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        analyses = proj.list_analyses()

        data = []
        for a in analyses:
            data.append({
                "analysis_id": a.get("analysisId", ""),
                "dataset": a.get("inputDataset", ""),
            })

        render(
            data,
            ["analysis_id", "dataset"],
            output_format=output,
            title=f"Analyses ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    dataset: str = typer.Argument(help="Input dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new visual analysis for a dataset."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        analysis = proj.create_analysis(dataset)
        result = {"analysis_id": analysis.analysis_id}
        render_raw(result, output)
        success(f"Created analysis {analysis.analysis_id}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show visual analysis definition."""
    project_key = resolve_project(project)
    resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        analysis = proj.get_analysis(analysis_id)
        definition = analysis.get_definition().get_raw()
        print(json.dumps(definition, indent=2, default=str))
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a visual analysis."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        analysis = proj.get_analysis(analysis_id)
        analysis.delete()
        success(f"Deleted analysis {analysis_id}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def tasks(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List ML tasks in a visual analysis."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        analysis = proj.get_analysis(analysis_id)
        ml_tasks = analysis.list_ml_tasks()

        data = []
        for t in ml_tasks:
            data.append({
                "mltask_id": t.get("mlTaskId", ""),
                "type": t.get("taskType", ""),
            })

        render(
            data,
            ["mltask_id", "type"],
            output_format=output,
            title=f"ML Tasks in {analysis_id}",
        )
    except Exception as e:
        handle_api_error(e)

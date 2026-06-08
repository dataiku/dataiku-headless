"""dku analysis — manage visual analyses."""

from __future__ import annotations

import typer

from dku_cli.commands._options import OutputOption, ProjectOption, YesOption
from dku_cli.errors import handle_errors
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success
from dku_cli.safety import Tier, guard

app = typer.Typer(help="Manage DSS visual analyses (lab).")


@app.command("list")
@handle_errors
def list_analyses(
    ctx: typer.Context,
    project: ProjectOption = None,
    output: OutputOption = None,
) -> None:
    """List visual analyses in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    analyses = proj.list_analyses()

    data = []
    for a in analyses:
        data.append(
            {
                "analysis_id": a.get("analysisId", ""),
                "dataset": a.get("inputDataset", ""),
            }
        )

    render(
        data,
        ["analysis_id", "dataset"],
        output_format=output,
        title=f"Analyses ({project_key})",
    )


@app.command()
@handle_errors
def create(
    ctx: typer.Context,
    dataset: str = typer.Argument(help="Input dataset name"),
    project: ProjectOption = None,
    output: OutputOption = None,
) -> None:
    """Create a new visual analysis for a dataset."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    analysis = proj.create_analysis(dataset)
    result = {"analysis_id": analysis.analysis_id}
    render_raw(result, output)
    success(f"Created analysis {analysis.analysis_id}")


@app.command()
@handle_errors
def get(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    project: ProjectOption = None,
    output: OutputOption = None,
) -> None:
    """Show visual analysis definition."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    analysis = proj.get_analysis(analysis_id)
    definition = analysis.get_definition().get_raw()
    render_raw(definition, output_format=output)


@app.command()
@handle_errors
def delete(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    project: ProjectOption = None,
    yes: YesOption = False,
) -> None:
    """Delete a visual analysis."""
    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="analysis.delete",
        subject=f"analysis '{analysis_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete analysis '{analysis_id}' from {project_key}?",
    )
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    analysis = proj.get_analysis(analysis_id)
    analysis.delete()
    success(f"Deleted analysis {analysis_id}")


@app.command()
@handle_errors
def tasks(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    project: ProjectOption = None,
    output: OutputOption = None,
) -> None:
    """List ML tasks in a visual analysis."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    analysis = proj.get_analysis(analysis_id)
    ml_tasks = analysis.list_ml_tasks()

    data = []
    for t in ml_tasks:
        data.append(
            {
                "mltask_id": t.get("mlTaskId", ""),
                "type": t.get("taskType", ""),
            }
        )

    render(
        data,
        ["mltask_id", "type"],
        output_format=output,
        title=f"ML Tasks in {analysis_id}",
    )

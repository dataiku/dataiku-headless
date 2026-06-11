"""dku analysis — manage visual analyses."""

from __future__ import annotations

import typer

from dku_cli.commands._options import ProjectOption, YesOption
from dku_cli.errors import exit_with_error, handle_errors
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import (
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)
from dku_cli.safety import Tier, guard

app = typer.Typer(help="Manage DSS visual analyses (lab).")


@app.command("list")
@handle_errors
def list_analyses(
    ctx: typer.Context,
    project: ProjectOption = None,
) -> None:
    """List visual analyses in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
) -> None:
    """Create a new visual analysis for a dataset."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
) -> None:
    """Show visual analysis definition."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
) -> None:
    """List ML tasks in a visual analysis.

    Prefer `dku ml status / models <ANALYSIS> <MLTASK>` for richer output
    once you know the mltask_id.
    """

    project_key = resolve_project(project)
    output = resolve_output_format()
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    analysis = proj.get_analysis(analysis_id)
    ml_tasks = analysis.list_ml_tasks()

    # `list_ml_tasks()` is documented to return a list of dicts, but on
    # some DSS versions / for some analysis shapes it returns a dict
    # whose `mlTasks` key holds the list — and items are occasionally
    # plain strings (mltask IDs, no metadata). Be defensive: handle
    # dict-wrapped lists, plain ID strings, and missing fields without
    # crashing with `'str' object has no attribute 'get'`.
    if isinstance(ml_tasks, dict):
        ml_tasks = ml_tasks.get("mlTasks") or ml_tasks.get("mltasks") or []
    if not isinstance(ml_tasks, list):
        exit_with_error(
            f"Unexpected list_ml_tasks() shape for analysis '{analysis_id}': "
            f"got {type(ml_tasks).__name__}.",
            details=[
                "Workaround: call dku ml status / models with the mltask_id directly.",
                f"  dku ml status <ANALYSIS> <MLTASK> -P {project_key}",
                f"  dku ml models <ANALYSIS> <MLTASK> -P {project_key}",
            ],
        )

    data = []
    for t in ml_tasks:
        if isinstance(t, dict):
            data.append(
                {
                    "mltask_id": t.get("mlTaskId", t.get("id", "")),
                    "type": t.get("taskType", t.get("type", "")),
                }
            )
        elif isinstance(t, str):
            # Bare ID string — preserve it under mltask_id so the row
            # is still useful even though we don't know the type.
            data.append({"mltask_id": t, "type": ""})
        else:
            warn(
                f"Skipping mltask entry of type {type(t).__name__} "
                "(neither dict nor string)."
            )

    if not data:
        info(
            f"No ML tasks in analysis '{analysis_id}'. "
            f"Create one with: dku ml create-prediction <DATASET> <TARGET> -P {project_key}"
        )

    render(
        data,
        ["mltask_id", "type"],
        output_format=output,
        title=f"ML Tasks in {analysis_id}",
    )

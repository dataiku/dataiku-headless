"""dku insight — list, get, create, delete, validate, get/set-definition."""

from __future__ import annotations

import difflib

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS insights (charts, reports, metrics views).")


@app.command("list")
def list_insights(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List insights in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insights = proj.list_insights()

        data = []
        for i in insights:
            data.append(
                {
                    "id": i.get("id", ""),
                    "name": i.get("name", ""),
                    "type": i.get("type", ""),
                }
            )

        render(
            data,
            ["id", "name", "type"],
            output_format=output,
            title=f"Insights ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get insight details."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        raw = insight.get_settings().get_raw()

        if output == "json":
            render_raw(raw, output_format=output)
        else:
            data = [
                {"field": "ID", "value": raw.get("id", insight_id)},
                {"field": "Name", "value": raw.get("name", "")},
                {"field": "Type", "value": raw.get("type", "")},
            ]
            render(
                data,
                ["field", "value"],
                output_format="table",
                title=f"Insight: {insight_id}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Insight name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    insight_type: str = typer.Option(
        "dataset_table",
        "--type",
        "-t",
        help="Insight type (chart, dataset_table, report, etc.)",
    ),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "--ds",
        help="Dataset to bind (sets params.datasetSmartName). Required for chart/dataset_table types.",
    ),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="JSON creation info (string, @file.json, or - for stdin)",
    ),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if insight already exists"
    ),
) -> None:
    """Create a new insight.

    Common types: chart, dataset_table, report, scenario_last_runs, metrics, eda, jupyter.
    Chart subtypes (set via set-definition): lines, multi_columns_lines, stacked_bars,
    grouped_columns, pie, scatter, boxplots, treemap, pivot_table, stacked_area.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        creation_info = read_json_input(definition) or {}
        creation_info.setdefault("type", insight_type)
        creation_info.setdefault("name", name)
        if dataset:
            creation_info.setdefault("params", {})
            creation_info["params"]["datasetSmartName"] = dataset
        insight = proj.create_insight(creation_info)
        success(f"Created insight '{name}' (id={insight.insight_id})")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(f"Insight '{name}' already exists in {project_key}, skipping create")
            return
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete an insight."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        insight.delete()
        success(f"Deleted insight '{insight_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the raw definition of an insight as JSON."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        defn = insight.get_settings().get_raw()
        render_raw(defn, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="JSON definition (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Update an insight's definition from JSON."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        new_def = read_json_input(definition)
        settings = insight.get_settings()
        raw = settings.get_raw()
        raw.clear()
        raw.update(new_def)
        settings.save()
        success(f"Updated definition for insight '{insight_id}'")
    except Exception as e:
        handle_api_error(e)


def _extract_chart_columns(chart_def: dict) -> list[str]:
    """Extract all column references from a chart definition."""
    columns = []
    for key in ("genericDimension0", "genericDimension1", "genericMeasures"):
        for item in chart_def.get(key, []):
            col = item.get("column")
            if col:
                columns.append(col)
    return columns


@app.command()
def validate(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID to validate"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Validate a chart insight's column references against its dataset schema.

    Checks that all column names in genericDimension0, genericDimension1,
    and genericMeasures exist in the bound dataset. Reports mismatches
    with fuzzy-match suggestions.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        raw = insight.get_settings().get_raw()

        insight_type = raw.get("type", "")
        if insight_type != "chart":
            exit_with_error(
                f"Validation only applies to chart insights (this is '{insight_type}')",
                details=[
                    f"dku insight get {insight_id} -P {project_key}  # check insight type",
                ],
            )

        params = raw.get("params", {})
        ds_name = params.get("datasetSmartName")
        if not ds_name:
            exit_with_error(
                f"Insight '{insight_id}' has no dataset binding (params.datasetSmartName is missing)",
                details=[
                    "Set it with: dku insight set-definition "
                    f'{insight_id} -d \'{{"params":{{"datasetSmartName":"DATASET_NAME"}}}}\' -P {project_key}',
                ],
            )

        chart_def = params.get("def", {})
        chart_columns = _extract_chart_columns(chart_def)
        if not chart_columns:
            warn(f"No column references found in chart definition for '{insight_id}'")
            return

        ds_def = proj.get_dataset(ds_name).get_definition()
        schema_columns = {
            c["name"] for c in ds_def.get("schema", {}).get("columns", [])
        }

        invalid = []
        for col in chart_columns:
            if col not in schema_columns:
                matches = difflib.get_close_matches(
                    col, schema_columns, n=3, cutoff=0.6
                )
                suggestion = f" Did you mean: {', '.join(matches)}?" if matches else ""
                invalid.append(
                    f"  Column '{col}' not found in dataset '{ds_name}'.{suggestion}"
                )

        if invalid:
            available = ", ".join(sorted(schema_columns))
            error(f"Found {len(invalid)} invalid column reference(s):")
            for line in invalid:
                info(line)
            info(f"  Available columns: {available}")
            info(
                f"  Fix: dku insight set-definition {insight_id} -d @fixed.json -P {project_key}"
            )
            raise SystemExit(1)
        else:
            success(
                f"All {len(chart_columns)} column reference(s) valid against dataset '{ds_name}'"
            )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)

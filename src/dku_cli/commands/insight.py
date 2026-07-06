"""dku insight — list, get, create, delete, validate, get/set-definition, set-metadata."""

from __future__ import annotations

import typer

from dku_cli.charts import chart_column_type, columns_referenced, lint_chart_def
from dku_cli.enums import ChartType, DimensionDateMode, MeasureAgg, MeasureDisplayAs
from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import (
    get_client_from_ctx,
    insight_url,
    read_json_input,
    resolve_project,
    update_taggable_metadata,
)
from dku_cli.output import (
    error,
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS insights (charts, reports, metrics views).")

# Default sampling block for chart insights. DSS 14.6 renders charts through
# spec.sampleSettings and NPEs ("Cannot read field 'selection' because
# 'spec.sampleSettings' is null", HTTP 500) when a chart insight is created
# without params.refreshableSelection — the UI always writes it, the public
# API does not. Canonical shape: dataiku skill references/dashboard-charts.md.
_DEFAULT_REFRESHABLE_SELECTION = {
    "selection": {
        "useMemTable": False,
        "filter": {"distinct": False, "enabled": False},
        "partitionSelectionMethod": "ALL",
        "latestPartitionsN": 1,
        "ordering": {"enabled": False, "rules": []},
        "samplingMethod": "FULL",
        "maxRecords": 10000,
        "targetRatio": 0.02,
        "ascending": True,
        "withinFirstN": -1,
        "maxReadUncompressedBytes": -1,
    },
    "autoRefreshSample": False,
    "_refreshTrigger": 0,
}

# Chart types whose data does NOT live in genericDimension0/genericMeasures, so
# the add-dimension/add-measure helpers can't fully configure them — they render
# blank until type-specific fields are set via set-definition. set-chart-type
# warns when one of these is selected.
_HELPER_INCOMPLETE_TYPES = {"scatter", "boxplots", "treemap"}


def _chart_column_type(proj, raw: dict, column: str, project_key: str) -> str | None:
    """Resolve a chart column's type (NUMERICAL/ALPHANUM/DATE) from the bound
    dataset's schema. Errors prescriptively when the column does not exist —
    chart column names are NOT validated server-side; a typo saves fine and
    renders a blank chart. Returns None when the schema cannot be read."""
    ds_name = (raw.get("params") or {}).get("datasetSmartName") or ""
    if not ds_name:
        return None
    try:
        schema = proj.get_dataset(ds_name).get_schema()
        columns = schema.get("columns", []) if isinstance(schema, dict) else schema
        by_name = {c.get("name"): c.get("type", "") for c in columns}
    except Exception:
        return None  # foreign/unreadable dataset — stay permissive
    if column not in by_name:
        exit_with_error(
            f"Column '{column}' does not exist in dataset '{ds_name}'.",
            details=[
                "Chart column names are not validated server-side — a wrong "
                "name saves but renders a blank chart.",
                f"Available columns: {', '.join(sorted(by_name))}",
                f"Inspect with: dku dataset schema {ds_name} -P {project_key}",
            ],
        )
    return chart_column_type(by_name[column])


@app.command("list")
def list_insights(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    dataset: str | None = typer.Option(
        None, "--dataset", "--ds", help="Filter by bound dataset name"
    ),
    insight_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by insight type (chart, dataset_table, report, etc.)",
    ),
) -> None:
    """List insights in a project.

    Use --dataset and --type to narrow results when building dashboards:
      dku insight list --dataset Branch_Orders --type chart -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insights = proj.list_insights()

        data = []
        for i in insights:
            if insight_type and i.get("type", "") != insight_type:
                continue
            if dataset:
                # dataset filter requires fetching each insight's params — only apply if flag set
                try:
                    raw = proj.get_insight(i.get("id", "")).get_settings().get_raw()
                    ds_name = raw.get("params", {}).get("datasetSmartName", "")
                    if ds_name != dataset:
                        continue
                except Exception:
                    continue
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
) -> None:
    """Get insight details."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        creation_info = read_json_input(definition) or {}
        creation_info.setdefault("type", insight_type)
        creation_info.setdefault("name", name)
        if dataset:
            creation_info.setdefault("params", {})
            creation_info["params"]["datasetSmartName"] = dataset
        if creation_info.get("type") == "chart":
            # Without a sampling block, DSS 14.6 chart rendering NPEs with
            # HTTP 500 ("spec.sampleSettings is null"). The UI always writes
            # it; inject the canonical default unless the caller provided one.
            creation_info.setdefault("params", {}).setdefault(
                "refreshableSelection", _DEFAULT_REFRESHABLE_SELECTION
            )
        insight = proj.create_insight(creation_info)
        url = insight_url(client, project_key, insight.insight_id)
        if output == "json":
            render_raw(
                {
                    "id": insight.insight_id,
                    "name": creation_info.get("name", name),
                    "type": creation_info.get("type", insight_type),
                    "url": url,
                },
                output_format=output,
            )
        else:
            success(f"Created insight '{name}' (id={insight.insight_id})")
            hint(f"URL (cite this exact form; the '_' after the id matters): {url}")
            hint(f"dku insight get {insight.insight_id} -P {project_key}")
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete an insight."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="insight.delete",
        subject=f"insight '{insight_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete insight '{insight_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        insight.delete()
        success(f"Deleted insight '{insight_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get the raw definition of an insight as JSON."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        if isinstance(new_def, dict) and new_def.get("type") == "chart":
            params = new_def.setdefault("params", {})
            if not (params.get("refreshableSelection") or {}).get("selection"):
                params["refreshableSelection"] = _DEFAULT_REFRESHABLE_SELECTION
                warn(
                    "Injected default sampling block (params.refreshableSelection) "
                    "— chart insights without one fail to render in dashboards "
                    '(HTTP 500, "spec.sampleSettings is null")'
                )
        settings = insight.get_settings()
        raw = settings.get_raw()
        prior = dict(raw)
        raw.clear()
        raw.update(new_def)
        raw["id"] = insight_id
        raw.setdefault("projectKey", project_key)
        for field in ("name", "owner"):
            if field not in raw and field in prior:
                raw[field] = prior[field]
        settings.save()
        success(f"Updated definition for insight '{insight_id}'")
    except Exception as e:
        handle_api_error(e)


def _require_sampling_block(params: dict, insight_id: str, project_key: str) -> None:
    """Fail validation when a chart has no params.refreshableSelection.selection."""
    if (params.get("refreshableSelection") or {}).get("selection"):
        return
    exit_with_error(
        f"Chart insight '{insight_id}' has no sampling block "
        "(params.refreshableSelection) — dashboards fail to render it "
        '(HTTP 500, NullPointerException: "spec.sampleSettings is null")',
        details=[
            f"dku insight get {insight_id} -P {project_key} -o json "
            "> def.json  # export current definition",
            f"dku insight set-definition {insight_id} -d @def.json "
            f"-P {project_key}  # re-save auto-injects the sampling block",
        ],
    )


@app.command()
def validate(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID to validate"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Pre-flight a chart insight before a human loads it.

    Charts fail at RENDER time, not save time: an empty required slot throws
    ArrayIndexOutOfBoundsException, a wrong column name renders blank, a geo
    chart with no GeoPoint-meaning column builds empty ("dataset is empty"),
    and some type strings (bubble, waterfall) are silently nulled on save.
    This checks every binding slot and per-type requirement against the bound
    dataset schema so those failures surface here, not in the browser.
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

        _require_sampling_block(params, insight_id, project_key)

        chart_def = params.get("def", {}) or {}
        try:
            ds_def = proj.get_dataset(ds_name).get_definition()
            columns_by_name = {
                c["name"]: {"type": c.get("type"), "meaning": c.get("meaning")}
                for c in ds_def.get("schema", {}).get("columns", [])
            }
        except Exception:
            columns_by_name = {}  # foreign/unreadable dataset — skip column checks

        issues = lint_chart_def(chart_def, columns_by_name)
        for i in (x for x in issues if x["level"] == "warn"):
            warn(i["msg"])
            info(f"  fix: {i['fix']}")
        errors = [i for i in issues if i["level"] == "error"]
        if errors:
            ctype = chart_def.get("type")
            error(
                f"{len(errors)} blocking issue(s) — chart '{ctype}' will not render cleanly:"
            )
            for i in errors:
                info(f"  - {i['msg']}")
                info(f"    fix: {i['fix']}")
            info(
                f"  After fixing: dku insight set-definition {insight_id} -d @fixed.json -P {project_key}"
            )
            raise SystemExit(1)

        ncols = len(columns_referenced(chart_def))
        msg = (
            f"chart '{chart_def.get('type')}' passes pre-flight: "
            f"required slots present, {ncols} column ref(s) valid against '{ds_name}'"
        )
        if not columns_by_name:
            msg += " (dataset schema unreadable — column checks skipped)"
        success(msg)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Insight description"
    ),
    short_desc: str | None = typer.Option(
        None, "--short-desc", help="Short description"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update insight description, short description, and/or tags.

    No JSON needed — updates metadata fields directly.
    """
    if description is None and short_desc is None and tags is None:
        error("Provide --description, --short-desc, and/or --tags to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        settings = insight.get_settings()
        update_taggable_metadata(settings, description, short_desc, tags)
        success(f"Updated metadata for insight '{insight_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def head(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    rows: int = typer.Option(10, "-n", "--rows", help="Number of rows"),
) -> None:
    """Preview rows from the dataset bound to an insight.

    Resolves the insight's dataset and proxies to dataset head — no need to
    look up the dataset name separately:
      dku insight head INSIGHT_ID -P PROJ -n 5
    """
    from dku_cli.errors import exit_with_error

    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        raw = proj.get_insight(insight_id).get_settings().get_raw()
        ds_name = raw.get("params", {}).get("datasetSmartName")
        if not ds_name:
            exit_with_error(
                f"Insight '{insight_id}' has no dataset binding (params.datasetSmartName missing)",
                details=[
                    f"dku insight get {insight_id} -P {project_key}  # check insight type/params"
                ],
            )
        ds = proj.get_dataset(ds_name)
        ds_def = ds.get_definition()
        columns = [
            c.get("name", f"col_{i}")
            for i, c in enumerate(ds_def.get("schema", {}).get("columns", []))
        ]
        data = []
        for i, row in enumerate(ds.iter_rows()):
            if i >= rows:
                break
            data.append(dict(zip(columns, row, strict=False)))
        if not data:
            from dku_cli.output import warn

            warn(f"Dataset '{ds_name}' has 0 rows")
            return
        render(
            data,
            columns,
            output_format=output,
            title=f"Insight {insight_id} → {ds_name} (first {len(data)} rows)",
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-chart-type")
def set_chart_type(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    chart_type: ChartType = typer.Argument(
        case_sensitive=False,
        help=(
            "Chart type: lines, multi_columns_lines, stacked_bars, "
            "grouped_columns, pie, scatter, boxplots, treemap, "
            "pivot_table, stacked_area"
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the chart type of a chart insight.

    dku insight set-chart-type INSIGHT_ID grouped_columns -P PROJ
    """
    from dku_cli.errors import exit_with_error

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        settings = insight.get_settings()
        raw = settings.get_raw()
        if raw.get("type") != "chart":
            exit_with_error(
                f"Insight '{insight_id}' is type '{raw.get('type')}', not 'chart'"
            )
        raw.setdefault("params", {}).setdefault("def", {})["type"] = chart_type
        settings.save()
        success(f"Chart type set to '{chart_type}' for insight '{insight_id}'")
        if chart_type in _HELPER_INCOMPLETE_TYPES:
            warn(
                f"'{chart_type}' needs chart-specific fields that add-dimension/"
                "add-measure do NOT set (scatter→uaXDimension/uaYDimension, "
                "boxplots→boxplotValue/boxplotBreakdownDim, "
                "treemap→yDimension+genericMeasures). It will render blank until "
                "you configure those via 'dku insight set-definition' — see "
                "references/dashboards.md."
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-dimension")
def add_dimension(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    column: str = typer.Option(
        ..., "--column", "-c", help="Column name to add as dimension"
    ),
    slot: int = typer.Option(
        0, "--slot", help="Dimension slot: 0 (X axis / first) or 1 (second)"
    ),
    breakdown: bool = typer.Option(
        False,
        "--breakdown",
        "-b",
        help="Add as the color/series breakdown (genericDimension1) instead of the "
        "X axis — for stacked / colored charts and pivot columns (same as --slot 1).",
    ),
    date_mode: DimensionDateMode = typer.Option(
        None,
        "--date-mode",
        case_sensitive=False,
        help="Bin a DATE column by YEAR|QUARTER|MONTH|WEEK|DAY|HOUR (sets dateParams). "
        "Needed for a real time axis — a raw date dim plots every distinct value.",
    ),
) -> None:
    """Add a dimension column to a chart insight.

    Slot 0 (default) is the X axis; --breakdown (slot 1) is the color/series split.
    DATE columns are auto-typed; add --date-mode to bin the time axis:
      dku insight add-dimension INSIGHT_ID -c region -P PROJ
      dku insight add-dimension INSIGHT_ID -c status --breakdown -P PROJ
      dku insight add-dimension INSIGHT_ID -c order_date --date-mode MONTH -P PROJ
    """
    from dku_cli.errors import exit_with_error

    if breakdown:
        slot = 1
    if slot not in (0, 1):
        exit_with_error("--slot must be 0 or 1")
    mode = date_mode.value if date_mode is not None else None
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        settings = insight.get_settings()
        raw = settings.get_raw()
        if raw.get("type") != "chart":
            exit_with_error(
                f"Insight '{insight_id}' is type '{raw.get('type')}', not 'chart'"
            )
        chart_def = raw.setdefault("params", {}).setdefault("def", {})
        key = f"genericDimension{slot}"
        dims = chart_def.setdefault(key, [])
        # Full GUI shape: a bare {column, type} dim crashes the chart editor
        # (TypeError reading numParams.nbBins / sort.type) — the frontend only
        # autocompletes objects it recognizes as complete.
        dim: dict = {
            "column": column,
            "isA": "dimension",
            "maxValues": 100,
            "generateOthersCategory": False,
            "filters": [],
            "sort": {
                "type": "NATURAL",
                "sortAscending": True,
                "label": "Natural ordering",
            },
            "numParams": {
                "mode": "FIXED_NB",
                "nbBins": 10,
                "binSize": 100,
                "emptyBinsMode": "ZEROS",
            },
        }
        col_type = _chart_column_type(proj, raw, column, project_key)
        if col_type:
            dim["type"] = col_type
        # Type is auto-resolved (the bug fix: dateonly/datetime now → DATE, not
        # ALPHANUM). Binning is only applied when --date-mode is explicit, so a
        # plain date dim keeps its prior shape; hint that binning is available.
        if mode is not None:
            if col_type == "DATE":
                dim["dateParams"] = {"mode": mode, "maxBinNumberForAutomaticMode": 0}
            else:
                warn(
                    f"--date-mode ignored: '{column}' is {col_type}, not a date column."
                )
        elif col_type == "DATE":
            info(
                f"'{column}' is a date column — pass --date-mode "
                "YEAR|QUARTER|MONTH|WEEK|DAY|HOUR to bin the time axis."
            )
        dims.append(dim)
        settings.save()
        where = "breakdown (slot 1)" if slot == 1 else "X axis (slot 0)"
        suffix = (
            f", binned by {dim['dateParams']['mode']}" if "dateParams" in dim else ""
        )
        success(f"Added dimension '{column}' to {where} of '{insight_id}'{suffix}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-measure")
def add_measure(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    column: str = typer.Option(
        None,
        "--column",
        "-c",
        help="Column name to add as measure. Omit with --agg COUNT for a "
        "plain row count ('Count of records').",
    ),
    aggregation: MeasureAgg = typer.Option(
        MeasureAgg.AVG,
        "--agg",
        case_sensitive=False,
        help="Aggregation: AVG, SUM, COUNT, MIN, MAX, COUNT_DISTINCT",
    ),
    axis: int = typer.Option(
        1,
        "--axis",
        help="Y axis: 1 (left, default) or 2 (right). Use 2 for a dual-axis combo "
        "(e.g. revenue bars on axis 1 + a rate line on axis 2).",
    ),
    display_as: MeasureDisplayAs = typer.Option(
        None,
        "--as",
        case_sensitive=False,
        help="Render THIS measure as: column | line | area (default: the chart's "
        "native type). Mix with --axis 2 for combo charts.",
    ),
) -> None:
    """Add a measure column to a chart insight.

    dku insight add-measure INSIGHT_ID --column revenue --agg SUM -P PROJ
    dku insight add-measure INSIGHT_ID --agg COUNT -P PROJ  # count of records
    # dual-axis combo: bars on the left, a rate line on the right
    dku insight add-measure INSIGHT_ID -c rate --agg AVG --axis 2 --as line -P PROJ
    """
    from dku_cli.errors import exit_with_error

    dss_aggs = {"COUNT_DISTINCT": "COUNTD"}
    agg = aggregation.upper()
    if column is None and agg != "COUNT":
        exit_with_error(
            f"--agg {agg} needs a --column; only --agg COUNT works without one "
            "(plain row count)."
        )
    if axis not in (1, 2):
        exit_with_error("--axis must be 1 (left) or 2 (right)")
    display_type = display_as.value if display_as is not None else None
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        settings = insight.get_settings()
        raw = settings.get_raw()
        if raw.get("type") != "chart":
            exit_with_error(
                f"Insight '{insight_id}' is type '{raw.get('type')}', not 'chart'"
            )
        chart_def = raw.setdefault("params", {}).setdefault("def", {})
        # isA/displayed mark the object as a complete measure — without them the
        # chart editor treats it as a half-dropped palette column and either
        # asserts ("no measure type") or rewrites the function on open.
        if column is None:
            # "Count of records": no column, pseudo-type COUNT — the one
            # column-less measure shape the pivot engine accepts.
            measure: dict = {
                "function": "COUNT",
                "type": "COUNT",
                "isA": "measure",
                "displayed": True,
            }
        else:
            measure = {
                "column": column,
                "function": dss_aggs.get(agg, agg),
                "isA": "measure",
                "displayed": True,
            }
            col_type = _chart_column_type(proj, raw, column, project_key)
            if col_type:
                # Charts require the measure's `type` to match the column. An
                # omitted type is treated as NUMERICAL and string/meaning columns
                # fail at render time with "Column X was expected to be NUMERICAL
                # but is not (found STRING_DICT)".
                if agg in ("AVG", "SUM", "MIN", "MAX") and col_type != "NUMERICAL":
                    exit_with_error(
                        f"{agg}({column}) needs a numerical column, but "
                        f"'{column}' is {col_type}.",
                        details=[
                            "Use --agg COUNT (row count) or --agg COUNT_DISTINCT "
                            "for non-numeric columns,",
                            "or fix the storage type first: dku dataset set-schema "
                            f"... -P {project_key}",
                        ],
                    )
                measure["type"] = col_type
        # axis1 is the DSS default — only write displayAxis for the right axis,
        # so a plain measure keeps its minimal shape.
        if axis == 2:
            measure["displayAxis"] = "axis2"
        if display_type is not None:
            measure["displayType"] = display_type
        chart_def.setdefault("genericMeasures", []).append(measure)
        settings.save()
        extra = []
        if axis == 2:
            extra.append("right axis")
        if display_type:
            extra.append(f"as {display_type}")
        suffix = f" ({', '.join(extra)})" if extra else ""
        label = column if column is not None else "count of records"
        success(f"Added measure '{label}' ({agg}) to insight '{insight_id}'{suffix}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("clear-columns")
def clear_columns(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Clear all dimension and measure column bindings from a chart insight.

    Use before reconfiguring columns to start fresh:
      dku insight clear-columns INSIGHT_ID -P PROJ
    """
    from dku_cli.errors import exit_with_error
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="insight.clear_columns",
        subject=f"all column bindings of insight '{insight_id}' in {project_key}",
        yes=yes,
        prompt=f"Clear all column bindings from insight '{insight_id}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        settings = insight.get_settings()
        raw = settings.get_raw()
        if raw.get("type") != "chart":
            exit_with_error(
                f"Insight '{insight_id}' is type '{raw.get('type')}', not 'chart'"
            )
        chart_def = raw.setdefault("params", {}).setdefault("def", {})
        chart_def["genericDimension0"] = []
        chart_def["genericDimension1"] = []
        chart_def["genericMeasures"] = []
        settings.save()
        success(f"Cleared all column bindings for insight '{insight_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-colors")
def set_colors(
    ctx: typer.Context,
    insight_id: str = typer.Argument(help="Insight ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    single: str = typer.Option(
        None,
        "--single",
        help="One color for all series (hex, e.g. '#2678b2').",
    ),
    palette: str = typer.Option(
        None,
        "--palette",
        help="Named color palette id (e.g. 'default', 'dku_dss_next', 'pastel').",
    ),
    category: list[str] = typer.Option(
        None,
        "--category",
        help="Per-category color as VALUE=HEX (repeatable), e.g. --category EU=#2E5EAA "
        "--category US=#D1495B. Sets customColors + paletteType=CATEGORY.",
    ),
    transparency: float = typer.Option(
        None, "--transparency", help="Fill transparency, 0.0 (clear) to 1.0 (solid)."
    ),
) -> None:
    """Set a chart's colors: a single color, a named palette, or per-category map.

    Charts have no dedicated colour API, so this patches params.def.colorOptions.
    Custom category colours need a categorical breakdown (the x dimension or a
    --breakdown dimension) to map against.

      dku insight set-colors ID --single '#2678b2' -P PROJ
      dku insight set-colors ID --palette dku_dss_next -P PROJ
      dku insight set-colors ID --category EU=#2E5EAA --category US=#D1495B -P PROJ

    Note: DSS may store paletteType as CONTINUOUS even after a CATEGORY set; the
    customColors still apply when a categorical breakdown is present (verify the
    rendered chart).
    """
    from dku_cli.errors import exit_with_error

    if not any([single, palette, category, transparency is not None]):
        exit_with_error(
            "Nothing to set. Provide at least one of "
            "--single / --palette / --category / --transparency.",
        )
    custom: dict[str, str] = {}
    for pair in category or []:
        if "=" not in pair:
            exit_with_error(
                f"--category must be VALUE=HEX, got '{pair}'",
                details=["Example: --category EU=#2E5EAA"],
            )
        k, v = pair.split("=", 1)
        custom[k.strip()] = v.strip()
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        insight = proj.get_insight(insight_id)
        settings = insight.get_settings()
        raw = settings.get_raw()
        if raw.get("type") != "chart":
            exit_with_error(
                f"Insight '{insight_id}' is type '{raw.get('type')}', not 'chart'"
            )
        chart_def = raw.setdefault("params", {}).setdefault("def", {})
        co = chart_def.setdefault("colorOptions", {})
        applied = []
        if single:
            co["singleColor"] = single
            applied.append(f"single={single}")
        if palette:
            co["colorPalette"] = palette
            applied.append(f"palette={palette}")
        if custom:
            co["customColors"] = custom
            co["paletteType"] = "CATEGORY"
            applied.append(f"{len(custom)} custom colour(s)")
        if transparency is not None:
            co["transparency"] = transparency
            applied.append(f"transparency={transparency}")
        settings.save()
        success(f"Set colors on '{insight_id}': {', '.join(applied)}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

"""dku dataset — list, schema, info, head, build, create, upload, delete, clear, get/set-definition, set-schema, set-metadata, set-column-description, ai-describe, rename, copy, partitions, exists, usages, lineage, detect, zone, share, unshare."""

from __future__ import annotations

import re
import time
from pathlib import Path

import typer

from dku_cli.commands._dataset_create import (
    _apply_uploaded_files_connection,
    _build_create_dataset_payload,
    _create_filesystem_dataset,
    _translate_create_dataset_error,
)
from dku_cli.commands._dataset_quality import register_dataset_quality_commands
from dku_cli.enums import InlineImportSource, JobsDbView
from dku_cli.errors import (
    exit_with_error,
    handle_api_error,
    is_already_exists_error,
    is_not_found_error,
)
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    resolve_project,
    unpersisted_key_paths,
)
from dku_cli.output import (
    error,
    filter_fields,
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS datasets.")
register_dataset_quality_commands(app)


def _autodetect_and_warn(
    ds, dataset_name: str, project_key: str, quiet_warnings: bool = False
) -> None:
    """Auto-detect an uploaded dataset's format/schema and warn on all-STRING.

    CSV uploads often detect every column as STRING, which breaks downstream
    numeric aggregation (group/window SUM) — surface a fix when that happens.

    ``quiet_warnings`` skips the header/STRING warnings — used when sheet
    targeting follows, where they describe the wrong (first) sheet and the
    follow-up re-detection supersedes them.
    """
    info("Auto-detecting format and schema...")
    try:
        detected = ds.autodetect_settings(infer_storage_types=True)
        detected.save()
    except Exception as exc:
        exit_with_error(
            f"Auto-detect failed for uploaded file in '{dataset_name}': {exc}",
            details=[
                "For small, odd, or headerless files, upload without detection "
                "and set the format/schema explicitly:",
                f"  dku dataset upload {dataset_name} <FILE> --no-autodetect "
                f"-P {project_key}",
                f"  dku dataset set-definition {dataset_name} -d "
                '\'{"formatType":"csv","formatParams":{"separator":",",'
                '"parseHeaderRow":true}}\' --deep-merge '
                f"-P {project_key}",
                f"  dku dataset set-schema {dataset_name} --columns "
                f"'<col type, col type>' -P {project_key}",
            ],
        )
    schema_cols = detected.get_raw().get("schema", {}).get("columns", [])
    success(
        f"Format detected: {detected.get_raw().get('formatType', 'unknown')} "
        f"({len(schema_cols)} columns)"
    )
    if not schema_cols or quiet_warnings:
        return

    # Header not parsed → generic col_0, col_1, … names. DSS's header heuristic
    # fails when the header row is mostly numeric (year columns, numeric IDs):
    # it can't tell header from data and leaves parseHeaderRow=false. Downstream
    # recipes then KeyError on the real names. Detect the col_<n> pattern and
    # tell the agent the fix.
    import re

    names = [c.get("name", "") for c in schema_cols]
    generic = [n for n in names if re.fullmatch(r"col_\d+", n)]
    header_eaten = len(generic) == len(names) and len(names) > 0
    if not header_eaten and not detected.get_raw().get("formatParams", {}).get(
        "parseHeaderRow", True
    ):
        # parseHeaderRow false but names aren't col_N (rare) — still flag
        header_eaten = len(generic) >= max(1, len(names) // 2)
    if header_eaten:
        warn(
            "Header row NOT parsed — columns named col_0, col_1, … "
            "This happens when the header is mostly numeric (year "
            "columns, numeric IDs). Fix BEFORE building recipes:\n"
            f"  dku dataset set-definition {dataset_name} --definition "
            '\'{"formatParams":{"parseHeaderRow":true}}\' --deep-merge '
            f"-P {project_key}\n"
            f"  then dku dataset set-schema {dataset_name} -d "
            f"'<columns-from-CSV-header>' -P {project_key}"
        )

    if all(c.get("type") == "string" for c in schema_cols):
        warn(
            "All columns detected as STRING. Downstream aggregation recipes "
            "(group, window) may fail on numeric operations. Fix with: "
            f"dku dataset infer-types {dataset_name} --apply -P {project_key}"
        )


def _redetect_schema_keeping_format(
    client, project_key: str, dataset_name: str, infer_types: bool = True
):
    """Re-run schema detection while preserving the saved formatType/formatParams.

    ``autodetect_settings()`` always re-detects the format from scratch
    (``detectPossibleFormats: true``), which resets manually-set params —
    e.g. an Excel sheet selection snaps back to the first sheet. This calls
    the same endpoint with ``detectPossibleFormats: false`` so detection
    honors the dataset's current format config and only re-infers columns.

    Returns ``(settings, detected_columns, text_reasons)``. The fresh
    per-format inference lives in ``schemaDetection.detectedSchema``;
    ``newSchema`` is that detection reconciled against the dataset's
    EXISTING schema and silently keeps stale columns on any mismatch —
    always read ``detectedSchema`` here.
    """
    from dataikuapi.dss.future import DSSFuture

    ds = client.get_project(project_key).get_dataset(dataset_name)
    settings = ds.get_settings()
    future_resp = client._perform_json(
        "POST",
        "/projects/%s/datasets/%s/actions/testAndDetectSettings/fsLike"
        % (project_key, dataset_name),
        body={"detectPossibleFormats": False, "inferStorageTypes": infer_types},
    )
    result = DSSFuture(client, future_resp.get("jobId"), future_resp).wait_for_result()
    fmt_result = result.get("format") or {}
    if not fmt_result.get("ok"):
        raise ValueError(
            "Schema detection failed against the current format config "
            f"(formatType={settings.get_raw().get('formatType')!r}). "
            "Check the format params — e.g. an Excel sheets pattern that "
            "matches no sheet."
        )
    schema_detection = fmt_result.get("schemaDetection") or {}
    detected = (
        schema_detection.get("detectedSchema")
        or schema_detection.get("newSchema")
        or {}
    ).get("columns", [])
    return settings, detected, schema_detection.get("textReasons") or []


def _run_detection(
    client,
    ds,
    project_key: str,
    dataset_name: str,
    infer_types: bool,
    keep_format: bool,
):
    """Run full autodetection, or schema-only detection when keep_format is set."""
    if not keep_format:
        return ds.autodetect_settings(infer_storage_types=infer_types)
    detected, detected_cols, _reasons = _redetect_schema_keeping_format(
        client, project_key, dataset_name, infer_types=infer_types
    )
    detected.get_raw()["schema"] = {"columns": detected_cols, "userModified": True}
    return detected


def _validate_sheet_flags(
    sheet: str | None,
    sheet_indices: str | None,
    all_sheets: bool,
    no_autodetect: bool,
) -> None:
    """Reject contradictory Excel sheet-targeting flag combinations."""
    selectors = sum(1 for s in (sheet, sheet_indices) if s is not None) + (
        1 if all_sheets else 0
    )
    if selectors > 1:
        exit_with_error("Pass at most one of --sheet / --sheet-indices / --all-sheets.")
    if selectors and no_autodetect:
        exit_with_error(
            "--sheet/--sheet-indices/--all-sheets need format detection; "
            "drop --no-autodetect."
        )


def _apply_excel_sheet_targeting(
    client,
    dataset_name: str,
    project_key: str,
    *,
    sheet: str | None,
    sheet_indices: str | None,
    all_sheets: bool,
    sheets_to_column: bool,
) -> None:
    """Retarget an uploaded Excel dataset's sheet selection and re-infer its schema.

    Replaces the manual dance: get-definition → edit formatParams.sheets →
    set-definition → hand-write the schema. ``parseHeaderRow`` is re-asserted
    because the initial autodetect may have run on a non-data first sheet and
    concluded there is no header.
    """
    ds = client.get_project(project_key).get_dataset(dataset_name)
    settings = ds.get_settings()
    raw = settings.get_raw()
    format_type = raw.get("formatType")
    if format_type != "excel":
        exit_with_error(
            f"--sheet/--sheet-indices/--all-sheets only apply to Excel files; "
            f"detected format is '{format_type}'.",
            details=[
                "These flags retarget formatParams.sheets on an excel-format dataset.",
                f"Inspect: dku dataset get-definition {dataset_name} -P {project_key}",
            ],
        )
    params = raw.setdefault("formatParams", {})
    if sheet is not None:
        # The "*" prefix is mandatory serialization syntax in NAMES mode
        # (the engine matches the exact name after it; no prefix → no match).
        params["sheetSelectionMode"] = "NAMES"
        params["sheets"] = f"*{sheet}"
        target_desc = f"sheet '{sheet}'"
    elif sheet_indices is not None:
        params["sheetSelectionMode"] = "INDICES"
        params["sheets"] = sheet_indices
        target_desc = f"sheet indices {sheet_indices} (0-based)"
    else:  # all_sheets
        params["sheetSelectionMode"] = "ALL"
        target_desc = "all sheets"
    if sheets_to_column:
        params["sheetsToColumn"] = True
    params["parseHeaderRow"] = True
    settings.save()

    settings, detected, _reasons = _redetect_schema_keeping_format(
        client, project_key, dataset_name, infer_types=True
    )
    settings.get_raw()["schema"] = {"columns": detected, "userModified": True}
    settings.save()

    success(f"Targeted {target_desc}: {len(detected)} columns")
    if sheets_to_column:
        info("Sheet name is prepended as the FIRST column of the dataset.")
    import re

    names = [c.get("name", "") for c in detected]
    if names and all(re.fullmatch(r"col_\d+", n) for n in names):
        warn(
            "Columns detected as col_0, col_1, … — the sheet selection may not "
            "have matched (names are matched exactly, case-sensitive), or the "
            "sheet has no header row. A non-matching selection silently falls "
            "back to another sheet. Verify with: "
            f"dku dataset head {dataset_name} -P {project_key} -n 3"
        )


def _dataset_exists(proj, name: str) -> bool:
    """True if the dataset exists; re-raises non-404 errors for the caller."""
    try:
        proj.get_dataset(name).get_schema()
        return True
    except Exception as e:  # noqa: BLE001
        if is_not_found_error(e):
            return False
        raise


@app.command("list")
def list_datasets(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    fields: str = typer.Option(
        None,
        "--fields",
        help="Comma-separated fields to include (name,type,columns)",
    ),
) -> None:
    """List datasets in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        datasets = proj.list_datasets(include_shared=True)

        data = []
        for ds in datasets:
            data.append(
                {
                    "name": ds.get("name", ""),
                    "type": ds.get("type", ""),
                    "schema_count": str(len(ds.get("schema", {}).get("columns", []))),
                }
            )

        data, keys = filter_fields(data, ["name", "type", "schema_count"], fields)

        render(
            data,
            keys,
            output_format=output,
            title=f"Datasets ({project_key})",
            headers={"name": "NAME", "type": "TYPE", "schema_count": "COLUMNS"},
        )
    except Exception as e:
        handle_api_error(e)


def _is_numeric_type(dss_type: str) -> bool:
    """Check if a DSS column type is numeric."""
    return dss_type.lower() in {
        "int",
        "bigint",
        "smallint",
        "tinyint",
        "float",
        "double",
        "decimal",
        "numeric",
        "number",
    }


def _make_computation(column: str, col_type: str, top_k: int) -> dict:
    """Build a multi-computation for column analysis based on column type.

    Returns a computation dict suitable for DSSStatisticsComputationSettings.

    The 'missing' filter computation is only included for numeric columns
    because DSS 14.x string-column filtering casts internally to numeric.
    """
    computations: list[dict] = [
        {"type": "count"},
        {"type": "count_distinct", "column": column},
        {
            "type": "grouped",
            "grouping": {
                "type": "anum",
                "column": column,
                "maxValues": top_k,
                "groupOthers": True,
            },
            "computation": {"type": "count"},
        },
    ]
    if _is_numeric_type(col_type):
        computations += [
            {
                "type": "grouped",
                "grouping": {
                    "type": "subset",
                    "filter": {"type": "missing", "column": column},
                },
                "computation": {"type": "count"},
            },
            {
                "type": "grouped",
                "grouping": {
                    "type": "subset",
                    "filter": {
                        "type": "not",
                        "filter": {"type": "missing", "column": column},
                    },
                },
                "computation": {"type": "count"},
            },
            {"type": "mean", "column": column},
            {"type": "std_dev", "column": column},
            {
                "type": "quantiles",
                "freqs": [0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0],
                "column": column,
            },
        ]
    return {"type": "multi", "computations": computations}


def _parse_result(result: dict, col_type: str) -> dict:
    """Parse a multi-computation result into a flat dict."""
    parsed: dict = {}
    for r in result.get("results", []):
        rtype = r.get("type")
        if rtype == "count":
            parsed["row_count"] = r.get("count", 0)
        elif rtype == "count_distinct":
            parsed["distinct_count"] = r.get("count", 0)
        elif rtype == "mean":
            parsed["mean"] = r.get("value") or r.get("mean")
        elif rtype == "std_dev":
            parsed["std_dev"] = r.get("value") or r.get("stdDev")
        elif rtype == "quantiles":
            quantiles = r.get("quantiles", [])
            for q in quantiles:
                freq = q.get("freq")
                val = q.get("quantile")
                if freq == 0.0:
                    parsed["min"] = val
                elif freq == 0.25:
                    parsed["p25"] = val
                elif freq == 0.5:
                    parsed["median"] = val
                elif freq == 0.75:
                    parsed["p75"] = val
                elif freq == 1.0:
                    parsed["max"] = val
                elif freq == 0.01:
                    parsed["p01"] = val
                elif freq == 0.05:
                    parsed["p05"] = val
                elif freq == 0.95:
                    parsed["p95"] = val
                elif freq == 0.99:
                    parsed["p99"] = val
        elif rtype == "grouped":
            grouping = r.get("groups", {})
            gtype = grouping.get("type")
            if gtype == "anum":
                top_values = []
                values = grouping.get("values", [])
                results = r.get("results", [])
                for val, res in zip(values, results):
                    top_values.append(
                        {
                            "value": val,
                            "count": res.get("count", 0),
                        }
                    )
                parsed["top_values"] = top_values
                parsed["has_others"] = grouping.get("hasOthers", False)
                parsed["has_all_values"] = grouping.get("hasAllValues", False)
            elif gtype == "subset":
                filter_ = grouping.get("filter", {})
                ftype = filter_.get("type")
                if ftype == "missing":
                    parsed["null_count"] = r.get("results", [{}])[0].get("count", 0)
                elif ftype == "not":
                    # Non-null count — we can infer null = total - non_null
                    non_null = r.get("results", [{}])[0].get("count", 0)
                    parsed["non_null_count"] = non_null
        elif rtype == "failed":
            parsed["_warning"] = r.get("message", "Unknown computation error")
    return parsed


@app.command("analyze-column")
def analyze_column(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    column: str = typer.Argument(help="Column name to analyze"),
    top_k: int = typer.Option(
        10, "--top-k", help="Number of top values to show (distribution)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Analyze a column: distribution, null rate, top-K values, and basic stats.

    Computes column-level statistics on DSS using the statistics worksheet
    engine and returns them in a structured format.
    High-value for agents writing data quality recipes — run this first to
    understand column shape before setting DQ rules.

    Note: Null rate is reported only for numeric columns (DSS 14.x limitation
    — the 'missing' filter casts internally to numeric). For string columns,
    null absence is inferred from value coverage.

    Example:
      dku dataset analyze-column my_ds age -P PROJ
      dku dataset analyze-column my_ds age --top-k 5 -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)

        # Determine column type from schema
        ds_def = ds.get_definition()
        columns = ds_def.get("schema", {}).get("columns", [])
        col_def = next((c for c in columns if c.get("name") == column), None)
        if col_def is None:
            exit_with_error(
                f"Column '{column}' not found in '{dataset_name}'.",
                details=[
                    f"Check schema: dku dataset schema {dataset_name} -P {project_key}",
                ],
            )
        col_type = col_def.get("type", "string")

        # Build computation, create temp worksheet, run
        computation = _make_computation(column, col_type, top_k)

        from dataikuapi.dss.statistics import DSSStatisticsComputationSettings

        ws = ds.create_statistics_worksheet(
            name=f"_dku_analyze_{column}_{int(time.time())}"
        )
        try:
            comp = DSSStatisticsComputationSettings(computation)
            result = ws.run_computation(comp, wait=True)
        finally:
            ws.delete()

        parsed = _parse_result(result.get_raw(), col_type)

        # For string columns, infer null from value coverage
        if not _is_numeric_type(col_type):
            top_vals = parsed.get("top_values", [])
            top_sum = sum(tv["count"] for tv in top_vals)
            total = parsed.get("row_count", 0)
            has_all = parsed.get("has_all_values", False)
            if has_all and top_sum == total:
                parsed["null_count"] = 0
            parsed.pop("has_others", None)
            parsed.pop("has_all_values", None)

        if fmt == "json":
            render_raw(parsed, output_format="json")
            return

        summary = [
            {"field": "Column", "value": column},
            {"field": "Type", "value": col_type},
            {"field": "Total rows", "value": str(parsed.get("row_count", 0))},
        ]
        row_count = parsed.get("row_count", 0)
        null_count = parsed.get("null_count")
        non_null = (
            row_count - null_count
            if null_count is not None
            else parsed.get("non_null_count", row_count)
        )
        if null_count is not None:
            null_rate = f"{null_count / row_count * 100:.1f}%" if row_count else "N/A"
        else:
            null_rate = "N/A"

        summary.append({"field": "Non-null", "value": str(non_null)})
        summary.append(
            {
                "field": "Null count",
                "value": str(null_count) if null_count is not None else "N/A",
            }
        )
        summary.append({"field": "Null rate", "value": null_rate})
        summary.append(
            {
                "field": "Distinct values",
                "value": str(parsed.get("distinct_count", "N/A")),
            }
        )

        for stat_key, label in [
            ("min", "Min"),
            ("max", "Max"),
            ("mean", "Mean"),
            ("std_dev", "StdDev"),
            ("p01", "P01"),
            ("p05", "P05"),
            ("p25", "P25"),
            ("median", "Median"),
            ("p75", "P75"),
            ("p95", "P95"),
            ("p99", "P99"),
        ]:
            val = parsed.get(stat_key)
            if val is not None:
                summary.append(
                    {
                        "field": label,
                        "value": f"{val:.4f}" if isinstance(val, float) else str(val),
                    }
                )

        render(
            summary,
            ["field", "value"],
            output_format=fmt,
            title=f"Column Analysis: {dataset_name}.{column}",
        )

        top_values = parsed.get("top_values", [])
        if top_values:
            tv_data = [
                {
                    "value": tv["value"],
                    "count": str(tv["count"]),
                    "frequency": f"{tv['count'] / non_null * 100:.1f}%"
                    if non_null
                    else "N/A",
                }
                for tv in top_values
            ]
            render(
                tv_data,
                ["value", "count", "frequency"],
                output_format=fmt,
                title=f"Top {len(tv_data)} Values",
            )

        warning = parsed.get("_warning")
        if warning:
            from dku_cli.output import warn

            warn(f"Computation note: {warning}")

    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("schema")
@app.command("get-schema", hidden=True)
def schema(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    fields: str = typer.Option(
        None,
        "--fields",
        help="Comma-separated fields to include (name,type,description)",
    ),
) -> None:
    """Show dataset schema.

    Also available as `get-schema` (hidden alias) for parity with the
    other `get-*` inspectors — agents reach for `get-schema` by analogy
    with `get-definition`. Recurring miss across migration sessions.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds_def = ds.get_definition()
        columns = ds_def.get("schema", {}).get("columns", [])

        has_descriptions = any(col.get("comment") for col in columns)
        if has_descriptions:
            data = [
                {
                    "name": col.get("name", ""),
                    "type": col.get("type", ""),
                    "description": col.get("comment", ""),
                }
                for col in columns
            ]
            keys = ["name", "type", "description"]
        else:
            data = [
                {"name": col.get("name", ""), "type": col.get("type", "")}
                for col in columns
            ]
            keys = ["name", "type"]

        data, keys = filter_fields(data, keys, fields)

        render(
            data,
            keys,
            output_format=output,
            title=f"Schema: {dataset_name}",
        )
    except Exception as e:
        handle_api_error(e)


def _format_bytes(size_bytes: int | float) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 0:
        return "unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{int(size_bytes)} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _format_count(n: int | float) -> str:
    """Format large numbers with commas."""
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return str(n)


_SIZE_WARNING_BYTES = 1_000_000_000  # 1 GB
_ROW_WARNING_COUNT = 10_000_000  # 10M rows


def _gather_dataset_info(
    ds, dataset_name: str, project_key: str, *, recompute: bool, fmt: str
) -> tuple[dict, dict]:
    """Run a single dataset's info collection and return (display_row, json_row).

    Extracted so `info` can iterate over multiple dataset names without
    duplicating the gather/format logic. Returns a (table-row, json-row)
    pair; the caller decides how to render. Stale-metrics hints and
    large-dataset warnings still go to stderr per dataset.
    """
    # Values parsed straight out of the compute_metrics response. Reading
    # get_last_metric_values() right after compute is a write-then-read race —
    # the last-values store can still return the PREVIOUS run's numbers (it
    # even reported a stale count for a dataset whose rebuild had just failed).
    fresh_values: dict[str, str] = {}
    if recompute:
        if fmt != "json":
            info(f"Recomputing metrics for '{dataset_name}'...")
        try:
            compute_result = ds.compute_metrics(
                metric_ids=[
                    "records:COUNT_RECORDS",
                    "basic:SIZE",
                    "basic:COUNT_FILES",
                ]
            )
            for computed in (
                (compute_result or {}).get("result", {}).get("computed", [])
            ):
                if computed.get("metricId") and "value" in computed:
                    fresh_values[computed["metricId"]] = computed["value"]
        except Exception as exc:
            if fmt != "json":
                warn(f"Metric recompute failed for '{dataset_name}': {exc}")

    ds_def = ds.get_definition()
    ds_type = ds_def.get("type", "unknown")
    params = ds_def.get("params", {})
    connection_name = params.get("connection", params.get("uploadConnection", ""))
    format_type = ds_def.get("formatType", "")
    columns = ds_def.get("schema", {}).get("columns", [])
    managed = ds_def.get("managed", False)
    tags = ds_def.get("tags", [])

    last_build_time = None
    build_success = None
    try:
        ds_info = ds.get_info()
        raw_info = ds_info.get_raw()
        last_build = raw_info.get("lastBuild", {})
        if last_build.get("buildEndTime"):
            from datetime import datetime, timezone

            ts = last_build["buildEndTime"] / 1000
            last_build_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
        build_success = last_build.get("buildSuccess")
    except Exception:
        pass

    metrics_stale = True

    def _fresh_int(metric_id: str):
        value = fresh_values.get(metric_id)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    row_count = _fresh_int("records:COUNT_RECORDS")
    data_size_bytes = _fresh_int("basic:SIZE")
    file_count = _fresh_int("basic:COUNT_FILES")
    if row_count is not None or data_size_bytes is not None:
        metrics_stale = False

    if row_count is None or data_size_bytes is None or file_count is None:
        try:
            metrics = ds.get_last_metric_values()
            available_ids = metrics.get_all_ids()
            if row_count is None and "records:COUNT_RECORDS" in available_ids:
                try:
                    row_count = metrics.get_global_value("records:COUNT_RECORDS")
                    metrics_stale = False
                except Exception:
                    pass
            if data_size_bytes is None and "basic:SIZE" in available_ids:
                try:
                    data_size_bytes = metrics.get_global_value("basic:SIZE")
                    metrics_stale = False
                except Exception:
                    pass
            if file_count is None and "basic:COUNT_FILES" in available_ids:
                try:
                    file_count = metrics.get_global_value("basic:COUNT_FILES")
                    metrics_stale = False
                except Exception:
                    pass
        except Exception:
            pass

    display_row = {
        "name": dataset_name,
        "type": ds_type,
        "managed": managed,
        "connection": connection_name or "(none)",
        "format": format_type or "(none)",
        "columns": len(columns),
        "rows": _format_count(row_count) if row_count is not None else "(not computed)",
        "size": _format_bytes(data_size_bytes)
        if data_size_bytes is not None
        else "(not computed)",
        "files": _format_count(file_count) if file_count is not None else "(n/a)",
        "last_build": last_build_time or "(never built)",
        "build_ok": str(build_success) if build_success is not None else "(unknown)",
        "tags": ", ".join(tags) if tags else "(none)",
    }
    json_row = {
        "name": dataset_name,
        "type": ds_type,
        "managed": managed,
        "connection": connection_name or None,
        "format": format_type or None,
        "columns": len(columns),
        "rows": int(row_count) if row_count is not None else None,
        "size_bytes": int(data_size_bytes) if data_size_bytes is not None else None,
        "size_human": _format_bytes(data_size_bytes)
        if data_size_bytes is not None
        else None,
        "files": int(file_count) if file_count is not None else None,
        "last_build": last_build_time,
        "build_success": build_success,
        "tags": tags,
        "metrics_computed": not metrics_stale,
    }

    if data_size_bytes is not None and data_size_bytes > _SIZE_WARNING_BYTES:
        warn(
            f"Large dataset '{dataset_name}': {_format_bytes(data_size_bytes)}. "
            "Use --rows/-n with 'head' to limit data pulled. "
            "Building downstream recipes may incur significant compute cost."
        )
    if row_count is not None and row_count > _ROW_WARNING_COUNT:
        warn(
            f"High row count on '{dataset_name}': {_format_count(row_count)} rows. "
            "Consider sampling before transforming. "
            "Use 'dku recipe create-sampling' to create a sample dataset."
        )
    if metrics_stale and fmt != "json":
        if last_build_time is not None:
            info(
                f"Metrics are stale for '{dataset_name}' — pass --recompute for fresh row count / size / file count: "
                f"dku dataset info {dataset_name} -P {project_key} --recompute"
            )
        else:
            info(
                f"Metrics not yet computed for '{dataset_name}'. Run: "
                f"dku dataset build {dataset_name} -P {project_key} --wait"
            )

    return display_row, json_row


@app.command("info")
@app.command("inspect", hidden=True)
def info_cmd(
    ctx: typer.Context,
    dataset_names: list[str] = typer.Argument(
        ...,
        help=(
            "Dataset name(s). Pass multiple to inspect several at once: "
            "`dku dataset info ds1 ds2 ds3 -P PROJ`. JSON output then returns a list."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    recompute: bool = typer.Option(
        False,
        "--recompute",
        "--fresh",
        help="Recompute metrics (row count, size, file count) instead of reading the cached values. Use after a recipe run to avoid stale numbers — DSS does not auto-recompute metrics on build.",
    ),
) -> None:
    """Show dataset metadata: size, row count, type, connection, last build.

    Use this BEFORE pulling data to understand how large a dataset is.
    Warns when datasets are large (>1GB or >10M rows) to prevent
    accidental expensive operations. Pass --recompute after a build to
    refresh row count, size, and file count metrics.

    Accepts multiple positional names (one shell call inspects N datasets):

    Example:
      dku dataset info my_data -P PROJ
      dku dataset info ds1 ds2 ds3 -P PROJ
      dku --format json dataset info my_data -P PROJ
      dku dataset info my_data -P PROJ --recompute
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        display_rows: list[dict] = []
        json_rows: list[dict] = []
        for dataset_name in dataset_names:
            ds = proj.get_dataset(dataset_name)
            display_row, json_row = _gather_dataset_info(
                ds, dataset_name, project_key, recompute=recompute, fmt=fmt
            )
            display_rows.append(display_row)
            json_rows.append(json_row)

        if fmt == "json":
            # Single-name calls keep the historical dict shape; multi-name
            # returns a list so consumers can iterate without branching.
            payload = json_rows[0] if len(json_rows) == 1 else json_rows
            render_raw(payload, output_format="json")
            return

        if len(display_rows) == 1:
            data = [{"field": k, "value": v} for k, v in display_rows[0].items()]
            render(
                data,
                ["field", "value"],
                output_format=fmt,
                title=f"Dataset Info: {dataset_names[0]}",
            )
        else:
            # Multi-dataset table: one column per dataset, one row per field.
            field_names = list(display_rows[0].keys())
            columns = ["field", *dataset_names]
            data = []
            for fname in field_names:
                row = {"field": fname}
                for ds_name, dr in zip(dataset_names, display_rows):
                    row[ds_name] = dr[fname]
                data.append(row)
            render(
                data,
                columns,
                output_format=fmt,
                title=f"Dataset Info ({len(dataset_names)} datasets)",
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def head(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    rows: int = typer.Option(
        10,
        "-n",
        "--rows",
        "--limit",
        help="Number of rows. 0 means ALL rows (same as --all).",
    ),
    all_rows: bool = typer.Option(
        False,
        "--all",
        help=(
            "Stream every row (verification / parity checks on small datasets). "
            "Check `dku dataset info` first on datasets you don't know — this "
            "reads the full data. For a file copy use `dku dataset download`."
        ),
    ),
    filter_columns: str = typer.Option(
        None,
        "--columns",
        "-C",
        help="Comma-separated column names to display (default: all). Use to inspect specific columns before transforming.",
    ),
) -> None:
    """Preview first rows of a dataset (or all rows with --all).

    Use --columns to inspect specific columns before creating recipes:
      dku dataset head INPUT --columns "order_date,price" -P PROJ -n 10
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)

        # Get column names from schema
        ds_def = ds.get_definition()
        all_columns = [
            col.get("name", f"col_{i}")
            for i, col in enumerate(ds_def.get("schema", {}).get("columns", []))
        ]

        # Empty schema => `iter_rows()` yields nothing or empty lists, and
        # the previous behavior was to print `[]` / `[{},{}]` with no
        # explanation. An agent reading that thinks the dataset is empty,
        # when in reality it just has no columns yet (never built). Surface
        # this explicitly with the recovery command.
        if not all_columns:
            exit_with_error(
                f"Dataset '{dataset_name}' has no columns — it likely has never been built.",
                details=[
                    "An unbuilt managed dataset has zero columns; `head` cannot show data.",
                    f"  dku dataset build {dataset_name} -P {project_key} --type RECURSIVE_BUILD --auto-update-schema --wait",
                    f"  dku dataset head {dataset_name} -P {project_key} -n 10",
                ],
            )

        # Filter columns if requested
        if filter_columns:
            requested = [c.strip() for c in filter_columns.split(",") if c.strip()]
            missing = [c for c in requested if c not in all_columns]
            if missing:
                exit_with_error(
                    f"Column(s) not found: {missing}",
                    details=[
                        f"Available columns: {', '.join(all_columns[:20])}"
                        + (
                            f" ... ({len(all_columns)} total)"
                            if len(all_columns) > 20
                            else ""
                        ),
                        f"Check schema: dku dataset schema {dataset_name} -P {project_key}",
                    ],
                )
            display_columns = requested
        else:
            display_columns = all_columns

        # iter_rows() returns lists, not dicts — zip with column names
        unlimited = all_rows or rows == 0
        data = []
        for i, row in enumerate(ds.iter_rows()):
            if not unlimited and i >= rows:
                break
            full_row = dict(zip(all_columns, row))
            data.append({c: full_row[c] for c in display_columns})

        render(
            data,
            display_columns,
            output_format=output,
            title=(
                f"{dataset_name} (all {len(data)} rows)"
                if unlimited
                else f"{dataset_name} (first {rows} rows)"
            ),
            # Preserve the real column-name case in headers. The table renderer
            # upper-cases headers by default, but here the headers ARE dataset
            # column names — and GREL/formula references are case-sensitive, so
            # an agent copying an upper-cased header into a Prepare formula gets
            # silent nulls / dropped rows. Show 'StateANSI', not 'STATEANSI'.
            headers={c: c for c in display_columns},
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def build(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
    job_type: str = typer.Option(
        None,
        "--type",
        "-t",
        help="Build type: NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD, RECURSIVE_MISSING_ONLY_BUILD",
    ),
    auto_update_schema: bool = typer.Option(
        False,
        "--auto-update-schema",
        help="Auto-update output schemas before each recipe run",
    ),
    no_verify: bool = typer.Option(
        False,
        "--no-verify",
        help="Skip the post-build rows/cols summary on successful --wait builds",
    ),
) -> None:
    """Trigger dataset build.

    Use --type RECURSIVE_BUILD --auto-update-schema to build the entire upstream
    pipeline with automatic schema propagation.

    With --wait, a successful build prints `Built <ds>: N rows, M cols` so
    success carries proof (0 rows = warning to investigate).
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        from dku_cli.output import error, info, success, warn

        # Catch the "RECURSIVE_BUILD on an orphan target succeeds and reports
        # success without building anything" failure mode. If `dataset_name`
        # has no producing recipe (managed dataset with no producer, or just
        # never wired), `dataset build` returns DONE without doing work and
        # masks failed recipe creates upstream (PENDING 2026-05-25 iterative
        # macro entry). Warn — don't block; intentional clear/no-op may be
        # desired.
        try:
            recipes_meta = proj.list_recipes() or []
            has_producer = False
            for r in recipes_meta:
                outs = (r or {}).get("outputs") or {}
                for role in outs.values():
                    for item in (role or {}).get("items") or []:
                        if (item or {}).get("ref") == dataset_name:
                            has_producer = True
                            break
                    if has_producer:
                        break
                if has_producer:
                    break
            if not has_producer:
                warn(
                    f"Dataset '{dataset_name}' has no producing recipe — the build will "
                    f"report success but no recipe will actually run."
                )
                info(
                    f"Wire a recipe first (e.g. `dku recipe create-prepare … --output-ds {dataset_name} -P {project_key}`), "
                    f"or build the producing dataset directly."
                )
        except Exception:
            pass  # Best-effort — never block the build on a metadata read failure.

        # Single async job-builder path for both plain and advanced builds.
        # (DSSDataset.build() blocks internally even without --wait and raises
        # a generic error on failure — inconsistent with `dku job run` /
        # `dku recipe run` and useless for agents who need the job id + log.)
        builder = proj.new_job(job_type or "NON_RECURSIVE_FORCED_BUILD")
        builder.with_output(dataset_name)
        if auto_update_schema:
            builder.with_auto_update_schema_before_each_recipe_run(True)
        job_start_ms = int(time.time() * 1000)
        job = builder.start()

        success(f"Build started for {dataset_name}")
        info(f"Job ID: {job.id}")
        hint(f"dku job log {job.id} -P {project_key}")
        if auto_update_schema:
            info("Auto-update schema: enabled")

        if wait:
            info("Waiting for completion...")
            while True:
                status = job.get_status()
                state = status.get("baseStatus", {}).get("state", "")
                if state in ("DONE", "FAILED", "ABORTED"):
                    break
                time.sleep(2)
            if state == "DONE":
                success("Build completed successfully")
                if not no_verify:
                    from dku_cli.build_summary import emit_build_summary

                    emit_build_summary(
                        client,
                        proj,
                        project_key,
                        [(dataset_name, "DATASET")],
                        job_start_ms,
                    )
            else:
                # FAILED/ABORTED must exit non-zero — agents chain
                # `dataset build --wait && next-step`; exit 0 here would let
                # the chain march on past a failed build.
                error(f"Build finished with state: {state}")
                info(f"Inspect why: dku job log {job.id} -P {project_key}")
                raise SystemExit(1)
    except SystemExit:
        raise
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    type_name: str = typer.Option(
        "Filesystem",
        "--type",
        "-t",
        help="Dataset type: Filesystem, UploadedFiles, Inline, PostgreSQL, MySQL, Snowflake, Redshift, BigQuery, Oracle, SQLServer, S3, ... Use the concrete DB name for SQL connections — 'SQL' is rejected by the DSS license system on most instances. Inline = editable spreadsheet-like dataset stored in DSS itself (no connection needed). Default: Filesystem",
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help="Connection name (defaults to filesystem_managed for Filesystem; required for SQL/S3; ignored for Inline)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if dataset already exists"
    ),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="Dataset definition JSON. Supported create-time fields: type, params, formatType, formatParams",
    ),
    keep_track_of_changes: bool = typer.Option(
        False,
        "--keep-track-of-changes",
        help="Inline only: store every edit in an audit log (params.keepTrackOfChanges).",
    ),
    enable_clipboard_api: bool = typer.Option(
        False,
        "--enable-clipboard-api",
        help="Inline only: allow paste-in via DSS UI clipboard API (params.enableClipboardApi).",
    ),
    import_source: InlineImportSource | None = typer.Option(
        None,
        "--import-source",
        case_sensitive=False,
        help="Inline only: seed source — NONE (default), CLIPBOARD, CSV, FILE. Sets params.importSourceType.",
    ),
    catalog: str | None = typer.Option(
        None,
        "--catalog",
        help="Databricks Unity Catalog name. Sets params.catalog (3-level: catalog.schema.table).",
    ),
    view: JobsDbView | None = typer.Option(
        None,
        "--view",
        case_sensitive=False,
        help="JobsDB only: live view to expose. METRICS_HISTORY | CHECK_HISTORY | JOBS_HISTORY. Sets params.view.",
    ),
    with_header: bool | None = typer.Option(
        None,
        "--with-header/--no-header",
        help="CSV/TSV: file has a header row. Sets formatParams.parseHeaderRow.",
    ),
    csv_dialect: str | None = typer.Option(
        None,
        "--csv-dialect",
        help="CSV dialect (excel, unix, etc.). Sets formatParams.style.",
    ),
    compress: str | None = typer.Option(
        None,
        "--compress",
        help="File compression for write: NONE | GZIP | BZIP2 | SNAPPY (filesystem-style outputs). Sets params.compress.",
    ),
    parquet_compression: str | None = typer.Option(
        None,
        "--parquet-compression",
        help="Parquet write codec: SNAPPY (default) | UNCOMPRESSED | GZIP | LZO. Sets formatParams.compressionCodec.",
    ),
    parquet_flavor: str | None = typer.Option(
        None,
        "--parquet-flavor",
        help="Parquet flavor: HIVE (default) | SPARK. Sets formatParams.flavor.",
    ),
    parquet_block_size_mb: int | None = typer.Option(
        None,
        "--parquet-block-size-mb",
        help="Parquet block (row-group) size in MB. Sets formatParams.blockSizeMB.",
    ),
    read_temporal_mode: str | None = typer.Option(
        None,
        "--read-temporal-mode",
        help="Parquet timestamp read mode: TIMESTAMP_NTZ | TIMESTAMP_TZ | LEGACY. Sets formatParams.readTemporalMode.",
    ),
    write_bad_data_behavior: str | None = typer.Option(
        None,
        "--write-bad-data-behavior",
        help="SQL write: DISCARD_ROW | NULL_VALUE | FAIL. Sets params.writeBadDataBehavior.",
    ),
    write_batch_size: int | None = typer.Option(
        None,
        "--write-batch-size",
        help="SQL bulk-load batch size. Sets params.writeBatchSize.",
    ),
    table_creation_mode: str | None = typer.Option(
        None,
        "--table-creation-mode",
        help="SQL table-creation behavior: auto | use_existing | fail_if_missing. Sets params.tableCreationMode.",
    ),
    no_drop_on_schema_mismatch: bool = typer.Option(
        False,
        "--no-drop-on-schema-mismatch",
        help="SQL: do NOT drop and recreate the table when the input schema diverges. Sets params.dropOnSchemaMismatch=false.",
    ),
    write_descriptions_as_comment: bool = typer.Option(
        False,
        "--write-descriptions-as-comment",
        help="SQL: emit column descriptions as DB column comments. Sets params.writeDescriptionsAsComment=true.",
    ),
    num_partitions: int | None = typer.Option(
        None,
        "--num-partitions",
        help="SQL/HDFS write parallelism. Sets params.numPartitions.",
    ),
    datetime_notz_read_mode: str | None = typer.Option(
        None,
        "--datetime-notz-read-mode",
        help="SQL date+time-without-tz read interpretation. Sets params.dateTimeNoTZReadMode.",
    ),
    dateonly_read_mode: str | None = typer.Option(
        None,
        "--dateonly-read-mode",
        help="SQL date-only read interpretation. Sets params.dateOnlyReadMode.",
    ),
    dist_style: str | None = typer.Option(
        None,
        "--dist-style",
        help="Redshift distribution style: AUTO | KEY | ALL | EVEN. Sets params.redshiftDistStyle.",
    ),
    dist_key: str | None = typer.Option(
        None,
        "--dist-key",
        help="Redshift KEY-style distribution column. Sets params.redshiftDistKey.",
    ),
    sort_key: str | None = typer.Option(
        None,
        "--sort-key",
        help="Redshift sort-key kind: COMPOUND | INTERLEAVED. Sets params.redshiftSortKey.",
    ),
    sort_key_columns: str | None = typer.Option(
        None,
        "--sort-key-columns",
        help="Redshift sort-key columns (comma-separated). Sets params.redshiftSortKeyColumns[].",
    ),
    use_bigquery_partitioning: bool = typer.Option(
        False,
        "--use-bigquery-partitioning",
        help="BigQuery: enable native time partitioning. Sets params.useBigQueryPartitioning=true.",
    ),
    bigquery_partitioning_type: str | None = typer.Option(
        None,
        "--bigquery-partitioning-type",
        help="BigQuery partitioning type: TIME | INTEGER_RANGE. Sets params.bigQueryPartitioningType.",
    ),
    bigquery_partitioning_period: str | None = typer.Option(
        None,
        "--bigquery-partitioning-period",
        help="BigQuery partitioning period: DAY | HOUR | MONTH | YEAR. Sets params.bigQueryPartitioningPeriod.",
    ),
    require_partition_filter: bool = typer.Option(
        False,
        "--require-partition-filter",
        help="BigQuery: require a partition filter in queries. Sets params.requirePartitionFilter=true.",
    ),
    upload_provider: str | None = typer.Option(
        None,
        "--upload-provider",
        help="UploadedFiles backend: LOCAL | S3 | AZURE | GCS. Sets params.uploadProvider.",
    ),
    metastore_sync: bool = typer.Option(
        False,
        "--metastore-sync",
        help="S3/Azure/GCS: synchronise to the Hive metastore on build. Sets params.metastoreSynchronizationEnabled=true.",
    ),
    metastore_database: str | None = typer.Option(
        None,
        "--metastore-database",
        help="Hive metastore database name. Sets params.metastoreDatabase.",
    ),
    metastore_table: str | None = typer.Option(
        None,
        "--metastore-table",
        help="Hive metastore table name. Sets params.metastoreTable.",
    ),
    include_glob: list[str] | None = typer.Option(
        None,
        "--include-glob",
        help="File-selection include glob (repeatable). Adds to params.filesSelectionRules.includeRules[].",
    ),
    exclude_glob: list[str] | None = typer.Option(
        None,
        "--exclude-glob",
        help="File-selection exclude glob (repeatable). Adds to params.filesSelectionRules.excludeRules[].",
    ),
    explicit_files: list[str] | None = typer.Option(
        None,
        "--explicit-files",
        help="Explicit file path (repeatable). Adds to params.filesSelectionRules.explicitFiles[].",
    ),
    variable_loop: str | None = typer.Option(
        None,
        "--variable-loop",
        help="Variable expansion loop config: literal JSON, @file.json, or '-' stdin. Sets params.variablesExpansionLoopConfig.",
    ),
) -> None:
    """Create a new dataset.

    For SQL dataset types (PostgreSQL, Snowflake, ...), the CLI auto-populates
    `mode: "table"` and `table: "${projectKey}_<name>"` so the dataset is
    immediately writable by downstream recipes. Without this, DSS creates a
    query-mode unmanaged dataset that no recipe can write to. Pass --definition
    with explicit params to opt out of the auto-populate.
    """
    project_key = resolve_project(project)
    # The DSS UI calls the Inline type "Editable" — accept the UI name.
    if type_name.lower() == "editable":
        info("Dataset type 'Editable' is called 'Inline' in the API — using Inline.")
        type_name = "Inline"
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        dataset_type, params, format_params, dataset_definition = (
            _build_create_dataset_payload(
                dataset_name=dataset_name,
                type_name=type_name,
                connection=connection,
                definition=definition,
                keep_track_of_changes=keep_track_of_changes,
                enable_clipboard_api=enable_clipboard_api,
                import_source=import_source,
                catalog=catalog,
                view=view,
                with_header=with_header,
                csv_dialect=csv_dialect,
                compress=compress,
                parquet_compression=parquet_compression,
                parquet_flavor=parquet_flavor,
                parquet_block_size_mb=parquet_block_size_mb,
                read_temporal_mode=read_temporal_mode,
                write_bad_data_behavior=write_bad_data_behavior,
                write_batch_size=write_batch_size,
                table_creation_mode=table_creation_mode,
                no_drop_on_schema_mismatch=no_drop_on_schema_mismatch,
                write_descriptions_as_comment=write_descriptions_as_comment,
                num_partitions=num_partitions,
                datetime_notz_read_mode=datetime_notz_read_mode,
                dateonly_read_mode=dateonly_read_mode,
                dist_style=dist_style,
                dist_key=dist_key,
                sort_key=sort_key,
                sort_key_columns=sort_key_columns,
                use_bigquery_partitioning=use_bigquery_partitioning,
                bigquery_partitioning_type=bigquery_partitioning_type,
                bigquery_partitioning_period=bigquery_partitioning_period,
                require_partition_filter=require_partition_filter,
                upload_provider=upload_provider,
                metastore_sync=metastore_sync,
                metastore_database=metastore_database,
                metastore_table=metastore_table,
                include_glob=include_glob,
                exclude_glob=exclude_glob,
                explicit_files=explicit_files,
                variable_loop=variable_loop,
            )
        )
        _apply_uploaded_files_connection(
            client,
            params,
            dataset_type=dataset_type,
            connection=connection,
        )

        if dataset_type == "Filesystem":
            if definition:
                error(
                    "Filesystem dataset creation via --definition is not supported yet. "
                    "Create the dataset with --connection first, then use 'dku dataset set-definition' to configure it."
                )
                raise typer.Exit(1)
            if not connection:
                connection = "filesystem_managed"
            _create_filesystem_dataset(proj, dataset_name, connection)
        else:
            try:
                proj.create_dataset(
                    dataset_name,
                    dataset_type,
                    params=params,
                    formatType=dataset_definition.get("formatType"),
                    formatParams=format_params
                    or dataset_definition.get("formatParams"),
                )
            except Exception as create_err:
                _translate_create_dataset_error(
                    create_err,
                    dataset_type=dataset_type,
                    dataset_name=dataset_name,
                    project_key=project_key,
                )
                raise
        hint(f"dku dataset build {dataset_name} -P {project_key}")
        success(
            f"Created dataset '{dataset_name}' (type={dataset_type}) in {project_key}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(
                f"Dataset '{dataset_name}' already exists in {project_key}, skipping create"
            )
            return
        if is_already_exists_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' already exists in {project_key}.",
                details=[
                    "Use --if-not-exists to skip creation when the dataset exists.",
                    f"Or delete first: dku dataset delete {dataset_name} -P {project_key} --yes",
                ],
            )
        handle_api_error(e)


@app.command()
def upload(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(
        help="Dataset name (must be UploadedFiles type)"
    ),
    local_path: Path = typer.Argument(help="Local file to upload"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    no_autodetect: bool = typer.Option(
        False, "--no-autodetect", help="Skip format/schema auto-detection after upload"
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        "--force",
        "-f",
        help="Clear existing files from the dataset before uploading.",
    ),
    sheet: str = typer.Option(
        None,
        "--sheet",
        help="Excel only: read this sheet (exact name, case-sensitive) instead of "
        "the autodetected first sheet. Re-infers the schema for that sheet.",
    ),
    sheet_indices: str = typer.Option(
        None,
        "--sheet-indices",
        help="Excel only: read these sheets by 0-based position, e.g. '0,2' or "
        "'1-' (comma list / ranges). Sheets must share one layout.",
    ),
    all_sheets: bool = typer.Option(
        False,
        "--all-sheets",
        help="Excel only: concatenate every sheet (sheets must share one layout).",
    ),
    sheets_to_column: bool = typer.Option(
        False,
        "--sheets-to-column",
        help="Excel only: prepend the sheet name as the first column "
        "(multi-sheet append tag, like Power Query's Source.Name).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Upload a file to an UploadedFiles dataset and auto-detect format/schema.

    By default, uploading a file with the same name as an existing upload
    fails. Pass --overwrite to clear the dataset first.

    For Excel workbooks, autodetection reads the FIRST sheet — pass --sheet,
    --sheet-indices, or --all-sheets to target the data sheet(s) directly:

        dku dataset upload book book.xlsx --sheet "Cleaned Data" -P PROJ
    """
    project_key = resolve_project(project)
    _validate_sheet_flags(sheet, sheet_indices, all_sheets, no_autodetect)

    if overwrite:
        from dku_cli.safety import Tier, guard

        guard(
            ctx,
            tier=Tier.DELETE,
            action="dataset.clear",
            subject=f"dataset '{dataset_name}' in project {project_key}",
            yes=yes,
            prompt=f"Wipe all rows from dataset '{dataset_name}' in project {project_key} before uploading? Data cannot be recovered.",
        )

    if not local_path.exists():
        from dku_cli.output import error

        error(f"File not found: {local_path}")
        raise typer.Exit(1)

    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)

        if overwrite:
            ds.clear()

        with local_path.open("rb") as f:
            ds.uploaded_add_file(f, local_path.name)

        # Warnings/suggestions first, status line LAST — `tail -1` automation
        # must capture the outcome, not a suggested-command fragment.
        if not no_autodetect:
            wants_sheets = bool(
                sheet or sheet_indices or all_sheets or sheets_to_column
            )
            _autodetect_and_warn(
                ds, dataset_name, project_key, quiet_warnings=wants_sheets
            )
            if wants_sheets:
                _apply_excel_sheet_targeting(
                    client,
                    dataset_name,
                    project_key,
                    sheet=sheet,
                    sheet_indices=sheet_indices,
                    all_sheets=all_sheets,
                    sheets_to_column=sheets_to_column,
                )
        hint(f"dku dataset schema {dataset_name} -P {project_key}")
        success(f"Uploaded {local_path.name} → {dataset_name}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-from-file")
def create_from_file(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Name for the new dataset"),
    local_path: Path = typer.Argument(help="Local file to upload (CSV, Parquet, …)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    connection: str = typer.Option(
        None, "--connection", "-c", help="Upload connection (default: instance default)"
    ),
    no_autodetect: bool = typer.Option(
        False, "--no-autodetect", help="Skip format/schema auto-detection"
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        "--force",
        "-f",
        help="If the dataset already exists, wipe it and re-upload (tier-2 guard).",
    ),
    sheet: str = typer.Option(
        None,
        "--sheet",
        help="Excel only: read this sheet (exact name, case-sensitive) instead of "
        "the autodetected first sheet. Re-infers the schema for that sheet.",
    ),
    sheet_indices: str = typer.Option(
        None,
        "--sheet-indices",
        help="Excel only: read these sheets by 0-based position, e.g. '0,2' or "
        "'1-' (comma list / ranges). Sheets must share one layout.",
    ),
    all_sheets: bool = typer.Option(
        False,
        "--all-sheets",
        help="Excel only: concatenate every sheet (sheets must share one layout).",
    ),
    sheets_to_column: bool = typer.Option(
        False,
        "--sheets-to-column",
        help="Excel only: prepend the sheet name as the first column "
        "(multi-sheet append tag, like Power Query's Source.Name).",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the safety guard (with --overwrite)"
    ),
) -> None:
    """Create an UploadedFiles dataset from a LOCAL file and auto-detect its schema.

    One step for the common "I have a CSV, make it a DSS dataset" flow:

        dku dataset create-from-file sales ./data/sales.csv -P MYPROJ

    For Excel workbooks, target the data sheet(s) in the same step:

        dku dataset create-from-file book book.xlsx --sheet "Cleaned Data" -P MYPROJ

    The path is local to where you run dku (your project dir under the MCP).
    """
    project_key = resolve_project(project)
    _validate_sheet_flags(sheet, sheet_indices, all_sheets, no_autodetect)
    if not local_path.exists():
        error(f"File not found: {local_path}")
        raise typer.Exit(1)

    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)

    try:
        exists = _dataset_exists(proj, dataset_name)
    except Exception as e:
        handle_api_error(e)
        return

    if exists and not overwrite:
        exit_with_error(
            f"Dataset '{dataset_name}' already exists in project {project_key}.",
            details=[
                f"Replace it: dku dataset create-from-file {dataset_name} {local_path} --overwrite -P {project_key}",
                f"Add to it:  dku dataset upload {dataset_name} {local_path} -P {project_key}",
            ],
        )
    if exists and overwrite:
        from dku_cli.safety import Tier, guard

        guard(
            ctx,
            tier=Tier.DELETE,
            action="dataset.clear",
            subject=f"dataset '{dataset_name}' in project {project_key}",
            yes=yes,
            prompt=(
                f"Replace dataset '{dataset_name}' in {project_key} with "
                f"{local_path.name}? Existing data is wiped."
            ),
        )

    try:
        if exists:
            ds = proj.get_dataset(dataset_name)
            ds.clear()
        else:
            ds = proj.create_upload_dataset(dataset_name, connection=connection)
        with local_path.open("rb") as f:
            ds.uploaded_add_file(f, local_path.name)
        # Warnings/suggestions first, status line LAST — `tail -1` automation
        # must capture the outcome, not a suggested-command fragment.
        if not no_autodetect:
            wants_sheets = bool(
                sheet or sheet_indices or all_sheets or sheets_to_column
            )
            _autodetect_and_warn(
                ds, dataset_name, project_key, quiet_warnings=wants_sheets
            )
            if wants_sheets:
                _apply_excel_sheet_targeting(
                    client,
                    dataset_name,
                    project_key,
                    sheet=sheet,
                    sheet_indices=sheet_indices,
                    all_sheets=all_sheets,
                    sheets_to_column=sheets_to_column,
                )
        hint(f"dku dataset schema {dataset_name} -P {project_key}")
        success(
            f"{'Replaced' if exists else 'Created'} dataset '{dataset_name}' "
            f"from {local_path.name}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def download(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset to export"),
    output: Path = typer.Argument(
        None, help="Local file to write ('-' or omitted: stdout)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    limit: int = typer.Option(
        None, "--limit", "-n", help="Max rows to download (default: all)"
    ),
) -> None:
    """Stream a dataset's rows to a local CSV (or stdout).

    The symmetric partner to `create-from-file` — pull DSS data onto disk so the
    agent can inspect or process it locally:

        dku dataset download customers ./customers.csv -P MYPROJ --limit 1000
    """
    import csv
    import sys

    # Honor the conventional '-' = stdout sentinel; without this, `download ds -`
    # silently creates a file literally named '-' in cwd.
    if output is not None and str(output) == "-":
        output = None

    if limit is not None and limit < 0:
        exit_with_error(
            "--limit must be a non-negative integer (0 writes header only).",
            status=2,
        )

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        cols = [c["name"] for c in ds.get_schema().get("columns", [])]

        fh = open(output, "w", newline="", encoding="utf-8") if output else sys.stdout
        n = 0
        try:
            writer = csv.writer(fh)
            if cols:
                writer.writerow(cols)
            for row in ds.iter_rows():
                if limit is not None and n >= limit:
                    break
                writer.writerow(row)
                n += 1
        finally:
            if output:
                fh.close()

        if output:
            success(f"Downloaded {n} rows from '{dataset_name}' → {output}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
    drop_data: bool = typer.Option(
        False,
        "--drop-data",
        help="Accepted for symmetry with 'project delete'; dataset delete always removes backing data.",
    ),
) -> None:
    """Delete a dataset.

    Before deleting, scans for recipes that have this dataset as an input or
    output and warns about cascade effects. When recipes consume the dataset
    as input, deleting it will also delete those recipes.
    """
    project_key = resolve_project(project)
    from dku_cli.safety import Tier, guard

    # Pre-query dependents BEFORE the safety guard so the cascade preview
    # makes it into the AGENT INSTRUCTION block (when --yes is missing).
    # Without this, the agent only sees a generic "Permanently delete X"
    # prompt and the user never learns recipes will be cascaded.
    # ds.get_usages() returns a list of dicts; field names vary slightly
    # across DSS versions so we handle both shapes.
    dependents: list[tuple[str, str]] = []
    usages_query_failed = False
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        usages = ds.get_usages() or []
        for u in usages:
            usage_type = u.get("type") or u.get("objectType") or ""
            obj_id = u.get("objectId") or u.get("id") or ""
            if not obj_id:
                continue
            if "RECIPE" in usage_type.upper():
                role = u.get("objectRole") or u.get("role") or ""
                reason = (
                    "uses as input"
                    if "INPUT" in role.upper()
                    else "produces"
                    if "OUTPUT" in role.upper()
                    else "depends on"
                )
                dependents.append((obj_id, reason))
    except Exception:
        # Non-fatal: bare delete still proceeds, but the prompt drops the
        # cascade preview and the user gets a "couldn't enumerate" warn.
        usages_query_failed = True

    cascade_lines: list[str] = []
    if dependents:
        cascade_lines.append(
            f" Will cascade-delete {len(dependents)} dependent recipe(s):"
        )
        for recipe_id, reason in dependents:
            cascade_lines.append(f"   - {recipe_id} ({reason})")
    base_prompt = (
        f"Permanently delete dataset '{dataset_name}' from project {project_key}? "
        f"This cannot be undone."
    )
    full_prompt = base_prompt + "".join("\n" + line for line in cascade_lines)

    guard(
        ctx,
        tier=Tier.DELETE,
        action="dataset.delete",
        subject=f"dataset '{dataset_name}' in project {project_key}",
        yes=yes,
        prompt=full_prompt,
    )
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)

        if usages_query_failed:
            warn(
                f"Could not enumerate dependents of '{dataset_name}' — "
                f"cascade effects unknown. Proceeding."
            )
        elif dependents:
            warn(
                f"Deleting '{dataset_name}' will also remove "
                f"{len(dependents)} dependent recipe(s):"
            )
            for recipe_id, reason in dependents:
                warn(f"  - {recipe_id} ({reason})")

        if drop_data:
            info(
                "Note: --drop-data is accepted for symmetry with 'project delete'; "
                "dataset delete always removes backing data."
            )

        ds.delete()
        success(f"Deleted dataset '{dataset_name}' from {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def clear(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Clear all data from a dataset."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="dataset.clear",
        subject=f"dataset '{dataset_name}' in project {project_key}",
        yes=yes,
        prompt=f"Wipe all rows from dataset '{dataset_name}' in project {project_key}? Data cannot be recovered.",
    )
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds.clear()
        success(f"Cleared dataset '{dataset_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get the full definition of a dataset as JSON."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds_def = ds.get_definition()
        render_raw(ds_def, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Definition JSON (string, @file.json, or '-' for stdin). Default is wholesale replace; pass --merge to overlay top-level keys onto the current definition, --deep-merge to recurse into nested dicts.",
    ),
    merge: bool = typer.Option(
        False,
        "--merge",
        help="Shallow merge: overlay top-level keys onto the existing definition instead of replacing it. Required to patch a single field (e.g. formatParams) without re-sending the entire def.",
    ),
    deep_merge: bool = typer.Option(
        False,
        "--deep-merge",
        help="Deep merge: recurse into nested dicts. Use to patch one field inside formatParams/params without losing siblings.",
    ),
) -> None:
    """Set the full definition of a dataset from JSON.

    Default is wholesale replace (callers send the entire definition).
    Pass --merge to overlay top-level keys, or --deep-merge to recurse — both
    GET the current definition, patch in memory, then PUT. Mirrors the merge
    flags on 'dku recipe set-definition'.
    """
    if merge and deep_merge:
        exit_with_error(
            "Use either --merge or --deep-merge, not both.",
        )
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        new_def = read_json_input(definition)
        if merge or deep_merge:
            current = ds.get_definition()
            if deep_merge:
                from dku_cli.commands.recipe._common import _deep_merge_dict

                merged = _deep_merge_dict(current, new_def)
            else:
                merged = dict(current)
                merged.update(new_def)
            ds.set_definition(merged)
        else:
            ds.set_definition(new_def)
        success(
            f"Updated definition for dataset '{dataset_name}'"
            + (" (deep-merged)" if deep_merge else (" (merged)" if merge else ""))
        )
        # Dataset definitions are typed settings: DSS silently drops unknown /
        # misplaced keys (exit 0, key gone). Re-read and diff the user's payload
        # so a mistyped field name fails loudly at the moment it happens.
        try:
            dropped = unpersisted_key_paths(new_def, ds.get_definition())
        except Exception:
            dropped = []
        if dropped:
            warn(
                f"Keys NOT persisted by DSS (unknown or misplaced): "
                f"{', '.join(dropped)}. Check field names against "
                f"'dku --format json dataset get-definition {dataset_name} "
                f"-P {project_key}'."
            )
    except typer.Exit:
        raise
    except Exception as e:
        if "projectKey" in str(e) and "missing" in str(e).lower():
            exit_with_error(
                f"Dataset definition update for '{dataset_name}' was rejected "
                "as incomplete.",
                details=[
                    "By default set-definition replaces the full dataset definition.",
                    "Patch one field with --deep-merge so required fields such "
                    "as projectKey/type/params are preserved:",
                    f"  dku dataset set-definition {dataset_name} "
                    f"-d '<partial-json>' --deep-merge -P {project_key}",
                    "Inspect the full shape: dku --format json "
                    f"dataset get-definition {dataset_name} -P {project_key}",
                ],
            )
        handle_api_error(e)


@app.command("set-schema")
def set_schema(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        "--columns",
        help=(
            "Schema as JSON (string, @file.json, '-' for stdin) OR shorthand "
            "'col type, col type, ...' (e.g. 'id int, name string, amount double')"
        ),
    ),
) -> None:
    """Set the schema of a dataset from JSON or shorthand.

    Accepts either {"columns": [{name, type}, ...]} or a plain
    [{name, type}, ...] array (auto-wrapped). The array form lets you
    round-trip with 'dku --format json dataset schema'.

    Shorthand: pass 'col1 type1, col2 type2' directly to -d for quick
    edits without a temp file. Example:
      dku dataset set-schema my_ds -d 'id int, name string, amount double' -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        current_def = ds.get_definition()
        schema_input = _parse_schema_input(definition)
        current_def["schema"] = schema_input
        ds.set_definition(current_def)
        success(f"Updated schema for dataset '{dataset_name}'")
    except Exception as e:
        handle_api_error(e)


_INT_RE = re.compile(r"^[+-]?\d+$")
_LEADING_ZERO_RE = re.compile(r"^0\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ].*)?$")
_BIGINT_MAX = 2**63 - 1


def _infer_column_type(values: list[str]) -> tuple[str, str]:
    """Infer a storage type from sampled string values.

    Returns (proposed_type, note). Conservative by design: every non-empty
    sampled value must parse, otherwise the column stays string. Date-like
    columns are reported but NOT retyped (set-schema `type: date` on file
    data reads all-null — the documented fix is a Prepare DateParser step).
    """
    non_empty = [v for v in values if v is not None and str(v).strip() != ""]
    if not non_empty:
        return "string", "no non-empty values sampled"
    vals = [str(v).strip() for v in non_empty]

    if all(_INT_RE.match(v) for v in vals):
        # Leading zeros mean identifier-like data (zip codes, account ids):
        # retyping would corrupt it by stripping the zeros.
        if any(_LEADING_ZERO_RE.match(v) for v in vals):
            return (
                "string",
                "integer-like but has leading zeros (identifier) — kept string",
            )
        if any(abs(int(v)) > _BIGINT_MAX for v in vals):
            return "string", "integer-like but exceeds bigint range — kept string"
        return "bigint", ""
    if all(_FLOAT_RE.match(v) for v in vals):
        return "double", ""
    if all(v.lower() in ("true", "false") for v in vals):
        return "boolean", ""
    if all(_ISO_DATE_RE.match(v) for v in vals):
        return (
            "string",
            "date-like — kept string; parse with a Prepare DateParser step "
            "(set-schema type:date on file data reads all-null)",
        )
    return "string", ""


def _collect_type_proposals(
    ds, columns: list[dict], string_cols: list[str], sample_rows: int
) -> tuple[list[dict], dict[str, str], int]:
    """Sample rows once and propose a storage type per string column.

    Returns (report_rows, {column: proposed_type}, rows_sampled).
    """
    all_names = [c.get("name") for c in columns]
    samples: dict[str, list] = {c: [] for c in string_cols}
    n_sampled = 0
    for i, row in enumerate(ds.iter_rows()):
        if i >= sample_rows:
            break
        n_sampled = i + 1
        full_row = dict(zip(all_names, row))
        for c in string_cols:
            samples[c].append(full_row.get(c))

    results: list[dict] = []
    changes: dict[str, str] = {}
    for c in string_cols:
        proposed, note = _infer_column_type(samples[c])
        if proposed != "string":
            changes[c] = proposed
        results.append(
            {"column": c, "current": "string", "proposed": proposed, "note": note}
        )
    return results, changes, n_sampled


@app.command("infer-types")
def infer_types(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    sample_rows: int = typer.Option(
        200, "--rows", "-n", help="Rows to sample for inference"
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Write the inferred types to the schema (default: dry-run report)",
    ),
) -> None:
    """Re-infer storage types for string columns from actual data and optionally apply.

    Upload autodetect and Prepare/visual-recipe outputs frequently leave
    numeric columns typed `string`, which breaks the next sum/avg/comparison.
    This samples real rows and proposes bigint/double/boolean for string
    columns where EVERY non-empty sampled value parses; date-like columns are
    reported but kept string (parse those with a Prepare DateParser step).

    Dry-run by default; pass --apply to write the schema. After applying,
    rebuild downstream datasets with --auto-update-schema to propagate.

    Example:
      dku dataset infer-types raw --apply -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds_def = ds.get_definition()
        columns = ds_def.get("schema", {}).get("columns", [])
        if not columns:
            exit_with_error(
                f"Dataset '{dataset_name}' has no columns — it likely has "
                "never been built.",
                details=[
                    f"Build it first: dku dataset build {dataset_name} "
                    f"-P {project_key} --wait",
                ],
            )

        string_cols = [c["name"] for c in columns if c.get("type") == "string"]
        if not string_cols:
            success(
                f"All {len(columns)} columns of '{dataset_name}' already have "
                "non-string types — nothing to infer."
            )
            return

        results, changes, n_sampled = _collect_type_proposals(
            ds, columns, string_cols, sample_rows
        )
        render(
            results,
            ["column", "current", "proposed", "note"],
            output_format=fmt,
            title=f"Type inference: {dataset_name} (sampled {n_sampled} rows)",
        )

        if not changes:
            info("No type changes proposed — all string columns look genuinely string.")
            return

        if not apply:
            info(
                f"{len(changes)} column(s) would change. Apply with: "
                f"dku dataset infer-types {dataset_name} --apply -P {project_key}"
            )
            return

        for col in columns:
            if col.get("name") in changes:
                col["type"] = changes[col["name"]]
        ds.set_definition(ds_def)
        success(
            f"Applied {len(changes)} type change(s) to '{dataset_name}': "
            + ", ".join(f"{k}→{v}" for k, v in changes.items())
        )
        # Only meaningful for external SQL tables: DSS cannot alter the source
        # column types there. File-based datasets (UploadedFiles, Filesystem)
        # cast at read time, and managed SQL tables are recreated on rebuild.
        if not ds_def.get("managed", True) and _resolve_sql_table(ds_def, project_key):
            warn(
                "This dataset reads an EXTERNAL table — the schema change does "
                "not alter the source storage type. Fix types at the source or "
                "via a Sync/Prepare recipe if reads error."
            )
        info(
            "Rebuild downstream datasets to propagate: "
            f"dku job run --target <downstream> -P {project_key} "
            "--type RECURSIVE_FORCED_BUILD --auto-update-schema --wait"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _parse_schema_input(value: str) -> dict:
    """Parse a schema definition from JSON, file, stdin, or shorthand.

    Shorthand form is 'col type, col type' — e.g. 'id int, amount double'.
    JSON forms accepted: {"columns": [...]}, plain [...] array, @file.json, '-'.
    """
    shorthand = _parse_schema_shorthand(value)
    if shorthand is not None:
        return shorthand
    try:
        schema_input = read_json_input(value)
    except typer.BadParameter as exc:
        raise typer.BadParameter(
            f"{exc}\n--definition accepts: JSON literal, @file.json, '-' for "
            "stdin, OR shorthand 'col1 type1, col2 type2'."
        ) from exc
    if isinstance(schema_input, list):
        return {"columns": schema_input}
    if isinstance(schema_input, dict):
        return schema_input
    raise typer.BadParameter(
        "--definition must be a JSON object, JSON array, or shorthand "
        "'col type, col type'."
    )


def _parse_schema_shorthand(value: str) -> dict | None:
    """Try to parse 'col type, col type' shorthand. Returns None if not shorthand.

    Bails out (returns None) on any structural ambiguity so the caller falls
    through to JSON parsing. Strict matching: every comma-separated chunk must
    be exactly two whitespace-separated tokens.
    """
    if not value:
        return None
    stripped = value.strip()
    # JSON / file / stdin always wins — never try shorthand on those
    if stripped.startswith(("{", "[", "@")) or stripped == "-":
        return None
    import shlex

    cols = []
    for chunk in stripped.split(","):
        try:
            parts = shlex.split(chunk.strip())
        except ValueError:
            return None
        if len(parts) != 2:
            return None
        name, ctype = parts
        # Reject obviously non-identifier names (basic sanity)
        if not name or any(c in name for c in "{}[]\\"):
            return None
        cols.append({"name": name, "type": ctype})
    if not cols:
        return None
    return {"columns": cols}


@app.command()
def rename(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Current dataset name"),
    new_name: str = typer.Option(..., "--name", help="New dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Rename a dataset."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds.rename(new_name)
        success(f"Renamed '{dataset_name}' to '{new_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def copy(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Source dataset name"),
    to_project: str = typer.Option(..., "--to-project", help="Target project key"),
    name: str | None = typer.Option(
        None, "--name", help="Name in target project (default: same name)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Copy a dataset to another project."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        new_name = name or dataset_name
        target_ds = client.get_project(to_project).get_dataset(new_name)
        ds.copy_to(target_ds)
        success(f"Copied '{dataset_name}' to {to_project}.{new_name}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def partitions(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List partitions of a dataset."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        parts = ds.list_partitions()
        data = [{"partition": p} for p in parts]
        render(
            data,
            ["partition"],
            output_format=output,
            title=f"Partitions ({dataset_name})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Dataset description"
    ),
    short_desc: str | None = typer.Option(
        None, "--short-desc", help="Short description (shown in dataset list)"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update dataset description, short description, and/or tags.

    Unlike set-definition, this is a targeted update — no JSON needed.
    Use after creating a dataset to document what it contains.
    """
    if description is None and short_desc is None and tags is None:
        error("Provide --description, --short-desc, and/or --tags to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        meta = ds.get_metadata()

        if description is not None:
            meta["description"] = description
        if short_desc is not None:
            meta["shortDesc"] = short_desc
        if tags is not None:
            meta["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        ds.set_metadata(meta)
        success(f"Updated metadata for dataset '{dataset_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-column-description")
def set_column_description(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    columns: list[str] = typer.Argument(
        help='Column-description pairs: col1 "desc1" col2 "desc2"'
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set descriptions on dataset columns.

    Pass alternating column names and descriptions:
      dku dataset set-column-description DS col1 "Revenue total" col2 "Customer ID" -P PROJ

    Column descriptions appear in the schema view and help document data meaning.
    """
    if len(columns) % 2 != 0:
        exit_with_error(
            "Arguments must be column-description pairs (even count).",
            details=[
                'Usage: dku dataset set-column-description DS col1 "desc1" col2 "desc2" -P PROJ',
                f"Got {len(columns)} arguments — must be even (column name, description, column name, description, ...).",
            ],
        )
    pairs = dict(zip(columns[0::2], columns[1::2]))
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds_def = ds.get_definition()
        schema_cols = ds_def.get("schema", {}).get("columns", [])

        updated = 0
        for col in schema_cols:
            if col["name"] in pairs:
                col["comment"] = pairs[col["name"]]
                updated += 1

        # Warn on unknown columns
        known_names = {c["name"] for c in schema_cols}
        unknown = set(pairs.keys()) - known_names
        if unknown:
            warn(f"Column(s) not in schema (skipped): {', '.join(sorted(unknown))}")

        ds.set_definition(ds_def)
        success(f"Updated descriptions for {updated} column(s) in '{dataset_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("ai-describe")
def ai_describe(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    language: str = typer.Option(
        "english",
        "--language",
        "-l",
        help="Language (english, french, german, dutch, portuguese, spanish)",
    ),
    save: bool = typer.Option(
        False, "--save", help="Save generated descriptions to the dataset"
    ),
) -> None:
    """Generate AI-powered descriptions for a dataset and its columns.

    Requires 'Generate Metadata' enabled in DSS AI Services admin settings.
    Rate-limited: 1000 requests/day, then throttled (~60s per request).

    Without --save, displays suggestions. With --save, persists to the dataset.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        result = ds.generate_ai_description(language=language, save_description=save)

        if save:
            success(f"AI descriptions saved to dataset '{dataset_name}'")
        else:
            info("AI-generated descriptions (not saved — use --save to persist):")

        render_raw(result, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def exists(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Check whether a dataset exists (exit code 0 = yes, 1 = no).

    Use before creating datasets to avoid duplicates, or in scripts to
    branch on dataset existence.

    Example:
      dku dataset exists my_data -P PROJ && echo "found"
      dku dataset exists my_data -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        found = ds.exists()

        if fmt == "json":
            render_raw(
                {"exists": found, "name": dataset_name, "project": project_key},
                output_format="json",
            )
        else:
            if found:
                success(f"Dataset '{dataset_name}' exists in {project_key}")
            else:
                info(f"Dataset '{dataset_name}' does not exist in {project_key}")

        raise typer.Exit(0 if found else 1)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _scan_insight_consumers(proj, dataset_name: str) -> list[dict]:
    """Walk every insight in the project; return rows for those whose
    `params.datasetSmartName` matches `dataset_name`.

    Closes the recurring deletion-safety question — bare get_usages()
    only returns recipe / analysis / model bindings, not chart-insight
    bindings. Without this, "is this dataset orphaned?" required a
    hand-rolled jq pipeline across two endpoints.
    """
    rows: list[dict] = []
    try:
        insights = proj.list_insights() or []
    except Exception:
        return rows
    for ins in insights:
        iid = ins.get("id", "")
        if not iid:
            continue
        try:
            raw = proj.get_insight(iid).get_settings().get_raw()
        except Exception:
            continue
        params = raw.get("params") or {}
        smart_name = params.get("datasetSmartName") or params.get("datasetName")
        if smart_name and (
            smart_name == dataset_name or smart_name.endswith(f".{dataset_name}")
        ):
            rows.append(
                {
                    "type": "INSIGHT",
                    "id": iid,
                    "project": raw.get("projectKey", ""),
                    "name": raw.get("name", ""),
                    "kind": raw.get("type", ""),
                }
            )
    return rows


def _scan_dashboard_tile_consumers(
    proj, dataset_name: str, insight_ids_using: set[str]
) -> list[dict]:
    """Walk every dashboard's pages[*].grid.tiles[*]; report tiles whose
    `tileParams.insightId` references an insight that consumes the dataset.

    Insight IDs already known to bind the dataset are passed in via
    `insight_ids_using` so we don't refetch each insight. Direct dataset
    bindings on tiles (rare — most tiles route through insights) are also
    surfaced via `tileParams.datasetSmartName` if present.
    """
    rows: list[dict] = []
    try:
        dashboards = proj.list_dashboards() or []
    except Exception:
        return rows
    for d in dashboards:
        did = d.get("id") if isinstance(d, dict) else None
        if not did:
            continue
        try:
            raw = proj.get_dashboard(did).get_settings().get_raw()
        except Exception:
            continue
        for page in raw.get("pages") or []:
            for tile in (page.get("grid") or {}).get("tiles") or []:
                params = tile.get("tileParams") or {}
                ref_iid = params.get("insightId")
                ref_ds = params.get("datasetSmartName") or params.get("datasetName")
                if (ref_iid and ref_iid in insight_ids_using) or (
                    ref_ds
                    and (ref_ds == dataset_name or ref_ds.endswith(f".{dataset_name}"))
                ):
                    rows.append(
                        {
                            "type": "DASHBOARD_TILE",
                            "id": did,
                            "project": raw.get("projectKey", ""),
                            "name": raw.get("name", ""),
                            "kind": tile.get("tileType", ""),
                        }
                    )
                    # Don't double-count if both fields point at it
                    break
    return rows


@app.command()
def usages(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    include_charts: bool = typer.Option(
        False,
        "--include-charts",
        help="Also scan insights and dashboard tiles for references "
        "(N+1 calls — only for deletion-safety checks).",
    ),
) -> None:
    """Show what recipes, analyses, or models use this dataset.

    Use to investigate the flow graph: which downstream recipes consume
    this dataset, and which upstream recipes produce it.

    Pass --include-charts to ALSO scan every insight (`params.datasetSmartName`)
    and every dashboard tile (`tileParams.insightId` chained to a matching
    insight). This costs O(insights + dashboards) extra API calls but
    closes the deletion-safety question that bare `usages` can't answer.

    Example:
      dku dataset usages my_data -P PROJ
      dku dataset usages my_data -P PROJ --include-charts
      dku dataset usages my_data -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        ds = proj.get_dataset(dataset_name)
        usage_list = ds.get_usages() or []

        rows: list[dict] = []
        for u in usage_list:
            rows.append(
                {
                    "type": u.get("type", u.get("objectType", "")),
                    "id": u.get("objectId", u.get("id", "")),
                    "project": u.get(
                        "objectProjectKey", u.get("projectKey", project_key)
                    ),
                    "name": "",
                    "kind": "",
                }
            )

        if include_charts:
            insight_rows = _scan_insight_consumers(proj, dataset_name)
            rows.extend(insight_rows)
            insight_ids_using = {r["id"] for r in insight_rows}
            rows.extend(
                _scan_dashboard_tile_consumers(proj, dataset_name, insight_ids_using)
            )

        if fmt == "json":
            render_raw(rows, output_format="json")
            return

        if not rows:
            scope = (
                "any recipe, analysis, model, insight, or dashboard tile"
                if include_charts
                else "any recipe, analysis, or model"
            )
            info(
                f"No usages found for dataset '{dataset_name}' in {project_key}. "
                f"This dataset is not referenced by {scope}."
            )
            if not include_charts:
                info(
                    "  Pass --include-charts to also scan insights and "
                    "dashboard tiles before deleting."
                )
            return

        columns = ["type", "id", "name", "kind", "project"]
        render(
            rows,
            columns,
            output_format=fmt,
            title=f"Usages of {dataset_name}",
            headers={
                "type": "TYPE",
                "id": "ID",
                "name": "NAME",
                "kind": "KIND",
                "project": "PROJECT",
            },
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def lineage(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    column: str = typer.Option(..., "--column", "-c", help="Column name to trace"),
    max_datasets: int | None = typer.Option(
        None,
        "--max-datasets",
        help="Maximum number of datasets to query for lineage (default: DSS hard limit)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Trace a column's provenance across the flow graph.

    Shows which upstream datasets and columns feed into the specified
    column, including cross-project lineage.

    Example:
      dku dataset lineage my_data --column revenue -P PROJ
      dku dataset lineage my_data -c customer_id -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        relations = ds.get_column_lineage(column, max_dataset_count=max_datasets)

        if fmt == "json":
            render_raw(relations, output_format="json")
        else:
            if not relations:
                info(
                    f"No lineage found for column '{column}' in {dataset_name}. "
                    "The column may be a source column with no upstream provenance, "
                    "or lineage has not been computed yet."
                )
                return

            data = []
            for rel in relations:
                # Real API returns inputDataset/inputColumn/outputDataset/outputColumn
                data.append(
                    {
                        "source_dataset": rel.get(
                            "inputDataset", rel.get("sourceDataset", "")
                        ),
                        "source_column": rel.get(
                            "inputColumn", rel.get("sourceColumn", "")
                        ),
                        "target_dataset": rel.get(
                            "outputDataset", rel.get("targetDataset", "")
                        ),
                        "target_column": rel.get(
                            "outputColumn", rel.get("targetColumn", "")
                        ),
                    }
                )

            render(
                data,
                [
                    "source_dataset",
                    "source_column",
                    "target_dataset",
                    "target_column",
                ],
                output_format=fmt,
                title=f"Column Lineage: {dataset_name}.{column}",
                headers={
                    "source_dataset": "SOURCE DS",
                    "source_column": "SOURCE COL",
                    "target_dataset": "TARGET DS",
                    "target_column": "TARGET COL",
                },
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def detect(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    save: bool = typer.Option(
        False, "--save", help="Save detected format and schema to the dataset"
    ),
    infer_types: bool = typer.Option(
        False,
        "--infer-types",
        help="Infer storage types (e.g. int vs string) instead of defaulting to string",
    ),
    keep_format: bool = typer.Option(
        False,
        "--keep-format",
        help="Re-infer the SCHEMA only, preserving the saved formatType/formatParams "
        "(full detection resets manual params, e.g. an Excel sheet selection).",
    ),
) -> None:
    """Detect format and schema for a dataset.

    Runs DSS auto-detection to discover the format type, format params,
    and column schema. Works for filesystem, SQL, and Elasticsearch datasets.

    Without --save, shows what was detected. With --save, persists to the dataset.

    Full detection re-detects the FORMAT too, resetting manual formatParams
    (an Excel sheet selection snaps back to the first sheet). After hand-editing
    format params, use --keep-format to re-infer only the columns.

    Example:
      dku dataset detect my_data -P PROJ
      dku dataset detect my_data --save --infer-types -P PROJ
      dku dataset detect my_data --save --keep-format -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        detected = _run_detection(
            client, ds, project_key, dataset_name, infer_types, keep_format
        )
        if save:
            detected.save()

        raw = detected.get_raw()
        format_type = raw.get("formatType", "")
        schema_cols = raw.get("schema", {}).get("columns", [])

        if fmt == "json":
            render_raw(
                {
                    "format_type": format_type,
                    "format_params": raw.get("formatParams", {}),
                    "columns": schema_cols,
                },
                output_format="json",
            )
        else:
            if save:
                success(
                    f"Detected and saved: {format_type} format, "
                    f"{len(schema_cols)} columns for '{dataset_name}'"
                )
            else:
                info(f"Detected format: {format_type} ({len(schema_cols)} columns)")
                info("Run with --save to persist these settings.")

            if schema_cols:
                data = [
                    {"name": c.get("name", ""), "type": c.get("type", "")}
                    for c in schema_cols
                ]
                render(
                    data,
                    ["name", "type"],
                    output_format=fmt,
                    title=f"Detected Schema: {dataset_name}",
                )

            string_cols = [c for c in schema_cols if c.get("type") == "string"]
            if schema_cols and len(string_cols) == len(schema_cols):
                warn(
                    "All columns detected as STRING. Use --infer-types to detect "
                    "numeric/date types, or fix manually with set-schema."
                )
    except ValueError as e:
        exit_with_error(
            str(e),
            details=[
                "Dataset type may not support auto-detection.",
                f"Check type: dku dataset info {dataset_name} -P {project_key}",
            ],
        )
    except typer.Exit:
        raise
    except Exception as e:
        msg = str(e)
        if "Format detection failed" in msg or "empty" in msg.lower():
            exit_with_error(
                f"Format detection failed for '{dataset_name}'.",
                details=[
                    "The dataset may be empty or have no data to detect from.",
                    f"Upload data first: dku dataset upload {dataset_name} FILE -P {project_key}",
                    f"Or set schema manually: dku dataset set-schema {dataset_name} -d @schema.json -P {project_key}",
                ],
            )
        handle_api_error(e)


@app.command()
def zone(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show which flow zone a dataset belongs to.

    Example:
      dku dataset zone my_data -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        # DSS raises NotFoundException when the dataset is in the default zone
        # (no zone membership has been explicitly set). Treat that as success.
        try:
            z = ds.get_zone()
            zone_id = z.id
            zone_name = z.name
        except Exception as e:
            if is_not_found_error(e) and "flow zone" in str(e).lower():
                zone_id = "default"
                zone_name = "Default"
            else:
                raise

        if fmt == "json":
            render_raw(
                {"zone_id": zone_id, "zone_name": zone_name, "dataset": dataset_name},
                output_format="json",
            )
        else:
            success(
                f"Dataset '{dataset_name}' is in zone '{zone_name}' (ID: {zone_id})"
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def share(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    zone_id: str = typer.Option(
        ..., "--zone", "-z", help="Zone name or ID to share to"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Share a dataset to another flow zone.

    Sharing makes the dataset visible in the target zone without moving it.

    Example:
      dku dataset share my_data --zone Analytics -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds.share_to_zone(zone_id)
        success(f"Shared dataset '{dataset_name}' to zone '{zone_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def unshare(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    zone_id: str = typer.Option(
        ..., "--zone", "-z", help="Zone name or ID to unshare from"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Unshare a dataset from a flow zone.

    Example:
      dku dataset unshare my_data --zone Analytics -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds.unshare_from_zone(zone_id)
        success(f"Unshared dataset '{dataset_name}' from zone '{zone_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _resolve_sql_table(ds_def: dict, project_key: str) -> tuple[str, str] | None:
    """Resolve an in-database table-mode dataset to (connection, physical_table).

    DSS stores the physical table as a template like '${projectKey}_ORDERS'; the
    agent otherwise has to fetch the definition, substitute the project key by hand,
    and remember the case rules. We resolve it here so a logical dataset name is
    enough. Catalog/schema are prefixed when set. Returns None for non-table-backed
    datasets (Filesystem/Uploaded/Inline, SQL datasets with no table, or query-mode
    SQL datasets whose params mode is not 'table').
    """
    params = ds_def.get("params", {})
    connection = params.get("connection")
    table = params.get("table")
    if not connection or not table:
        return None
    # A query-mode SQL dataset may carry a leftover/templated 'table' value, but
    # DSS evaluates its customQuery, not that table. dataikuapi gates physical-table
    # handling on params['mode'] == 'table' (codegen.py). Treat an explicitly
    # non-'table' mode (e.g. 'query') as not table-backed so callers fall back to
    # the metric path. An absent 'mode' is left as table-backed for compatibility
    # with UI/legacy table datasets that omit the key.
    mode = params.get("mode")
    if mode is not None and mode != "table":
        return None

    def _sub(value):
        return (
            value.replace("${projectKey}", project_key)
            if isinstance(value, str)
            else value
        )

    qualified = ".".join(
        p
        for p in (_sub(params.get("catalog")), _sub(params.get("schema")), _sub(table))
        if p
    )
    return connection, qualified


def _row_count_via_metrics(ds) -> int | None:
    """Compute and read the COUNT_RECORDS metric (works for any dataset type)."""
    try:
        ds.compute_metrics(metric_ids=["records:COUNT_RECORDS"])
    except Exception:
        pass  # fall through to read whatever value is available
    try:
        return ds.get_last_metric_values().get_global_value("records:COUNT_RECORDS")
    except Exception:
        return None


@app.command()
def count(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    where: str = typer.Option(
        None,
        "--where",
        "-w",
        help="SQL WHERE clause (SQL-backed datasets only). Snowflake folds "
        "unquoted identifiers to UPPER — quote lowercase columns.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Count rows in a dataset by its logical name.

    SQL-backed datasets resolve the physical table and run SELECT COUNT(*) (so
    --where is supported and the count is exact and cheap). Other dataset types
    fall back to the COUNT_RECORDS metric. Replaces the raw-SQL-with-physical-table
    detour for the common "how many rows?" check.

    Examples:
      dku dataset count orders -P PROJ
      dku dataset count orders --where "\\"status\\" = 'SETTLED'" -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds_def = ds.get_definition()
        resolved = _resolve_sql_table(ds_def, project_key)

        if resolved is not None:
            connection, table = resolved
            sql = f"SELECT COUNT(*) AS n FROM {table}"
            if where:
                sql += f" WHERE {where}"
            result = client.sql_query(sql, connection=connection)
            rows = list(result.iter_rows())
            n = int(rows[0][0]) if rows else 0
            source = "sql"
        else:
            if where:
                exit_with_error(
                    f"--where is only supported on SQL-backed datasets; "
                    f"'{dataset_name}' is type '{ds_def.get('type')}'.",
                    details=[
                        "Filter first with a recipe: dku recipe create-filter ...",
                        "Or count unfiltered (drop --where).",
                    ],
                )
            n = _row_count_via_metrics(ds)
            source = "metric"
            if n is None:
                build_cmd = f"dku dataset build {dataset_name} -P {project_key}"
                exit_with_error(
                    f"Could not compute a row count for '{dataset_name}'.",
                    details=[f"Build it first: {build_cmd} --wait"],
                )
            n = int(n)

        if fmt == "json":
            render_raw(
                {"dataset": dataset_name, "count": n, "where": where, "source": source},
                output_format="json",
            )
        else:
            render(
                [{"dataset": dataset_name, "rows": str(n), "where": where or "(all)"}],
                ["dataset", "rows", "where"],
                output_format=fmt,
                title=f"Row Count: {dataset_name}",
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def query(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="SQL-backed dataset name"),
    sql: str = typer.Option(
        ...,
        "--sql",
        "-q",
        help="SQL to run. Use {{table}} for the dataset's resolved physical table.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Run SQL against a dataset's backing table by logical name.

    Resolves the dataset's connection + physical table so you don't hand-resolve
    '${projectKey}_<NAME>' or look up the connection. Use the {{table}} token in
    your SQL for the resolved physical table. SQL-backed (in-database) datasets only.

    Example:
      dku dataset query orders -q "SELECT COUNT(*) FROM {{table}}" -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ds_def = ds.get_definition()
        resolved = _resolve_sql_table(ds_def, project_key)
        if resolved is None:
            head_cmd = f"dku dataset head {dataset_name} -P {project_key}"
            exit_with_error(
                f"'{dataset_name}' is not a SQL-table-backed dataset "
                f"(type '{ds_def.get('type')}') — cannot run SQL against it.",
                details=[
                    "Use this on Snowflake/PostgreSQL/BigQuery table-mode datasets.",
                    f"For file datasets, read rows: {head_cmd}",
                ],
            )
        connection, table = resolved
        query_text = sql.replace("{{table}}", table)
        result = client.sql_query(query_text, connection=connection)
        schema = result.get_schema()
        columns = [col["name"] for col in schema]
        data = [dict(zip(columns, row)) for row in result.iter_rows()]
        render(
            data,
            columns,
            output_format=fmt,
            title=f"Query: {dataset_name} ({connection})",
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

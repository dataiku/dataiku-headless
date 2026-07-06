"""Window visual recipe commands."""

from __future__ import annotations

from dku_cli.enums import EngineType, FrameMode, LagDateUnit

# ruff: noqa: F403,F405
from ._common import *

_VALID_WINDOW_TYPES = frozenset(
    {
        "lag",
        "lead",
        "lagDiff",
        "leadDiff",
        "rank",
        "denseRank",
        "rowNumber",
        "sum",
        "avg",
        "min",
        "max",
        "count",
        "countDistinct",
        "first",
        "last",
        "firstLastNotNull",
        "stddev",
        "concat",
        "concatDistinct",
    }
)
# These are top-level booleans in the DSS payload, not per-column
_TOP_LEVEL_WINDOW_TYPES = frozenset({"rank", "denseRank", "rowNumber"})
# These are per-column boolean flags in the values[] array
_COLUMN_WINDOW_TYPES = frozenset(
    {
        "lag",
        "lead",
        "lagDiff",
        "leadDiff",
        "sum",
        "avg",
        "min",
        "max",
        "count",
        "countDistinct",
        "first",
        "last",
        "firstLastNotNull",
        "stddev",
        "concat",
        "concatDistinct",
    }
)


def _parse_compute_specs(specs: list[str]) -> list[dict]:
    """Parse --compute specs into computation dicts. Three accepted shapes:

    - 'TYPE:column'                — source-required types (sum/avg/lag/...).
      Output column auto-named '<column>_<type>' to match DSS's default.
    - 'TYPE:column:output_column'  — explicit rename.
    - 'TYPE::output_column' or 'TYPE:output_column' — top-level types
      (rank/denseRank/rowNumber) where the source column is meaningless.
    """
    parsed = []
    for comp_spec in specs:
        parts = comp_spec.split(":")
        comp_type = parts[0]
        if comp_type not in _VALID_WINDOW_TYPES:
            exit_with_error(
                f"Unknown window computation type: '{comp_type}'.",
                details=[f"Valid types: {', '.join(sorted(_VALID_WINDOW_TYPES))}"],
            )
        if len(parts) == 2:
            # 'TYPE:second' — meaning depends on whether the type takes a column.
            second = parts[1]
            if comp_type in _TOP_LEVEL_WINDOW_TYPES:
                # rank/denseRank/rowNumber: second is the output name.
                source_col = None
                output_col = second
            else:
                # sum/avg/lag/...: second is the source column.
                # Auto-name the output as DSS would (<col>_<type>).
                source_col = second
                output_col = f"{second}_{comp_type.lower()}"
        elif len(parts) == 3:
            # TYPE:column:output_column (empty column OK for rank types)
            source_col = parts[1] or None
            output_col = parts[2]
        else:
            exit_with_error(
                f"Invalid --compute format: '{comp_spec}'.",
                details=[
                    "Expected forms:",
                    "  'TYPE:column'                  — sum/avg/lag/... (output auto-named '<col>_<type>')",
                    "  'TYPE:column:output_column'    — explicit output name",
                    "  'TYPE::output_column'          — rank/denseRank/rowNumber",
                    "Examples: --compute 'sum:amount' --compute 'lag:price:price_lag1' --compute 'rank::row_rank'",
                ],
            )
        if comp_type not in _TOP_LEVEL_WINDOW_TYPES and not source_col:
            exit_with_error(
                f"Computation type '{comp_type}' requires a source column.",
                details=[
                    f"Use: --compute '{comp_type}:COLUMN' (output auto-named) or "
                    f"--compute '{comp_type}:COLUMN:OUTPUT_COLUMN' (explicit)."
                ],
            )
        entry: dict = {"type": comp_type, "outputColumn": output_col}
        if source_col:
            entry["column"] = source_col
        parsed.append(entry)
    return parsed


def _parse_offsets_spec(specs: list[str], flag: str) -> dict[str, list[int]]:
    """Parse 'COL:1,2,3' multi-offset specs."""
    parsed: dict[str, list[int]] = {}
    for spec in specs:
        if ":" not in spec:
            exit_with_error(
                f"Invalid {flag} '{spec}'. Expected 'COL:OFFSET[,OFFSET...]'.",
            )
        col, offsets_str = spec.split(":", 1)
        offsets: list[int] = []
        for part in offsets_str.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                offsets.append(int(part))
            except ValueError:
                exit_with_error(
                    f"Invalid {flag} '{spec}': offsets must be integers (got '{part}').",
                )
        if not offsets:
            exit_with_error(
                f"Invalid {flag} '{spec}': at least one integer offset is required.",
            )
        parsed[col.strip()] = offsets
    return parsed


def _apply_offset_specs(
    payload: dict, offsets_by_col: dict[str, list[int]], op: str
) -> None:
    """Apply lag/lead multi-offset specs to a Window payload values[] entry.

    DSS uses `lagValues` / `leadValues` as a comma-separated string on the
    per-column entry, plus the boolean `lag` / `lead` flag set to true.
    """
    if not offsets_by_col:
        return
    values = payload.setdefault("values", [])
    for col, offsets in offsets_by_col.items():
        col_entry = None
        for v in values:
            if v.get("column") == col:
                col_entry = v
                break
        if col_entry is None:
            col_entry = {"column": col, "value": False}
            values.append(col_entry)
        col_entry[op] = True
        col_entry[f"{op}Values"] = ",".join(str(o) for o in offsets)


def _apply_window_computations(
    payload: dict, computations: list[dict], recipe_name: str = ""
) -> None:
    """Apply parsed --compute specs to a Window recipe obj_payload.

    DSS Window recipes use two mechanisms:
    - Top-level booleans: rowNumber, rank, denseRank (global, not per-column)
    - values[] array: per-column flags like lag, lead, sum, avg, etc.

    **DSS does not support custom output column names for window computations.**
    Top-level computations produce fixed names (`rownumber`, `rank`, `denserank`).
    Per-column computations produce `${col}_${func}`. If the user provided a
    third colon segment (e.g. `rowNumber::my_rn`), we warn and point at the
    post-recipe rename workaround.
    """
    values = payload.setdefault("values", [])
    custom_names: list[tuple[str, str, str]] = []  # (type, source, requested_name)

    for comp in computations:
        comp_type = comp["type"]
        output_col = comp.get("outputColumn") or ""
        source_col = comp.get("column") or ""

        # Work out what DSS is going to name this column given the payload.
        if comp_type in _TOP_LEVEL_WINDOW_TYPES:
            dss_name = comp_type.lower()
            # Enable the top-level flag
            payload[comp_type] = True
        else:
            # Per-column flag — DSS generates `${col}_${func}`
            dss_name = f"{source_col}_{comp_type.lower()}"
            # Find or create the column entry in values[]
            col_entry = None
            for v in values:
                if v.get("column") == source_col:
                    col_entry = v
                    break
            if col_entry is None:
                col_entry = {"column": source_col, "value": False}
                values.append(col_entry)
            col_entry[comp_type] = True

        # If the user asked for a custom name that doesn't match what DSS
        # will produce, queue a warning.
        if output_col and output_col != dss_name:
            custom_names.append((comp_type, source_col, output_col))

    if custom_names:
        target = recipe_name or "<recipe>"
        warn(
            "DSS does not support custom output column names for window "
            "computations — the column will be named by the computation type, "
            "not by your third --compute segment."
        )
        for comp_type, source_col, requested in custom_names:
            actual = (
                comp_type.lower()
                if comp_type in _TOP_LEVEL_WINDOW_TYPES
                else f"{source_col}_{comp_type.lower()}"
            )
            info(
                f"  --compute '{comp_type}:{source_col}:{requested}' → column '{actual}'"
            )
        info(
            "To rename after build, chain a Prepare recipe: "
            f"dku recipe create rename_{target} -t prepare -i OUTPUT_DS --output-ds OUTPUT_DS_renamed -P PROJ "
            "&& dku recipe add-rename rename_<recipe> --from <actual> --to <desired> -P PROJ"
        )


@app.command("create-window")
def create_window(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    partition_key: list[str] | None = typer.Option(
        None,
        "--partition-key",
        "--partition-col",
        "--partition",
        "-k",
        help="PARTITION BY column (repeatable). Defines groups for window functions.",
    ),
    order_key: list[str] | None = typer.Option(
        None,
        "--order-key",
        "--order-col",
        "--order",
        help="ORDER BY column. Append ':desc' for descending (default: ascending). Repeatable.",
    ),
    compute: list[str] | None = typer.Option(
        None,
        "--compute",
        help=(
            "Window computation. Three accepted forms: "
            "(1) 'TYPE:column' for sum/avg/lag/etc. — output auto-named "
            "'<column>_<type>' to match DSS's default. "
            "(2) 'TYPE:column:output_column' — output_column is ADVISORY ONLY "
            "(DSS ignores it; see NOTE below — use --rename SRC:DST to rename). "
            "(3) 'TYPE::output' for rank/denseRank/rowNumber (no source column). "
            "Types: lag, lead, lagDiff, leadDiff, rank, denseRank, rowNumber, "
            "sum, avg, min, max, count, countDistinct, first, last, "
            "firstLastNotNull, stddev, concat, concatDistinct. "
            "lagDiff/leadDiff = current value MINUS lag/lead value (delta). "
            "firstLastNotNull = first non-null value in ordering (handles "
            "gappy timeseries). concat/concatDistinct = string aggregation "
            "(LISTAGG-equivalent within partition). "
            "NOTE: the output_column segment is advisory — DSS names columns by "
            "type (top-level: 'rownumber'/'rank'/'denserank') or "
            "'<col>_<type>' (per-column: 'price_lag', 'price_avg'). "
            "To force a different name, use --rename SRC:DST. Repeatable."
        ),
    ),
    lag_offsets: list[str] | None = typer.Option(
        None,
        "--lag-offsets",
        help=(
            "Multi-offset lag: 'COL:1,2,3' produces COL_lag1, COL_lag2, "
            "COL_lag3 in one recipe. Replaces the multi-recipe workaround "
            "for moving averages with N preceding values. Repeatable per "
            "column."
        ),
    ),
    lead_offsets: list[str] | None = typer.Option(
        None,
        "--lead-offsets",
        help="Multi-offset lead: 'COL:1,2,3'. Same shape as --lag-offsets.",
    ),
    lag_date_unit: LagDateUnit | None = typer.Option(
        None,
        "--lag-date-unit",
        case_sensitive=False,
        help=(
            "When lagging/leading a date column, the unit DSS uses to compute the "
            "offset (DAY, HOUR, MONTH, ...). Sets dateDiffUnit on each affected "
            "values[] entry. Default in DSS: DAY."
        ),
    ),
    rename: list[str] | None = typer.Option(
        None,
        "--rename",
        help=(
            "Rename a generated window output column: 'SRC:DST'. Writes "
            "outputColumnNameOverrides. Use to disambiguate when two Window "
            "recipes feed the same downstream and would collide on default "
            "names. Repeatable."
        ),
    ),
    frame_preceding: int | None = typer.Option(
        None,
        "--frame-preceding",
        help="Window frame: number of preceding rows (sets precedingRows + limitPreceding=true).",
    ),
    frame_following: int | None = typer.Option(
        None,
        "--frame-following",
        help="Window frame: number of following rows (sets followingRows + limitFollowing=true).",
    ),
    frame_unbounded: bool = typer.Option(
        False,
        "--frame-unbounded",
        help="Window frame: unbounded preceding & following (sets enableLimits=false).",
    ),
    frame_mode: FrameMode | None = typer.Option(
        None,
        "--frame-mode",
        case_sensitive=False,
        help=(
            "Frame interpretation: ROWS (default — N rows around current row) "
            "or RANGE (value-based on the order column — e.g. 'all rows whose "
            "order_date is within 30 days of current'). Sets "
            "windows[0].windowLimitMode. RANGE is the only way to express "
            "date-range windows without padding to one-row-per-day."
        ),
    ),
    range_lower: int | None = typer.Option(
        None,
        "--range-lower",
        help=(
            "Lower bound for --frame-mode RANGE (negative = past). E.g. "
            "--range-lower -30 with --order-key order_date counts rows whose "
            "order_date is up to 30 days before the current row's. Sets "
            "windows[0].windowLowerBound."
        ),
    ),
    range_upper: int | None = typer.Option(
        None,
        "--range-upper",
        help=(
            "Upper bound for --frame-mode RANGE. E.g. --range-upper 0 means "
            "'up to current row'. Sets windows[0].windowUpperBound."
        ),
    ),
    enable_cume_dist: bool = typer.Option(
        False,
        "--enable-cume-dist",
        help="Enable cumulative distribution column (`cumeDist`). Top-level boolean.",
    ),
    enable_ntile: int | None = typer.Option(
        None,
        "--enable-ntile",
        help="Enable NTILE bucketing with this many buckets. Sets ntile=true + ntileValues=N.",
    ),
    global_agg: bool = typer.Option(
        False,
        "--global-agg",
        help="Compute global aggregations (over all rows, not partition).",
    ),
    pre_filter: str | None = typer.Option(
        None,
        "--pre-filter",
        help="GREL formula applied BEFORE windowing (filters input rows).",
    ),
    post_filter: str | None = typer.Option(
        None,
        "--post-filter",
        help=(
            "GREL formula applied AFTER windowing. Common pattern: drop "
            "boundary rows after a Lag/Lead computation. Replaces a "
            "downstream Filter recipe."
        ),
    ),
    computed_col: list[str] | None = typer.Option(
        None,
        "--computed-col",
        help=(
            "Add a computed column before windowing: 'name=expr[:type]'. "
            "Repeatable. Default type: string."
        ),
    ),
    keep_columns: str | None = typer.Option(
        None,
        "--keep-columns",
        help=(
            "Project the output to only these input columns plus window "
            "outputs (comma-separated). Sets retrievedColumnsSelectionMode="
            "EXPLICIT. Replaces a downstream Prepare ColumnsSelector."
        ),
    ),
    engine: EngineType | None = typer.Option(
        None,
        "--engine",
        case_sensitive=False,
        help="payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE.",
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help=(
            "Create the output as a managed dataset on this connection "
            "(e.g. a Snowflake connection for in-database execution). "
            "Without it the output lands on the default managed "
            "(filesystem) connection."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Window recipe. Computes window/analytic functions (rank, lag, cumsum).

    Use this instead of df.groupby().transform() in Python.
    Use --partition-key for PARTITION BY, --order-key for ORDER BY,
    and --compute for window functions.

    Examples:
      dku recipe create-window ranked -i data --output-ds ranked -k stock \\
        --order-key date --compute 'rowNumber::rn' -P PROJ

      Multi-offset lag (replaces N separate Window recipes for an N-row MA):
        dku recipe create-window mw -i data --output-ds out -k stock \\
          --order-key date --lag-offsets 'price:1,2,3,4,5' -P PROJ

      Frame (3-row trailing average):
        dku recipe create-window roll -i data --output-ds out -k stock \\
          --order-key date --compute 'avg:price:' --frame-preceding 2 --frame-following 0 -P PROJ

      Avoid output-name collision between two Window recipes on same column:
        dku recipe create-window w1 ... --compute 'lag:Value:' --rename Value_lag1:lag1_w1
    """
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)
    # Validate --compute format early (before any API calls)
    parsed_computations = _parse_compute_specs(compute) if compute else []
    parsed_lag_offsets = (
        _parse_offsets_spec(lag_offsets, "--lag-offsets") if lag_offsets else {}
    )
    parsed_lead_offsets = (
        _parse_offsets_spec(lead_offsets, "--lead-offsets") if lead_offsets else {}
    )
    parsed_renames: dict[str, str] = {}
    if rename:
        for entry in rename:
            if ":" not in entry:
                exit_with_error(
                    f"Invalid --rename '{entry}'. Expected 'SRC:DST'.",
                )
            src, dst = entry.split(":", 1)
            parsed_renames[src.strip()] = dst.strip()
    lag_date_unit_upper: str | None = None
    if lag_date_unit:
        lag_date_unit_upper = lag_date_unit.value
    frame_mode_upper: str | None = None
    if frame_mode:
        frame_mode_upper = frame_mode.value
    if frame_mode_upper == "RANGE" and (range_lower is None and range_upper is None):
        exit_with_error(
            "--frame-mode RANGE requires --range-lower and/or --range-upper.",
            details=[
                "Example: --frame-mode RANGE --range-lower -30 --range-upper 0 "
                "(last 30 days incl. current row, paired with --order-key date_col)."
            ],
        )
    if (
        range_lower is not None or range_upper is not None
    ) and frame_mode_upper != "RANGE":
        exit_with_error(
            "--range-lower/--range-upper require --frame-mode RANGE.",
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("window", recipe_name)
        builder.with_input(input_ds)
        _wire_single_output(client, proj, builder, output_ds, project_key, connection)
        builder.build()

        # Configure partition/order keys and computations (WindowRecipeSettings has no helpers).
        # DSS reads partitioning and ordering from payload.windows[0] and requires the
        # enablePartitioning / enableOrdering boolean flags. Writing to the top-level
        # partitioningColumns / orders fields (without the enable flags inside windows[0])
        # silently produces GLOBAL aggregations instead of per-partition ones.
        needs_save = bool(
            partition_key
            or order_key
            or parsed_computations
            or parsed_lag_offsets
            or parsed_lead_offsets
            or parsed_renames
            or frame_preceding is not None
            or frame_following is not None
            or frame_unbounded
            or frame_mode_upper
            or enable_cume_dist
            or enable_ntile is not None
            or global_agg
            or pre_filter
            or post_filter
            or computed_col
            or keep_columns
            or engine_upper
            or lag_date_unit_upper
        )
        if needs_save:
            recipe_obj = proj.get_recipe(recipe_name)
            win_settings = recipe_obj.get_settings()
            payload = _get_recipe_payload(win_settings)

            # Ensure windows[0] exists — DSS's builder creates it by default, but
            # guard against an empty list just in case.
            windows = payload.setdefault("windows", [])
            if isinstance(windows, list):
                if not windows:
                    windows.append({})
                win0 = windows[0]
            else:
                win0 = None

            if partition_key:
                if isinstance(win0, dict):
                    win0["enablePartitioning"] = True
                    win0["partitioningColumns"] = list(partition_key)
                # Keep the top-level field for forward compat with DSS versions
                # that inspect it alongside windows[0].
                payload["partitioningColumns"] = [
                    {"column": col} for col in partition_key
                ]
                info(f"Partition by: {', '.join(partition_key)}")
            if order_key:
                parsed_orders = _parse_order_specs(order_key)
                if isinstance(win0, dict):
                    win0["enableOrdering"] = True
                    win0["orders"] = parsed_orders
                payload["orders"] = parsed_orders
                info(f"Order by: {', '.join(order_key)}")
            if parsed_computations:
                _apply_window_computations(
                    payload, parsed_computations, recipe_name=recipe_name
                )
                info(
                    f"Computations: {', '.join(c['type'] for c in parsed_computations)}"
                )
            if parsed_lag_offsets or parsed_lead_offsets:
                _apply_offset_specs(payload, parsed_lag_offsets, "lag")
                _apply_offset_specs(payload, parsed_lead_offsets, "lead")
                if parsed_lag_offsets:
                    info(
                        "Multi-lag: "
                        + ", ".join(f"{c}={o}" for c, o in parsed_lag_offsets.items())
                    )
                if parsed_lead_offsets:
                    info(
                        "Multi-lead: "
                        + ", ".join(f"{c}={o}" for c, o in parsed_lead_offsets.items())
                    )
            # --lag-date-unit applies dateDiffUnit to every per-column entry
            # that has lag/lead/lagDiff/leadDiff enabled (date columns lagged by
            # date unit, not row count).
            if lag_date_unit_upper:
                values = payload.setdefault("values", [])
                target_flags = {"lag", "lead", "lagDiff", "leadDiff"}
                for v in values:
                    if any(v.get(f) for f in target_flags):
                        v["dateDiffUnit"] = lag_date_unit_upper
                info(f"Lag date unit: {lag_date_unit_upper}")
            if parsed_renames:
                payload["outputColumnNameOverrides"] = dict(parsed_renames)
                info(
                    "Rename: "
                    + ", ".join(f"{s}→{d}" for s, d in parsed_renames.items())
                )
            if frame_mode_upper == "RANGE":
                if isinstance(win0, dict):
                    win0["enableLimits"] = True
                    win0["windowLimitMode"] = "RANGE"
                    if range_lower is not None:
                        win0["windowLowerBound"] = range_lower
                        win0["limitPreceding"] = True
                    if range_upper is not None:
                        win0["windowUpperBound"] = range_upper
                        win0["limitFollowing"] = True
                info(
                    f"Frame: RANGE mode, lower={range_lower}, upper={range_upper} "
                    "(value-based on order column)"
                )
            elif frame_unbounded:
                if isinstance(win0, dict):
                    win0["enableLimits"] = True
                    win0["limitPreceding"] = False
                    win0["limitFollowing"] = False
                payload["legacyUnboundedWindowStreamBehavior"] = True
                info("Frame: unbounded preceding & following (full partition)")
            else:
                if frame_preceding is not None and isinstance(win0, dict):
                    win0["enableLimits"] = True
                    win0["limitPreceding"] = True
                    win0["precedingRows"] = frame_preceding
                if frame_following is not None and isinstance(win0, dict):
                    win0["enableLimits"] = True
                    win0["limitFollowing"] = True
                    win0["followingRows"] = frame_following
                if frame_preceding is not None or frame_following is not None:
                    info(
                        f"Frame: preceding={frame_preceding}, following={frame_following}"
                    )
            if enable_cume_dist:
                payload["cumeDist"] = True
                info("Cumulative distribution enabled")
            if enable_ntile is not None:
                payload["ntile"] = True
                payload["ntileValues"] = enable_ntile
                info(f"NTILE: {enable_ntile} buckets")
            if global_agg:
                payload["globalAggregations"] = True
                info("Global aggregations enabled")
            _apply_pipeline_options(
                payload,
                pre_filter=pre_filter,
                post_filter=post_filter,
                computed_cols=computed_col,
                renames=None,  # already handled above via --rename
            )
            if pre_filter:
                info(f"Pre-filter: {pre_filter}")
            if post_filter:
                info(f"Post-filter: {post_filter}")
            if computed_col:
                info(f"Computed cols: {len(computed_col)}")
            if keep_columns:
                kept = [c.strip() for c in keep_columns.split(",") if c.strip()]
                payload["retrievedColumnsSelectionMode"] = "EXPLICIT"
                # DSS represents per-column kept-or-not as `values[]` boolean flags;
                # initialize a list of {column, value:true} so EXPLICIT mode has a
                # source of truth. Columns not listed default to value:false and
                # get dropped from the output.
                payload["retrievedColumns"] = [
                    {"column": c, "value": True} for c in kept
                ]
                info(f"Keep columns: {', '.join(kept)}")
            _apply_engine_type(payload, engine_upper)
            if engine_upper:
                info(f"Engine: {engine_upper}")
            win_settings.save()

        _auto_apply_schema(proj, recipe_name)
        success(f"Created window recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

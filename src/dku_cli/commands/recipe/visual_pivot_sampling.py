"""Pivot and sampling visual recipe commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from ._common import *
from dku_cli.enums import (
    EngineType,
    IdentifierMode,
    PartitionSelection,
    PivotAgg,
    SamplingMethod,
    Slugification,
    ValueLimit,
)


@app.command("create-pivot")
def create_pivot(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    row_key: list[str] | None = typer.Option(
        None, "--row-key", "-r", help="Row dimension column(s). Repeatable."
    ),
    column_key: str | None = typer.Option(
        None,
        "--column-key",
        "-c",
        help="Column dimension (values become column headers)",
    ),
    value_column: str | None = typer.Option(
        None, "--value-column", "-v", help="Value column to aggregate into cells"
    ),
    agg_type: PivotAgg | None = typer.Option(
        None,
        "--agg-type",
        case_sensitive=False,
        help=(
            "Aggregation type for pivot cells: SUM, AVG, MIN, MAX, COUNT, "
            "COUNT_DISTINCT, CONCAT, CONCAT_DISTINCT, STDDEV, FIRST, LAST, "
            "FIRST_LAST_NOT_NULL. FIRST/LAST/FIRST_LAST_NOT_NULL require "
            "--order-column for deterministic ordering (canonical 'keep most-"
            "recent value per group' pattern for timeseries pivots)."
        ),
    ),
    order_column: str | None = typer.Option(
        None,
        "--order-column",
        help=(
            "Required when --agg-type is FIRST, LAST, or FIRST_LAST_NOT_NULL. "
            "Sets payload.pivots[0].valueColumns[0].orderColumn for "
            "deterministic ordering (e.g. timestamp on sensor data)."
        ),
    ),
    no_global_count: bool = typer.Option(
        False,
        "--no-global-count",
        help="Suppress the per-modality 'count' column that DSS adds to every pivot by default. Mirrors the create-group flag.",
    ),
    value_limit: ValueLimit = typer.Option(
        ValueLimit.TOP_N,
        "--value-limit",
        case_sensitive=False,
        help=(
            "Modality value limit: TOP_N (default, keeps top N by frequency), "
            "NO_LIMIT (keep every distinct column-key value), AT_LEAST_N_OCC "
            "(keep only modalities with at least N occurrences), or EXPLICIT "
            "(whitelist specific modalities via --explicit-values). DSS crashes "
            "at build time if this field is missing from the payload."
        ),
    ),
    topn_limit: int = typer.Option(
        20,
        "--topn-limit",
        help="When --value-limit=TOP_N, keep this many distinct column-key modalities (default 20, mirrors the DSS UI default).",
    ),
    min_occ_limit: int = typer.Option(
        0,
        "--min-occ-limit",
        help="When --value-limit=AT_LEAST_N_OCC, keep only modalities with at least N occurrences in the input.",
    ),
    pre_filter: str | None = typer.Option(
        None, "--pre-filter", help="GREL formula applied BEFORE pivoting."
    ),
    post_filter: str | None = typer.Option(
        None,
        "--post-filter",
        help="GREL formula applied AFTER pivoting.",
    ),
    computed_col: list[str] | None = typer.Option(
        None,
        "--computed-col",
        help="Add a computed column before pivoting: 'name=expr[:type]'. Repeatable.",
    ),
    rename: list[str] | None = typer.Option(
        None,
        "--rename",
        help="Rename a generated pivot column: 'SRC:DST'. Repeatable.",
    ),
    explicit_values: list[str] | None = typer.Option(
        None,
        "--explicit-values",
        help="When --value-limit=EXPLICIT, whitelist column-key modalities to keep in the output. Repeatable; each value becomes a separate entry. DSS stores this as a nested array of single-value arrays.",
    ),
    other_column: list[str] | None = typer.Option(
        None,
        "--other-column",
        help=(
            "Carry an extra column through the pivot with an aggregation. "
            "Format: 'COL[:AGG[:ORDER_COL]]'. AGG defaults to LAST and accepts "
            "FIRST/LAST/MIN/MAX/SUM/AVG/COUNT/COUNT_DISTINCT/CONCAT/STDDEV. "
            "ORDER_COL is required for FIRST/LAST. Example: "
            "--other-column 'equipment_id:LAST:timestamp'. Maps to "
            "payload.otherColumns[]."
        ),
    ),
    modality_slugification: Slugification | None = typer.Option(
        None,
        "--modality-slugification",
        case_sensitive=False,
        help="Modality column-name slugification: NONE (default, preserves spaces/punct), SOFT_SLUGIFY, HARD_SLUGIFY. Sets payload.modalitySlugification.",
    ),
    no_sort_modalities: bool = typer.Option(
        False,
        "--no-sort-modalities",
        help="Disable alphabetic sort of pivot output columns. Sets payload.sortModalities=false.",
    ),
    identifier_mode: IdentifierMode | None = typer.Option(
        None,
        "--identifier-mode",
        case_sensitive=False,
        help="Row-key selection mode: EXPLICIT (default — only --row-key columns) or AUTO (all input columns become identifiers). Sets payload.identifierColumnsSelection.",
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
        help=(
            "Create the output as a managed dataset on this connection "
            "(e.g. a Snowflake connection for in-database execution). "
            "Without it the output lands on the default managed "
            "(filesystem) connection."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Pivot recipe (long→wide). NEVER use df.pivot_table() in Python.

    Transposes rows into columns: each unique value in --column-key becomes
    a new column, filled with aggregated --value-column values.

    By default DSS adds a count column per pivoted modality regardless of
    --agg-type. Pass --no-global-count to suppress it when you only want the
    explicit aggregate in the output.

    Modality defaults: DSS limits the number of distinct column-key values
    written into the output. The CLI emits valueLimit=TOP_N and topnLimit=20
    to match the UI default — without these, DSS crashes at build time with
    'Unexpected value limit on modality collection'. Override with
    --value-limit NO_LIMIT (keep all), --value-limit AT_LEAST_N_OCC
    --min-occ-limit N (keep modalities seen at least N times),
    --value-limit EXPLICIT --explicit-values v1 --explicit-values v2
    (whitelist), or --topn-limit N if the dataset needs different limits.

    Example: dku recipe create-pivot piv -i sales --output-ds sales_wide --row-key product --column-key month --value-column revenue --agg-type SUM -P PROJ
    """
    _PIVOT_AGGS_REQUIRING_ORDER = frozenset({"FIRST", "LAST", "FIRST_LAST_NOT_NULL"})
    _VALID_OTHER_AGGS = frozenset(
        {
            "FIRST",
            "LAST",
            "FIRST_LAST_NOT_NULL",
            "SUM",
            "AVG",
            "MIN",
            "MAX",
            "COUNT",
            "COUNT_DISTINCT",
            "CONCAT",
            "CONCAT_DISTINCT",
            "STDDEV",
        }
    )
    _OTHER_AGG_FLAG_MAP = {
        "FIRST": "first",
        "LAST": "last",
        "FIRST_LAST_NOT_NULL": "firstLastNotNull",
        "SUM": "sum",
        "AVG": "avg",
        "MIN": "min",
        "MAX": "max",
        "COUNT": "count",
        "COUNT_DISTINCT": "countDistinct",
        "CONCAT": "concat",
        "CONCAT_DISTINCT": "concatDistinct",
        "STDDEV": "stddev",
    }
    if agg_type and agg_type.value in _PIVOT_AGGS_REQUIRING_ORDER and not order_column:
        exit_with_error(
            f"--agg-type {agg_type.value} requires --order-column.",
            details=[
                "FIRST/LAST/FIRST_LAST_NOT_NULL need a deterministic ordering column.",
                "Example: --agg-type LAST --value-column reading --order-column timestamp",
            ],
        )
    if order_column and (
        not agg_type or agg_type.value not in _PIVOT_AGGS_REQUIRING_ORDER
    ):
        exit_with_error(
            "--order-column only applies when --agg-type is FIRST, LAST, or FIRST_LAST_NOT_NULL.",
        )
    if value_limit.value == "EXPLICIT" and not explicit_values:
        exit_with_error(
            "--value-limit EXPLICIT requires at least one --explicit-values entry.",
            details=[
                "Pass --explicit-values once per modality to whitelist, e.g.:",
                "  --value-limit EXPLICIT --explicit-values 2024 --explicit-values 2025",
            ],
        )
    if explicit_values and value_limit.value != "EXPLICIT":
        exit_with_error(
            "--explicit-values requires --value-limit EXPLICIT.",
        )
    # Validate --other-column specs early
    parsed_other_columns: list[dict] = []
    if other_column:
        for spec in other_column:
            parts = spec.split(":")
            col = parts[0].strip()
            if not col:
                exit_with_error(
                    f"Invalid --other-column '{spec}': missing column name.",
                )
            agg_str = (
                parts[1].strip().upper()
                if len(parts) >= 2 and parts[1].strip()
                else "LAST"
            )
            order_col = parts[2].strip() if len(parts) >= 3 else None
            if agg_str not in _VALID_OTHER_AGGS:
                exit_with_error(
                    f"Invalid --other-column aggregation '{agg_str}'.",
                    details=[f"Valid: {', '.join(sorted(_VALID_OTHER_AGGS))}"],
                )
            if agg_str in {"FIRST", "LAST", "FIRST_LAST_NOT_NULL"} and not order_col:
                exit_with_error(
                    f"--other-column {agg_str} on '{col}' requires an ORDER_COL: --other-column '{col}:{agg_str}:order_col'.",
                )
            entry = {
                "column": col,
                "type": "string",
                "first": False,
                "last": False,
                "firstLastNotNull": False,
                "min": False,
                "max": False,
                "count": False,
                "countDistinct": False,
                "sum": False,
                "concat": False,
                "concatDistinct": False,
                "stddev": False,
                "avg": False,
            }
            entry[_OTHER_AGG_FLAG_MAP[agg_str]] = True
            if order_col:
                entry["orderColumn"] = order_col
            parsed_other_columns.append(entry)
    slug_upper: str | None = None
    if modality_slugification:
        slug_upper = modality_slugification.value
    id_mode_upper: str | None = None
    if identifier_mode:
        id_mode_upper = identifier_mode.value
        if id_mode_upper == "ALL":
            id_mode_upper = "AUTO"
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("pivot", recipe_name)
        builder.with_input(input_ds)
        _wire_single_output(client, proj, builder, output_ds, project_key, connection)
        builder.build()

        # Configure pivot dimensions and aggregation.
        # DSS stores pivot config in payload.explicitIdentifiers (row keys) and
        # payload.pivots[0] (column key, value columns, aggregation functions).
        # Always normalize modality settings to match the DSS UI payload — otherwise
        # DSS crashes at build time with:
        #   "Unexpected value limit on modality collection"
        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)
        if row_key:
            payload["explicitIdentifiers"] = list(row_key)
        # Configure the first pivot entry (DSS default creates one)
        pivots = payload.setdefault("pivots", [{}])
        pivot = pivots[0] if pivots else {}
        if not pivots:
            pivots.append(pivot)
        if column_key:
            pivot["keyColumns"] = [column_key]
        # Value-column aggregation flag mapping.
        # DSS pivot valueColumns are GroupingValue objects that use BOOLEAN fields
        # (sum, avg, count, ...) NOT a `function` string. Writing `function: "SUM"`
        # looks accepted but the recipe produces no aggregated columns at build time.
        _AGG_FLAG_MAP = {
            "SUM": "sum",
            "AVG": "avg",
            "MIN": "min",
            "MAX": "max",
            "COUNT": "count",
            "COUNT_DISTINCT": "countDistinct",
            "CONCAT": "concat",
            "CONCAT_DISTINCT": "concatDistinct",
            "STDDEV": "stddev",
            "FIRST": "first",
            "LAST": "last",
            "FIRST_LAST_NOT_NULL": "firstLastNotNull",
        }

        def _build_value_column(
            col: str, agg: str, order_col: str | None = None
        ) -> dict:
            flag = _AGG_FLAG_MAP[agg.upper()]
            vc = {
                "column": col,
                "type": "double",  # UI writes this as a schema hint for numeric aggs
                "min": False,
                "max": False,
                "count": False,
                "countDistinct": False,
                "sum": False,
                "concat": False,
                "concatDistinct": False,
                "stddev": False,
                "avg": False,
                "first": False,
                "last": False,
                "firstLastNotNull": False,
            }
            vc[flag] = True
            if order_col:
                vc["orderColumn"] = order_col
            return vc

        if value_column:
            agg_fn = agg_type.value if agg_type else "SUM"
            pivot["valueColumns"] = [
                _build_value_column(value_column, agg_fn, order_column)
            ]
        elif agg_type:
            # agg_type without value_column — toggle the boolean flag on existing entries
            flag = _AGG_FLAG_MAP[agg_type.value]
            for vc in pivot.get("valueColumns", []):
                for existing_flag in _AGG_FLAG_MAP.values():
                    vc[existing_flag] = False
                vc[flag] = True
                vc.setdefault("type", "double")
                if order_column:
                    vc["orderColumn"] = order_column
        if no_global_count:
            pivot["globalCount"] = False
        # Always set modality limits so the payload matches a UI-normalized recipe.
        # DSS stores explicitValues as an array of single-element arrays
        # ([["v1"], ["v2"]]), not a flat ["v1", "v2"] list. The flat form is
        # silently ignored and DSS falls back to the topnLimit defaults.
        vl_upper = value_limit.value
        pivot["valueLimit"] = vl_upper
        pivot["topnLimit"] = topn_limit
        pivot["minOccLimit"] = min_occ_limit
        if vl_upper == "EXPLICIT" and explicit_values:
            pivot["explicitValues"] = [[v] for v in explicit_values]
        else:
            pivot.setdefault("explicitValues", [])
        if parsed_other_columns:
            payload["otherColumns"] = parsed_other_columns
            info(f"Other columns: {len(parsed_other_columns)}")
        if slug_upper is not None:
            payload["modalitySlugification"] = slug_upper
            info(f"Modality slugification: {slug_upper}")
        if no_sort_modalities:
            payload["sortModalities"] = False
            info("Sort modalities: disabled")
        if id_mode_upper is not None:
            payload["identifierColumnsSelection"] = id_mode_upper
            info(f"Identifier mode: {id_mode_upper}")
        _apply_pipeline_options(
            payload,
            pre_filter=pre_filter,
            post_filter=post_filter,
            computed_cols=computed_col,
            renames=rename,
        )
        _apply_engine_type(payload, engine_upper)
        if pre_filter:
            info(f"Pre-filter: {pre_filter}")
        if post_filter:
            info(f"Post-filter: {post_filter}")
        if computed_col:
            info(f"Computed cols: {len(computed_col)}")
        if rename:
            info(f"Renames: {len(rename)}")
        if engine_upper:
            info(f"Engine: {engine_upper}")
        settings.save()
        info(
            f"Pivot config: row={row_key}, column={column_key}, value={value_column}, agg={agg_type}, value_limit={vl_upper}, topn_limit={topn_limit}, min_occ_limit={min_occ_limit}"
        )

        # Skip _auto_apply_schema for pivot: DSS refuses to pre-compute the output
        # schema because modality lists must be collected by the build itself
        # ("Modality lists stored in output schema are not up-to-date"). The schema
        # will be populated correctly when the recipe runs — no action needed here.
        info(
            f"Output schema for '{output_ds}' will be populated when you run the recipe (pivot modalities are collected at build time)."
        )
        success(f"Created pivot recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-sampling")
def create_sampling(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    method: SamplingMethod = typer.Option(
        SamplingMethod.RANDOM_FIXED_NB,
        "--method",
        "-m",
        case_sensitive=False,
        help=(
            "Sampling method: RANDOM_FIXED_NB, RANDOM_FIXED_RATIO, "
            "HEAD_SEQUENTIAL, STRATIFIED, CLASS_REBALANCE, FULL "
            "(no subsampling — useful with --filter-condition for a pure "
            "filter-only recipe)."
        ),
    ),
    size: int | None = typer.Option(
        None, "--size", "-n", help="Sample size (for RANDOM_FIXED_NB)"
    ),
    ratio: float | None = typer.Option(
        None, "--ratio", help="Sample ratio 0.0-1.0 (for RANDOM_FIXED_RATIO)"
    ),
    filter_condition: str | None = typer.Option(
        None,
        "--filter-condition",
        help=(
            "GREL formula applied as a row filter alongside the sample "
            "(writes definition.params.selection.filter + payload uiData "
            "mirror). Honored by the Sampling UI — but several DSS build "
            "engines silently ignore this filter at recipe runtime. "
            "If the build output is unfiltered, fall back to a Prepare "
            "recipe via `dku recipe create-filter`, which writes a "
            "FilterOnCustomFormula step and is reliably applied."
        ),
    ),
    partition_selection: PartitionSelection | None = typer.Option(
        None,
        "--partition-selection",
        case_sensitive=False,
        help=(
            "Partition selection on a partitioned input: ALL (default — "
            "sample across every partition), LATEST_N (take only the most "
            "recent N partitions, see --latest-partitions), or EXPLICIT "
            "(use the partition spec)."
        ),
    ),
    latest_partitions: int | None = typer.Option(
        None,
        "--latest-partitions",
        help=(
            "When --partition-selection LATEST_N, sample from this many "
            "most-recent partitions. Canonical 'last N days' pattern when "
            "the input is daily-partitioned."
        ),
    ),
    order_by: list[str] = typer.Option(
        [],
        "--order-by",
        help=(
            "Order rows before sampling: 'COL[:desc]' (repeatable). Critical "
            "for HEAD_SEQUENTIAL on partitioned datasets — without ordering "
            "the 'head' is non-deterministic."
        ),
    ),
    max_bytes: int | None = typer.Option(
        None,
        "--max-bytes",
        help=(
            "Cap the input scan at this many uncompressed bytes (sets "
            "selection.maxReadUncompressedBytes). -1 = no cap (default)."
        ),
    ),
    use_mem_table: bool = typer.Option(
        False,
        "--use-mem-table",
        help=(
            "Materialize sampling intermediate as an in-memory table. Faster "
            "for small samples; OOMs on large ones."
        ),
    ),
    within_first: int | None = typer.Option(
        None,
        "--within-first",
        help=(
            "Restrict the sampling source to the first N rows of the input "
            "(sets selection.withinFirstN). -1 = no cap (default)."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Sampling recipe. Takes a random, stratified, or head sample.

    Use this instead of df.sample() in Python. For row filtering by condition,
    use --method FULL + --filter-condition (or use create-filter if you do not
    need any sampling). For partitioned inputs, prefer --partition-selection
    LATEST_N + --latest-partitions over Python iter_partitioned().

    Examples:
      dku recipe create-sampling sample_1k -i big_data --output-ds sample --size 1000 -P PROJ

      Filter-only Sampling recipe (no subsampling):
        dku recipe create-sampling fil -i rows --output-ds active \\
          --method FULL --filter-condition 'status=="active"' -P PROJ

      Most-recent 7 partitions, deterministic head:
        dku recipe create-sampling recent -i daily_events --output-ds sample \\
          --method HEAD_SEQUENTIAL --size 100000 \\
          --partition-selection LATEST_N --latest-partitions 7 \\
          --order-by event_ts:desc -P PROJ
    """
    project_key = resolve_project(project)
    method_upper = method.value
    partition_selection_upper: str | None = None
    if partition_selection:
        partition_selection_upper = partition_selection.value
    if partition_selection_upper == "LATEST_N" and latest_partitions is None:
        exit_with_error(
            "--partition-selection LATEST_N requires --latest-partitions N.",
        )
    if latest_partitions is not None and partition_selection_upper not in {
        "LATEST_N",
        None,
    }:
        exit_with_error(
            "--latest-partitions only applies with --partition-selection LATEST_N.",
        )
    parsed_orders: list[dict] = []
    for entry in order_by:
        col = entry
        desc = False
        if ":" in entry:
            col, suffix = entry.rsplit(":", 1)
            desc = suffix.strip().lower() == "desc"
        parsed_orders.append({"column": col.strip(), "desc": desc})
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("sampling", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure sampling method and params in raw definition (DSS reads
        # from definition.params.selection, NOT obj_payload.selection)
        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        selection = raw_def.setdefault("params", {}).setdefault("selection", {})
        selection["samplingMethod"] = method_upper
        if size is not None:
            selection["maxRecords"] = size
        if ratio is not None:
            selection["targetRatio"] = ratio
        if partition_selection_upper is not None:
            selection["partitionSelectionMethod"] = partition_selection_upper
        if latest_partitions is not None:
            selection["latestPartitionsN"] = latest_partitions
        if parsed_orders:
            ordering = selection.setdefault("ordering", {"enabled": True, "rules": []})
            ordering["enabled"] = True
            ordering["rules"] = parsed_orders
            info(f"Order by: {', '.join(o['column'] for o in parsed_orders)}")
        if max_bytes is not None:
            selection["maxReadUncompressedBytes"] = max_bytes
        if use_mem_table:
            selection["useMemTable"] = True
        if within_first is not None:
            selection["withinFirstN"] = within_first
        if filter_condition:
            # Write the filter to BOTH the selection and the payload — the
            # Sampling UI reads from selection.filter while introspection
            # tools and some engine versions look at the payload. NB: many
            # DSS build engines silently ignore the Sampling filter at
            # runtime (per repeated reports); the warning below points at
            # the reliable fallback.
            sel_filter = selection.setdefault("filter", {})
            sel_filter["enabled"] = True
            sel_filter["distinct"] = False
            sel_filter["uiData"] = {"mode": "CUSTOM", "expression": filter_condition}
            sel_filter["expression"] = filter_condition
            payload = _get_recipe_payload(settings)
            payload["enabled"] = True
            payload["uiData"] = {"mode": "CUSTOM", "expression": filter_condition}
            info(f"Filter: {filter_condition}")
            warn(
                "Sampling recipe filter is unreliable on many DSS engines. "
                "If the build output is unfiltered, use "
                "`dku recipe create-filter` instead."
            )
        settings.save()

        _auto_apply_schema(proj, recipe_name)
        success(
            f"Created sampling recipe '{recipe_name}' ({method_upper}) in {project_key}"
        )
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

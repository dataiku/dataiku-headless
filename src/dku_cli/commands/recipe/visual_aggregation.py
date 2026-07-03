"""Aggregation-style visual recipe commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from dku_cli.enums import EngineType

from ._common import *

_VALID_AGGS = frozenset(
    {
        "sum",
        "avg",
        "min",
        "max",
        "count",
        "count_distinct",
        "concat",
        "stddev",
        # Extended (per discovery loop / payload introspection):
        "first",
        "last",
        "first_last_not_null",
        "concat_distinct",
        "sum2",
    }
)
# Map CLI agg names to the JSON field names DSS expects on the values[] entry.
# The base aggs (sum, avg, min, max, count, concat, stddev) match 1:1.
_AGG_JSON_FIELD = {
    "count_distinct": "countDistinct",
    "first_last_not_null": "firstLastNotNull",
    "concat_distinct": "concatDistinct",
}

# Valid Stack `--mode` values and the shared guidance shown on rejection.
# Referenced from both stack-mode error sites so a new mode is added in one place.
_STACK_MODES = frozenset({"UNION", "INTERSECT", "FROM_DATASET", "FROM_INDEX", "REMAP"})
_STACK_MODE_HELP = (
    "Use UNION (default), INTERSECT, FROM_DATASET:NAME, FROM_INDEX:N, or REMAP."
)


@app.command("create-group")
def create_group(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    group_key: list[str] | None = typer.Option(
        None,
        "--group-key",
        "-k",
        help="Column(s) to group by. Repeatable: -k col1 -k col2.",
    ),
    agg: list[str] = typer.Option(
        None,
        "--agg",
        help=(
            "Aggregation: 'col:func1,func2'. Functions accepted via --agg: "
            "sum, avg, min, max, count, count_distinct, concat, concat_distinct, "
            "stddev, first, last, first_last_not_null, sum2. Repeatable. "
            "MEDIAN/PERCENTILE: not an in-memory Group aggregate — Group's median "
            "is SQL-engine ONLY (fails on the DSS engine: 'Median aggregation is "
            "not implemented for DSS Engine') and percentile is not a Group "
            "aggregate at all. Both are a VISUAL Window-rank pattern (row_number + "
            "count over the group, then pick/weight the bracketing rows and Group "
            "them) — no SQL recipe needed in-memory. Use a SQL PERCENTILE_CONT(p) "
            "recipe only for SQL-backed input or a SQL engine-mandate."
        ),
    ),
    no_global_count: bool = typer.Option(
        False,
        "--no-global-count",
        help="Suppress the per-group 'count' column that DSS adds by default.",
    ),
    rename: list[str] | None = typer.Option(
        None,
        "--rename",
        help=(
            "Rename any output column: 'SRC:DST'. Writes outputColumnNameOverrides — "
            "applies to BOTH the group key and generated aggregate columns. "
            "Examples: --rename FileName:'XLS File' (group key); "
            "--rename Customer_ID_count:Count (aggregate). "
            "Repeatable. Avoids a downstream Prepare add-rename."
        ),
    ),
    agg_order: list[str] = typer.Option(
        [],
        "--agg-order",
        help=(
            "Per-column ordering for concat / concat_distinct / first / last "
            "/ first_last_not_null aggs: 'col=order_col'. Repeatable. Sets "
            "values[].orderColumn — gives DETERMINISTIC concat output (without "
            "this, Snowflake LISTAGG / Postgres STRING_AGG row order is engine-"
            "dependent). Example: --agg item_recommendation:concat "
            "--agg-order item_recommendation=Segment."
        ),
    ),
    agg_separator: list[str] = typer.Option(
        [],
        "--agg-separator",
        help=(
            "Per-column separator for concat aggs: 'col=,' (defaults to ','). "
            "Repeatable. Sets values[].concatSeparator. Use ' | ' for "
            "human-readable lists; use the empty string '' to concatenate "
            "without delimiters."
        ),
    ),
    pre_filter: str | None = typer.Option(
        None,
        "--pre-filter",
        help=(
            "GREL formula applied BEFORE grouping (filters input rows). "
            "Replaces an upstream Filter recipe. Example: 'price > 0'."
        ),
    ),
    post_filter: str | None = typer.Option(
        None,
        "--post-filter",
        help=(
            "GREL formula applied AFTER grouping (filters aggregate rows). "
            "Replaces a downstream Filter recipe. Example: 'count > 1'."
        ),
    ),
    computed_col: list[str] | None = typer.Option(
        None,
        "--computed-col",
        help=(
            "Add a computed column before grouping: 'name=expr[:type]'. "
            "Repeatable. Type defaults to string; specify bigint/double/etc. "
            "after a trailing ':TYPE'. Example: --computed-col 'country=\"US\":string'."
        ),
    ),
    engine: EngineType | None = typer.Option(
        None,
        "--engine",
        case_sensitive=False,
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Top-level field, separate from engineParams.<engine>.executionEngine. "
            "Required for SQL pushdown on Snowflake/Postgres/Redshift — without it, "
            "DSS may pick the slower DSS engine."
        ),
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
    """Create a Group (aggregate) recipe. NEVER use Python for aggregations — use this instead.

    Use --agg to configure aggregation functions: --agg 'amount:sum,avg' --agg 'id:count'.
    Without --agg, defaults to COUNT per group. Use -k for group keys (repeatable: -k col1 -k col2).

    Aggregation functions: sum, avg, min, max, count, count_distinct, concat, stddev,
    first, last, first_last_not_null, concat_distinct, sum2.

    Median is a SQL-engine-ONLY DSS Group aggregate (fails on the in-memory DSS
    engine with "Median aggregation is not implemented for DSS Engine") and is not
    reachable through --agg — pass --engine SQL and set the `median` JSON flag via
    `dku recipe set-settings`. Percentiles/quantiles are not a Group aggregate at
    all: use a SQL recipe (PERCENTILE_CONT(p) WITHIN GROUP (ORDER BY col)).

    By default DSS adds a 'count' column (rows per group). Pass --no-global-count
    to suppress it when only the explicit aggregates should appear in the output.
    """
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)
    # Validate --agg format early (before any API calls)
    if agg:
        for agg_spec in agg:
            if ":" not in agg_spec:
                exit_with_error(
                    f"Invalid --agg format: '{agg_spec}'.",
                    details=[
                        "Expected: 'column:func1,func2'. Example: --agg 'amount:sum,avg'"
                    ],
                )
            _, funcs_str = agg_spec.split(":", 1)
            funcs = {f.strip().lower() for f in funcs_str.split(",")}
            invalid = funcs - _VALID_AGGS
            if invalid:
                exit_with_error(
                    f"Unknown aggregation functions: {', '.join(sorted(invalid))}.",
                    details=[f"Valid: {', '.join(sorted(_VALID_AGGS))}"],
                )
    # Parse --agg-order col=order_col  (and --agg-separator col=sep)
    agg_order_map: dict[str, str] = {}
    for entry in agg_order:
        if "=" not in entry:
            exit_with_error(
                f"Invalid --agg-order '{entry}'. Expected 'col=order_col'.",
            )
        c, o = entry.split("=", 1)
        agg_order_map[c.strip()] = o.strip()
    agg_sep_map: dict[str, str] = {}
    for entry in agg_separator:
        if "=" not in entry:
            exit_with_error(
                f"Invalid --agg-separator '{entry}'. Expected 'col=sep' (sep may be empty).",
            )
        c, sep = entry.split("=", 1)
        agg_sep_map[c.strip()] = sep
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("grouping", recipe_name)
        builder.with_input(input_ds)
        if group_key:
            builder.with_group_key(group_key[0])
        _wire_single_output(client, proj, builder, output_ds, project_key, connection)
        builder.build()

        # Post-build: add extra group keys, aggregation config, and/or disable global count
        needs_settings = (
            (group_key and len(group_key) > 1)
            or not group_key
            or agg
            or no_global_count
            or rename
            or pre_filter
            or post_filter
            or computed_col
            or engine_upper
        )
        if needs_settings:
            recipe_obj = proj.get_recipe(recipe_name)
            group_settings = recipe_obj.get_settings()
            if not group_key:
                # No -k given: caller wants a global aggregate (one output row).
                # The dataikuapi grouping builder leaves a `[{}]` placeholder in
                # `payload.keys` which crashes DSS at run time with
                # `AssertionError` in ExpressionUtils.getSchemaColumn.
                group_settings.obj_payload["keys"] = []
            elif len(group_key) > 1:
                for extra_key in group_key[1:]:
                    group_settings.add_grouping_key(extra_key)
            if agg:
                # Aggs the dataikuapi helper accepts directly via kwargs.
                _BASIC_AGG_KW = {
                    "sum",
                    "avg",
                    "min",
                    "max",
                    "count",
                    "count_distinct",
                    "concat",
                    "stddev",
                }
                # Merge specs by column BEFORE applying: the dataikuapi helper
                # writes every kwarg (True or False) to the column's values[]
                # entry, so applying per-spec makes a repeated
                # `--agg amount:sum --agg amount:avg` last-wins (earlier flags
                # reset to False) while the echo still lists every function.
                funcs_by_col: dict[str, set[str]] = {}
                for agg_spec in agg:
                    col, funcs_str = agg_spec.split(":", 1)
                    funcs_by_col.setdefault(col.strip(), set()).update(
                        f.strip().lower() for f in funcs_str.split(",")
                    )
                for col, funcs in funcs_by_col.items():
                    cs = group_settings.set_column_aggregations(
                        col,
                        **{f: (f in funcs) for f in _BASIC_AGG_KW},
                    )
                    # The helper has a bug where `avg=` is accepted but never
                    # written to the settings dict — patch directly.
                    cs["avg"] = "avg" in funcs
                    # Extended aggs use JSON field names DSS expects on values[]:
                    for cli_name in funcs:
                        if cli_name in {"first", "last", "sum2"}:
                            cs[cli_name] = True
                        elif cli_name in _AGG_JSON_FIELD:
                            cs[_AGG_JSON_FIELD[cli_name]] = True
                info(f"Aggregations: {', '.join(agg)}")
            # Prune values[] entries with no aggregation flags set. The
            # dataikuapi grouping builder seeds values[] with one entry per
            # input column (all flags False), so a recipe with one --agg
            # ends up with N-1 dead entries cluttering the UI ("Aggregate"
            # tab shows every column with no checkboxes). Empty entries are
            # functional no-ops at run time, just visual noise.
            _AGG_FLAGS = (
                "sum",
                "avg",
                "min",
                "max",
                "count",
                "countDistinct",
                "concat",
                "concatDistinct",
                "stddev",
                "first",
                "last",
                "firstLastNotNull",
                "sum2",
                "median",
            )
            payload = group_settings.obj_payload
            values = payload.get("values") or []
            payload["values"] = [v for v in values if any(v.get(f) for f in _AGG_FLAGS)]
            # Apply --agg-order / --agg-separator to the matching values[] entry.
            if agg_order_map or agg_sep_map:
                for v in payload["values"]:
                    col = v.get("column")
                    if col in agg_order_map:
                        v["orderColumn"] = agg_order_map[col]
                    if col in agg_sep_map:
                        v["concatSeparator"] = agg_sep_map[col]
            if no_global_count:
                group_settings.set_global_count_enabled(False)
                info("Global 'count' column disabled.")
            _apply_pipeline_options(
                group_settings.obj_payload,
                pre_filter=pre_filter,
                post_filter=post_filter,
                computed_cols=computed_col,
                renames=rename,
            )
            _apply_engine_type(group_settings.obj_payload, engine_upper)
            if engine_upper:
                info(f"Engine: {engine_upper}")
            if rename:
                info(
                    "Rename: "
                    + ", ".join(
                        f"{s}→{d}"
                        for s, d in (
                            group_settings.obj_payload.get("outputColumnNameOverrides")
                            or {}
                        ).items()
                    )
                )
            if pre_filter:
                info(f"Pre-filter: {pre_filter}")
            if post_filter:
                info(f"Post-filter: {post_filter}")
            if computed_col:
                info(f"Computed cols: {len(computed_col)}")
            group_settings.save()

        _auto_apply_schema(proj, recipe_name)
        success(f"Created group recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
        if group_key:
            info(f"Grouped by: {', '.join(group_key)}")
        if not no_global_count:
            info(
                "Output includes a global 'count' column (rows per group) added by "
                "DSS. Pass --no-global-count to suppress it if downstream steps don't "
                "expect it."
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-stack")
def create_stack(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    inputs: list[str] = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input datasets to stack (repeat: -i ds1 -i ds2). Order matters for --origin-label indices.",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    origin_column: str | None = typer.Option(
        None,
        "--origin-column",
        help=(
            "Add an origin column to the output identifying which input each row "
            "came from. Replaces the common anti-pattern of adding a prepare "
            "recipe on each input just to tag its source."
        ),
    ),
    origin_labels: list[str] | None = typer.Option(
        None,
        "--origin-label",
        help=(
            "Override the origin label for an input: 'INDEX:VALUE' where INDEX is "
            "the 0-based position of the input in --input flags. Repeatable. "
            "Unmapped inputs default to their dataset name. Requires --origin-column."
        ),
    ),
    mode: str = typer.Option(
        "UNION",
        "--mode",
        help=(
            "Column selection mode: UNION (default, superset of columns), "
            "INTERSECT (only columns present in ALL inputs), "
            "FROM_DATASET:NAME (copy schema from named input), "
            "FROM_INDEX:N (copy schema from input at 0-based position N — useful "
            "when input names are templated/cross-environment), or "
            "REMAP (custom output schema with per-input columns alignment — "
            "requires --columns and --columns-match)."
        ),
    ),
    columns: str | None = typer.Option(
        None,
        "--columns",
        help=(
            "Project the output to these columns (comma-separated). For "
            "REMAP mode this defines the output schema and is required. "
            "For UNION/INTERSECT it acts as a downstream column projection — "
            "avoids a Prepare add-delete-columns recipe."
        ),
    ),
    columns_match: list[str] | None = typer.Option(
        None,
        "--columns-match",
        help=(
            "REMAP-only: 'INDEX:c1,c2,c3' — for input INDEX, names the source "
            "columns positionally aligned to --columns. Repeatable, one per "
            "input. Empty slot: 'INDEX:c1,,c3' (input does not provide the "
            "middle output column)."
        ),
    ),
    input_filters: list[str] | None = typer.Option(
        None,
        "--input-filter",
        help=(
            "Per-input pre-filter: 'INDEX:GREL_EXPR' — only rows matching "
            "the formula flow into the stack from that input. Repeatable. "
            "Replaces a per-input Filter recipe."
        ),
    ),
    post_filter: str | None = typer.Option(
        None,
        "--post-filter",
        help=(
            "GREL formula applied AFTER stacking. Replaces a downstream Filter recipe."
        ),
    ),
    engine: EngineType | None = typer.Option(
        None,
        "--engine",
        case_sensitive=False,
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Top-level field, separate from engineParams.<engine>.executionEngine. "
            "Set SQL for Snowflake/Postgres pushdown."
        ),
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
    """Create a Stack recipe. Vertically concatenates datasets (UNION).

    Use this instead of pd.concat in Python. Pass --origin-column to tag each
    row with its source input in one recipe, instead of prepare recipes per
    input.

    Examples:
      Basic:
        dku recipe create-stack merge -i a -i b --output-ds all -P PROJ

      With origin column (replaces per-input prepare recipes):
        dku recipe create-stack merge -i customers -i prospects --output-ds people \\
          --origin-column source -P PROJ

      With custom origin labels:
        dku recipe create-stack merge -i customers -i prospects --output-ds people \\
          --origin-column source --origin-label 0:active --origin-label 1:lead -P PROJ

      Intersect schemas (only columns present in all inputs):
        dku recipe create-stack merge -i a -i b --output-ds all --mode INTERSECT -P PROJ

      REMAP — align mis-named columns into a single output schema (replaces N
      upstream ColumnRenamer recipes):
        dku recipe create-stack merge -i orders -i sales --output-ds all \\
          --mode REMAP --columns "id,amount,date" \\
          --columns-match 0:order_id,total,order_date \\
          --columns-match 1:sale_id,price,sold_at -P PROJ

      With per-input filter and column projection:
        dku recipe create-stack merge -i a -i b --output-ds all \\
          --columns "id,amount" --input-filter '0:status=="active"' -P PROJ
    """
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)
    if len(inputs) < 2:
        exit_with_error(
            "Stack recipes need at least 2 input datasets.",
            details=[
                "Use: dku recipe create-stack NAME -i ds1 -i ds2 --output-ds out -P PROJ"
            ],
        )
    if origin_labels and not origin_column:
        exit_with_error(
            "--origin-label requires --origin-column.",
            details=[
                "Add --origin-column COL to name the source column, then repeat "
                "--origin-label INDEX:VALUE to override labels.",
            ],
        )

    label_map: dict[int, str] = {}
    if origin_labels:
        for entry in origin_labels:
            if ":" not in entry:
                exit_with_error(
                    f"Invalid --origin-label '{entry}'. Expected 'INDEX:VALUE'.",
                    details=[
                        "Example: --origin-label 0:customers --origin-label 1:prospects",
                    ],
                )
            idx_str, value = entry.split(":", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                exit_with_error(
                    f"Invalid input index in --origin-label '{entry}': '{idx_str}' is not an integer.",
                )
            if idx < 0 or idx >= len(inputs):
                exit_with_error(
                    f"--origin-label index {idx} out of range (0..{len(inputs) - 1}).",
                    details=[
                        f"Inputs in order: {', '.join(f'{i}={n}' for i, n in enumerate(inputs))}",
                    ],
                )
            label_map[idx] = value

    from_dataset_name: str | None = None
    from_index_value: int | None = None
    mode_value = mode.strip()
    if ":" in mode_value:
        head, tail = mode_value.split(":", 1)
        mode_upper = head.strip().upper()
        suffix = tail.strip()
        if mode_upper == "FROM_DATASET":
            from_dataset_name = suffix
        elif mode_upper == "FROM_INDEX":
            try:
                from_index_value = int(suffix)
            except ValueError:
                exit_with_error(
                    f"Invalid --mode '{mode}': FROM_INDEX requires an integer "
                    f"(got '{suffix}').",
                )
        else:
            exit_with_error(
                f"Invalid --mode '{mode}'.",
                details=[
                    _STACK_MODE_HELP,
                    "Only FROM_DATASET / FROM_INDEX accept a ':' suffix.",
                ],
            )
    else:
        mode_upper = mode_value.upper()
    if mode_upper not in _STACK_MODES:
        exit_with_error(
            f"Invalid --mode '{mode}'.",
            details=[_STACK_MODE_HELP],
        )
    if mode_upper == "FROM_DATASET" and not from_dataset_name:
        exit_with_error(
            "--mode FROM_DATASET requires the dataset name: --mode FROM_DATASET:DS.",
        )
    if mode_upper == "FROM_DATASET" and from_dataset_name not in inputs:
        exit_with_error(
            f"--mode FROM_DATASET:{from_dataset_name} references a dataset that is not an input.",
            details=[
                f"Inputs in order: {', '.join(inputs)}",
                "Use one of the -i/--input dataset names after FROM_DATASET:.",
            ],
        )
    if mode_upper == "FROM_INDEX":
        if from_index_value is None:
            exit_with_error(
                "--mode FROM_INDEX requires an integer index: --mode FROM_INDEX:0.",
            )
        if from_index_value < 0 or from_index_value >= len(inputs):
            exit_with_error(
                f"--mode FROM_INDEX:{from_index_value} out of range "
                f"(0..{len(inputs) - 1}).",
                details=[
                    f"Inputs in order: {', '.join(f'{i}={n}' for i, n in enumerate(inputs))}",
                ],
            )

    columns_list: list[str] = []
    if columns:
        columns_list = [c.strip() for c in columns.split(",") if c.strip()]

    columns_match_map: dict[int, list[str]] = {}
    if columns_match:
        for entry in columns_match:
            if ":" not in entry:
                exit_with_error(
                    f"Invalid --columns-match '{entry}'. Expected 'INDEX:c1,c2,c3'.",
                )
            idx_str, cols_str = entry.split(":", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                exit_with_error(
                    f"Invalid input index in --columns-match '{entry}': '{idx_str}' is not an integer.",
                )
            if idx < 0 or idx >= len(inputs):
                exit_with_error(
                    f"--columns-match index {idx} out of range (0..{len(inputs) - 1}).",
                )
            columns_match_map[idx] = [c.strip() for c in cols_str.split(",")]

    input_filter_map: dict[int, str] = {}
    if input_filters:
        for entry in input_filters:
            if ":" not in entry:
                exit_with_error(
                    f"Invalid --input-filter '{entry}'. Expected 'INDEX:GREL_EXPR'.",
                )
            idx_str, expr = entry.split(":", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                exit_with_error(
                    f"Invalid input index in --input-filter '{entry}': '{idx_str}' is not an integer.",
                )
            if idx < 0 or idx >= len(inputs):
                exit_with_error(
                    f"--input-filter index {idx} out of range (0..{len(inputs) - 1}).",
                )
            input_filter_map[idx] = expr

    if mode_upper == "REMAP":
        if not columns_list:
            exit_with_error(
                "--mode REMAP requires --columns 'a,b,c' to define the output schema.",
                details=[
                    "REMAP aligns mis-named columns into one output schema. The schema is the "
                    "list of output column names; --columns-match positionally maps each input.",
                    "Example: --mode REMAP --columns 'id,amount' --columns-match 0:src_id,total --columns-match 1:sale_id,price",
                ],
            )
        if not columns_match_map:
            exit_with_error(
                "--mode REMAP requires at least one --columns-match INDEX:c1,c2,c3.",
            )
        for idx, src_cols in columns_match_map.items():
            if len(src_cols) != len(columns_list):
                exit_with_error(
                    f"--columns-match {idx}: got {len(src_cols)} source columns "
                    f"but --columns has {len(columns_list)} output columns.",
                    details=[
                        "The number of source columns per input MUST equal the number of output columns.",
                        "Use an empty slot (',,') if an input does not provide a given output column.",
                    ],
                )
    elif columns_match:
        exit_with_error(
            "--columns-match is only valid with --mode REMAP.",
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("vstack", recipe_name)
        for ds in inputs:
            builder.with_input(ds)
        _wire_single_output(client, proj, builder, output_ds, project_key, connection)
        builder.build()

        needs_settings_save = bool(
            origin_column
            or mode_upper != "UNION"
            or columns_list
            or input_filter_map
            or post_filter
            or engine_upper
        )
        if needs_settings_save:
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            if origin_column:
                settings.add_origin_column(origin_column, label_map)
            if mode_upper == "INTERSECT":
                settings.set_intersection_input_schema_mode()
            elif mode_upper == "FROM_DATASET":
                settings.set_from_dataset_input_schema_mode(from_dataset_name)
            elif mode_upper == "FROM_INDEX":
                payload = settings.obj_payload
                payload["mode"] = "FROM_INDEX"
                payload["selectedColumnsIndexes"] = [str(from_index_value)]
                # The schema-source dataset must also be carried in
                # `copySchemaFromDatasetWithName` so the recipe can validate.
                payload["copySchemaFromDatasetWithName"] = inputs[from_index_value]
                # DSS reads selectedColumns to project output; initialize empty
                # so apply-schema doesn't NPE before columns get propagated.
                payload.setdefault("selectedColumns", [])
            elif mode_upper == "REMAP":
                payload = settings.obj_payload
                payload["mode"] = "REMAP"
                payload["selectedColumns"] = list(columns_list)
                virtual_inputs = payload.get("virtualInputs", [])
                empty_match = ["" for _ in columns_list]
                for vi in virtual_inputs:
                    vi["columnsMatch"] = list(empty_match)
                for idx, src_cols in columns_match_map.items():
                    if idx < len(virtual_inputs):
                        virtual_inputs[idx]["columnsMatch"] = list(src_cols)
            elif columns_list:
                # UNION/INTERSECT/FROM_DATASET column projection (avoids downstream Prepare).
                settings.obj_payload["selectedColumns"] = list(columns_list)
            if input_filter_map:
                virtual_inputs = settings.obj_payload.get("virtualInputs", [])
                for idx, expr in input_filter_map.items():
                    if idx < len(virtual_inputs):
                        virtual_inputs[idx]["preFilter"] = _build_pipeline_filter(expr)
            if post_filter:
                settings.obj_payload["postFilter"] = _build_pipeline_filter(post_filter)
            _apply_engine_type(settings.obj_payload, engine_upper)
            settings.save()

        _auto_apply_schema(proj, recipe_name)
        success(f"Created stack recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
        if engine_upper:
            info(f"Engine: {engine_upper}")
        if origin_column:
            info(f"Origin column: {origin_column}")
        if mode_upper != "UNION":
            label = (
                f"{mode_upper}:{from_dataset_name}" if from_dataset_name else mode_upper
            )
            info(f"Schema mode: {label}")
        if columns_list:
            info(f"Selected columns: {', '.join(columns_list)}")
        if input_filter_map:
            for idx, expr in sorted(input_filter_map.items()):
                info(f"Pre-filter on input {idx}: {expr}")
        if post_filter:
            info(f"Post-filter: {post_filter}")
    except Exception as e:
        handle_api_error(e)


@app.command("create-distinct")
def create_distinct(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    on: list[str] | None = typer.Option(
        None,
        "--on",
        help=(
            "Column(s) defining uniqueness. Repeatable. Default: ALL input columns "
            "(matching Python df.drop_duplicates() semantics). Specify --on col1 "
            "--on col2 to dedup on a subset; the output then contains only those "
            "columns (DSS Distinct has no keep-first-row semantics)."
        ),
    ),
    pre_filter: str | None = typer.Option(
        None, "--pre-filter", help="GREL formula applied BEFORE deduplication."
    ),
    post_filter: str | None = typer.Option(
        None, "--post-filter", help="GREL formula applied AFTER deduplication."
    ),
    computed_col: list[str] | None = typer.Option(
        None,
        "--computed-col",
        help="Add a computed column before dedup: 'name=expr[:type]'. Repeatable.",
    ),
    rename: list[str] | None = typer.Option(
        None,
        "--rename",
        help="Rename an output column: 'SRC:DST'. Repeatable.",
    ),
    engine: EngineType | None = typer.Option(
        None,
        "--engine",
        case_sensitive=False,
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Top-level field; set SQL for Snowflake/Postgres pushdown."
        ),
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
    """Create a Distinct recipe. Deduplicates rows.

    Use this instead of df.drop_duplicates() in Python. By default, deduplicates
    on ALL columns of the input dataset (so two rows collapse only when every
    column value matches). Use --on to dedup on a subset.

    Example: dku recipe create-distinct dedup -i rows --output-ds unique -P PROJ
    Example: dku recipe create-distinct dedup -i rows --output-ds unique --on customer_id --on order_date -P PROJ
    """
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # Resolve keys BEFORE creating anything — a Distinct without keys builds
        # to "No distinct column" (DSS payload defaults to keys=[first_col] +
        # selectAllColumns=false, which silently produces a single-column
        # projection). If --on is omitted and we can't read the input schema
        # (input doesn't exist, or exists but is unbuilt), refuse to create the
        # half-broken recipe + orphan output dataset.
        if on:
            key_cols = list(on)
            # A subset was requested: output and dedup on exactly those columns
            # (selectAllColumns is forced False below — see the keys block).
        else:
            try:
                input_schema = (
                    proj.get_dataset(input_ds).get_schema().get("columns", [])
                )
                key_cols = [c["name"] for c in input_schema]
            except Exception:
                key_cols = []
            if not key_cols:
                exit_with_error(
                    f"Cannot infer distinct keys: input '{input_ds}' has no readable schema.",
                    details=[
                        "The input dataset either does not exist or has never been built (zero columns).",
                        "Either pass explicit keys, or build the input first:",
                        f"  dku recipe create-distinct {recipe_name} -i {input_ds} --output-ds {output_ds} --on COL [--on COL2 ...] -P {project_key}",
                        f"  dku dataset build {input_ds} -P {project_key} --type RECURSIVE_BUILD --auto-update-schema --wait",
                    ],
                )

        builder = proj.new_recipe("distinct", recipe_name)
        builder.with_input(input_ds)
        _wire_single_output(client, proj, builder, output_ds, project_key, connection)
        builder.build()

        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)

        if key_cols:
            payload["keys"] = [{"column": c} for c in key_cols]
            # selectAllColumns=True dedupes on EVERY column (full-row distinct),
            # ignoring `keys` for the dedup. That is correct only when no --on was
            # given (key_cols == all input columns). With an explicit --on subset,
            # selectAllColumns MUST be False, otherwise the subset is silently
            # ignored and DSS dedupes on all columns (e.g. --on "Reference Number"
            # returns ~every row instead of one per Reference Number). With it
            # False, dedup is on the subset and the output projects to those keys.
            payload["selectAllColumns"] = not bool(on)
            info(
                "Distinct on: "
                + ", ".join(key_cols[:5])
                + (f" (+{len(key_cols) - 5} more)" if len(key_cols) > 5 else "")
            )
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

        _auto_apply_schema(proj, recipe_name)
        success(f"Created distinct recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
    except Exception as e:
        handle_api_error(e)

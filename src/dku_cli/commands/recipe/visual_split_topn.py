"""Split and top-N visual recipe commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from ._common import *
from dku_cli.enums import EngineType, SplitMode


@app.command("create-split")
def create_split(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: list[str] = typer.Option(
        ...,
        "--output-ds",
        "--output-dataset",
        help=(
            "Output dataset name. Repeatable — Split recipes need 2+ outputs. "
            "The 0-based position is the OUT_INDEX referenced by --value-split etc."
        ),
    ),
    mode: SplitMode = typer.Option(
        SplitMode.VALUES,
        "--mode",
        case_sensitive=False,
        help=(
            "Split mode: VALUES (default — by discriminator column), RANDOM "
            "(by ratio), RANGE (by numeric/date range), FILTER (by GREL "
            "expression per output), CENTILE (by ordered ratio)."
        ),
    ),
    column: str | None = typer.Option(
        None,
        "--column",
        "-c",
        help="Discriminator column for VALUES / RANGE modes.",
    ),
    value_splits: list[str] | None = typer.Option(
        None,
        "--value-split",
        help=(
            "VALUES mode. Format: 'COLUMN_VALUE=OUT_INDEX'. "
            "LEFT side is the value found in --column; RIGHT side is the "
            "0-based index of the --output-ds you listed (in order). So "
            "with --output-ds active --output-ds lapsed, "
            '--value-split active=0 means \'rows where --column == "active" '
            "go to the FIRST output (active)'. Repeatable."
        ),
    ),
    random_shares: list[str] | None = typer.Option(
        None,
        "--random-share",
        help=(
            "RANDOM / CENTILE mode: 'OUT_INDEX:PERCENT' — share of rows "
            "(0-100) routed to OUT_INDEX. Repeatable. Shares should sum to "
            "100 across all listed outputs."
        ),
    ),
    range_splits: list[str] | None = typer.Option(
        None,
        "--range-split",
        help=(
            "RANGE mode: 'MIN..MAX=OUT_INDEX'. Use '..' as the separator. "
            "Empty MIN or MAX means open-ended (e.g. '..100=0' or '100..=1'). "
            "Repeatable."
        ),
    ),
    filter_splits: list[str] | None = typer.Option(
        None,
        "--filter-split",
        help=(
            "FILTER mode: 'GREL_EXPR=OUT_INDEX'. Repeatable. The first "
            "matching filter wins per row."
        ),
    ),
    centile_orders: list[str] | None = typer.Option(
        None,
        "--centile-order",
        help=(
            "CENTILE mode: column to order by, append ':desc' for descending. "
            "Repeatable. Combine with --random-share OUT_INDEX:PCT."
        ),
    ),
    seed: int = typer.Option(
        1337,
        "--seed",
        help="Seed for RANDOM / RANDOM_COLUMNS modes (default 1337).",
    ),
    default_output: int | None = typer.Option(
        None,
        "--default-output",
        help=(
            "OUT_INDEX where rows that match no split go. If omitted, "
            "unmatched rows are dropped."
        ),
    ),
    engine: EngineType | None = typer.Option(
        None,
        "--engine",
        case_sensitive=False,
        help="payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Split recipe. Routes input rows to N output datasets.

    Use this instead of N Filter recipes or a Python recipe with conditional
    df.iloc[]. Most common pattern: VALUES mode with a discriminator column.

    Examples:
      VALUES mode (split by column value):
        dku recipe create-split route -i orders \\
          --output-ds active --output-ds lapsed --output-ds churned \\
          --mode VALUES --column status \\
          --value-split active=0 --value-split lapsed=1 --value-split churned=2 \\
          -P PROJ

      RANDOM mode (70/30 train/test):
        dku recipe create-split traintest -i rows \\
          --output-ds train --output-ds test \\
          --mode RANDOM --random-share 0:70 --random-share 1:30 --seed 42 -P PROJ

      RANGE mode (numeric bins):
        dku recipe create-split bin -i rows \\
          --output-ds low --output-ds high \\
          --mode RANGE --column price --range-split ..100=0 --range-split 100..=1 -P PROJ

      FILTER mode (GREL per output):
        dku recipe create-split tag -i rows \\
          --output-ds vip --output-ds rest \\
          --mode FILTER --filter-split 'spend>1000=0' --default-output 1 -P PROJ
    """
    project_key = resolve_project(project)
    if len(output_ds) < 2:
        exit_with_error(
            "Split recipes need at least 2 output datasets.",
            code="invalid_argument",
            details=[
                "Repeat --output-ds: --output-ds out1 --output-ds out2 [...]",
            ],
        )
    mode_upper = mode.value

    if mode_upper == "VALUES":
        if not column:
            exit_with_error(
                "--mode VALUES requires --column COL.",
                code="invalid_argument",
            )
        if not value_splits:
            exit_with_error(
                "--mode VALUES requires at least one --value-split VAL=OUT_INDEX.",
                code="invalid_argument",
            )
    elif mode_upper == "RANDOM":
        if not random_shares:
            exit_with_error(
                "--mode RANDOM requires --random-share OUT_INDEX:PERCENT.",
                code="invalid_argument",
            )
    elif mode_upper == "RANGE":
        if not column:
            exit_with_error(
                "--mode RANGE requires --column COL.",
                code="invalid_argument",
            )
        if not range_splits:
            exit_with_error(
                "--mode RANGE requires at least one --range-split MIN..MAX=OUT_INDEX.",
                code="invalid_argument",
            )
    elif mode_upper == "FILTER":
        if not filter_splits:
            exit_with_error(
                "--mode FILTER requires at least one --filter-split EXPR=OUT_INDEX.",
                code="invalid_argument",
            )
    elif mode_upper == "CENTILE":
        if not centile_orders:
            exit_with_error(
                "--mode CENTILE requires at least one --centile-order COL[:desc].",
                code="invalid_argument",
            )
        if not random_shares:
            exit_with_error(
                "--mode CENTILE requires --random-share OUT_INDEX:PERCENT.",
                code="invalid_argument",
            )

    if default_output is not None and (
        default_output < 0 or default_output >= len(output_ds)
    ):
        exit_with_error(
            f"--default-output {default_output} out of range (0..{len(output_ds) - 1}).",
            code="invalid_argument",
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        for ds in output_ds:
            _ensure_output_dataset(client, proj, ds, project_key)
        builder = proj.new_recipe("split", recipe_name)
        builder.with_input(input_ds)
        for ds in output_ds:
            builder.with_existing_output(ds)
        builder.build()

        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = settings.obj_payload
        payload["mode"] = "FILTERS" if mode_upper == "FILTER" else mode_upper

        if mode_upper == "VALUES":
            payload["column"] = column
            splits = []
            for entry in value_splits or []:
                if "=" not in entry:
                    exit_with_error(
                        f"Invalid --value-split '{entry}'. Expected 'VALUE=OUT_INDEX'.",
                        code="invalid_argument",
                    )
                value, idx_str = entry.rsplit("=", 1)
                try:
                    idx = int(idx_str)
                except ValueError:
                    exit_with_error(
                        f"Invalid OUT_INDEX in --value-split '{entry}'.",
                        code="invalid_argument",
                    )
                if idx < 0 or idx >= len(output_ds):
                    exit_with_error(
                        f"--value-split OUT_INDEX {idx} out of range.",
                        code="invalid_argument",
                    )
                splits.append({"outputIndex": idx, "value": value})
            payload["valueSplits"] = splits
        elif mode_upper == "RANDOM":
            payload["seed"] = seed
            payload["randomSplits"] = _build_share_splits(
                random_shares, len(output_ds), "--random-share"
            )
        elif mode_upper == "RANGE":
            payload["column"] = column
            payload["rangeSetTime"] = False
            splits = []
            for entry in range_splits or []:
                if "=" not in entry:
                    exit_with_error(
                        f"Invalid --range-split '{entry}'. Expected 'MIN..MAX=OUT_INDEX'.",
                        code="invalid_argument",
                    )
                rng, idx_str = entry.rsplit("=", 1)
                try:
                    idx = int(idx_str)
                except ValueError:
                    exit_with_error(
                        f"Invalid OUT_INDEX in --range-split '{entry}'.",
                        code="invalid_argument",
                    )
                if ".." not in rng:
                    exit_with_error(
                        f"Invalid range in --range-split '{entry}'. Expected 'MIN..MAX' (either bound may be empty).",
                        code="invalid_argument",
                    )
                min_str, max_str = rng.split("..", 1)
                split_obj = {
                    "outputIndex": idx,
                    "include_min": True,
                    "include_max": False,
                }
                if min_str.strip():
                    split_obj["min"] = min_str.strip()
                if max_str.strip():
                    split_obj["max"] = max_str.strip()
                splits.append(split_obj)
            payload["rangeSplits"] = splits
        elif mode_upper == "FILTER":
            splits = []
            for entry in filter_splits or []:
                if "=" not in entry:
                    exit_with_error(
                        f"Invalid --filter-split '{entry}'. Expected 'EXPR=OUT_INDEX'.",
                        code="invalid_argument",
                    )
                expr, idx_str = entry.rsplit("=", 1)
                try:
                    idx = int(idx_str)
                except ValueError:
                    exit_with_error(
                        f"Invalid OUT_INDEX in --filter-split '{entry}'.",
                        code="invalid_argument",
                    )
                # DSS evaluates the TOP-LEVEL `expression` field when
                # uiData.mode == "CUSTOM"; placing it only inside uiData makes
                # DSS fall through to empty conditions[] and match all rows.
                splits.append(
                    {
                        "outputIndex": idx,
                        "filter": _build_pipeline_filter(expr),
                    }
                )
            payload["filterSplits"] = splits
        elif mode_upper == "CENTILE":
            orders = []
            for entry in centile_orders or []:
                if ":" in entry:
                    col, direction = entry.rsplit(":", 1)
                    desc = direction.strip().lower() == "desc"
                else:
                    col, desc = entry, False
                orders.append({"column": col.strip(), "desc": desc})
            payload["centileOrders"] = orders
            payload["centileSplits"] = _build_share_splits(
                random_shares, len(output_ds), "--random-share"
            )

        if default_output is not None:
            payload["defaultOutputIndex"] = default_output
        engine_upper = _enum_value(engine)
        _apply_engine_type(payload, engine_upper)
        settings.save()

        _auto_apply_schema(proj, recipe_name)
        if engine_upper:
            info(f"Engine: {engine_upper}")
        success(
            f"Created split recipe '{recipe_name}' (mode={mode_upper}, "
            f"outputs={len(output_ds)}) in {project_key}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _build_share_splits(
    entries: list[str] | None, n_outputs: int, flag: str
) -> list[dict]:
    splits: list[dict] = []
    for entry in entries or []:
        if ":" not in entry:
            exit_with_error(
                f"Invalid {flag} '{entry}'. Expected 'OUT_INDEX:PERCENT'.",
                code="invalid_argument",
            )
        idx_str, share_str = entry.split(":", 1)
        try:
            idx = int(idx_str)
            share = float(share_str)
        except ValueError:
            exit_with_error(
                f"Invalid {flag} '{entry}'. OUT_INDEX must be int and PERCENT a number.",
                code="invalid_argument",
            )
        if idx < 0 or idx >= n_outputs:
            exit_with_error(
                f"{flag} index {idx} out of range (0..{n_outputs - 1}).",
                code="invalid_argument",
            )
        splits.append({"outputIndex": idx, "share": share})
    return splits


@app.command("create-topn")
def create_topn(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    n: int = typer.Option(
        10, "--n", "-n", help="Number of top rows to keep (default: 10)"
    ),
    sort_col: str = typer.Option(
        None,
        "--sort-col",
        "-s",
        help="Column to rank by: 'col' (desc) or 'col:asc'. Default direction: desc (top values).",
    ),
    rank_by: list[str] | None = typer.Option(
        None,
        "--rank-by",
        help="Ranking column. Append ':desc' for descending (default: ascending). Repeatable.",
    ),
    partition_key: list[str] | None = typer.Option(
        None,
        "--partition-key",
        "-k",
        help="Partition column for top N per group. Repeatable.",
    ),
    bottom: int | None = typer.Option(
        None,
        "--bottom",
        help=(
            "Keep the BOTTOM N rows per group instead of top N (writes "
            "lastRows=N, firstRows=0). Mutually exclusive with --n."
        ),
    ),
    enable_rank: bool = typer.Option(
        False, "--rank", help="Add a `rank` output column."
    ),
    enable_dense_rank: bool = typer.Option(
        False, "--dense-rank", help="Add a `denseRank` output column."
    ),
    enable_row_number: bool = typer.Option(
        False, "--row-number", help="Add a `rowNumber` output column."
    ),
    duplicate_count: bool = typer.Option(
        False, "--duplicate-count", help="Add a `duplicateCount` output column."
    ),
    columns: str | None = typer.Option(
        None,
        "--columns",
        help=(
            "Project to these columns (comma-separated). Sets "
            "retrievedColumnsSelectionMode=SELECTED + retrievedColumns. "
            "Avoids a downstream Prepare add-delete-columns."
        ),
    ),
    rename: list[str] | None = typer.Option(
        None,
        "--rename",
        help=(
            "Rename a generated column (rank/denseRank/rowNumber/...): 'SRC:DST'. "
            "Repeatable. Writes outputColumnNameOverrides."
        ),
    ),
    pre_filter: str | None = typer.Option(
        None, "--pre-filter", help="GREL formula applied BEFORE TopN ranking."
    ),
    post_filter: str | None = typer.Option(
        None,
        "--post-filter",
        help="GREL formula applied AFTER TopN selection.",
    ),
    computed_col: list[str] | None = typer.Option(
        None,
        "--computed-col",
        help="Add a computed column before ranking: 'name=expr[:type]'. Repeatable.",
    ),
    engine: EngineType | None = typer.Option(
        None,
        "--engine",
        case_sensitive=False,
        help="payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Top N recipe. Returns the top/bottom N rows per group.

    Use this instead of df.nlargest() or df.head() in Python.
    Use --sort-col or --rank-by for the ordering column, --n for how many rows, and
    --partition-key for top N per group.

    Examples:
      dku recipe create-topn top10 -i sales --output-ds top10 --n 10 --sort-col revenue:desc -P PROJ

      Bottom-N with rank column and projection:
        dku recipe create-topn worst -i sales --output-ds worst3 \\
          --bottom 3 --sort-col revenue --rank --columns "id,revenue,rank" -P PROJ
    """
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)
    if bottom is not None and bottom < 0:
        exit_with_error(
            "--bottom must be a non-negative integer.", code="invalid_argument"
        )
    # --bottom and --n are mutually exclusive (see --bottom help). Reject both
    # rather than silently discarding --n. `n` defaults to 10.
    if bottom is not None and n != 10:
        exit_with_error(
            "--bottom and --n are mutually exclusive.",
            code="invalid_argument",
            details=[
                "Use --n for top-N or --bottom for bottom-N, not both.",
                "For the bottom 3 rows, drop --n: --bottom 3.",
            ],
        )
    columns_list: list[str] = []
    if columns:
        columns_list = [c.strip() for c in columns.split(",") if c.strip()]
    renames_map: dict[str, str] = {}
    if rename:
        for entry in rename:
            if ":" not in entry:
                exit_with_error(
                    f"Invalid --rename '{entry}'. Expected 'SRC:DST'.",
                    code="invalid_argument",
                )
            src, dst = entry.split(":", 1)
            renames_map[src.strip()] = dst.strip()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("topn", recipe_name)
        builder.with_input(input_ds)
        builder.with_output(output_ds)
        builder.build()

        # Configure topN settings in obj_payload (TopNRecipeSettings has no helpers).
        # DSS uses `firstRows` for the actual row count and `keys` (string array)
        # for partition columns — NOT `topN` alone or `partitioningColumns`.
        recipe_obj = proj.get_recipe(recipe_name)
        topn_settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(topn_settings)
        if bottom is not None:
            payload["topN"] = bottom
            payload["firstRows"] = 0
            payload["lastRows"] = bottom
        else:
            payload["topN"] = n
            payload["firstRows"] = n
            payload["lastRows"] = 0
        # --sort-col takes precedence over --rank-by (single-column shorthand)
        if sort_col:
            if ":" in sort_col:
                col, direction = sort_col.rsplit(":", 1)
                desc = direction.strip().lower() != "asc"
            else:
                col = sort_col
                desc = True  # TopN default: desc (top values)
            payload["orders"] = [{"column": col.strip(), "desc": desc}]
            info(f"Sort: {sort_col}")
        elif rank_by:
            payload["orders"] = _parse_order_specs(rank_by)
            info(f"Rank by: {', '.join(rank_by)}")
        if partition_key:
            payload["keys"] = list(partition_key)
            info(f"Partition by: {', '.join(partition_key)}")
        if enable_rank:
            payload["rank"] = True
        if enable_dense_rank:
            payload["denseRank"] = True
        if enable_row_number:
            payload["rowNumber"] = True
        if duplicate_count:
            payload["duplicateCount"] = True
        if columns_list:
            payload["retrievedColumnsSelectionMode"] = "SELECTED"
            payload["retrievedColumns"] = list(columns_list)
            info(f"Selected columns: {', '.join(columns_list)}")
        if renames_map:
            payload["outputColumnNameOverrides"] = renames_map
            info("Rename: " + ", ".join(f"{s}→{d}" for s, d in renames_map.items()))
        _apply_pipeline_options(
            payload,
            pre_filter=pre_filter,
            post_filter=post_filter,
            computed_cols=computed_col,
            renames=None,  # already handled above
        )
        _apply_engine_type(payload, engine_upper)
        if pre_filter:
            info(f"Pre-filter: {pre_filter}")
        if post_filter:
            info(f"Post-filter: {post_filter}")
        if computed_col:
            info(f"Computed cols: {len(computed_col)}")
        if engine_upper:
            info(f"Engine: {engine_upper}")
        topn_settings.save()

        _auto_apply_schema(proj, recipe_name)
        kind = "bottom" if bottom is not None else "top"
        amount = bottom if bottom is not None else n
        success(
            f"Created topn recipe '{recipe_name}' ({kind} {amount}) in {project_key}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

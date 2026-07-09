"""Code-adjacent visual recipe commands."""

from __future__ import annotations

import contextlib

# ruff: noqa: F403,F405
from dku_cli.enums import EngineType, FilterAction

from ._common import *


@app.command("create-sync")
def create_sync(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help="Connection for the auto-created output dataset (e.g. filesystem_managed). Required when the project has no default managed connection.",
    ),
    schema_mode: str | None = typer.Option(
        None,
        "--schema-mode",
        help="Output schema policy. STRICT_SYNC (default — input and output schemas must match). FREE_SCHEMA_NAME_BASED (allow extra/missing columns; match by name). DSS silently normalises any other value to FREE_SCHEMA_NAME_BASED.",
    ),
    max_threads: int | None = typer.Option(
        None,
        "--max-threads",
        help="Parallel-write thread count for the sync engine (default 4).",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a sync recipe with optional schema/engine tuning.

    Sync copies one dataset to another (e.g. Filesystem → Snowflake, or
    schema migration between connections). The output dataset is auto-created
    on `--connection`. Without `--schema-mode` the recipe uses STRICT_SYNC,
    which fails if the input schema and output schema differ — for
    schema-evolution syncs pass `--schema-mode FREE_SCHEMA_NAME_BASED`.

    `--max-threads` raises the per-engine parallel-write thread count for
    fast targets (S3, Snowflake bulk-load, etc.).

    Example:
        dku recipe create-sync stage_to_warehouse \\
            -i raw_csv --output-ds warehouse_table \\
            -c snowflake_prod --schema-mode FREE_SCHEMA_NAME_BASED \\
            --max-threads 8 -P PROJ
    """
    project_key = resolve_project(project)
    try:
        from dataikuapi.dss.recipe import SyncRecipeCreator

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = SyncRecipeCreator(recipe_name, proj)
        builder.with_input(input_ds)
        if connection:
            builder.with_new_output(output_ds, connection)
        else:
            builder.with_new_output(output_ds, None)
        builder.build()

        if schema_mode is not None or max_threads is not None:
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            raw = settings.get_recipe_raw_definition()
            params = raw.setdefault("params", {})
            if schema_mode is not None:
                params["schemaMode"] = schema_mode
            if max_threads is not None:
                engine = params.setdefault("engineParams", {})
                engine["maxThreads"] = max_threads
            settings.save()
        success(f"Created sync recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        if is_already_exists_error(e):
            exit_with_error(
                f"Output dataset '{output_ds}' already exists in {project_key}.",
                details=[
                    "Sync auto-creates its output dataset.",
                    f"Delete it first: dku dataset delete {output_ds} -P {project_key}",
                    "Or use a different --output-ds name.",
                ],
            )
        if is_connection_required_error(e):
            exit_with_error(
                f"Project {project_key} has no default managed connection.",
                details=[
                    "Pass --connection / -c with a managed connection name.",
                    "Find one: dku connection list",
                ],
            )
        handle_api_error(e)


@app.command("create-sql")
def create_sql(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: list[str] = typer.Option(
        [], "--input", "-i", help="Input dataset (repeatable for joins)"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    connection: str = typer.Option(
        ..., "--connection", help="SQL connection name (where the query runs)"
    ),
    sql: str | None = typer.Option(
        None, "--sql", help="SQL body: literal, @file.sql, or '-' for stdin"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a sql_query recipe.

    The SQL body is stored as a raw text payload (NOT JSON). The output dataset
    must be on `--connection` (sql_query is a SingleOutputRecipeCreator). Run
    `dku recipe apply-schema RECIPE` after creation, otherwise the first build
    fails with `INSERT has more expressions than target columns`.

    Reference output table as `${projectKey}_<dataset>` inside the SQL body.

    Example:
        dku recipe create-sql q -i raw --output-ds clean \\
            --connection prod_pg --sql @cleanup.sql -P PROJ
    """
    project_key = resolve_project(project)
    try:
        from dataikuapi.dss.recipe import SQLQueryRecipeCreator

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = SQLQueryRecipeCreator(recipe_name, proj)
        for ds in input_ds:
            builder.with_input(ds)
        builder.with_existing_output(output_ds)
        builder.build()

        if sql:
            body = read_text_input(sql)
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            # sql_query payload IS a string (the SQL itself), not an object.
            settings.set_payload(body) if hasattr(settings, "set_payload") else None
            if not hasattr(settings, "set_payload"):
                # Older dataikuapi: payload is a string in obj_payload
                settings.obj_payload = body
            settings.save()
            info(f"Wrote {len(body)} bytes of SQL")
        success(f"Created sql_query recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
        info(
            "Tip: dku recipe apply-schema "
            + recipe_name
            + f" -P {project_key} (run before first build)"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-sql")
def set_sql(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    sql: str = typer.Option(
        ..., "--sql", help="New SQL body: literal, @file.sql, or '-' for stdin"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Update the SQL body of a sql_query recipe.

    Equivalent to `dku recipe set-code` but explicit for SQL recipes.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        body = read_text_input(sql)
        recipe_obj = proj.get_recipe(recipe_name)
        with locked_settings(
            client, project_key, "recipe", recipe_name, recipe_obj.get_settings
        ) as settings:
            if hasattr(settings, "set_payload"):
                settings.set_payload(body)
            else:
                settings.obj_payload = body
        success(f"Updated SQL for '{recipe_name}' ({len(body)} bytes)")
    except Exception as e:
        handle_api_error(e)


@app.command("create-r")
def create_r(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: list[str] = typer.Option(
        [], "--input", "-i", help="Input dataset (repeatable)"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    code: str | None = typer.Option(
        None, "--code", help="R code: literal, @file.R, or '-' for stdin"
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        help="Managed connection for the auto-created output dataset (defaults to project default)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an R code recipe.

    Mirrors `dku recipe create -t r` but with an explicit `--code` flag (file
    or stdin) and auto-create of the output dataset.

    Example:
        dku recipe create-r ingest_sdtm --output-ds dm_raw \\
            --code @ingest.R -P PROJ
    """
    project_key = resolve_project(project)
    try:
        from dataikuapi.dss.recipe import CodeRecipeCreator

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = CodeRecipeCreator(recipe_name, "r", proj)
        for ds in input_ds:
            builder.with_input(ds)
        # CodeRecipeCreator uses with_output(name) — there is no
        # with_existing_output on this class.
        builder.with_output(output_ds)
        builder.build()
        if code:
            body = read_text_input(code)
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            if hasattr(settings, "set_payload"):
                settings.set_payload(body)
            else:
                settings.obj_payload = body
            settings.save()
            info(f"Wrote {len(body)} bytes of R code")
        success(f"Created R recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-clustering-scoring")
def create_clustering_scoring(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset to score"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset"
    ),
    model: str = typer.Option(..., "--model", help="Saved clustering model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Clustering Scoring recipe (classic ML — assigns cluster labels).

    Example:
        dku recipe create-clustering-scoring score_clusters \\
            -i customers --output-ds customers_segmented --model abc123 -P PROJ
    """
    project_key = resolve_project(project)
    try:
        from dataikuapi.dss.recipe import ClusteringScoringRecipeCreator

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = ClusteringScoringRecipeCreator(recipe_name, proj)
        builder.with_input_model(model)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        # DSS auto-names scoring recipes 'score_<input>'; reconcile so the
        # schema apply below targets the real recipe (else the output stays at
        # 0 columns and the first build fails on a schema incompatibility).
        recipe_name = _build_scoring_recipe(builder, recipe_name)
        _auto_apply_schema(proj, recipe_name)
        success(
            f"Created clustering_scoring recipe '{recipe_name}' in {project_key} (model={model})"
        )
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-prepare")
def create_prepare(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    engine: EngineType | None = typer.Option(
        None,
        "--engine",
        case_sensitive=False,
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Set SQL for Snowflake/Postgres pushdown — Prepare runs in-DB without "
            "shuttling rows through the DSS engine."
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
    """Create an empty Prepare recipe (auto-creates output dataset).

    Shortcut for `recipe create -t shaker` that auto-creates the output
    dataset like every other `create-*` visual shortcut. The recipe is
    created with no steps — chain `dku recipe add-formula`, `add-rename`,
    `add-step`, etc. to configure it.

    Internal type is `shaker` (DSS legacy name); `dku recipe create -t prepare`
    is rejected by `dataikuapi`.

    Example:
      dku recipe create-prepare clean -i raw --output-ds cleaned -P PROJ \\
        && dku recipe add-formula clean --column total --expr 'price * qty' -P PROJ

    SQL pushdown:
      dku recipe create-prepare clean -i raw --output-ds cleaned --engine SQL -P PROJ
    """
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("shaker", recipe_name)
        builder.with_input(input_ds)
        _wire_single_output(client, proj, builder, output_ds, project_key, connection)
        builder.build()
        if engine_upper:
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            payload = _get_recipe_payload(settings)
            _apply_engine_type(payload, engine_upper)
            settings.save()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created prepare recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
    except Exception as e:
        handle_api_error(e)


@app.command("create-sort")
def create_sort(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    sort_col: list[str] = typer.Option(
        None,
        "--sort-col",
        "-s",
        help="Sort column: 'col' (asc) or 'col:desc'. Repeatable.",
    ),
    enable_rank: bool = typer.Option(
        False, "--rank", help="Emit a 'rank' column alongside sorted rows."
    ),
    enable_dense_rank: bool = typer.Option(
        False,
        "--dense-rank",
        help="Emit a 'denseRank' column.",
    ),
    enable_row_number: bool = typer.Option(
        False,
        "--row-number",
        help="Emit a 'rowNumber' column.",
    ),
    pre_filter: str | None = typer.Option(
        None, "--pre-filter", help="GREL formula applied BEFORE sorting."
    ),
    post_filter: str | None = typer.Option(
        None,
        "--post-filter",
        help="GREL formula applied AFTER sorting.",
    ),
    computed_col: list[str] | None = typer.Option(
        None,
        "--computed-col",
        help="Add a computed column before sorting: 'name=expr[:type]'. Repeatable.",
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
    """Create a Sort recipe.

    Use this instead of df.sort_values() in Python.
    Use --sort-col to configure sort columns at creation time.

    Sort recipes support the same 4-stage pipeline as Group/Window/Distinct
    (preFilter → computedColumns → orders → postFilter). Use --rank /
    --dense-rank / --row-number to also emit ranking columns alongside the
    sorted rows (the recipe shape is identical to a 1-window TopN with no
    cap on rows).

    Example: dku recipe create-sort my_sort -i data --output-ds sorted --sort-col price:desc -P PROJ
    """
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("sort", recipe_name)
        builder.with_input(input_ds)
        _wire_single_output(client, proj, builder, output_ds, project_key, connection)
        builder.build()

        needs_save = bool(
            sort_col
            or pre_filter
            or post_filter
            or computed_col
            or rename
            or enable_rank
            or enable_dense_rank
            or enable_row_number
            or engine_upper
        )
        if needs_save:
            recipe_obj = proj.get_recipe(recipe_name)
            sort_settings = recipe_obj.get_settings()
            if sort_col:
                with contextlib.suppress(AttributeError, TypeError):
                    sort_settings.clear_sorting_keys()
                for col_spec in sort_col:
                    if ":" in col_spec:
                        col, direction = col_spec.rsplit(":", 1)
                        ascending = direction.strip().lower() != "desc"
                    else:
                        col = col_spec
                        ascending = True
                    try:
                        sort_settings.add_sorting_key(col.strip(), ascending=ascending)
                    except (AttributeError, TypeError):
                        # Fallback: set via raw params
                        raw = sort_settings.get_recipe_raw_definition()
                        params = raw.setdefault("params", {})
                        orders = params.setdefault("orders", [])
                        orders.append({"column": col.strip(), "desc": not ascending})
                info(f"Sort columns: {', '.join(sort_col)}")
            payload = _get_recipe_payload(sort_settings)
            if enable_rank:
                payload["rank"] = True
            if enable_dense_rank:
                payload["denseRank"] = True
            if enable_row_number:
                payload["rowNumber"] = True
            _apply_pipeline_options(
                payload,
                pre_filter=pre_filter,
                post_filter=post_filter,
                computed_cols=computed_col,
                renames=rename,
            )
            _apply_engine_type(payload, engine_upper)
            sort_settings.save()
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

        _auto_apply_schema(proj, recipe_name)
        success(f"Created sort recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
    except Exception as e:
        handle_api_error(e)


@app.command("create-filter")
def create_filter(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    filter_formula: str = typer.Option(
        ...,
        "--filter-formula",
        "--filter",
        "-f",
        help="DSS formula filter expression (e.g. 'age > 30')",
    ),
    action: FilterAction = typer.Option(
        FilterAction.KEEP_ROW,
        "--action",
        case_sensitive=False,
        help="KEEP_ROW (keep matching) or REMOVE_ROW (drop matching)",
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help=(
            "Create the output as a managed dataset on this connection "
            "(e.g. a Snowflake connection for in-database filtering/pushdown). "
            "Without it the output lands on the default managed connection."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a filter recipe (rows matching the formula).

    Builds a Prepare recipe with a single FilterOnCustomFormula step.
    Prefer this over the Sampling recipe type, whose filter schema is unstable
    and which silently drops the filter expression on many DSS versions.

    Use instead of df[df.col > X] in Python.

    For in-database filtering, pass --connection (the output is created on that
    connection so the filter runs where the data lives).
    """
    project_key = resolve_project(project)
    action = action.value
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("shaker", recipe_name)
        builder.with_input(input_ds)
        _wire_single_output(client, proj, builder, output_ds, project_key, connection)
        builder.build()

        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        steps = _ensure_steps_array(settings)
        steps.append(
            {
                "metaType": "PROCESSOR",
                "type": "FilterOnCustomFormula",
                "params": {"expression": filter_formula, "action": action},
            }
        )
        settings.save()
        info(f"Filter: {filter_formula} ({action})")

        _auto_apply_schema(proj, recipe_name)
        success(f"Created filter recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


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

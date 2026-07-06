"""Folder, sync, SQL, and scoring visual recipe commands."""

from __future__ import annotations

from dku_cli.enums import EngineType, ExportFormat, MergeFolderConflict

# ruff: noqa: F403,F405
from ._common import *


@app.command("create-update")
def create_update(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Source dataset (deltas)"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Target dataset (existing)"
    ),
    unique_key: list[str] = typer.Option(
        ...,
        "--unique-key",
        help="Column defining row identity (repeatable for composite key)",
    ),
    add_missing_rows: bool = typer.Option(
        True,
        "--add-missing-rows/--no-add-missing-rows",
        help="Insert rows present in input but missing in target (default: yes)",
    ),
    delete_missing_rows: bool = typer.Option(
        False,
        "--delete-missing-rows/--no-delete-missing-rows",
        help="Delete rows present in target but missing in input (default: no)",
    ),
    add_missing_cols: bool = typer.Option(
        True,
        "--add-missing-cols/--no-add-missing-cols",
        help="Add columns present in input but missing in target (default: yes)",
    ),
    delete_missing_cols: bool = typer.Option(
        False,
        "--delete-missing-cols/--no-delete-missing-cols",
        help="Delete columns present in target but missing in input (default: no)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Update (UPSERT) recipe.

    Maintains the output dataset by merging rows from input on a unique key.
    The output dataset MUST already exist (Update operates in-place; the
    output is not auto-created because there is no schema-source to copy from).

    The ``update`` recipe stores its config under ``recipe.params`` (not the
    JSON payload). Different from the SQL-merge ``upsert`` recipe type which
    is keyed on ``payload.keys`` and runs as a SQL MERGE.

    Example:
        dku recipe create-update upsert_customers \\
            -i customers_delta --output-ds customers_master \\
            --unique-key customer_id -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        # Update operates on an existing output; do not auto-create.
        try:
            proj.get_dataset(output_ds).get_schema()
        except Exception:
            exit_with_error(
                f"Output dataset '{output_ds}' does not exist in {project_key}.",
                details=[
                    "Update recipes write into an EXISTING target. Create it first:",
                    f"  dku dataset create {output_ds} -P {project_key} --type Filesystem",
                    "Or seed it from an upstream recipe (e.g. a one-time sync) before this update.",
                ],
            )
        recipe_obj = _raw_create_recipe(
            proj,
            "update",
            recipe_name,
            inputs=[(input_ds, "main")],
            outputs=[(output_ds, "main")],
        )
        settings = recipe_obj.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        raw_def["params"] = {
            "uniqueKey": list(unique_key),
            "addMissingRows": add_missing_rows,
            "deleteMissingRows": delete_missing_rows,
            "addMissingCols": add_missing_cols,
            "deleteMissingCols": delete_missing_cols,
            "filter": {"distinct": False, "enabled": False},
        }
        settings.save()
        success(
            f"Created update recipe '{recipe_name}' in {project_key} "
            f"(key={','.join(unique_key)}, +rows={add_missing_rows}, "
            f"-rows={delete_missing_rows}, +cols={add_missing_cols}, -cols={delete_missing_cols})"
        )
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-extract-failed-rows")
def create_extract_failed_rows(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset (with checks defined)"
    ),
    output_ds: str = typer.Option(
        ...,
        "--output-ds",
        "--output-dataset",
        help="Quarantine dataset (will be created)",
    ),
    rule_id: list[str] = typer.Option(
        [],
        "--rule-id",
        help=(
            "Check rule ID to extract failures for (repeatable). "
            "Use 'dku dq list DATASET -P PROJ' to discover IDs. "
            "Default: extract failures for all enabled rules on the input."
        ),
    ),
    rule_column: list[str] = typer.Option(
        [],
        "--rule-column",
        help=(
            "Map rule to a column: 'RULE_ID:column'. Repeatable. "
            "If omitted, the column is taken from the rule definition."
        ),
    ),
    engine: EngineType | None = typer.Option(
        None,
        "--engine",
        case_sensitive=False,
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Set SQL for Snowflake/Postgres pushdown."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Extract-Failed-Rows recipe (built-in DSS recipe type).

    Quarantines rows that violated dataset checks on the input.

    The input dataset MUST have checks defined (`dku dq create ...`).
    Without --rule-id, the recipe extracts rows failing ANY enabled rule.

    Example:
        dku recipe create-extract-failed-rows quarantine_customers \\
            -i customers --output-ds customers_failed \\
            --rule-id customer_id_not_null --rule-id email_format -P PROJ
    """
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)

    rule_column_map: dict[str, str] = {}
    for entry in rule_column:
        if ":" not in entry:
            exit_with_error(
                f"Invalid --rule-column '{entry}'. Expected 'RULE_ID:column'.",
            )
        rid, col = entry.split(":", 1)
        rule_column_map[rid.strip()] = col.strip()

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("extract_failed_rows", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()

        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)

        column_rules: list[dict] = []
        if rule_id:
            for rid in rule_id:
                column_rules.append(
                    {
                        "ruleColumn": rule_column_map.get(rid, ""),
                        "ruleId": rid,
                        "isSelected": True,
                    }
                )
        payload["columnRules"] = column_rules
        _apply_engine_type(payload, engine_upper)
        settings.save()
        _auto_apply_schema(proj, recipe_name)
        if engine_upper:
            info(f"Engine: {engine_upper}")
        success(
            f"Created extract_failed_rows recipe '{recipe_name}' in {project_key} "
            f"({len(column_rules) or 'all'} rule(s))"
        )
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-list-folder-contents")
def create_list_folder_contents(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    folder: str = typer.Option(
        ...,
        "--folder",
        "--input",
        "-i",
        help="Source managed folder ID or name (also accepts --input/-i for parity with other create-* verbs).",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset (1 row per file)"
    ),
    no_path: bool = typer.Option(False, "--no-path", help="Don't emit 'path' column"),
    no_basename: bool = typer.Option(
        False, "--no-basename", help="Don't emit 'basename' column"
    ),
    no_extension: bool = typer.Option(
        False, "--no-extension", help="Don't emit 'extension' column"
    ),
    no_size: bool = typer.Option(False, "--no-size", help="Don't emit 'size' column"),
    no_last_modified: bool = typer.Option(
        False, "--no-last-modified", help="Don't emit 'lastModified' column"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a List-Folder-Contents recipe (built-in DSS recipe type).

    Emits one row per file in the source folder, with metadata columns
    (path, basename, extension, size, lastModified). Parent-folder
    columns (``levelMapping[]``) are not yet exposed by a flag — set
    them via ``dku recipe set-settings`` after creation.

    Example:
        dku recipe create-list-folder-contents inventory_files \\
            --folder raw_uploads --output-ds inventory_index -P PROJ
    """
    project_key = resolve_project(project)

    try:
        from dku_cli.helpers import resolve_folder

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder_obj = resolve_folder(proj, folder)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        # list_folder_contents is not in proj.new_recipe(); use raw create.
        recipe_obj = _raw_create_recipe(
            proj,
            "list_folder_contents",
            recipe_name,
            inputs=[(folder_obj.id, "main")],
            outputs=[(output_ds, "main")],
        )
        settings = recipe_obj.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        raw_def["params"] = {
            "path": not no_path,
            "basename": not no_basename,
            "extension": not no_extension,
            "size": not no_size,
            "lastModified": not no_last_modified,
            "levelMapping": [],
        }
        settings.save()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created list_folder_contents recipe '{recipe_name}' in {project_key}")
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-merge-folder")
def create_merge_folder(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    inputs: list[str] = typer.Option(
        ..., "--input", "-i", help="Source folder ID or name (repeatable, ≥1)"
    ),
    output_folder: str = typer.Option(
        ..., "--output-folder", help="Destination managed folder (will be created)"
    ),
    clear_before_copy: bool = typer.Option(
        False,
        "--clear-before-copy",
        help="Delete destination contents before copying",
    ),
    conflict_handling: MergeFolderConflict = typer.Option(
        MergeFolderConflict.OVERWRITE,
        "--conflict",
        case_sensitive=False,
        help="OVERWRITE | SKIP | FAIL when same path exists in multiple sources",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Merge-Folder recipe (built-in DSS folder→folder recipe).

    Combines files from multiple source managed folders into one destination.

    Example:
        dku recipe create-merge-folder consolidate_uploads \\
            -i upload_us -i upload_eu -i upload_apac \\
            --output-folder all_uploads --clear-before-copy -P PROJ
    """
    project_key = resolve_project(project)
    try:
        from dku_cli.helpers import resolve_folder

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        input_ids = [resolve_folder(proj, ref).id for ref in inputs]

        # Auto-create the destination folder if it doesn't exist.
        out_id = _ensure_output_folder(proj, output_folder)

        recipe_obj = _raw_create_recipe(
            proj,
            "merge_folder",
            recipe_name,
            inputs=[(fid, "main") for fid in input_ids],
            outputs=[(out_id, "main")],
        )
        settings = recipe_obj.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        raw_def["params"] = {
            "clearBeforeCopy": clear_before_copy,
            "conflictHandling": conflict_handling.value,
        }
        settings.save()
        success(
            f"Created merge_folder recipe '{recipe_name}' in {project_key} "
            f"({len(input_ids)} source(s) → {output_folder})"
        )
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-download")
def create_download(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    output_folder: str = typer.Option(
        ...,
        "--output-folder",
        help="Destination managed folder (will be auto-created if missing)",
    ),
    source: list[str] = typer.Option(
        ...,
        "--source",
        help=(
            "External source: 'PROVIDER:URL'. PROVIDER ∈ "
            "{HTTP,HTTPS,FTP,SCP,S3}. Repeatable. URL is provider-specific "
            "(http(s)://..., ftp://..., scp://user@host/path, s3://bucket/key)."
        ),
    ),
    delete_extra: bool = typer.Option(
        False,
        "--delete-extra",
        help="Delete files in the destination folder that aren't in the sources (mirror semantics).",
    ),
    copy_even_uptodate: bool = typer.Option(
        False,
        "--copy-even-up-to-date",
        help="Re-copy files even when the destination already has them (forces full pull).",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Download recipe (built-in DSS recipe).

    Pulls files from external HTTP/HTTPS/FTP/SCP/S3 sources into a managed
    folder. No input role; the output is a folder. Migration target: Alteryx
    Download tool, SAS `proc http` chains.

    Examples:
        dku recipe create-download fetch_csvs \\
            --output-folder raw_csvs \\
            --source 'HTTPS:https://example.com/data/2026.csv' \\
            --source 'HTTPS:https://example.com/data/2025.csv' \\
            -P PROJ

        dku recipe create-download fetch_s3 \\
            --output-folder s3_dump --source 'S3:s3://bucket/key.parquet' \\
            --delete-extra -P PROJ
    """
    _VALID_PROVIDERS = {"HTTP", "HTTPS", "FTP", "SCP", "S3"}
    sources_payload: list[dict] = []
    for entry in source:
        if ":" not in entry:
            exit_with_error(
                f"Invalid --source '{entry}'. Expected 'PROVIDER:URL'.",
                details=[f"Valid providers: {', '.join(sorted(_VALID_PROVIDERS))}"],
            )
        provider, url = entry.split(":", 1)
        provider_upper = provider.strip().upper()
        if provider_upper not in _VALID_PROVIDERS:
            exit_with_error(
                f"Invalid --source provider '{provider}'.",
                details=[f"Valid: {', '.join(sorted(_VALID_PROVIDERS))}"],
            )
        sources_payload.append(
            {"providerType": provider_upper, "params": {"url": url.strip()}}
        )
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # Auto-create the destination folder if it doesn't exist.
        out_id = _ensure_output_folder(proj, output_folder)

        recipe_obj = _raw_create_recipe(
            proj,
            "download",
            recipe_name,
            inputs=[],
            outputs=[(out_id, "main")],
        )
        settings = recipe_obj.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        raw_def["params"] = {
            "sources": sources_payload,
            "deleteExtraFiles": delete_extra,
            "copyEvenUpToDateFiles": copy_even_uptodate,
        }
        settings.save()
        success(
            f"Created download recipe '{recipe_name}' in {project_key} "
            f"({len(sources_payload)} source(s) → {output_folder})"
        )
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-export")
def create_export(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Source dataset"
    ),
    output_folder: str = typer.Option(
        ...,
        "--output-folder",
        help="Destination managed folder (will be auto-created if missing)",
    ),
    format: ExportFormat = typer.Option(
        ExportFormat.csv,
        "--format",
        case_sensitive=False,
        help="Export format: csv, excel, json, parquet, avro, tsv. Default: csv.",
    ),
    apply_exploration_filters: bool = typer.Option(
        False,
        "--apply-exploration-filters",
        help="Apply the dataset's saved exploration filters to the export.",
    ),
    apply_coloring: bool = typer.Option(
        False,
        "--apply-coloring",
        help="Carry the dataset's coloring rules into the export (Excel-only).",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Export recipe (built-in DSS recipe).

    Writes one file per dataset partition into a managed folder. Use this
    instead of a Sync-to-folder pattern when the consumer needs CSV/Excel/etc.
    rather than DSS-native storage.

    Example:
        dku recipe create-export to_csv -i sales --output-folder exports \\
            --format csv -P PROJ
    """
    fmt_lower = format.value
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # Auto-create the destination folder.
        out_id = _ensure_output_folder(proj, output_folder)

        recipe_obj = _raw_create_recipe(
            proj,
            "export",
            recipe_name,
            inputs=[(input_ds, "main")],
            outputs=[(out_id, "main")],
        )
        settings = recipe_obj.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        raw_def["params"] = {
            "exportParams": {
                "format": fmt_lower,
                "applyExplorationFilters": apply_exploration_filters,
                "applyColoring": apply_coloring,
            }
        }
        settings.save()
        success(
            f"Created export recipe '{recipe_name}' in {project_key} "
            f"({input_ds} → {output_folder} as {fmt_lower})"
        )
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-prediction-scoring")
def create_prediction_scoring(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset to score"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset (predictions)"
    ),
    model: str = typer.Option(..., "--model", help="Saved model ID to score with"),
    output_probabilities: bool = typer.Option(
        True,
        "--output-probabilities/--no-output-probabilities",
        help="Emit per-class probability columns (classification only).",
    ),
    output_explanations: bool = typer.Option(
        False,
        "--output-explanations",
        help="Emit per-prediction explanation columns (Shapley/ICE).",
    ),
    keep_cols: str | None = typer.Option(
        None,
        "--keep-cols",
        help="Comma-separated input columns to keep in the output. Default: all input columns.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Prediction Scoring recipe (classic ML).

    The full payload (sparkParams, gpuConfig, individualExplanationParams,
    etc.) is large; this shortcut writes the high-frequency fields and
    falls back to `dku recipe set-settings @file.json` for advanced tuning.

    Example:
        dku recipe create-prediction-scoring score_q4 \\
            -i q4_inputs --output-ds q4_predictions --model 7bdMB26q -P PROJ
    """
    project_key = resolve_project(project)
    try:
        from dataikuapi.dss.recipe import PredictionScoringRecipeCreator

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = PredictionScoringRecipeCreator(recipe_name, proj)
        builder.with_input_model(model)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)

        # On some DSS / dataikuapi version pairs, the response parser raises
        # KeyError('recipe') AFTER the recipe is successfully created on the
        # server. The recipe IS there — just the SDK's post-build response
        # decoder couldn't find an expected key. Swallow that one specific
        # KeyError; re-raise anything else.
        built_recipe = None
        try:
            built_recipe = builder.build()
        except KeyError as ke:
            if str(ke).strip("'") != "recipe":
                raise

        # DSS auto-names scoring recipes 'score_<input>'; reconcile to the
        # requested name so the payload patch + schema apply below hit the real
        # recipe (else the output stays at 0 columns and the build fails).
        if built_recipe is not None:
            recipe_name = _reconcile_scoring_name(built_recipe, recipe_name)
        else:
            # The KeyError swallowed the build handle — resolve the recipe by
            # name. Try the requested name first, then DSS's 'score_<input>'
            # auto-name, and rename the auto-name back when found.
            actual_recipe_name = recipe_name
            try:
                proj.get_recipe(recipe_name).get_settings()
            except Exception:
                auto_name = f"score_{input_ds}"
                try:
                    proj.get_recipe(auto_name).get_settings()
                    actual_recipe_name = auto_name
                except Exception:
                    exit_with_error(
                        f"Prediction-scoring recipe build did not produce a recipe "
                        f"named '{recipe_name}' or '{auto_name}'.",
                        details=[
                            "Re-check the inputs:",
                            f"  Input dataset: {input_ds}",
                            f"  Output dataset: {output_ds}",
                            f"  Saved model: {model}",
                            f"  Project: {project_key}",
                        ],
                    )
            if actual_recipe_name != recipe_name:
                try:
                    proj.get_recipe(actual_recipe_name).rename(recipe_name)
                except Exception as rename_err:
                    warn(
                        f"Could not rename '{actual_recipe_name}' → '{recipe_name}': "
                        f"{rename_err}. Continuing with the auto-name; you can rename "
                        f"manually with: dku recipe rename {actual_recipe_name} --name {recipe_name} -P {project_key}"
                    )
                    recipe_name = actual_recipe_name

        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)
        payload["outputProbabilities"] = output_probabilities
        payload["outputExplanations"] = output_explanations
        if keep_cols:
            payload["filterInputColumns"] = True
            payload["keptInputColumns"] = [
                c.strip() for c in keep_cols.split(",") if c.strip()
            ]
        settings.save()
        _auto_apply_schema(proj, recipe_name)
        success(
            f"Created prediction_scoring recipe '{recipe_name}' in {project_key} (model={model})"
        )
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-evaluation")
def create_evaluation(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input dataset (with target column + predictions)",
    ),
    model: str = typer.Option(..., "--model", help="Saved model ID to evaluate"),
    output_metrics: str | None = typer.Option(
        None, "--output-metrics-ds", help="Output dataset for metrics (optional)"
    ),
    output_predictions: str | None = typer.Option(
        None,
        "--output-predictions-ds",
        help="Output dataset for per-row predictions (optional)",
    ),
    output_evaluation_store: str | None = typer.Option(
        None,
        "--output-evaluation-store",
        help=(
            "ID of the evaluation store to write to (preferred over metrics dataset). "
            "Use `dku evaluation-store list -P PROJ` to find IDs."
        ),
    ),
    metrics: str | None = typer.Option(
        None,
        "--metrics",
        help=(
            "Comma-separated metric names to compute. Sets payload.metrics[]. "
            "When omitted, DSS uses the saved-model defaults."
        ),
    ),
    custom_metric: list[str] | None = typer.Option(
        None,
        "--custom-metric",
        help=(
            "Inline custom metric: 'NAME=GREL' or @file with a Python expression. "
            "Repeatable. Appends to payload.customMetrics[]."
        ),
    ),
    metrics_append: bool = typer.Option(
        False,
        "--metrics-append/--metrics-overwrite",
        help=(
            "When the metrics dataset already exists, append a new row each build "
            "(default DSS behavior is appendMode=true). --metrics-overwrite sets "
            "appendMode=false on the metrics output (each build replaces)."
        ),
    ),
    predictions_append: bool = typer.Option(
        False,
        "--predictions-append/--predictions-overwrite",
        help="Same as --metrics-append but for the per-row predictions output.",
    ),
    evaluation_type: str | None = typer.Option(
        None,
        "--evaluation-type",
        help=(
            "Evaluation flavor: PREDICTION (default), TIMESERIES, etc. "
            "Sets payload.evaluationType."
        ),
    ),
    compute_per_timeseries_metrics: bool = typer.Option(
        False,
        "--compute-per-timeseries-metrics",
        help="Time-series only: compute metrics per series. Sets payload.computePerTimeSeriesMetrics=true.",
    ),
    max_forecast_horizons: int | None = typer.Option(
        None,
        "--max-forecast-horizons",
        help="Time-series only: maximum forecast horizons to evaluate. Sets payload.maxForecastHorizons.",
    ),
    past_timesteps: int | None = typer.Option(
        None,
        "--past-timesteps",
        help="Time-series only: number of past timesteps fed to the model. Sets payload.pastTimesteps.",
    ),
    enable_drift: bool = typer.Option(
        False,
        "--enable-drift",
        help="Enable concept-drift detection. Sets payload.enableDrift=true.",
    ),
    drift_confidence: float | None = typer.Option(
        None,
        "--drift-confidence",
        help="Drift-test confidence level (0.95 etc.). Sets payload.driftConfidenceLevel.",
    ),
    treat_drift_failure_as_error: bool = typer.Option(
        False,
        "--treat-drift-failure-as-error",
        help="Fail the build when drift exceeds threshold. Sets payload.treatDriftFailureAsError=true.",
    ),
    mlflow_output: bool = typer.Option(
        False,
        "--mlflow-output",
        help="Write metrics to the MLflow tracking store (when configured). Sets payload.mlflowOutputEnabled=true.",
    ),
    treatment_mode: str | None = typer.Option(
        None,
        "--treatment-mode",
        help="Sub-population treatment mode (NONE, COLUMN, FORMULA, etc.). Sets payload.treatmentMode.",
    ),
    treatment_ratio: float | None = typer.Option(
        None,
        "--treatment-ratio",
        help="Sub-population treatment ratio. Sets payload.treatmentRatio.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Evaluation recipe (classic ML).

    Output role for evaluation stores is `evaluationStore`, NOT `main`.
    At least one of --output-metrics-ds, --output-predictions-ds, or
    --output-evaluation-store is required.

    appendMode default: DSS APPENDS one metrics row per build (so re-running
    creates duplicates). Use --metrics-overwrite for replace-on-each-build.

    Example:
        dku recipe create-evaluation eval_q4 -i q4_holdout \\
            --model 7bdMB26q --output-evaluation-store 9ASdtxO9 -P PROJ
    """
    if not (output_metrics or output_predictions or output_evaluation_store):
        exit_with_error(
            "Provide at least one output: --output-metrics-ds, --output-predictions-ds, or --output-evaluation-store.",
        )
    parsed_custom_metrics: list[dict] = []
    if custom_metric:
        for spec in custom_metric:
            if "=" not in spec:
                exit_with_error(
                    f"Invalid --custom-metric '{spec}'. Expected 'NAME=GREL_OR_PYTHON'.",
                )
            name, expr = spec.split("=", 1)
            name = name.strip()
            expr = read_text_input(expr) if expr.startswith("@") else expr
            parsed_custom_metrics.append({"name": name, "code": expr})

    project_key = resolve_project(project)
    try:
        from dataikuapi.dss.recipe import EvaluationRecipeCreator

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = EvaluationRecipeCreator(recipe_name, proj)
        builder.with_input_model(model)
        builder.with_input(input_ds)
        if output_metrics:
            _ensure_output_dataset(client, proj, output_metrics, project_key)
            builder.with_output(output_metrics, role="main")
        if output_predictions:
            _ensure_output_dataset(client, proj, output_predictions, project_key)
            builder.with_output(output_predictions, role="output")
        if output_evaluation_store:
            builder.with_output(output_evaluation_store, role="evaluationStore")
        builder.build()

        # Post-creation knobs: payload + per-output appendMode flags.
        any_payload_change = bool(
            metrics
            or parsed_custom_metrics
            or evaluation_type
            or compute_per_timeseries_metrics
            or max_forecast_horizons is not None
            or past_timesteps is not None
            or enable_drift
            or drift_confidence is not None
            or treat_drift_failure_as_error
            or mlflow_output
            or treatment_mode
            or treatment_ratio is not None
        )
        # appendMode lives on each output entry — we always write the literal
        # flag value the user passed (default: append on both metrics/predictions,
        # which mirrors DSS UI behavior).
        if any_payload_change or output_metrics or output_predictions:
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            payload = _get_recipe_payload(settings)
            if metrics:
                payload["metrics"] = [m.strip() for m in metrics.split(",")]
            if parsed_custom_metrics:
                payload.setdefault("customMetrics", []).extend(parsed_custom_metrics)
            if evaluation_type:
                payload["evaluationType"] = evaluation_type
            if compute_per_timeseries_metrics:
                payload["computePerTimeSeriesMetrics"] = True
            if max_forecast_horizons is not None:
                payload["maxForecastHorizons"] = max_forecast_horizons
            if past_timesteps is not None:
                payload["pastTimesteps"] = past_timesteps
            if enable_drift:
                payload["enableDrift"] = True
            if drift_confidence is not None:
                payload["driftConfidenceLevel"] = drift_confidence
            if treat_drift_failure_as_error:
                payload["treatDriftFailureAsError"] = True
            if mlflow_output:
                payload["mlflowOutputEnabled"] = True
            if treatment_mode:
                payload["treatmentMode"] = treatment_mode
            if treatment_ratio is not None:
                payload["treatmentRatio"] = treatment_ratio
            # appendMode lives on the OUTPUTS, not the payload — flip per role.
            if output_metrics or output_predictions:
                raw_def = settings.get_recipe_raw_definition()
                outs = raw_def.get("outputs", {})
                for role, append_flag in (
                    ("main", metrics_append),
                    ("output", predictions_append),
                ):
                    role_block = outs.get(role)
                    if not role_block:
                        continue
                    for item in role_block.get("items", []):
                        item["appendMode"] = bool(append_flag)
            settings.save()
        success(
            f"Created evaluation recipe '{recipe_name}' in {project_key} (model={model})"
        )
        recipe_created_hint(recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

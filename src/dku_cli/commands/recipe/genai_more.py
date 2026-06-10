"""Additional GenAI and built-in recipe commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from dku_cli.enums import StatementsMode

from ._common import *

# ---------------------------------------------------------------------------
# Additional built-in recipe verbs (eda_univariate, sql_script, generate_features,
# nlp_llm_user_provided_classification)
# ---------------------------------------------------------------------------


_VALID_UNIVARIATE_TYPES = frozenset({"CATEGORICAL", "NUMERICAL"})


@app.command("create-eda-univariate")
def create_eda_univariate(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset (univariate stats)"
    ),
    analyse: list[str] = typer.Option(
        ...,
        "--analyse",
        "-a",
        help=(
            "Column to analyse, format 'NAME:TYPE'. TYPE is CATEGORICAL or NUMERICAL. "
            "Repeatable. Example: --analyse VISIT:CATEGORICAL --analyse AVAL:NUMERICAL"
        ),
    ),
    with_frequency_table: bool = typer.Option(
        False,
        "--with-frequency-table",
        help="Top-level withFrequencyTable=true (per-modality counts/frequencies for CATEGORICAL columns).",
    ),
    with_quantile_table: bool = typer.Option(
        False,
        "--with-quantile-table",
        help="Top-level withQuantileTable=true (decile/percentile rows for NUMERICAL columns).",
    ),
    with_summary_stats: bool = typer.Option(
        True,
        "--with-summary-stats/--no-summary-stats",
        help="Top-level withSummaryStats (mean/std/min/max/...). Default on.",
    ),
    with_confidence_intervals: bool = typer.Option(
        False,
        "--with-confidence-intervals",
        help="Top-level withConfidenceIntervals=true. Pair with --confidence-level.",
    ),
    confidence_level: float | None = typer.Option(
        None,
        "--confidence-level",
        help="Top-level confidenceLevel (e.g. 0.95). Default DSS value.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an EDA Univariate recipe.

    Migration target: SAS PROC FREQ + PROC UNIVARIATE, R `summary()` chains.
    Each --analyse adds a column to payload.analyses[] with the right per-column
    boolean toggles. Toggles default to whichever analysis tables you flag at the
    top level (--with-frequency-table, --with-quantile-table, --with-summary-stats).

    Example:
        dku recipe create-eda-univariate stats -i clinical -- output-ds stats_out \\
            --analyse VISIT:CATEGORICAL --analyse AVAL:NUMERICAL \\
            --with-frequency-table --with-quantile-table -P PROJ
    """
    parsed: list[dict] = []
    for spec in analyse:
        if ":" not in spec:
            exit_with_error(
                f"Invalid --analyse '{spec}'. Expected 'COLUMN:TYPE' (TYPE in CATEGORICAL/NUMERICAL).",
                code="invalid_argument",
            )
        col, t = spec.split(":", 1)
        col = col.strip()
        t_upper = t.strip().upper()
        if t_upper not in _VALID_UNIVARIATE_TYPES:
            exit_with_error(
                f"Invalid --analyse type '{t}'.",
                code="invalid_argument",
                details=[f"Valid: {', '.join(sorted(_VALID_UNIVARIATE_TYPES))}"],
            )
        if not col:
            exit_with_error(
                f"Invalid --analyse '{spec}': missing column name.",
                code="invalid_argument",
            )
        entry = {
            "column": {"name": col, "type": t_upper},
            "frequencyTable": with_frequency_table and t_upper == "CATEGORICAL",
            "quantileTable": with_quantile_table and t_upper == "NUMERICAL",
            "summaryStats": with_summary_stats,
        }
        parsed.append(entry)

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        recipe_obj = _raw_create_recipe(
            proj,
            "eda_univariate",
            recipe_name,
            inputs=[(input_ds, "main")],
            outputs=[(output_ds, "main")],
        )
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)
        payload["analyses"] = parsed
        payload["withFrequencyTable"] = bool(with_frequency_table)
        payload["withQuantileTable"] = bool(with_quantile_table)
        payload["withSummaryStats"] = bool(with_summary_stats)
        payload["withConfidenceIntervals"] = bool(with_confidence_intervals)
        if confidence_level is not None:
            payload["confidenceLevel"] = confidence_level
        # Force payload re-serialisation: some recipe types come back from
        # rawCreation with payload=None, and dataikuapi's _payload_to_str only
        # writes self.data["payload"] when _str_payload or _obj_payload is set.
        # Round-tripping through str_payload guarantees the JSON makes it onto
        # the PUT body.
        if hasattr(settings, "str_payload"):
            settings.str_payload = json.dumps(payload)
        settings.save()
        success(f"Created eda_univariate recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-sql-script")
def create_sql_script(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: list[str] = typer.Option(
        [],
        "--input",
        "-i",
        help="Input dataset (repeatable). Optional for pure DDL scripts.",
    ),
    output_ds: list[str] = typer.Option(
        [],
        "--output-ds",
        "--output-dataset",
        help="Output dataset (repeatable for multi-output scripts).",
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help="SQL connection where the multi-statement script runs. Defaults to the project default.",
    ),
    sql: str | None = typer.Option(
        None,
        "--sql",
        help="SQL body: literal, @file.sql, or '-' for stdin. Multi-statement scripts go here.",
    ),
    use_psql: bool = typer.Option(
        False,
        "--use-psql/--no-use-psql",
        help=(
            "Treat the body as a psql-style script. Required for backslash "
            "directives, \\copy, conditional IF blocks, or DELIMITER stored-"
            "proc bodies. Off by default — turn on for Snowflake/Postgres/"
            "Redshift multi-statement DDL pipelines."
        ),
    ),
    statements_mode: StatementsMode | None = typer.Option(
        None,
        "--statements-mode",
        case_sensitive=False,
        help=(
            "Multi-statement parsing: SPLIT (each ';'-terminated statement as "
            "its own JDBC call — required for CREATE/INSERT/SELECT chains), "
            "UNIFIED (whole body as one batched statement), or RAW (no "
            "splitting). Default SPLIT — use SPLIT for Snowflake."
        ),
    ),
    allow_multiple_connections: bool = typer.Option(
        False,
        "--allow-multiple-connections",
        help="Allow the script to span more than one connection (advanced).",
    ),
    no_infer_output_schema: bool = typer.Option(
        False,
        "--no-infer-output-schema",
        help=(
            "Skip output-dataset schema inference from the script. Use when "
            "the schema is fixed or already set on the output dataset."
        ),
    ),
    skip_prerun_validate: bool = typer.Option(
        False,
        "--skip-prerun-validate",
        help=(
            "Skip the pre-run validation pass DSS does before executing. "
            "Useful for scripts whose validity DSS can't statically check "
            "(e.g. depending on objects created by an earlier statement)."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a sql_script recipe (multi-statement SQL — DDL / stored-proc-like flows).

    sql_script differs from sql_query: it allows multiple SQL statements and
    is suited for setup steps (CREATE TABLE, INDEX, MERGE chains). The body is
    stored as a raw text payload — use ``set-code`` to update it later.

    Example:
        dku recipe create-sql-script setup_warehouse \\
            --connection prod_pg --sql @setup.sql -P PROJ

    For Snowflake DDL scripts that need psql-style parsing:
        dku recipe create-sql-script cohort \\
            --connection sf --sql @cohort.sql --use-psql --statements-mode SPLIT -P PROJ
    """
    # --statements-mode is a StatementsMode click.Choice: invalid values are
    # rejected at parse time, so no body-level validation is needed.
    sm = _enum_value(statements_mode)
    project_key = resolve_project(project)
    try:
        from dataikuapi.dss.recipe import CodeRecipeCreator

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        for ds in output_ds:
            _ensure_output_dataset(client, proj, ds, project_key)
        builder = CodeRecipeCreator(recipe_name, "sql_script", proj)
        if connection is not None:
            # CodeRecipeCreator stores its target connection on the proto;
            # set it via the underlying recipe_proto to control where the
            # script runs.
            builder.recipe_proto.setdefault("params", {})["targetConnection"] = (
                connection
            )
        for ds in input_ds:
            builder.with_input(ds)
        for ds in output_ds:
            builder.with_output(ds)
        builder.build()

        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        if sql:
            body = read_text_input(sql)
            if hasattr(settings, "set_payload"):
                settings.set_payload(body)
            else:
                settings.obj_payload = body
            info(f"Wrote {len(body)} bytes of SQL")
        # Recipe-level params (sql_script-specific knobs live here, not in the payload).
        rp = _get_or_create_recipe_params(settings)
        if use_psql:
            rp["usePsql"] = True
        if sm is not None:
            rp["statementsParsingMode"] = sm
        if allow_multiple_connections:
            rp["allowMultipleConnections"] = True
        if no_infer_output_schema:
            rp["inferOutputDatasetsSchema"] = False
        if skip_prerun_validate:
            rp["skipPrerunValidate"] = True
        settings.save()
        success(f"Created sql_script recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-generate-features")
def create_generate_features(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input dataset to engineer features from",
    ),
    output_ds: str = typer.Option(
        ...,
        "--output-ds",
        "--output-dataset",
        help="Output dataset (engineered features)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Generate Features recipe (auto feature engineering).

    DSS scans the input dataset and synthesises a battery of derived features
    (date parts, text length, categorical encodings, etc.). The default config
    is sensible — tune via ``set-settings`` once the recipe exists if needed.

    Example:
        dku recipe create-generate-features autof -i raw --output-ds raw_with_features -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("generate_features", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created generate_features recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-prompt")
def create_prompt(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input dataset name (provides the variable values per row).",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    completion_llm: str = typer.Option(
        ..., "--completion-llm", help="Completion LLM ID (stored as payload.llmId)."
    ),
    prompt_text: str = typer.Option(
        ...,
        "--prompt",
        help=(
            "Prompt template (user message). Use {{var}} placeholders that match "
            "--input-var names. Supports literal, @file.txt, or '-' stdin. "
            "Multi-line: pass @file.txt or '-' for stdin "
            "(a literal \\n is NOT unescaped). "
            "Stored at payload.prompt.textPromptTemplate."
        ),
    ),
    system_prompt: str | None = typer.Option(
        None,
        "--system-prompt",
        help=(
            "Optional system message. Plain text, no placeholders needed. "
            "Stored at payload.prompt.textPromptSystemTemplate. "
            "Literal, @file.txt, or '-' stdin."
        ),
    ),
    input_var: list[str] | None = typer.Option(
        None,
        "--input-var",
        help=(
            "Bind a {{var}} placeholder to an input column: 'NAME=COLUMN'. "
            "Repeatable. Example: --input-var customer=customer_name. "
            "Stored in payload.prompt.textPromptTemplateInputs."
        ),
    ),
    response_format: str | None = typer.Option(
        None,
        "--response-format",
        help=(
            "Constrain LLM output format. 'json' sets payload.completionSettings.responseFormat={'type':'json'} "
            "(supported by OpenAI/Anthropic JSON mode). DO NOT confuse with "
            "resultValidation.expectedFormat:JSON — that field crashes builds."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Prompt recipe (LLM batch generation, one row per input).

    The recipe runs the prompt template once per input row and appends an
    ``llm_output`` column (plus 4 raw/trace columns) to the output. To expose
    the result under a friendly column name, add a downstream Prepare recipe
    with ``add-rename llm_output=<name>``.

    Example:
      dku recipe create-prompt summarise -i articles --output-ds summaries \\
        --completion-llm openai:gpt-4o-mini \\
        --prompt 'Summarize this article:\\n\\n{{body}}' \\
        --input-var body=article_body \\
        --response-format json -P PROJ
    """
    parsed_input_vars: list[dict] = []
    if input_var:
        for spec in input_var:
            if "=" not in spec:
                exit_with_error(
                    f"Invalid --input-var '{spec}'. Expected 'NAME=COLUMN'.",
                    code="invalid_argument",
                )
            name, col = spec.split("=", 1)
            parsed_input_vars.append(
                {
                    "name": name.strip(),
                    "datasetColumnName": col.strip(),
                    "type": "TEXT",
                }
            )

    rf_normalized: dict | None = None
    if response_format:
        rf = response_format.strip().lower()
        if rf == "json":
            rf_normalized = {"type": "json"}
        else:
            exit_with_error(
                f"Invalid --response-format '{response_format}'.",
                code="invalid_argument",
                details=["Currently supported: 'json'."],
            )

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        # Use the SDK builder (not rawCreation) so DSS populates the full default
        # prompt payload — structural fields like resultValidation and
        # guardrailsPipelineSettings must be present or the build NPEs.
        builder = proj.new_recipe("prompt", recipe_name)
        builder.with_input(input_ds)
        builder.with_llm(completion_llm)
        builder.with_existing_output(output_ds)
        recipe_obj = builder.create()

        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)
        payload["llmId"] = completion_llm
        prompt_obj = payload.setdefault("prompt", {})
        prompt_obj["promptMode"] = "PROMPT_TEMPLATE_TEXT"
        prompt_obj["promptTemplateQueriesSource"] = "DATASET"
        prompt_obj["textPromptTemplate"] = read_text_input(prompt_text)
        if system_prompt:
            prompt_obj["textPromptSystemTemplate"] = read_text_input(system_prompt)
        prompt_obj["textPromptTemplateInputs"] = parsed_input_vars
        if rf_normalized:
            payload.setdefault("completionSettings", {})["responseFormat"] = (
                rf_normalized
            )
        # settings.obj_payload is read-only; write back via the public
        # str_payload setter so settings.save() actually pushes our changes
        # to DSS (in particular llmId, which DSS needs at run time).
        settings.str_payload = json.dumps(payload)
        settings.save()
        success(f"Created prompt recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-llm-classify")
def create_llm_classify(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ...,
        "--output-ds",
        "--output-dataset",
        help="Output dataset (with class column)",
    ),
    completion_llm: str = typer.Option(
        ..., "--completion-llm", help="Completion LLM ID used for entailment scoring."
    ),
    input_col: str = typer.Option(
        ..., "--input-col", help="Column with the text to classify."
    ),
    output_col: str = typer.Option(
        "predicted_class",
        "--output-col",
        help="Output column name for the predicted class label.",
    ),
    classes: list[str] = typer.Option(
        ...,
        "--class",
        help=(
            "A possible class label (repeatable, REQUIRED). DSS needs at least 2; "
            "a single class produces a no-op recipe with empty predictions."
        ),
    ),
    hypothesis_template: str = typer.Option(
        "This text is about {{input}}",
        "--hypothesis-template",
        help=(
            "NLI hypothesis template. {{input}} is substituted with each class "
            "label; the LLM scores text → hypothesis for each, picks the argmax. "
            "Default: 'This text is about {{input}}'."
        ),
    ),
    explain_output: bool = typer.Option(
        False,
        "--explain-output",
        help="Add a JSON column with per-class scores in the output (default: only the predicted label).",
    ),
    example: list[str] | None = typer.Option(
        None,
        "--example",
        help=(
            "Few-shot example, format 'TEXT||LABEL'. Repeatable. Adds an entry "
            "to payload.examples[]. Use ||  as the separator so commas and "
            "colons in TEXT are preserved."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an LLM Classify recipe (zero/few-shot text classification via NLI).

    Migration target: SAS / Alteryx text-bucketing workflows; "open-ended prompt
    that asks the LLM to pick a label" cookbooks (which are flaky because the
    LLM may invent labels). This recipe constrains output to ``--class`` labels
    and uses NLI scoring under the hood — much more reliable.

    Example:
        dku recipe create-llm-classify classify_orders -i orders \\
            --output-ds orders_with_class --completion-llm openai:gpt-4o-mini \\
            --input-col description --class urgent --class routine --class scheduled \\
            --hypothesis-template 'This work order is {{input}}' -P PROJ
    """
    if len(classes) < 2:
        exit_with_error(
            "create-llm-classify needs at least two --class values; got "
            + str(len(classes)),
            code="invalid_argument",
            details=[
                "DSS silently produces empty predictions when possibleClasses has < 2 entries.",
                "Pass --class twice or more, e.g. --class urgent --class routine.",
            ],
        )

    parsed_examples: list[dict] = []
    if example:
        for spec in example:
            if "||" not in spec:
                exit_with_error(
                    f"Invalid --example '{spec}'. Expected 'TEXT||LABEL'.",
                    code="invalid_argument",
                )
            text, label = spec.split("||", 1)
            label = label.strip()
            if label and label not in classes:
                warn(
                    f"--example label '{label}' is not in --class list; the LLM may treat it as out-of-distribution."
                )
            parsed_examples.append({"input": text.strip(), "output": label})

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        recipe_obj = _raw_create_recipe(
            proj,
            "nlp_llm_user_provided_classification",
            recipe_name,
            inputs=[(input_ds, "main")],
            outputs=[(output_ds, "main")],
        )
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)
        payload["completionLLMId"] = completion_llm
        payload["inputColumnName"] = input_col
        payload["outputColumnName"] = output_col
        # DSS expects possibleClasses[] as an array of objects with {label: ...},
        # not a flat string array — the latter throws
        # "Expected BEGIN_OBJECT but was STRING" at recipe save time.
        payload["possibleClasses"] = [{"label": c} for c in classes]
        payload["hypothesisTemplate"] = hypothesis_template
        payload["explainOutput"] = bool(explain_output)
        payload["examples"] = parsed_examples
        payload.setdefault("completionSettings", {}).setdefault("stopSequences", [])
        # Force payload serialisation (rawCreation returns payload=None).
        if hasattr(settings, "str_payload"):
            settings.str_payload = json.dumps(payload)
        settings.save()
        success(f"Created llm_classify recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

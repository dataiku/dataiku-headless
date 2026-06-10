"""Core recipe commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from dku_cli.enums import ContainerMode, EnvMode, JobType

from ._common import *

# Visual types whose recipe payload requires extra config (group keys, join keys,
# a window definition, ...) that the generic `create` path cannot supply. Building
# one of these through `proj.new_recipe(type)` + `.build()` makes DSS reject it with
# "Unknown type. Please use create_recipe for custom recipes". Each has a dedicated
# `create-<verb>` that supplies the mandatory config — route the agent there.
_DEDICATED_VERB_TYPES = {
    "group": "create-group",
    "join": "create-join",
    "window": "create-window",
    "distinct": "create-distinct",
    "topn": "create-topn",
    "pivot": "create-pivot",
    "sort": "create-sort",
    "split": "create-split",
    "stack": "create-stack",
    "sampling": "create-sampling",
    "sample": "create-sampling",
}


@app.command("list")
def list_recipes(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
    fields: str = typer.Option(
        None,
        "--fields",
        help="Comma-separated fields to include (name,type,tags)",
    ),
) -> None:
    """List recipes in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipes = proj.list_recipes()

        data = []
        for r in recipes:
            data.append(
                {
                    "name": r.get("name", ""),
                    "type": r.get("type", ""),
                    "tags": ", ".join(r.get("tags", []))
                    if isinstance(r.get("tags"), list)
                    else "",
                }
            )

        data, keys = filter_fields(data, ["name", "type", "tags"], fields)

        render(
            data,
            keys,
            output_format=output,
            title=f"Recipes ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show recipe details."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipe = _get_recipe_or_exit(proj, recipe_name, project_key)
        settings = recipe.get_settings()
        raw_def = settings.get_recipe_raw_definition()

        if output == "json":
            print(json.dumps(raw_def, indent=2, default=str))
        else:
            input_refs = settings.get_flat_input_refs()
            output_refs = settings.get_flat_output_refs()

            data = [
                {"field": "Name", "value": recipe_name},
                {"field": "Type", "value": raw_def.get("type", "")},
                {"field": "Inputs", "value": ", ".join(input_refs) or "(none)"},
                {"field": "Outputs", "value": ", ".join(output_refs) or "(none)"},
            ]

            render(
                data,
                ["field", "value"],
                output_format=output,
                title=f"Recipe: {recipe_name}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the full recipe definition (raw definition + payload).

    Returns the recipe's raw_definition (I/O mappings, connection, type) and
    obj_payload (visual recipe config: aggregations, join keys, window specs, etc.).
    Use 'dku recipe set-definition' to update these values.

    Examples:
      dku recipe get-definition my_group -P PROJ -o json
      dku recipe get-definition my_join -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipe = _get_recipe_or_exit(proj, recipe_name, project_key)
        settings = recipe.get_settings()
        raw_def = settings.get_recipe_raw_definition()

        # Code recipes (sql_query, python, etc.) store raw source text; visual
        # recipes store a JSON config. obj_payload crashes for code recipes.
        if _is_text_payload_recipe(settings):
            payload = _get_text_payload(settings)
        else:
            try:
                payload = settings.obj_payload
            except (json.JSONDecodeError, ValueError):
                payload = _get_text_payload(settings)

        if output == "json":
            result = {"definition": raw_def, "payload": payload}
            print(json.dumps(result, indent=2, default=str))
        else:
            input_refs = settings.get_flat_input_refs()
            output_refs = settings.get_flat_output_refs()
            if isinstance(payload, str):
                preview = payload[:200] + ("..." if len(payload) > 200 else "")
                payload_display = preview if preview else "(none)"
            else:
                payload_display = (
                    json.dumps(payload, default=str) if payload else "(none)"
                )
            data = [
                {"field": "Name", "value": recipe_name},
                {"field": "Type", "value": raw_def.get("type", "")},
                {"field": "Inputs", "value": ", ".join(input_refs) or "(none)"},
                {"field": "Outputs", "value": ", ".join(output_refs) or "(none)"},
                {
                    "field": "Payload",
                    "value": payload_display,
                },
            ]
            render(
                data,
                ["field", "value"],
                output_format=output,
                title=f"Recipe Definition: {recipe_name}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def run(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
    job_type: JobType = typer.Option(
        JobType.NON_RECURSIVE_FORCED_BUILD,
        "--type",
        "-t",
        case_sensitive=False,
        help="Build type: NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD, RECURSIVE_MISSING_ONLY_BUILD",
    ),
    auto_update_schema: bool = typer.Option(
        False,
        "--auto-update-schema",
        help="Auto-update output schemas before each recipe run",
    ),
    timeout: int | None = typer.Option(
        None,
        "--timeout",
        help="When --wait is set, max seconds to wait before failing (matches dku job run). Default: no limit.",
    ),
) -> None:
    """Run a recipe.

    Use --type RECURSIVE_BUILD --auto-update-schema to build upstream
    dependencies with automatic schema propagation.
    """
    project_key = resolve_project(project)
    # Track job.id outside the try so the except handler can reference it
    # when the wait loop raises (e.g. on FAILED status).
    job_id: str | None = None
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipe = _get_recipe_or_exit(proj, recipe_name, project_key)

        # Always use the job builder path, not recipe.run(). recipe.run()
        # blocks internally and raises on failure BEFORE we learn the job
        # ID, so agents have no way to inspect the log. The builder path
        # returns a DSSJob object immediately after start(), which gives us
        # job.id even when the job later fails in the wait loop.
        settings = recipe.get_settings()
        output_refs = settings.get_flat_output_refs()
        if not output_refs:
            exit_with_error(
                f"Recipe '{recipe_name}' has no outputs to build.",
                code="no_outputs",
                status=1,
                details=[
                    f"Check wiring: dku recipe get {recipe_name} -P {project_key} -o json",
                ],
            )

        builder = proj.new_job(job_type.value)
        # get_flat_output_refs() returns bare refs with no object type. The job
        # builder defaults object_type to DATASET, so managed-folder / saved-model
        # outputs would error with "dataset does not exist". Resolve the real type.
        for resolved_ref, object_type in resolve_build_output_types(proj, output_refs):
            builder.with_output(resolved_ref, object_type=object_type)
        if auto_update_schema:
            builder.with_auto_update_schema_before_each_recipe_run(True)
        job = builder.start()
        job_id = job.id

        success(f"Recipe '{recipe_name}' started")
        info(f"Job ID: {job_id}")
        if auto_update_schema:
            info("Auto-update schema: enabled")

        # recipe.run(no_fail=True) already waited; poll state from the job object.
        status = job.get_status()
        state = status.get("baseStatus", {}).get("state", "")

        if wait and state not in ("DONE", "FAILED", "ABORTED"):
            info("Waiting for completion...")
            start = time.time()
            while state not in ("DONE", "FAILED", "ABORTED"):
                if timeout is not None and (time.time() - start) > timeout:
                    exit_with_error(
                        f"Recipe '{recipe_name}' did not finish within {timeout}s (job {job.id}).",
                        code="timeout",
                        details=[
                            f"Job is still running — poll status: dku job status {job.id} -P {project_key}",
                            f"View log: dku job log {job.id} -P {project_key}",
                            f"Abort if needed: dku job abort {job.id} -P {project_key}",
                        ],
                    )
                time.sleep(2)
                status = job.get_status()
                state = status.get("baseStatus", {}).get("state", "")

        if state == "DONE":
            if wait:
                success("Recipe completed successfully")
            # Hint: Prepare recipes with rename/formula steps frequently need a
            # follow-up apply-schema before downstream recipes see the new
            # columns. The first run propagates the upstream schema only;
            # rename/formula additions show up after a second apply-schema +
            # re-run. Skip the hint if the user already passed --auto-update-schema.
            if not auto_update_schema:
                try:
                    raw = settings.get_recipe_raw_definition()
                    if raw.get("type") == "shaker":
                        payload = _get_recipe_payload(settings)
                        steps = payload.get("steps", [])
                        schema_changing = {
                            "ColumnRenamer",
                            "CreateColumnWithGREL",
                            "ColumnsSelector",
                            "ColumnReorder",
                        }
                        if any(s.get("type") in schema_changing for s in steps):
                            info(
                                "Tip: rename/formula/select steps may have changed the output schema. "
                                f"If downstream recipes can't see new/renamed columns, run: "
                                f"dku recipe apply-schema {recipe_name} -P {project_key}"
                            )
                except Exception:
                    # Hint is advisory — don't break the run path on inspection errors.
                    pass
        elif state in ("FAILED", "ABORTED"):
            err_msg = status.get("errorMessage") or (status.get("error") or {}).get(
                "message", ""
            )
            details = []
            if err_msg:
                details.append(f"Error: {err_msg}")
            details.append(f"View log: dku job log {job_id} -P {project_key}")
            details.append(f"Full status: dku job status {job_id} -P {project_key}")
            exit_with_error(
                f"Recipe '{recipe_name}' {state.lower()} (job {job_id}).",
                code="job_failed",
                status=4,
                details=details,
            )
    except typer.Exit:
        raise
    except Exception as e:
        # If the exception came from the wait loop after we already know the
        # job ID, give the agent the log command instead of just a raw API
        # error. This covers the case where dataikuapi raises before our
        # explicit state check fires.
        if job_id:
            exit_with_error(
                f"Recipe '{recipe_name}' run failed: {e}",
                code="job_failed",
                status=4,
                details=[
                    f"Inspect the log: dku job log {job_id} -P {project_key}",
                    f"Job status: dku job status {job_id} -P {project_key} -o json",
                ],
            )
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    type_name: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Recipe type: python, sql, join, group, etc. For plugin recipes: CustomCode_<recipeComponentId>",
    ),
    inputs: list[str] = typer.Option(
        [],
        "--input",
        "-i",
        "--input-ds",
        "--input-dataset",
        help="Input dataset name (must exist). Repeatable: `-i A -i B` wires both. Optional for code recipes: python, r, shell, pyspark, cpython, sparkr (data generation).",
    ),
    output_ds: str | None = typer.Option(
        None,
        "--output-ds",
        "--output-dataset",
        help="Output dataset name (auto-created for code recipes, must exist for plugin recipes). Mutually exclusive with --output-folder.",
    ),
    output_folder: str | None = typer.Option(
        None,
        "--output-folder",
        help="Wire an EXISTING managed folder (by name or ID) as the recipe output instead of a dataset. Create the folder first: dku folder create NAME -P PROJ. Mutually exclusive with --output-ds.",
    ),
    input_folders: list[str] = typer.Option(
        [],
        "--input-folder",
        help="Wire an EXISTING managed folder (by name or ID) as a recipe input — for code recipes that read files (XML/JSON/PDF/etc.) from a folder. Repeatable. Combine with -i to mix dataset and folder inputs.",
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help="Connection for the auto-created output dataset. Works for code recipes (python, r, shell, sql, sql_query) and for sync recipes. Run 'dku connection list' to see available connections.",
    ),
    input_role: str = typer.Option(
        "main",
        "--input-role",
        help="Input role name (for plugin recipes with non-standard roles)",
    ),
    output_role: str = typer.Option(
        "main",
        "--output-role",
        help="Output role name (for plugin recipes with non-standard roles)",
    ),
    params: str | None = typer.Option(
        None,
        "--params",
        help="Plugin recipe config as JSON string, @file.json, or '-' for stdin",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Saved model ID or name (required for prediction_scoring / clustering_scoring)",
    ),
    container_mode: ContainerMode | None = typer.Option(
        None,
        "--container-mode",
        case_sensitive=False,
        help=(
            "Code-recipe container execution mode (python/r/sql/pyspark/cpython/sparkr): "
            "INHERIT (use project default), NONE (run on the DSS process), "
            "EXPLICIT_CONTAINER (use --container-conf), KUBERNETES, EXPLICIT_K8S. "
            "Sets params.containerSelection.containerMode. Use EXPLICIT_CONTAINER + "
            "--container-conf 'gpu-pool' to pin a Python recipe to a GPU node pool."
        ),
    ),
    container_conf: str | None = typer.Option(
        None,
        "--container-conf",
        help=(
            "Container configuration name when --container-mode EXPLICIT_CONTAINER. "
            "Sets params.containerSelection.containerConf."
        ),
    ),
    env_mode: EnvMode | None = typer.Option(
        None,
        "--env-mode",
        case_sensitive=False,
        help=(
            "Code-recipe code-env mode: INHERIT (use project default), "
            "USE_BUILTIN_MODE, EXPLICIT_ENV (specify --env-name). "
            "Sets params.envSelection.envMode."
        ),
    ),
    env_name: str | None = typer.Option(
        None,
        "--env-name",
        help=(
            "Code env name when --env-mode EXPLICIT_ENV. Sets "
            "params.envSelection.envName."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(
        None,
        "-o",
        "--output",
        help="Output FORMAT (table/json/csv). For output dataset, use --output-ds",
    ),
) -> None:
    """Create a new recipe.

    Prefer visual recipes over Python — use --type join, group, sort, distinct, etc.
    Python/SQL are for logic that visual recipes can't express.

    For code recipes (python, sql), the output dataset is auto-created. If the DSS
    project has no default managed connection, use --connection to specify one
    (e.g. --connection filesystem_managed).

    Plugin recipes use type CustomCode_<recipeComponentId>. The output dataset
    must already exist. Pass plugin config with --params — it is written to
    params.customConfig with the required params.containerSelection (the recipe
    NPEs at run time otherwise):

      dku recipe create my_step -t CustomCode_my-recipe \\
        -i input_ds --output-ds output_ds --params '{"key": "val"}' -P PROJ

    To wire a managed folder as the output instead of a dataset, use
    --output-folder (the folder must already exist):

      dku recipe create my_step -t CustomCode_my-recipe \\
        -i input_ds --output-folder my_folder --params '{...}' -P PROJ

    Discover available plugin recipes: dku plugin recipes [PLUGIN_ID]
    """
    project_key = resolve_project(project)
    # Detect type passed as recipe name (e.g. `dku recipe create python ...`)
    if recipe_name.lower() in _KNOWN_RECIPE_TYPES:
        exit_with_error(
            f"'{recipe_name}' looks like a recipe type, not a recipe name.",
            code="invalid_argument",
            details=[
                f"Correct syntax: dku recipe create <NAME> --type {recipe_name} --input <DS> --output-ds <DS> -P <PROJ>",
            ],
        )
    # Detect --output/--output-ds confusion
    if output is not None and output.lower() not in ("table", "json", "csv"):
        exit_with_error(
            f"Invalid output format '{output}'.",
            code="invalid_argument",
            details=[
                f"Did you mean --output-ds '{output}'?",
                "Use --output-ds for the output dataset name, -o for output format (table/json/csv).",
            ],
        )
    # Resolve the output target: exactly one of --output-ds / --output-folder.
    if output_ds and output_folder:
        exit_with_error(
            "Pass only one of --output-ds and --output-folder.",
            code="invalid_argument",
            details=[
                "--output-ds wires/creates a dataset output.",
                "--output-folder wires an existing managed folder output.",
            ],
        )
    if not output_ds and not output_folder:
        exit_with_error(
            "No output specified. Provide --output-ds <DATASET> or --output-folder <FOLDER>.",
            code="missing_param",
            details=[
                f"Dataset output: dku recipe create {recipe_name} -t {type_name} -i <INPUT> --output-ds <DATASET> -P {project_key}",
                f"Folder output:  dku recipe create {recipe_name} -t {type_name} -i <INPUT> --output-folder <FOLDER> -P {project_key}",
            ],
        )
    # Parse --params if provided
    params_dict = None
    if params is not None:
        params_text = read_text_input(params)
        try:
            params_dict = json.loads(params_text)
        except json.JSONDecodeError as exc:
            exit_with_error(
                f"Invalid JSON in --params: {exc}",
                code="invalid_argument",
                details=[
                    'Pass a JSON object: --params \'{"key": "value"}\'',
                    "Or from file: --params @config.json",
                    "Or from stdin: echo '{...}' | dku recipe create ... --params -",
                ],
            )
    type_lower_for_check = type_name.lower()
    is_scoring_type = type_lower_for_check in _SCORING_RECIPE_TYPES
    if is_scoring_type and model is None:
        exit_with_error(
            f"Recipe type '{type_name}' requires a saved model. Pass --model SAVED_MODEL_ID_OR_NAME.",
            code="missing_param",
            details=[
                "List saved models: dku ml models -P " + project_key,
                f"Example: dku recipe create {recipe_name} -t {type_name} -i <INPUT_DS> "
                f"--model <SAVED_MODEL_ID> --output-ds {output_ds} -P {project_key}",
            ],
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        resolved_model_id: str | None = None
        if model is not None:
            resolved_model_id = resolve_saved_model(proj, model).id
        # Validate an input is provided for types that require it. A folder
        # input (code recipes reading files) satisfies the requirement too.
        if (
            not inputs
            and not input_folders
            and type_name.lower() not in _INPUT_OPTIONAL_TYPES
        ):
            exit_with_error(
                f"--input is required for recipe type '{type_name}'.",
                code="missing_input",
                details=[
                    "Only code recipes (python, r, shell, pyspark, cpython, sparkr) support creation without an input dataset.",
                    f"Example: dku recipe create {recipe_name} -t {type_name} -i <INPUT_DS> --output-ds {output_ds} -P {project_key}",
                ],
            )
        # Resolve --output-folder to a managed-folder ID (must already exist).
        # Folder outputs are always wired as existing objects (never auto-created).
        output_folder_id: str | None = None
        if output_folder:
            output_folder_id = resolve_folder(proj, output_folder).id
        # Resolve --input-folder names/IDs to managed-folder IDs (must exist).
        # Folder inputs feed code recipes that parse files (XML/JSON/PDF/...).
        input_folder_ids: list[str] = [
            resolve_folder(proj, f).id for f in input_folders
        ]
        # The ref to wire as the recipe output (dataset name or folder ID).
        output_ref = output_folder_id or output_ds
        if _is_plugin_recipe_type(type_name):
            # Plugin recipes: project.new_recipe() returns None for unknown types.
            # Use DSSRecipeCreator directly in raw mode.
            from dataikuapi.dss.recipe import DSSRecipeCreator

            builder = DSSRecipeCreator(type_name, recipe_name, proj)
            builder.set_raw_mode()
            for _input in inputs:
                builder.with_input(_input, role=input_role)
            for _fid in input_folder_ids:
                builder.with_input(_fid, role=input_role)
            # output_ref resolves folder-or-dataset outputs (upstream fix);
            # plugin recipes can target a managed folder, not just a dataset.
            builder.with_output(output_ref, role=output_role)
            # Plugin (CustomCode_*) recipes read their configuration from
            # recipe.params.customConfig — NOT from the payload. Writing --params
            # to creation_settings["rawPayload"] (the old behavior) left the
            # plugin unconfigured: it ran with empty config. We also MUST seed
            # params.containerSelection — DSS NPEs at build time when it is null.
            # Verified shape (see migration/ayx/alteryx-toolkit.md § Wiring).
            recipe_params = {
                "containerSelection": {"containerMode": "INHERIT"},
            }
            if params_dict is not None:
                recipe_params["customConfig"] = params_dict
            builder.recipe_proto["params"] = recipe_params
            built = builder.build()
        else:
            builder = proj.new_recipe(type_name, recipe_name)
            if builder is None:
                exit_with_error(
                    f"Unknown recipe type '{type_name}'.",
                    code="unknown_recipe_type",
                    details=[
                        "Built-in types: python, sql, join, group, sort, distinct, topn, window, stack, split, prepare, filter, sync",
                        "Plugin recipe types use format: CustomCode_<recipeComponentId>",
                        "Discover plugin recipes: dku plugin recipes",
                    ],
                )
            for _input in inputs:
                builder.with_input(_input)
            for _fid in input_folder_ids:
                builder.with_input(_fid)
            # Output wiring:
            # - Code recipes use CodeRecipeCreator.with_new_output_dataset(name, connection)
            # - Everything else with --connection uses
            #   SingleOutputRecipeCreator.with_new_output(name, connection) — this
            #   covers sync, sql_query, AND visual recipes (join, group, sort, distinct,
            #   prepare, window, pivot, sampling, stack, fuzzyjoin, geojoin) which all
            #   inherit it from VirtualInputsSingleOutputRecipeCreator / SingleOutputRecipeCreator.
            # - Visual recipes without --connection fall back to with_existing_output().
            # - Recipe types that subclass DSSRecipeCreator directly (topn) have no
            #   auto-create method and fall through to with_output().
            type_lower = type_name.lower()
            is_visual = type_lower in _VISUAL_RECIPE_TYPES
            if output_folder_id:
                # Existing managed folder — wire as-is, never auto-create.
                builder.with_output(output_folder_id)
            elif connection and hasattr(builder, "with_new_output_dataset"):
                builder.with_new_output_dataset(output_ds, connection)
            elif connection and hasattr(builder, "with_new_output"):
                builder.with_new_output(output_ds, connection)
            elif is_visual and hasattr(builder, "with_existing_output"):
                builder.with_existing_output(output_ds)
            else:
                builder.with_output(output_ds)
            # Scoring recipes require the saved model wired BEFORE build (the creator
            # is a *ScoringRecipeCreator). Building without it throws a server-side
            # IndexOutOfBoundsException; with_input_model puts it in the "model" role.
            if (
                is_scoring_type
                and resolved_model_id is not None
                and hasattr(builder, "with_input_model")
            ):
                builder.with_input_model(resolved_model_id)
            built = builder.build()
        # DSS auto-names scoring recipes 'score_<input>', ignoring recipe_name.
        # Reconcile to the requested name and apply the output schema so the recipe
        # is immediately buildable (else the output stays at 0 columns and the build
        # fails "Schema incompatibility: N columns in data, 0 columns in target").
        if is_scoring_type and resolved_model_id is not None:
            recipe_name = _reconcile_scoring_name(built, recipe_name)
            _auto_apply_schema(proj, recipe_name)
        # Container / env-mode pinning for code recipes.
        if container_mode is not None:
            if container_mode.value == "EXPLICIT_CONTAINER" and not container_conf:
                exit_with_error(
                    "--container-mode EXPLICIT_CONTAINER requires --container-conf.",
                    code="invalid_argument",
                )
        if env_mode is not None:
            if env_mode.value == "EXPLICIT_ENV" and not env_name:
                exit_with_error(
                    "--env-mode EXPLICIT_ENV requires --env-name.",
                    code="invalid_argument",
                )
        if container_mode or env_mode:
            recipe = proj.get_recipe(recipe_name)
            recipe_settings = recipe.get_settings()
            rp = _get_or_create_recipe_params(recipe_settings)
            if container_mode:
                cs = rp.setdefault("containerSelection", {})
                cs["containerMode"] = container_mode.upper()
                if container_conf:
                    cs["containerConf"] = container_conf
                info(
                    f"Container: {container_mode.upper()}"
                    + (f" ({container_conf})" if container_conf else "")
                )
            if env_mode:
                es = rp.setdefault("envSelection", {})
                es["envMode"] = env_mode.upper()
                if env_name:
                    es["envName"] = env_name
                info(
                    f"Env: {env_mode.upper()}" + (f" ({env_name})" if env_name else "")
                )
            recipe_settings.save()
        if output_folder_id:
            info(f"Output folder: {output_folder_id}")
        success(f"Created recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        if is_already_exists_error(e):
            exit_with_error(
                f"Output dataset '{output_ds}' already exists in {project_key}.",
                code="already_exists",
                details=[
                    "Code recipes (python, sql) auto-create their output dataset.",
                    f"Delete it first: dku dataset delete {output_ds} -P {project_key}",
                    "Or use a different --output-ds name.",
                ],
            )
        if is_connection_required_error(e):
            # Visual recipes (prepare, shaker, join, group, ...) need the output to pre-exist.
            # Code recipes (python, r, shell) and sync/sql_query need a --connection for auto-creation.
            if type_name.lower() in _VISUAL_RECIPE_TYPES:
                exit_with_error(
                    f"FAILED: recipe '{recipe_name}' was NOT created — output dataset '{output_ds}' must be created first.",
                    code="output_not_found",
                    details=[
                        f"Output dataset '{output_ds}' does not exist.",
                        f"`dku recipe create -t {type_name}` does NOT auto-create the output (the typed shortcuts create-join / create-group / ... do).",
                        "",
                        "Fix in two commands:",
                        f"  dku dataset create {output_ds} --type Filesystem -c filesystem_managed -P {project_key}",
                        f"  dku recipe create {recipe_name} -t {type_name} {' '.join(f'-i {i}' for i in inputs)} --output-ds {output_ds} -P {project_key}",
                        "",
                        "If you don't need a generic prepare and a typed shortcut fits the task,",
                        "those auto-create their output: create-join, create-group, create-stack,",
                        "create-distinct, create-sort, create-filter, create-window, create-topn,",
                        "create-pivot, create-sampling, create-split.",
                    ],
                )
            else:
                exit_with_error(
                    f"Cannot auto-create output dataset '{output_ds}' — no default managed connection configured.",
                    code="connection_required",
                    details=[
                        "This DSS project has no default managed connection for auto-creating datasets.",
                        "Fix: add --connection <NAME> to specify where the output should be stored.",
                        "Find available connections: dku connection list",
                        f"Example: dku recipe create {recipe_name} -t {type_name} {' '.join(f'-i {i}' for i in inputs)} --output-ds {output_ds} --connection filesystem_managed -P {project_key}",
                    ],
                )
        dedicated_verb = _DEDICATED_VERB_TYPES.get(type_name.lower())
        if dedicated_verb and "create_recipe" in str(e):
            # DSS: "Unknown type. Please use create_recipe for custom recipes" —
            # the generic create path can't supply this type's mandatory config.
            example_key = (
                " -k <COLUMN>"
                if dedicated_verb in ("create-group", "create-window")
                else ""
            )
            exit_with_error(
                f"recipe '{recipe_name}' was NOT created — type '{type_name}' needs its dedicated verb.",
                code="use_dedicated_verb",
                details=[
                    f"`dku recipe create -t {type_name}` can't supply the config this recipe requires",
                    "(group keys, join keys, a window definition, ...).",
                    "",
                    "Use the typed shortcut instead — it auto-creates the output too:",
                    f"  dku recipe {dedicated_verb} {recipe_name} "
                    + " ".join(f"-i {i}" for i in inputs)
                    + f" --output-ds {output_ds}{example_key} -P {project_key}",
                    "",
                    f"See: dku recipe {dedicated_verb} --help",
                ],
            )
        if "recipe type" in str(e).lower() and "unknown" in str(e).lower():
            exit_with_error(
                f"Recipe type '{type_name}' is unknown to DSS.",
                code="unknown_recipe_type",
                details=[
                    "Plugin recipe type format is: CustomCode_<recipeComponentId>",
                    "  The plugin ID is NOT part of the type. Only the recipe directory name.",
                    "Discover available types: dku plugin recipes",
                    "If the plugin was just installed, DSS may need a restart to register types.",
                ],
            )
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a recipe."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="recipe.delete",
        subject=f"recipe '{recipe_name}' in project {project_key}",
        yes=yes,
        prompt=f"Delete recipe '{recipe_name}' from project {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        recipe.delete()
        success(f"Deleted recipe '{recipe_name}' from {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def rename(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Current recipe name"),
    new_name: str = typer.Option(..., "--name", help="New recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Rename a recipe.

    Example:
      dku recipe rename compute_old --name compute_new -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        recipe.rename(new_name)
        success(f"Renamed recipe '{recipe_name}' to '{new_name}' in {project_key}")
    except ValueError as e:
        # dataikuapi raises ValueError if new_name == old name
        exit_with_error(
            str(e),
            code="invalid_argument",
            details=[
                f"The recipe is already named '{recipe_name}'.",
                "Provide a different name with --name.",
            ],
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def status(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
    engines: bool = typer.Option(
        False,
        "--engines",
        help="List all candidate engines with per-engine status (TYPE, LABEL, VARIANT, SEVERITY, MESSAGE).",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Dump the full server status payload (engines, sqlWithExecutionPlanList, pivotModalities, outputSchema with originalType, sqlWarning, recipe-type-keyed buckets, etc.). Implies -o json unless overridden.",
    ),
) -> None:
    """Show recipe status: engine, severity, and check messages.

    Default: selected engine + severity + top-level check messages.

    --engines: per-engine candidate table (why DSS picked / rejected each).
    --full:   the full get-status payload as JSON. Surfaces fields the default
              view hides — sqlWithExecutionPlanList (per-output compiled SQL on
              Split), pivotModalities + sqlWarning (Pivot modality cache),
              outputSchema.columns[].originalType (source-DB column types),
              and recipe-type-keyed message buckets (group:, splitting:,
              pivot:, filter:, topn:, retrievedColumns:, ...).

    Examples:
      dku recipe status compute_data -P PROJ
      dku recipe status compute_data -P PROJ --engines
      dku recipe status compute_data -P PROJ --full           # JSON
      dku recipe status compute_data -P PROJ --full | jq '.engines[]|select(.statusWarnLevel!="OK")'
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        recipe_status = recipe.get_status()

        if full:
            # Dump the entire server payload. Default to JSON since the shape
            # is recipe-type-dependent (Sync has 25 engines; Pivot has nested
            # pivotModalities; Split has sqlWithExecutionPlanList).
            full_fmt = "json" if output is None else fmt
            render_raw(recipe_status.data, output_format=full_fmt)
            return

        if engines:
            engine_rows = recipe_status.data.get("engines") or []
            data = []
            for eng in engine_rows:
                data.append(
                    {
                        "type": eng.get("type", ""),
                        "label": eng.get("label", "") or eng.get("typeLabel", ""),
                        "variant": eng.get("variantLabel", "")
                        or eng.get("variant", ""),
                        "severity": eng.get("statusWarnLevel", ""),
                        "message": eng.get("statusMessage", "") or "",
                        "recommended": "yes" if eng.get("recommended") else "",
                    }
                )
            if data:
                render(
                    data,
                    ["type", "label", "variant", "severity", "message", "recommended"],
                    output_format=fmt,
                    title=f"Engines: {recipe_name}",
                    headers={
                        "type": "TYPE",
                        "label": "LABEL",
                        "variant": "VARIANT",
                        "severity": "SEVERITY",
                        "message": "MESSAGE",
                        "recommended": "RECOMMENDED",
                    },
                )
            else:
                info(
                    f"Recipe '{recipe_name}' has no engine candidates "
                    "(prediction_training, prompt, and similar types use no flow engine)."
                )
            return

        # Extract engine info
        engine = None
        try:
            engine_details = recipe_status.get_selected_engine_details()
            engine = engine_details.get("type", "unknown")
        except (ValueError, KeyError):
            pass  # Some recipe types have no engine concept

        severity = recipe_status.get_status_severity()
        messages = recipe_status.get_status_messages()

        if fmt == "json":
            result = {
                "recipe": recipe_name,
                "project": project_key,
                "engine": engine,
                "severity": severity,
                "messages": messages,
            }
            render_raw(result, output_format="json")
        else:
            # Summary line
            info(f"Recipe: {recipe_name}")
            info(f"Engine: {engine or '(none)'}")
            info(f"Severity: {severity or '(no checks)'}")

            if messages:
                data = []
                for msg in messages:
                    data.append(
                        {
                            "severity": msg.get("severity", ""),
                            "title": msg.get("title", ""),
                            "message": msg.get("message", ""),
                        }
                    )
                render(
                    data,
                    ["severity", "title", "message"],
                    output_format=fmt,
                    title="Status Messages",
                    headers={
                        "severity": "SEVERITY",
                        "title": "TITLE",
                        "message": "MESSAGE",
                    },
                )
            else:
                info("No status messages.")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

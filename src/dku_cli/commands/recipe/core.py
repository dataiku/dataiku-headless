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


def _plugin_has_recipe_component(file_tree, component: str) -> bool:
    """True if a dev plugin's file tree contains custom-recipes/<component>/."""
    for item in file_tree:
        if isinstance(item, dict) and item.get("name") == "custom-recipes":
            for child in item.get("children", []):
                if (
                    isinstance(child, dict)
                    and child.get("name") == component
                    and "children" in child
                ):
                    return True
    return False


def _read_plugin_recipe_manifest(client, type_name: str) -> dict | None:
    """Return the parsed recipe.json for a CustomCode_<component> plugin recipe.

    Searches dev plugins for the owning component (the same list_files traversal
    `dku plugin recipes` uses). Returns None when no dev plugin exposes the
    component — installed/non-dev plugins raise on list_files, so the manifest
    (and its declared roles) is unreadable.
    """
    component = type_name[len("CustomCode_") :]
    try:
        plugins = client.list_plugins()
    except Exception:
        return None
    for p in plugins:
        pid = p.get("id", "") if isinstance(p, dict) else ""
        if not pid:
            continue
        try:
            plugin = client.get_plugin(pid)
            file_tree = plugin.list_files()
        except Exception:
            continue
        if not _plugin_has_recipe_component(file_tree, component):
            continue
        try:
            with plugin.get_file(f"custom-recipes/{component}/recipe.json") as fp:
                return json.loads(fp.read())
        except Exception:
            return None
    return None


def _declared_role_names(roles) -> list[str]:
    """Extract role names from a recipe.json inputRoles/outputRoles list."""
    out: list[str] = []
    if isinstance(roles, list):
        for r in roles:
            if isinstance(r, dict) and r.get("name"):
                out.append(r["name"])
    return out


def _resolve_plugin_role(
    requested: str | None,
    declared: list[str],
    kind: str,
    manifest_readable: bool,
    recipe_name: str,
    type_name: str,
) -> str:
    """Resolve a plugin recipe input/output role against the declared role set.

    - Omitted role + exactly one declared role → that role (auto-resolve).
    - Given role (or the 'main' fallback) that the readable manifest does not
      declare → exit_with_error listing the valid roles (illegal at create time).
    - Falls back to 'main' when nothing else resolves (unreadable manifest).
    """
    if requested is None and manifest_readable and len(declared) == 1:
        return declared[0]
    effective = requested if requested is not None else "main"
    if manifest_readable and declared and effective not in declared:
        exit_with_error(
            f"{kind.capitalize()} role '{effective}' is not declared by plugin recipe '{type_name}'.",
            details=[
                f"Valid {kind} role(s): {', '.join(declared)}",
                f"Retry with --{kind}-role <ROLE> from the list above:",
                f"  dku recipe create {recipe_name} -t {type_name} --{kind}-role {declared[0]} ... -P <PROJ>",
            ],
        )
    return effective


@app.command("list")
def list_recipes(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    fields: str = typer.Option(
        None,
        "--fields",
        help="Comma-separated fields to include (name,type,tags)",
    ),
) -> None:
    """List recipes in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
) -> None:
    """Show recipe identity and I/O (name, type, inputs, outputs) — NO payload.

    The visual recipe config (join keys, aggregations, steps, …) is the
    payload: read it with 'get-settings' (full settings incl. parsed payload)
    or 'get-definition' (raw definition + payload; pairs with set-definition).
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
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
) -> None:
    """Get the full recipe definition (raw definition + payload).

    Returns the recipe's raw_definition (I/O mappings, connection, type) and
    obj_payload (visual recipe config: aggregations, join keys, window specs, etc.).
    Use 'dku recipe set-definition' to update these values.

    Examples:
      dku --format json recipe get-definition my_group -P PROJ
      dku recipe get-definition my_join -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        True,
        "--auto-update-schema/--no-auto-update-schema",
        help=(
            "Update output schemas before each recipe run (default: on; "
            "imported from the Dataiku Agent Dev Kit, which builds with it on). "
            "With --wait, schema changes are reported per dataset. Use "
            "--no-auto-update-schema to preserve the stored schema — required "
            "for partitioned datasets (a schema change can make other "
            "partitions unreadable) and hand-curated schemas/meanings."
        ),
    ),
    timeout: int | None = typer.Option(
        None,
        "--timeout",
        help="When --wait is set, max seconds to wait before failing (matches dku job run). Default: no limit.",
    ),
    no_verify: bool = typer.Option(
        False,
        "--no-verify",
        help="Skip the post-build rows/cols summary for each built output dataset",
    ),
) -> None:
    """Run a recipe.

    Use --type RECURSIVE_BUILD --auto-update-schema to build upstream
    dependencies with automatic schema propagation.

    With --wait, a successful run prints `Built <ds>: N rows, M cols` per
    output dataset so success carries proof (0 rows = warning to investigate).
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
                status=1,
                details=[
                    f"Check wiring: dku recipe get {recipe_name} -P {project_key}",
                ],
            )

        builder = proj.new_job(job_type.value)
        # get_flat_output_refs() returns bare refs with no object type. The job
        # builder defaults object_type to DATASET, so managed-folder / saved-model
        # outputs would error with "dataset does not exist". Resolve the real type.
        resolved_targets = list(resolve_build_output_types(proj, output_refs))
        for resolved_ref, object_type in resolved_targets:
            builder.with_output(resolved_ref, object_type=object_type)
        if auto_update_schema:
            builder.with_auto_update_schema_before_each_recipe_run(True)
        # Pre-build schema snapshot so an auto-applied update is reported, not
        # silent (build_summary._emit_schema_delta). Only when we wait + can change.
        from dku_cli.build_summary import snapshot_schemas

        prev_schemas = (
            snapshot_schemas(proj, resolved_targets)
            if (wait and auto_update_schema)
            else None
        )
        job_start_ms = int(time.time() * 1000)
        job = builder.start()
        job_id = job.id

        success(f"Recipe '{recipe_name}' started")
        info(f"Job ID: {job_id}")
        from dku_cli.output import hint

        hint(f"dku job log {job_id} -P {project_key}")

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
                if not no_verify:
                    from dku_cli.build_summary import emit_build_summary

                    emit_build_summary(
                        client,
                        proj,
                        project_key,
                        resolved_targets,
                        job_start_ms,
                        prev_schemas=prev_schemas,
                    )
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
            # An empty job log on FAILED usually means the recipe never started
            # executing: the inherited container's code-env image isn't built, so
            # DSS dies before emitting any activity log. Surface the recovery.
            try:
                log_text = job.get_log()
            except Exception:
                log_text = None
            if not (log_text and log_text.strip()):
                details += [
                    "",
                    "The job log is empty — the recipe likely never started. The inherited "
                    "container's code-env image may be unbuilt.",
                    "  Build the image:           dku code-env update-images <ENV_NAME>",
                    f"  Or run on the DSS process: dku recipe set-env {recipe_name} --container-mode NONE -P {project_key}",
                ]
            exit_with_error(
                f"Recipe '{recipe_name}' {state.lower()} (job {job_id}).",
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
                status=4,
                details=[
                    f"Inspect the log: dku job log {job_id} -P {project_key}",
                    f"Job status: dku job status {job_id} -P {project_key}",
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
    input_role: str | None = typer.Option(
        None,
        "--input-role",
        help="Input role name for plugin recipes. Omit to auto-resolve when the plugin declares exactly one input role; validated against the plugin's declared roles for dev plugins.",
    ),
    output_role: str | None = typer.Option(
        None,
        "--output-role",
        help="Output role name for plugin recipes. Omit to auto-resolve when the plugin declares exactly one output role; validated against the plugin's declared roles for dev plugins.",
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
            details=[
                f"Correct syntax: dku recipe create <NAME> --type {recipe_name} --input <DS> --output-ds <DS> -P <PROJ>",
            ],
        )
    # Resolve the output target: exactly one of --output-ds / --output-folder.
    if output_ds and output_folder:
        exit_with_error(
            "Pass only one of --output-ds and --output-folder.",
            details=[
                "--output-ds wires/creates a dataset output.",
                "--output-folder wires an existing managed folder output.",
            ],
        )
    if not output_ds and not output_folder:
        exit_with_error(
            "No output specified. Provide --output-ds <DATASET> or --output-folder <FOLDER>.",
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

            # Resolve I/O roles against the plugin's declared role set so the
            # recipe wires onto roles the plugin actually has (named-role plugins
            # have no 'main' — wiring there fails at build).
            manifest = _read_plugin_recipe_manifest(client, type_name)
            manifest_readable = manifest is not None
            declared_in = (
                _declared_role_names(manifest.get("inputRoles")) if manifest else []
            )
            declared_out = (
                _declared_role_names(manifest.get("outputRoles")) if manifest else []
            )
            if not manifest_readable and (input_role is None or output_role is None):
                warn(
                    f"Could not read plugin recipe '{type_name}' manifest (installed/non-dev "
                    "plugin). Defaulting unset role(s) to 'main', which may not match the "
                    "plugin's declared roles — if the build fails, set --input-role/--output-role "
                    "explicitly (see: dku plugin recipes)."
                )
            resolved_input_role = _resolve_plugin_role(
                input_role,
                declared_in,
                "input",
                manifest_readable,
                recipe_name,
                type_name,
            )
            resolved_output_role = _resolve_plugin_role(
                output_role,
                declared_out,
                "output",
                manifest_readable,
                recipe_name,
                type_name,
            )

            builder = DSSRecipeCreator(type_name, recipe_name, proj)
            builder.set_raw_mode()
            for _input in inputs:
                builder.with_input(_input, role=resolved_input_role)
            for _fid in input_folder_ids:
                builder.with_input(_fid, role=resolved_input_role)
            # output_ref resolves folder-or-dataset outputs (upstream fix);
            # plugin recipes can target a managed folder, not just a dataset.
            builder.with_output(output_ref, role=resolved_output_role)
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
            # - Code recipes without --connection pre-create a managed FS output,
            #   then wire it as an existing output via with_output().
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
            elif type_lower in _TEXT_PAYLOAD_RECIPE_TYPES and hasattr(
                builder, "with_new_output_dataset"
            ):
                _ensure_output_dataset(
                    client,
                    proj,
                    output_ds,
                    project_key,
                    input_dataset_ref=inputs[0] if inputs else None,
                )
                builder.with_output(output_ds)
            elif type_lower in {"prepare", "shaker"} and hasattr(
                builder, "with_existing_output"
            ):
                _ensure_output_dataset(
                    client,
                    proj,
                    output_ds,
                    project_key,
                    input_dataset_ref=inputs[0] if inputs else None,
                )
                builder.with_existing_output(output_ds)
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
        if (
            output_ds
            and not output_folder_id
            and type_name.lower() in _TEXT_PAYLOAD_RECIPE_TYPES
        ):
            _ensure_file_output_format(proj, output_ds)
        # Container / env-mode pinning for code recipes.
        if container_mode is not None:
            if container_mode.value == "EXPLICIT_CONTAINER" and not container_conf:
                exit_with_error(
                    "--container-mode EXPLICIT_CONTAINER requires --container-conf.",
                )
        if env_mode is not None:
            if env_mode.value == "EXPLICIT_ENV" and not env_name:
                exit_with_error(
                    "--env-mode EXPLICIT_ENV requires --env-name.",
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
        from dku_cli.output import hint

        hint(f"dku recipe run {recipe_name} -P {project_key}")
    except Exception as e:
        if is_already_exists_error(e):
            exit_with_error(
                f"Output dataset '{output_ds}' already exists in {project_key}.",
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
                details = [
                    f"Output dataset '{output_ds}' does not exist.",
                    f"`dku recipe create -t {type_name}` does NOT auto-create the output (the typed shortcuts create-prepare / create-join / create-group / ... do).",
                    "",
                ]
                if type_name.lower() in ("prepare", "shaker"):
                    details += [
                        "Fix in ONE command — create-prepare auto-creates the output:",
                        f"  dku recipe create-prepare {recipe_name} {' '.join(f'-i {i}' for i in inputs)} --output-ds {output_ds} -P {project_key}",
                        "",
                        "Or in two commands:",
                    ]
                else:
                    details.append("Fix in two commands:")
                details += [
                    f"  dku dataset create {output_ds} --type Filesystem -c filesystem_managed -P {project_key}",
                    f"  dku recipe create {recipe_name} -t {type_name} {' '.join(f'-i {i}' for i in inputs)} --output-ds {output_ds} -P {project_key}",
                    "",
                    "Typed shortcuts auto-create their output: create-prepare, create-join,",
                    "create-group, create-stack, create-distinct, create-sort, create-filter,",
                    "create-window, create-topn, create-pivot, create-sampling, create-split.",
                    "",
                    # Restate the verdict LAST: agents pipe through `tail -N`
                    # and must not mistake the hint lines for success.
                    f"FAILED — recipe '{recipe_name}' was NOT created.",
                ]
                exit_with_error(
                    f"FAILED: recipe '{recipe_name}' was NOT created — output dataset '{output_ds}' must be created first.",
                    details=details,
                )
            else:
                exit_with_error(
                    f"Cannot auto-create output dataset '{output_ds}' — no default managed connection configured.",
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
                    "",
                    f"FAILED — recipe '{recipe_name}' was NOT created.",
                ],
            )
        if "recipe type" in str(e).lower() and "unknown" in str(e).lower():
            exit_with_error(
                f"Recipe type '{type_name}' is unknown to DSS.",
                details=[
                    "Plugin recipe type format is: CustomCode_<recipeComponentId>",
                    "  The plugin ID is NOT part of the type. Only the recipe directory name.",
                    "Discover available types: dku plugin recipes",
                    "If the plugin was just installed, DSS may need a restart to register types.",
                ],
            )
        handle_api_error(e)


def _ensure_file_output_format(proj, output_ds: str) -> None:
    """Pin a default format on filesystem-like code-recipe outputs.

    DSS can auto-create a managed Filesystem output without formatType; the
    recipe then fails only at build time with a raw Java exception. SQL outputs
    do not use file format settings, so only touch filesystem/uploaded shapes.
    """
    try:
        ds = proj.get_dataset(output_ds)
        definition = ds.get_definition()
        if definition.get("formatType"):
            return
        if definition.get("type") not in {"Filesystem", "UploadedFiles"}:
            return
        definition["formatType"] = "csv"
        definition.setdefault(
            "formatParams",
            {
                "style": "excel",
                "charset": "utf8",
                "separator": ",",
                "quoteChar": '"',
                "escapeChar": "\\",
                "parseHeaderRow": True,
            },
        )
        ds.set_definition(definition)
        info(f"Set default CSV format on output dataset '{output_ds}'")
    except Exception as exc:
        warn(f"Could not set output dataset format for '{output_ds}': {exc}")


@app.command("create-python")
def create_python(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    inputs: list[str] = typer.Option(
        [],
        "--input",
        "-i",
        "--input-ds",
        "--input-dataset",
        help="Input dataset name. Repeatable. Optional for data-generation recipes.",
    ),
    output_ds: str = typer.Option(
        ...,
        "--output-ds",
        "--output-dataset",
        help="Output dataset name (auto-created).",
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help="Connection for the auto-created output dataset.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Alias for `recipe create NAME -t python`.

    Agents naturally try `create-python` by analogy with visual shortcuts.
    Keep it as a thin wrapper so help/discovery has a successful path.
    """
    create(
        ctx=ctx,
        recipe_name=recipe_name,
        type_name="python",
        inputs=inputs,
        output_ds=output_ds,
        output_folder=None,
        input_folders=[],
        connection=connection,
        input_role="main",
        output_role="main",
        params=None,
        model=None,
        container_mode=None,
        container_conf=None,
        env_mode=None,
        env_name=None,
        project=project,
    )


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
    engines: bool = typer.Option(
        False,
        "--engines",
        help="List all candidate engines with per-engine status (TYPE, LABEL, VARIANT, SEVERITY, MESSAGE).",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Dump the full server status payload (engines, sqlWithExecutionPlanList, pivotModalities, outputSchema with originalType, sqlWarning, recipe-type-keyed buckets, etc.). Renders as JSON.",
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
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        recipe_status = recipe.get_status()

        if full:
            # Dump the entire server payload as JSON — the shape is
            # recipe-type-dependent (Sync has 25 engines; Pivot has nested
            # pivotModalities; Split has sqlWithExecutionPlanList).
            render_raw(recipe_status.data, output_format=fmt)
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

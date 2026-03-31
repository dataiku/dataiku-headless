"""dku recipe — list, get, get-definition, run, create, delete, set-code, get-code, set-definition, add-input, add-output, plus GenAI recipe creation."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer

from dataikuapi.dss.recipe import (
    FuzzyJoinRecipeCreator,
    GeoJoinRecipeCreator,
)

from dku_cli.errors import (
    exit_with_error,
    handle_api_error,
    is_already_exists_error,
    is_connection_required_error,
    is_not_found_error,
)
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    read_text_input,
    resolve_project,
)
from dku_cli.output import (
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS recipes.")

_KNOWN_RECIPE_TYPES = frozenset(
    {
        "python",
        "sql",
        "sql_script",
        "sql_query",
        "sync",
        "join",
        "split",
        "group",
        "distinct",
        "topn",
        "sort",
        "window",
        "pivot",
        "stack",
        "prepare",
        "sample",
        "filter",
        "download",
        "upload",
        "impala",
        "hive",
        "pig",
        "spark_sql",
        "pyspark",
        "sparkr",
        "r",
        "shell",
        "cpython",
        "streaming",
        "geojoin",
        "fuzzyjoin",
    }
)


def _is_plugin_recipe_type(type_name: str) -> bool:
    """Plugin recipe types follow the pattern CustomCode_<pluginId>_<recipeId>."""
    return type_name.startswith("CustomCode_") and type_name.count("_") >= 2


def _require_existing_dataset(
    proj, dataset_name: str, project_key: str, role: str
) -> None:
    try:
        proj.get_dataset(dataset_name).get_definition()
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"{role} dataset '{dataset_name}' does not exist in project '{project_key}'. "
                "Create it first, then retry.",
                code="missing_dataset",
            )
        handle_api_error(e)


def _create_eval_recipe_raw(
    client,
    proj,
    recipe_name: str,
    recipe_type: str,
    input_ds: str,
    eval_store: str,
    output_ds: str | None,
    output_metrics: str | None,
):
    recipe_proto = {
        "projectKey": proj.project_key,
        "type": recipe_type,
        "name": recipe_name,
        "inputs": {
            "main": {
                "items": [{"ref": input_ds}],
            }
        },
        "outputs": {
            "evaluationStore": {
                "items": [{"ref": eval_store, "appendMode": False}],
            }
        },
    }

    if output_ds:
        recipe_proto["outputs"]["main"] = {
            "items": [{"ref": output_ds, "appendMode": False}],
        }
    if output_metrics:
        recipe_proto["outputs"]["metrics"] = {
            "items": [{"ref": output_metrics, "appendMode": True}],
        }

    # PRIVATE API: dataikuapi builders don't support eval-store outputs or rawCreation.
    # Switch to public builder when dataikuapi adds eval recipe support.
    response = client._perform_json(
        "POST",
        f"/projects/{proj.project_key}/recipes/",
        body={
            "recipePrototype": recipe_proto,
            "creationSettings": {"rawCreation": True},
        },
    )
    return proj.get_recipe(response["name"])


def _get_recipe_payload(settings) -> dict:
    """Get or init the recipe payload, handling read-only obj_payload property."""
    try:
        payload = settings.obj_payload
        if payload is not None:
            return payload
    except (AttributeError, TypeError, KeyError):
        pass

    # obj_payload is read-only in real dataikuapi — write to raw_params directly
    if hasattr(settings, "raw_params"):
        settings.raw_params.setdefault("payload", {})
        return settings.raw_params["payload"]

    # Last resort: manipulate the raw recipe definition dict
    raw = settings.get_recipe_raw_definition()
    raw.setdefault("params", {}).setdefault("payload", {})
    return raw["params"]["payload"]


def _parse_order_specs(specs: list[str]) -> list[dict]:
    """Parse order specifications like 'col', 'col:desc', 'col:asc' into payload format."""
    orders = []
    for spec in specs:
        if spec.endswith(":desc"):
            orders.append({"column": spec[:-5], "desc": True})
        elif spec.endswith(":asc"):
            orders.append({"column": spec[:-4], "desc": False})
        else:
            orders.append({"column": spec, "desc": False})
    return orders


def _get_prepare_settings(proj, recipe_name: str, project_key: str):
    """Get settings for a prepare recipe, validating type. Returns (recipe, settings)."""
    recipe = proj.get_recipe(recipe_name)
    settings = recipe.get_settings()
    raw_def = settings.get_recipe_raw_definition()
    rtype = raw_def.get("type", "")
    if rtype not in ("prepare", "shaker"):
        exit_with_error(
            f"Recipe '{recipe_name}' is type '{rtype}', not 'prepare'. "
            "Step commands only work on prepare recipes.",
            code="wrong_recipe_type",
            details=[
                f"Create a prepare recipe first: dku recipe create <NAME> -t prepare -i <INPUT> --output-ds <OUTPUT> -P {project_key}",
            ],
        )
    return recipe, settings


def _ensure_steps_array(settings) -> list:
    """Ensure obj_payload has a 'steps' list. Fresh recipes may not have it. Returns the steps list."""
    payload = _get_recipe_payload(settings)
    if "steps" not in payload:
        payload["steps"] = []
    return payload["steps"]


def _validate_step_index(steps: list, index: int, recipe_name: str) -> None:
    """Validate step index is in range."""
    if index < 0 or index >= len(steps):
        count = len(steps)
        if count == 0:
            exit_with_error(
                f"Recipe '{recipe_name}' has no steps.",
                code="invalid_index",
                details=[
                    f"Add steps first: dku recipe add-step {recipe_name} --type <TYPE> --params '<JSON>' -P <PROJ>"
                ],
            )
        else:
            exit_with_error(
                f"Step index {index} out of range. Recipe '{recipe_name}' has {count} steps (0–{count - 1}).",
                code="invalid_index",
                details=[f"List steps: dku recipe list-steps {recipe_name} -P <PROJ>"],
            )


@app.command("list")
def list_recipes(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
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

        render(
            data,
            ["name", "type", "tags"],
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
        recipe = proj.get_recipe(recipe_name)
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
        recipe = proj.get_recipe(recipe_name)
        settings = recipe.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        payload = settings.obj_payload

        if output == "json":
            result = {"definition": raw_def, "payload": payload}
            print(json.dumps(result, indent=2, default=str))
        else:
            input_refs = settings.get_flat_input_refs()
            output_refs = settings.get_flat_output_refs()
            data = [
                {"field": "Name", "value": recipe_name},
                {"field": "Type", "value": raw_def.get("type", "")},
                {"field": "Inputs", "value": ", ".join(input_refs) or "(none)"},
                {"field": "Outputs", "value": ", ".join(output_refs) or "(none)"},
                {
                    "field": "Payload",
                    "value": json.dumps(payload, default=str) if payload else "(none)",
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
) -> None:
    """Run a recipe.

    Use --type RECURSIVE_BUILD --auto-update-schema to build upstream
    dependencies with automatic schema propagation.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipe = proj.get_recipe(recipe_name)

        if job_type or auto_update_schema:
            # Get recipe outputs to build via job builder
            settings = recipe.get_settings()
            output_refs = settings.get_flat_output_refs()
            if not output_refs:
                from dku_cli.output import error

                error(f"Recipe '{recipe_name}' has no outputs to build")
                raise typer.Exit(1)

            builder = proj.new_job(job_type or "NON_RECURSIVE_FORCED_BUILD")
            for ref in output_refs:
                builder.with_output(ref)
            if auto_update_schema:
                builder.with_auto_update_schema_before_each_recipe_run(True)
            job = builder.start()
        else:
            job = recipe.run()

        success(f"Recipe '{recipe_name}' started")
        info(f"Job ID: {job.id}")
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
                success("Recipe completed successfully")
            else:
                from dku_cli.output import error

                error(f"Recipe finished with state: {state}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    type_name: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Recipe type: python, sql, join, group, etc. For plugin recipes: CustomCode_<pluginId>_<recipeId>",
    ),
    input_ds: str = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        "--input-dataset",
        help="Input dataset name (must exist)",
    ),
    output_ds: str = typer.Option(
        ...,
        "--output-ds",
        "--output-dataset",
        help="Output dataset name (auto-created for code recipes, must exist for plugin recipes)",
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help="Connection for output dataset (code recipes). Use when project has no default managed connection. Run 'dku connection list' to see available connections.",
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

    Plugin recipes use type CustomCode_<pluginId>_<recipeId>. The output dataset
    must already exist. Use --params to pass initial configuration:

      dku recipe create my_step -t CustomCode_my-plugin_my-recipe \\
        -i input_ds --output-ds output_ds --params '{"key": "val"}' -P PROJ

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
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        if _is_plugin_recipe_type(type_name):
            # Plugin recipes: project.new_recipe() returns None for unknown types.
            # Use DSSRecipeCreator directly in raw mode.
            from dataikuapi.dss.recipe import DSSRecipeCreator

            builder = DSSRecipeCreator(type_name, recipe_name, proj)
            builder.set_raw_mode()
            builder.with_input(input_ds, role=input_role)
            builder.with_output(output_ds, role=output_role)
            if params_dict is not None:
                builder.creation_settings["rawPayload"] = json.dumps(params_dict)
            builder.build()
        else:
            builder = proj.new_recipe(type_name, recipe_name)
            if builder is None:
                exit_with_error(
                    f"Unknown recipe type '{type_name}'.",
                    code="unknown_recipe_type",
                    details=[
                        "Built-in types: python, sql, join, group, sort, distinct, topn, window, stack, split, prepare, filter, sync",
                        "Plugin recipe types use format: CustomCode_<pluginId>_<recipeId>",
                        "Discover plugin recipes: dku plugin recipes",
                    ],
                )
            builder.with_input(input_ds)
            # Visual recipe creators have with_existing_output() — output must already exist.
            # Code recipe creators (CodeRecipeCreator) use:
            #   - with_new_output_dataset(name, connection) when --connection is provided
            #   - with_output(name) when no connection (requires existing dataset or project default)
            is_visual = hasattr(builder, "with_existing_output")
            if is_visual:
                if connection:
                    warn(
                        "--connection is ignored for visual recipes (output must already exist)."
                    )
                builder.with_existing_output(output_ds)
            elif connection:
                builder.with_new_output_dataset(output_ds, connection)
            else:
                builder.with_output(output_ds)
            builder.build()
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
            # Visual recipes (prepare, sync, etc.) need the output to pre-exist.
            # Code recipes need a --connection for auto-creation.
            visual_types = {
                "prepare",
                "shaker",
                "sync",
                "join",
                "group",
                "sort",
                "distinct",
                "topn",
                "window",
                "stack",
                "split",
                "filter",
                "pivot",
                "sample",
            }
            if type_name in visual_types:
                exit_with_error(
                    f"Output dataset '{output_ds}' does not exist. Visual recipes require the output dataset to be created first.",
                    code="output_not_found",
                    details=[
                        f"Create it first: dku dataset create {output_ds} --type Filesystem -c filesystem_managed -P {project_key}",
                        f"Then retry: dku recipe create {recipe_name} -t {type_name} -i {input_ds} --output-ds {output_ds} -P {project_key}",
                        "Tip: visual recipe shortcuts (create-join, create-group, etc.) auto-create the output dataset.",
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
                        f"Example: dku recipe create {recipe_name} -t {type_name} -i {input_ds} --output-ds {output_ds} --connection filesystem_managed -P {project_key}",
                    ],
                )
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        recipe.delete()
        success(f"Deleted recipe '{recipe_name}' from {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("set-code")
def set_code(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    code: str = typer.Option(
        ..., "--code", "-c", help="Code: literal string, @file.py, or '-' for stdin"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the code payload of a code recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)

        if code == "-":
            code_text = sys.stdin.read()
        elif code.startswith("@"):
            code_text = Path(code[1:]).read_text()
        else:
            code_text = code

        settings = recipe.get_settings()
        settings.set_payload(code_text)
        settings.save()
        success(f"Updated code for recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("get-code")
def get_code(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the code payload of a code recipe."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("text", "json"), default="text")
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        payload = settings.get_payload()
        if output == "json":
            render_raw({"code": payload}, output_format="json")
        else:
            print(payload)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="Recipe definition JSON — updates raw_definition (connection, I/O). String, @file.json, or '-' for stdin.",
    ),
    payload_json: str | None = typer.Option(
        None,
        "--payload",
        help="Recipe payload JSON — updates obj_payload (visual recipe config: aggregations, computations, etc.). String, @file.json, or '-' for stdin.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the definition or payload of a recipe from JSON.

    Use --definition to update recipe-level settings (I/O mappings, connection info).
    Use --payload to update the visual recipe configuration (aggregations, window
    computations, join keys, filter conditions, etc.). These are mutually exclusive.

    Examples:
      dku recipe set-definition my_topn --payload '{"topN": 5}' -P PROJ
      dku recipe set-definition my_recipe -d @recipe_def.json -P PROJ
    """
    if not definition and not payload_json:
        exit_with_error(
            "Provide either --definition or --payload.",
            code="invalid_argument",
            details=[
                "--definition: updates raw recipe definition (connection, I/O mappings)",
                "--payload: updates obj_payload (visual recipe config: aggregations, computations)",
            ],
        )
    if definition and payload_json:
        exit_with_error(
            "Cannot use both --definition and --payload. Provide one.",
            code="invalid_argument",
        )
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        if definition:
            new_def = read_json_input(definition)
            raw = settings.get_recipe_raw_definition()
            raw.update(new_def)
            target = "definition"
        else:
            new_payload = read_json_input(payload_json)
            current = _get_recipe_payload(settings)
            current.update(new_payload)
            target = "payload"
        settings.save()
        success(f"Updated {target} for recipe '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-settings")
def get_settings_cmd(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get full recipe settings as JSON (includes visual recipe payload).

    Unlike 'get' which shows a summary, this returns the complete settings
    including the payload — visual recipe configuration like sort orders,
    join keys, filter conditions, aggregations, etc.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        # Build complete settings dict: definition + parsed payload
        full = dict(raw_def)
        try:
            payload = settings.obj_payload
            if payload is not None:
                full["payload"] = payload
        except (AttributeError, TypeError):
            pass
        if "payload" not in full and hasattr(settings, "raw_params"):
            full["payload"] = settings.raw_params.get("payload")
        render_raw(full, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-settings")
def set_settings_cmd(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    settings_json: str = typer.Option(
        ...,
        "--settings",
        "-s",
        help="Settings JSON (string, @file.json, or '-' for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set full recipe settings from JSON (supports visual recipe payload).

    Accepts a JSON object. Keys at root level update the recipe definition.
    The 'payload' key (if present) updates the visual recipe configuration
    (sort orders, join keys, filter conditions, aggregations, etc.).

    Payload update is a SHALLOW merge: top-level payload keys are replaced,
    not deep-merged. Use 'get-settings' first to read, modify, then 'set-settings'
    to preserve existing nested configuration.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        new_settings = read_json_input(settings_json)

        # Update definition (everything except payload)
        raw = settings.get_recipe_raw_definition()
        for k, v in new_settings.items():
            if k != "payload":
                raw[k] = v

        # Update payload (visual recipe config) — shallow merge at top level
        if "payload" in new_settings:
            payload = _get_recipe_payload(settings)
            payload.update(new_settings["payload"])

        settings.save()
        success(f"Updated settings for recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("add-input")
def add_input(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    ref: str = typer.Argument(help="Dataset reference to add as input"),
    role: str = typer.Option("main", "--role", help="Input role"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an input dataset to a recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        settings.add_input(role, ref)
        settings.save()
        success(f"Added input '{ref}' to recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("add-output")
def add_output(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    ref: str = typer.Argument(help="Dataset reference to add as output"),
    role: str = typer.Option("main", "--role", help="Output role"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an output dataset to a recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        settings.add_output(role, ref)
        settings.save()
        success(f"Added output '{ref}' to recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Schema inspection commands
# ---------------------------------------------------------------------------


@app.command("check-schema")
def check_schema(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Check if recipe outputs need schema updates.

    Exit code 0 = no changes needed, 1 = changes needed.
    Note: does not work for code recipes (Python, R) — only visual recipes.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        updates = recipe.compute_schema_updates()

        if output == "json":
            render_raw(updates.data, output_format="json")
        else:
            data = []
            for comp in updates.data.get("computables", []):
                cols = comp.get("newSchema", {}).get("columns", [])
                data.append(
                    {
                        "output": comp.get("datasetName", comp.get("id", "")),
                        "type": comp.get("type", ""),
                        "columns": str(len(cols)),
                        "changed": str(comp.get("schemaChanged", False)),
                    }
                )
            render(
                data,
                ["output", "type", "columns", "changed"],
                output_format=output,
                title=f"Schema Check: {recipe_name}",
            )

        if updates.any_action_required():
            warn(
                f"Schema updates required ({updates.data.get('totalIncompatibilities', 0)} incompatibilities)"
            )
            raise SystemExit(1)
        else:
            success(f"No schema updates needed for '{recipe_name}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("apply-schema")
def apply_schema(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Compute and apply required schema updates to recipe outputs.

    Note: does not work for code recipes (Python, R) — only visual recipes.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("table", "json"), default="json")
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        updates = recipe.compute_schema_updates()

        if not updates.any_action_required():
            success(f"No schema updates needed for '{recipe_name}'")
            return

        results = updates.apply()
        render_raw(results, output_format=output)
        success(f"Applied schema updates for '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Prepare recipe step commands
# ---------------------------------------------------------------------------


def _step_target(step: dict) -> str:
    """Extract a short 'target' summary from step params for table display."""
    params = step.get("params", {})
    # Try common param keys in priority order
    for key in ("expression", "column", "columns", "renamings"):
        val = params.get(key)
        if val is not None:
            s = str(val)
            return s[:40] + ("…" if len(s) > 40 else "")
    return ""


@app.command("list-steps")
def list_steps(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List steps in a prepare recipe.

    Shows each step's index, processor type, name, disabled status, and target column/expression.
    Use -o json for full step parameters.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)

        if output == "json":
            render_raw(steps, output_format="json")
            return

        if not steps:
            info(
                f"No steps in recipe '{recipe_name}'. Add with: dku recipe add-step {recipe_name} --type <TYPE> --params '<JSON>' -P {project_key}"
            )
            return

        rows = []
        for i, step in enumerate(steps):
            rows.append(
                {
                    "index": str(i),
                    "type": step.get("type", ""),
                    "name": step.get("name", ""),
                    "disabled": str(step.get("disabled", False)),
                    "target": _step_target(step),
                }
            )
        render(
            rows,
            ["index", "type", "name", "disabled", "target"],
            output_format=output,
            title=f"Steps: {recipe_name}",
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-step")
def add_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    step_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Processor type (e.g. CreateColumnWithGREL, ColumnRenamer, FillEmptyWithValue, ColumnsSelector, FindReplace, FilterOnValue, RemoveRowsOnEmpty, StringTransformer, ColumnCopier, PythonUDF). ~95 types available.",
    ),
    params: str = typer.Option(
        ..., "--params", help="Step params: JSON string, @file.json, or '-' for stdin"
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    name: str | None = typer.Option(None, "--name", help="Optional step display name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a processor step to a prepare recipe (generic — any of ~95 processor types).

    For common operations, prefer named shortcuts: add-formula, add-rename,
    add-filter-rows, add-fill-empty, add-delete-columns, add-find-replace.
    Use add-step for advanced or unusual processors.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)

        parsed_params = read_json_input(params)
        step_dict: dict = {
            "metaType": "PROCESSOR",
            "type": step_type,
            "params": parsed_params,
        }
        if name:
            step_dict["name"] = name

        if at is not None:
            if at < 0 or at > len(steps):
                exit_with_error(
                    f"--at {at} out of range. Valid: 0–{len(steps)}.",
                    code="invalid_index",
                )
            steps.insert(at, step_dict)
            idx = at
        else:
            steps.append(step_dict)
            idx = len(steps) - 1

        settings.save()
        success(f"Added {step_type} step to '{recipe_name}' at index {idx}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-step")
def remove_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: list[int] = typer.Option(
        ...,
        "--index",
        help="Step index to remove (0-based, repeatable). Use 'list-steps' to see indices.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Remove one or more steps from a prepare recipe by index.

    When removing multiple steps, they are removed in descending order
    internally to avoid index shifting.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)

        # Validate all indices before removing any
        for idx in index:
            _validate_step_index(steps, idx, recipe_name)

        # Remove in descending order to avoid shifting
        for idx in sorted(set(index), reverse=True):
            steps.pop(idx)

        settings.save()
        removed = ", ".join(str(i) for i in sorted(index))
        success(f"Removed step(s) [{removed}] from '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-step")
def get_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: int = typer.Option(..., "--index", help="Step index (0-based)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get full details of a single prepare recipe step.

    Returns the complete step JSON including all parameters.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        _validate_step_index(steps, index, recipe_name)
        render_raw(steps[index], output_format=output)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("disable-step")
def disable_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: list[int] = typer.Option(
        ..., "--index", help="Step index to disable (0-based, repeatable)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Disable steps in a prepare recipe (skipped during execution).

    Disabled steps remain in the recipe but are not executed when the recipe runs.
    Use 'enable-step' to re-enable. Useful for debugging data pipelines step-by-step.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        for idx in index:
            _validate_step_index(steps, idx, recipe_name)
            steps[idx]["disabled"] = True
        settings.save()
        indices = ", ".join(str(i) for i in index)
        success(f"Disabled step(s) [{indices}] in '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("enable-step")
def enable_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: list[int] = typer.Option(
        ..., "--index", help="Step index to enable (0-based, repeatable)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Enable previously disabled steps in a prepare recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        for idx in index:
            _validate_step_index(steps, idx, recipe_name)
            steps[idx]["disabled"] = False
        settings.save()
        indices = ", ".join(str(i) for i in index)
        success(f"Enabled step(s) [{indices}] in '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Prepare recipe step shortcuts (named wrappers for common processors)
# ---------------------------------------------------------------------------


def _add_prepare_step(
    ctx, recipe_name: str, project: str | None, step_type: str, params: dict
) -> None:
    """Shared logic for all named step shortcuts."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        steps.append({"metaType": "PROCESSOR", "type": step_type, "params": params})
        settings.save()
        success(f"Added {step_type} step to '{recipe_name}' (index {len(steps) - 1})")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-formula")
def add_formula(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    expr: str = typer.Option(
        ...,
        "--expr",
        "-e",
        help="GREL expression (e.g. 'upper(city)', 'price * 1.1', 'if(age>=18,\"adult\",\"minor\")')",
    ),
    column: str = typer.Option(
        ..., "--column", "-c", help="Output column name for the formula result"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a formula step (GREL expression) to create or transform a column.

    Use instead of Python for computed columns, string transforms, and conditionals.
    Formula reference: skills/dataiku/references/formulas.md
    """
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "CreateColumnWithGREL",
        {
            "expression": expr,
            "column": column,
        },
    )


@app.command("add-rename")
def add_rename(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    rename_from: str = typer.Option(
        None, "--from", help="Column to rename (use with --to)"
    ),
    rename_to: str = typer.Option(
        None, "--to", help="New column name (use with --from)"
    ),
    mappings: str = typer.Option(
        None,
        "--mappings",
        help='Bulk renames as JSON: \'{"old1":"new1","old2":"new2"}\' or @file.json',
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a column rename step. Use --from/--to for single, --mappings for bulk.

    Use instead of df.rename() in Python.
    """
    if mappings and (rename_from or rename_to):
        exit_with_error(
            "Use --from/--to OR --mappings, not both.",
            code="invalid_argument",
        )
    if mappings:
        parsed = read_json_input(mappings)
        if not isinstance(parsed, dict):
            exit_with_error(
                '--mappings must be a JSON object: \'{"old":"new"}\'',
                code="invalid_argument",
            )
        renamings = [{"from": k, "to": v} for k, v in parsed.items()]
    elif rename_from and rename_to:
        renamings = [{"from": rename_from, "to": rename_to}]
    else:
        exit_with_error(
            "Provide --from and --to for a single rename, or --mappings for bulk.",
            code="invalid_argument",
            details=[
                "Single: dku recipe add-rename RECIPE --from old_name --to new_name -P PROJ",
                'Bulk: dku recipe add-rename RECIPE --mappings \'{"old1":"new1","old2":"new2"}\' -P PROJ',
            ],
        )
    _add_prepare_step(
        ctx, recipe_name, project, "ColumnRenamer", {"renamings": renamings}
    )


@app.command("add-filter-rows")
def add_filter_rows(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    column: str = typer.Option(
        None, "--column", "-c", help="Column to filter on (value-based)"
    ),
    values: str = typer.Option(
        None, "--values", help="Comma-separated values to match"
    ),
    formula: str = typer.Option(
        None,
        "--formula",
        help="GREL formula for expression-based filtering (e.g. 'price > 100')",
    ),
    action: str = typer.Option(
        "REMOVE_ROW", "--action", help="KEEP_ROW, REMOVE_ROW, CLEAR_CELL, or FLAG"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a filter/flag step to remove or keep rows matching conditions.

    Use --column + --values for value-based, or --formula for expression-based.
    Use instead of df[df.col > x] in Python.
    """
    if formula and (column or values):
        exit_with_error(
            "Use --column/--values OR --formula, not both.", code="invalid_argument"
        )
    if formula:
        _add_prepare_step(
            ctx,
            recipe_name,
            project,
            "FilterOnFormula",
            {
                "expression": formula,
                "action": action.upper(),
            },
        )
    elif column and values:
        _add_prepare_step(
            ctx,
            recipe_name,
            project,
            "FlagOnValue",
            {
                "appliesTo": "SINGLE_COLUMN",
                "columns": [column],
                "values": [v.strip() for v in values.split(",")],
                "action": action.upper(),
                "matchingMode": "FULL_STRING",
                "normalizationMode": "EXACT",
                "booleanMode": "AND",
            },
        )
    else:
        exit_with_error(
            "Provide --column + --values, or --formula.",
            code="invalid_argument",
            details=[
                "Value-based: dku recipe add-filter-rows RECIPE --column status --values 'active,pending' --action KEEP_ROW -P PROJ",
                "Formula: dku recipe add-filter-rows RECIPE --formula 'price > 100' --action REMOVE_ROW -P PROJ",
            ],
        )


@app.command("add-fill-empty")
def add_fill_empty(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    column: str = typer.Option(
        ..., "--column", "-c", help="Column to fill empty values in"
    ),
    value: str = typer.Option(..., "--value", help="Value to fill empty cells with"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a step that fills empty/null values in a column with a fixed value.

    Use instead of df.fillna() in Python.
    """
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "FillEmptyWithValue",
        {
            "appliesTo": "SINGLE_COLUMN",
            "columns": [column],
            "value": value,
        },
    )


@app.command("add-delete-columns")
def add_delete_columns(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    columns: str = typer.Option(
        ..., "--columns", help="Comma-separated column names to delete"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a step to delete (drop) columns from the dataset.

    Use instead of df.drop(columns=[...]) in Python.
    """
    cols_list = [c.strip() for c in columns.split(",")]
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "ColumnsSelector",
        {
            "appliesTo": "COLUMNS",
            "columns": cols_list,
            "keep": False,
        },
    )


@app.command("add-find-replace")
def add_find_replace(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    column: str = typer.Option(..., "--column", "-c", help="Column to search in"),
    find: str = typer.Option(..., "--find", help="Value to find"),
    replace: str = typer.Option(..., "--replace", help="Replacement value"),
    matching: str = typer.Option(
        "FULL_STRING", "--matching", help="FULL_STRING, SUBSTRING, or PATTERN (regex)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a find-and-replace step on a column.

    Use instead of df[col].str.replace() in Python.
    """
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "FindReplace",
        {
            "appliesTo": "SINGLE_COLUMN",
            "columns": [column],
            "output": "",
            "mapping": [{"from": find, "to": replace}],
            "matching": matching.upper(),
            "normalization": "EXACT",
        },
    )


@app.command("add-fold")
def add_fold(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    columns: str = typer.Option(
        None,
        "--columns",
        help="Comma-separated column names to fold (wide→long). Mutually exclusive with --pattern.",
    ),
    pattern: str = typer.Option(
        None,
        "--pattern",
        help="Regex pattern matching column names to fold (e.g. '.*-25'). Mutually exclusive with --columns.",
    ),
    key_column: str = typer.Option(
        "fold_key", "--key-column", help="Output column for original column names"
    ),
    value_column: str = typer.Option(
        "fold_value", "--value-column", help="Output column for cell values"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Fold (unpivot) multiple columns into key-value rows (wide→long).

    Use instead of pd.melt() or pd.wide_to_long() in Python.
    Specify columns explicitly with --columns, or match by regex with --pattern.

    Example: dku recipe add-fold prep1 --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ
    """
    if columns and pattern:
        exit_with_error(
            "Use --columns OR --pattern, not both.",
            code="invalid_argument",
            details=["--columns: explicit list. --pattern: regex match."],
        )
    if not columns and not pattern:
        exit_with_error(
            "Specify --columns or --pattern to select columns to fold.",
            code="invalid_argument",
            details=[
                'Example: dku recipe add-fold RECIPE --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ',
                'Example: dku recipe add-fold RECIPE --pattern ".*-25" --key-column month --value-column sales -P PROJ',
            ],
        )
    if columns:
        col_list = [c.strip() for c in columns.split(",")]
        _add_prepare_step(
            ctx,
            recipe_name,
            project,
            "FoldColumnsByName",
            {
                "columns": col_list,
                "keyColumn": key_column,
                "valueColumn": value_column,
            },
        )
    else:
        _add_prepare_step(
            ctx,
            recipe_name,
            project,
            "FoldColumnsByPattern",
            {
                "columnNamePattern": pattern,
                "columnNameColumn": key_column,
                "columnContentColumn": value_column,
            },
        )


@app.command("add-geopoint")
def add_geopoint(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    lat_column: str = typer.Option(
        ..., "--lat-column", "--lat", help="Latitude column name"
    ),
    lon_column: str = typer.Option(
        ..., "--lon-column", "--lon", help="Longitude column name"
    ),
    output_column: str = typer.Option(
        "geopoint", "--output-column", "-c", help="Output geopoint column name"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a geopoint column from latitude/longitude columns.

    Use instead of manually formatting WKT in Python. Output is a WKT POINT
    in EPSG:4326 (WGS84) that can be used in geo join recipes and map charts.

    Example: dku recipe add-geopoint prep1 --lat-column lat --lon-column lon -P PROJ
    """
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "GeoPointCreator",
        {
            "lat_column": lat_column,
            "lon_column": lon_column,
            "out_column": output_column,
        },
    )


@app.command("add-geodistance")
def add_geodistance(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    from_column: str = typer.Option(
        ..., "--from-column", "--from", help="Source geopoint or geometry column"
    ),
    to_column: str = typer.Option(
        ..., "--to-column", "--to", help="Target geopoint or geometry column"
    ),
    output_column: str = typer.Option(
        "geo_distance", "--output-column", "-c", help="Output distance column name"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Compute distance between two geopoint/geometry columns.

    Use instead of haversine calculations in Python. Both columns must be
    geopoint or geometry type (use add-geopoint first if needed).

    Example: dku recipe add-geodistance prep1 --from origin --to destination -P PROJ
    """
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "GeoDistanceProcessor",
        {
            "input1_column": from_column,
            "input2_column": to_column,
            "output_column": output_column,
        },
    )


# ---------------------------------------------------------------------------
# Visual recipe creation commands (prefer these over Python)
# ---------------------------------------------------------------------------


def _ensure_output_dataset(client, proj, dataset_name: str, project_key: str) -> None:
    """Create a managed output dataset if it doesn't exist (visual recipes need it).

    Prefers 'filesystem_managed' if it allows managed datasets.
    Otherwise discovers the first connection with allowManagedDatasets=True.
    Falls back to 'filesystem_managed' if discovery fails (admin-only API).
    """
    try:
        proj.get_dataset(dataset_name).get_definition()
    except Exception as e:
        if is_not_found_error(e):
            conn_name = "filesystem_managed"
            try:
                conns = client.list_connections()
                # Prefer filesystem_managed — it's the safest default
                if "filesystem_managed" in conns and conns["filesystem_managed"].get(
                    "allowManagedDatasets"
                ):
                    conn_name = "filesystem_managed"
                else:
                    for name, props in conns.items():
                        if props.get("allowManagedDatasets"):
                            conn_name = name
                            break
            except Exception:
                pass  # list_connections is admin-only, fall back
            builder = proj.new_managed_dataset(dataset_name)
            builder.with_store_into(conn_name)
            builder.create()
            info(
                f"Auto-created managed output dataset '{dataset_name}' on connection '{conn_name}' in {project_key}"
            )
            return
        raise


def _auto_apply_schema(proj, recipe_name: str) -> None:
    """Best-effort schema propagation after visual recipe creation."""
    try:
        recipe = proj.get_recipe(recipe_name)
        updates = recipe.compute_schema_updates()
        if updates.any_action_required():
            updates.apply()
            info(f"Auto-applied schema updates for '{recipe_name}'")
    except Exception as exc:
        warn(f"Could not auto-apply schema for '{recipe_name}': {exc}")


@app.command("create-join")
def create_join(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    inputs: list[str] = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input datasets (repeat for multiple: -i ds1 -i ds2)",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    join_key: list[str] = typer.Option(
        None,
        "--join-key",
        "-k",
        help=(
            "Join key: 'col' (same both sides) or 'left=right'. Repeatable. "
            "For multi-input joins (3+ datasets), prefix with join index: '1:col' targets the 2nd join pair. "
            "Unprefixed keys target join 0 (first pair)."
        ),
    ),
    join_type: str = typer.Option(
        "LEFT",
        "--join-type",
        "-j",
        help="Join type: LEFT, INNER, RIGHT, CROSS. Applied to all join pairs. Default: LEFT.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Join recipe. NEVER use Python for joins — use this instead.

    Supports 2+ input datasets in a SINGLE recipe — prefer this over
    cascading join recipes. Pass all datasets with -i: -i ds1 -i ds2 -i ds3.

    Join keys auto-detect from matching column names. For explicit keys,
    use --join-key col (join 0, first pair) and --join-key 1:col (join 1,
    second pair). Format: 'col' (same both sides) or 'left=right'.
    CROSS joins need no keys.
    """
    _VALID_JOIN_TYPES = {"LEFT", "INNER", "RIGHT", "CROSS"}
    project_key = resolve_project(project)
    jt = join_type.upper()
    if jt not in _VALID_JOIN_TYPES:
        exit_with_error(
            f"Invalid join type '{join_type}'. Must be one of: {', '.join(sorted(_VALID_JOIN_TYPES))}",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-join NAME -i ds1 -i ds2 --output-ds out --join-type LEFT -P PROJ"
            ],
        )
    if len(inputs) < 2:
        exit_with_error(
            "Join recipes need at least 2 input datasets.",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-join NAME -i ds1 -i ds2 --output-ds out -P PROJ"
            ],
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("join", recipe_name)
        for ds in inputs:
            builder.with_input(ds)
        builder.with_existing_output(output_ds)
        builder.build()

        recipe_obj = proj.get_recipe(recipe_name)
        join_settings = recipe_obj.get_settings()
        joins = join_settings.raw_joins

        # Newly created join recipes may have an empty joins list.
        # Create the default join structure(s) matching DSS's expected format.
        if not joins:
            for i in range(len(inputs) - 1):
                joins.append({"table1": 0, "table2": i + 1, "type": jt, "on": []})

        # Set join type on all existing join pairs
        for j in joins:
            j["type"] = jt

        # Configure join keys if provided (skip for CROSS joins)
        if join_key and jt != "CROSS":
            import re

            from dataikuapi.dss.recipe import JoinRecipeSettings

            # Parse indexed key specs: "col", "left=right", "1:col", "1:left=right"
            keys_by_idx: dict[int, list[tuple[str, str]]] = {}
            for key_spec in join_key:
                idx = 0
                spec = key_spec
                m = re.match(r"^(\d+):", key_spec)
                if m:
                    idx = int(m.group(1))
                    spec = key_spec[m.end() :]
                if "=" in spec:
                    col1, col2 = spec.split("=", 1)
                else:
                    col1 = col2 = spec
                keys_by_idx.setdefault(idx, []).append((col1.strip(), col2.strip()))

            for idx, key_pairs in keys_by_idx.items():
                if idx >= len(joins):
                    exit_with_error(
                        f"Join index {idx} out of range — recipe has {len(joins)} join pair(s) (0-indexed).",
                        code="invalid_argument",
                        details=[
                            f"With {len(inputs)} inputs, valid join indices are 0..{len(joins) - 1}",
                        ],
                    )
                target_join = joins[idx]
                for col1, col2 in key_pairs:
                    JoinRecipeSettings.add_condition_to_join(
                        target_join,
                        type="EQ",
                        column1=col1,
                        column2=col2,
                    )

            info(f"Join keys: {', '.join(join_key)}")
        elif join_key and jt == "CROSS":
            warn("CROSS join ignores --join-key (no conditions needed)")

        join_settings.save()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created {jt} join recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


_VALID_GEO_OPERATORS = frozenset(
    {"WITHIN_DISTANCE", "BEYOND_DISTANCE", "INTERSECTS", "CONTAINS"}
)

_VALID_GEO_DISTANCE_UNITS = frozenset(
    {"meter", "km", "foot", "yard", "mile", "nautical_mile"}
)


@app.command("create-geojoin")
def create_geojoin(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    inputs: list[str] = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input datasets (exactly 2: -i left_ds -i right_ds)",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    geo_column: list[str] | None = typer.Option(
        None,
        "--geo-column",
        "-g",
        help=(
            "Geo columns from each dataset (repeat 2x: -g left_geo -g right_geo). "
            "Omit to let DSS auto-detect from geopoint/geometry columns."
        ),
    ),
    operator: str = typer.Option(
        "WITHIN_DISTANCE",
        "--operator",
        "--op",
        help="Geo operator: WITHIN_DISTANCE, BEYOND_DISTANCE, INTERSECTS, CONTAINS",
    ),
    distance: float = typer.Option(
        1000,
        "--distance",
        "-d",
        help="Distance threshold (only for WITHIN_DISTANCE / BEYOND_DISTANCE)",
    ),
    distance_unit: str = typer.Option(
        "meter",
        "--distance-unit",
        "-u",
        help="Distance unit: meter, km, foot, yard, mile, nautical_mile",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Geo Join recipe. NEVER use Python haversine — use this instead.

    Joins two datasets using geospatial matching. Both datasets must have
    a geopoint or geometry column (use add-geopoint to create one first).

    Operators:
      WITHIN_DISTANCE  — rows within --distance of each other (default)
      BEYOND_DISTANCE  — rows farther than --distance
      INTERSECTS       — geometries that overlap (no distance needed)
      CONTAINS         — left geometry contains right geometry

    Example: dku recipe create-geojoin geo_step -i stores -i customers \\
      --output-ds nearby --operator WITHIN_DISTANCE --distance 5000 -u meter -P PROJ
    """
    project_key = resolve_project(project)
    op = operator.upper()
    if op not in _VALID_GEO_OPERATORS:
        exit_with_error(
            f"Invalid geo operator '{operator}'. Must be one of: {', '.join(sorted(_VALID_GEO_OPERATORS))}",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-geojoin NAME -i ds1 -i ds2 --output-ds out --operator WITHIN_DISTANCE -P PROJ"
            ],
        )
    du = distance_unit.lower()
    if du not in _VALID_GEO_DISTANCE_UNITS:
        exit_with_error(
            f"Invalid distance unit '{distance_unit}'. Must be one of: {', '.join(sorted(_VALID_GEO_DISTANCE_UNITS))}",
            code="invalid_argument",
        )
    if len(inputs) != 2:
        exit_with_error(
            f"Geo join requires exactly 2 input datasets, got {len(inputs)}.",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-geojoin NAME -i left_ds -i right_ds --output-ds out -P PROJ"
            ],
        )
    if geo_column and len(geo_column) != 2:
        exit_with_error(
            f"--geo-column must be specified exactly twice (left and right), got {len(geo_column)}.",
            code="invalid_argument",
            details=[
                "Use: -g left_geo_col -g right_geo_col",
                "Or omit --geo-column to let DSS auto-detect from geopoint/geometry columns.",
            ],
        )
    if op in ("INTERSECTS", "CONTAINS") and distance != 1000:
        warn(f"{op} ignores --distance (no distance threshold needed)")

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)

        # GeoJoinRecipeCreator exists in dataikuapi but is not wired into
        # DSSProject.new_recipe(). Instantiate directly.
        builder = GeoJoinRecipeCreator(recipe_name, proj)
        for ds in inputs:
            builder.with_input(ds)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure geo join conditions in payload
        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)

        # Geo join stores its config in the joins array, similar to regular join.
        # Each join entry has geoJoin fields for spatial matching.
        joins = payload.get("joins", [])
        if not joins:
            joins = [{"table1": 0, "table2": 1, "on": []}]
            payload["joins"] = joins

        geo_join = joins[0]
        geo_join["geoJoin"] = True
        geo_join["geoOperator"] = op
        if op in ("WITHIN_DISTANCE", "BEYOND_DISTANCE"):
            geo_join["geoDistance"] = distance
            geo_join["geoUnit"] = du

        if geo_column:
            geo_join["geoColumn1"] = geo_column[0]
            geo_join["geoColumn2"] = geo_column[1]

        settings.save()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created geo join recipe '{recipe_name}' ({op}) in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


_VALID_FUZZY_METHODS = frozenset(
    {"LEVENSHTEIN", "JARO_WINKLER", "NORMALIZED_LEVENSHTEIN"}
)


@app.command("create-fuzzy-join")
def create_fuzzy_join(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    inputs: list[str] = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input datasets (exactly 2: -i left_ds -i right_ds)",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    fuzzy_key: list[str] | None = typer.Option(
        None,
        "--fuzzy-key",
        "-f",
        help="Fuzzy match column: 'col' (same both sides) or 'left=right'. Repeatable.",
    ),
    join_key: list[str] | None = typer.Option(
        None,
        "--join-key",
        "-k",
        help="Exact-match key: 'col' (same both sides) or 'left=right'. Repeatable.",
    ),
    max_distance: int = typer.Option(
        1,
        "--max-distance",
        help="Maximum edit distance for fuzzy matching (default: 1)",
    ),
    method: str = typer.Option(
        "LEVENSHTEIN",
        "--method",
        "-m",
        help="Fuzzy method: LEVENSHTEIN, JARO_WINKLER, NORMALIZED_LEVENSHTEIN",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Fuzzy Join recipe for approximate string matching.

    Joins two datasets using approximate (fuzzy) matching on text columns.
    Use for name deduplication, address matching, or linking messy text data.

    Example: dku recipe create-fuzzy-join fuzzy_step -i ds1 -i ds2 \\
      --output-ds matched --fuzzy-key name --max-distance 2 -P PROJ
    """
    project_key = resolve_project(project)
    m = method.upper()
    if m not in _VALID_FUZZY_METHODS:
        exit_with_error(
            f"Invalid fuzzy method '{method}'. Must be one of: {', '.join(sorted(_VALID_FUZZY_METHODS))}",
            code="invalid_argument",
        )
    if len(inputs) != 2:
        exit_with_error(
            f"Fuzzy join requires exactly 2 input datasets, got {len(inputs)}.",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-fuzzy-join NAME -i left_ds -i right_ds --output-ds out -P PROJ"
            ],
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)

        # FuzzyJoinRecipeCreator exists in dataikuapi but is not wired into
        # DSSProject.new_recipe(). Instantiate directly.
        builder = FuzzyJoinRecipeCreator(recipe_name, proj)
        for ds in inputs:
            builder.with_input(ds)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure fuzzy join conditions in payload
        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)

        joins = payload.get("joins", [])
        if not joins:
            joins = [{"table1": 0, "table2": 1, "on": []}]
            payload["joins"] = joins

        fj = joins[0]
        fj["fuzzyJoinMethod"] = m
        fj["fuzzyJoinMaxDistance"] = max_distance

        # Configure fuzzy key conditions
        if fuzzy_key:
            conditions = fj.setdefault("on", [])
            for key_spec in fuzzy_key:
                if "=" in key_spec:
                    col1, col2 = key_spec.split("=", 1)
                else:
                    col1 = col2 = key_spec
                conditions.append(
                    {
                        "column1": {"name": col1.strip(), "table": 0},
                        "column2": {"name": col2.strip(), "table": 1},
                        "type": "FUZZY",
                    }
                )

        # Configure exact-match key conditions
        if join_key:
            conditions = fj.setdefault("on", [])
            for key_spec in join_key:
                if "=" in key_spec:
                    col1, col2 = key_spec.split("=", 1)
                else:
                    col1 = col2 = key_spec
                conditions.append(
                    {
                        "column1": {"name": col1.strip(), "table": 0},
                        "column2": {"name": col2.strip(), "table": 1},
                        "type": "EQ",
                    }
                )

        settings.save()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created fuzzy join recipe '{recipe_name}' ({m}) in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


_VALID_AGGS = frozenset(
    {"sum", "avg", "min", "max", "count", "count_distinct", "concat", "stddev"}
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
        help="Aggregation: 'col:func1,func2'. Functions: sum, avg, min, max, count, count_distinct, concat, stddev. Repeatable.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Group (aggregate) recipe. NEVER use Python for aggregations — use this instead.

    Use --agg to configure aggregation functions: --agg 'amount:sum,avg' --agg 'id:count'.
    Without --agg, defaults to COUNT per group. Use -k for group keys (repeatable: -k col1 -k col2).
    """
    project_key = resolve_project(project)
    # Validate --agg format early (before any API calls)
    if agg:
        for agg_spec in agg:
            if ":" not in agg_spec:
                exit_with_error(
                    f"Invalid --agg format: '{agg_spec}'.",
                    code="invalid_argument",
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
                    code="invalid_argument",
                    details=[f"Valid: {', '.join(sorted(_VALID_AGGS))}"],
                )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("grouping", recipe_name)
        builder.with_input(input_ds)
        if group_key:
            builder.with_group_key(group_key[0])
        builder.with_existing_output(output_ds)
        builder.build()

        # Post-build: add extra group keys and/or aggregation config
        needs_settings = (group_key and len(group_key) > 1) or agg
        if needs_settings:
            recipe_obj = proj.get_recipe(recipe_name)
            group_settings = recipe_obj.get_settings()
            if group_key and len(group_key) > 1:
                for extra_key in group_key[1:]:
                    group_settings.add_grouping_key(extra_key)
            if agg:
                for agg_spec in agg:
                    col, funcs_str = agg_spec.split(":", 1)
                    funcs = {f.strip().lower() for f in funcs_str.split(",")}
                    # Use set_column_aggregations for most flags, then patch avg
                    # directly — dataikuapi has a bug where avg= is accepted but
                    # never written to the settings dict.
                    cs = group_settings.set_column_aggregations(
                        col.strip(),
                        **{f: (f in funcs) for f in _VALID_AGGS},
                    )
                    cs["avg"] = "avg" in funcs
                info(f"Aggregations: {', '.join(agg)}")
            group_settings.save()

        _auto_apply_schema(proj, recipe_name)
        success(f"Created group recipe '{recipe_name}' in {project_key}")
        if group_key:
            info(f"Grouped by: {', '.join(group_key)}")
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
        help="Input datasets to stack (repeat: -i ds1 -i ds2)",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Stack recipe. Vertically concatenates datasets (UNION).

    Use this instead of pd.concat in Python.
    """
    project_key = resolve_project(project)
    if len(inputs) < 2:
        exit_with_error(
            "Stack recipes need at least 2 input datasets.",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-stack NAME -i ds1 -i ds2 --output-ds out -P PROJ"
            ],
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("vstack", recipe_name)
        for ds in inputs:
            builder.with_input(ds)
        builder.with_existing_output(output_ds)
        builder.build()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created stack recipe '{recipe_name}' in {project_key}")
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
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Distinct recipe. Deduplicates rows.

    Use this instead of df.drop_duplicates() in Python.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("distinct", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created distinct recipe '{recipe_name}' in {project_key}")
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
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Sort recipe.

    Use this instead of df.sort_values() in Python.
    Use --sort-col to configure sort columns at creation time.

    Example: dku recipe create-sort my_sort -i data --output-ds sorted --sort-col price:desc -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("sort", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()

        if sort_col:
            recipe_obj = proj.get_recipe(recipe_name)
            sort_settings = recipe_obj.get_settings()
            try:
                sort_settings.clear_sorting_keys()
            except (AttributeError, TypeError):
                pass
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
            sort_settings.save()
            info(f"Sort columns: {', '.join(sort_col)}")

        _auto_apply_schema(proj, recipe_name)
        success(f"Created sort recipe '{recipe_name}' in {project_key}")
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
        None,
        "--filter-formula",
        "--filter",
        "-f",
        help="DSS formula filter expression (e.g. 'age > 30')",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Sample/Filter recipe. Filters rows by condition.

    Use this instead of df[df.col > X] in Python. Pass --filter-formula to
    configure the filter expression inline, or configure in the DSS UI / via
    set-definition.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("sampling", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()
        if filter_formula:
            recipe_obj = proj.get_recipe(recipe_name)
            filter_settings = recipe_obj.get_settings()
            payload = _get_recipe_payload(filter_settings)
            payload["filterExpression"] = filter_formula
            payload["samplingMethod"] = "FULL"
            filter_settings.save()
            info(f"Filter: {filter_formula}")
        _auto_apply_schema(proj, recipe_name)
        success(f"Created filter recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


_VALID_WINDOW_TYPES = frozenset(
    {
        "lag",
        "lead",
        "rank",
        "denseRank",
        "rowNumber",
        "sum",
        "avg",
        "min",
        "max",
        "count",
        "first",
        "last",
        "stddev",
        "concat",
    }
)
# These are top-level booleans in the DSS payload, not per-column
_TOP_LEVEL_WINDOW_TYPES = frozenset({"rank", "denseRank", "rowNumber"})
# These are per-column boolean flags in the values[] array
_COLUMN_WINDOW_TYPES = frozenset(
    {
        "lag",
        "lead",
        "sum",
        "avg",
        "min",
        "max",
        "count",
        "countDistinct",
        "first",
        "last",
        "stddev",
        "concat",
    }
)


def _parse_compute_specs(specs: list[str]) -> list[dict]:
    """Parse --compute specs like 'TYPE:column:output' into computation dicts.

    For rank/denseRank/rowNumber, source column is optional: 'rank::output' or 'rank:output'.
    For other types, source column is required: 'lag:price:price_lag1'.
    """
    parsed = []
    for comp_spec in specs:
        parts = comp_spec.split(":")
        if len(parts) == 2:
            # TYPE:output_column (no source column)
            comp_type, output_col = parts
            source_col = None
        elif len(parts) == 3:
            # TYPE:column:output_column (empty column OK for rank types)
            comp_type = parts[0]
            source_col = parts[1] or None
            output_col = parts[2]
        else:
            exit_with_error(
                f"Invalid --compute format: '{comp_spec}'.",
                code="invalid_argument",
                details=[
                    "Expected: 'TYPE:column:output_column' or 'TYPE::output_column' (for rank/rowNumber).",
                    "Examples: --compute 'lag:price:price_lag1' --compute 'rank::row_rank'",
                ],
            )
        if comp_type not in _VALID_WINDOW_TYPES:
            exit_with_error(
                f"Unknown window computation type: '{comp_type}'.",
                code="invalid_argument",
                details=[f"Valid types: {', '.join(sorted(_VALID_WINDOW_TYPES))}"],
            )
        if comp_type not in _TOP_LEVEL_WINDOW_TYPES and not source_col:
            exit_with_error(
                f"Computation type '{comp_type}' requires a source column.",
                code="invalid_argument",
                details=[f"Use: --compute '{comp_type}:COLUMN:OUTPUT_COLUMN'"],
            )
        entry: dict = {"type": comp_type, "outputColumn": output_col}
        if source_col:
            entry["column"] = source_col
        parsed.append(entry)
    return parsed


def _apply_window_computations(payload: dict, computations: list[dict]) -> None:
    """Apply parsed --compute specs to a Window recipe obj_payload.

    DSS Window recipes use two mechanisms:
    - Top-level booleans: rowNumber, rank, denseRank (global, not per-column)
    - values[] array: per-column flags like lag, lead, sum, avg, etc.
    """
    values = payload.setdefault("values", [])

    for comp in computations:
        comp_type = comp["type"]
        if comp_type in _TOP_LEVEL_WINDOW_TYPES:
            # Enable top-level flag (e.g., payload["rowNumber"] = True)
            payload[comp_type] = True
        else:
            # Find or create the column entry in values[]
            source_col = comp["column"]
            col_entry = None
            for v in values:
                if v.get("column") == source_col:
                    col_entry = v
                    break
            if col_entry is None:
                col_entry = {"column": source_col, "value": False}
                values.append(col_entry)
            # Enable the computation type flag
            col_entry[comp_type] = True


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
            "Window computation. Format: TYPE:column:output_column. "
            "Column optional for rank/denseRank/rowNumber (use TYPE::output). "
            "Types: lag, lead, rank, denseRank, rowNumber, sum, avg, min, max, count, first, last. "
            "Repeatable."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Window recipe. Computes window/analytic functions (rank, lag, cumsum).

    Use this instead of df.groupby().transform() in Python.
    Use --partition-key for PARTITION BY, --order-key for ORDER BY,
    and --compute for window functions.

    Example: dku recipe create-window ranked -i data --output-ds ranked -k stock --order-key date --compute 'rowNumber::rn' -P PROJ
    """
    project_key = resolve_project(project)
    # Validate --compute format early (before any API calls)
    parsed_computations = _parse_compute_specs(compute) if compute else []
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("window", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure partition/order keys and computations (WindowRecipeSettings has no helpers)
        if partition_key or order_key or parsed_computations:
            recipe_obj = proj.get_recipe(recipe_name)
            win_settings = recipe_obj.get_settings()
            payload = _get_recipe_payload(win_settings)
            if partition_key:
                payload["partitioningColumns"] = [
                    {"column": col} for col in partition_key
                ]
                info(f"Partition by: {', '.join(partition_key)}")
            if order_key:
                payload["orders"] = _parse_order_specs(order_key)
                info(f"Order by: {', '.join(order_key)}")
            if parsed_computations:
                _apply_window_computations(payload, parsed_computations)
                info(
                    f"Computations: {', '.join(c['type'] for c in parsed_computations)}"
                )
            win_settings.save()

        _auto_apply_schema(proj, recipe_name)
        success(f"Created window recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-split")
def create_split(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", "--input-ds", help="Input dataset name"
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="First output dataset name"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Split recipe. Splits data into multiple datasets by condition.

    Add more outputs via add-output. Configure split conditions in the DSS UI
    or via set-definition.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("split", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created split recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


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
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Top N recipe. Returns the top/bottom N rows per group.

    Use this instead of df.nlargest() or df.head() in Python.
    Use --sort-col or --rank-by for the ordering column, --n for how many rows, and
    --partition-key for top N per group.

    Example: dku recipe create-topn top10 -i sales --output-ds top10 --n 10 --sort-col revenue:desc -P PROJ
    """
    project_key = resolve_project(project)
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
        payload["topN"] = n
        payload["firstRows"] = n
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
        topn_settings.save()

        _auto_apply_schema(proj, recipe_name)
        success(f"Created topn recipe '{recipe_name}' (top {n}) in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


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
    agg_type: str | None = typer.Option(
        None,
        "--agg-type",
        help="Aggregation type for pivot cells: SUM, AVG, MIN, MAX, COUNT, COUNT_DISTINCT, CONCAT, STDDEV.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Pivot recipe (long→wide). NEVER use df.pivot_table() in Python.

    Transposes rows into columns: each unique value in --column-key becomes
    a new column, filled with aggregated --value-column values.

    Example: dku recipe create-pivot piv -i sales --output-ds sales_wide --row-key product --column-key month --value-column revenue --agg-type SUM -P PROJ
    """
    _VALID_PIVOT_AGGS = frozenset(
        {"SUM", "AVG", "MIN", "MAX", "COUNT", "COUNT_DISTINCT", "CONCAT", "STDDEV"}
    )
    if agg_type and agg_type.upper() not in _VALID_PIVOT_AGGS:
        exit_with_error(
            f"Unknown aggregation type: '{agg_type}'.",
            code="invalid_argument",
            details=[f"Valid: {', '.join(sorted(_VALID_PIVOT_AGGS))}"],
        )
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("pivot", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure pivot dimensions and aggregation.
        # DSS stores pivot config in payload.explicitIdentifiers (row keys) and
        # payload.pivots[0] (column key, value columns, aggregation functions).
        if row_key or column_key or value_column or agg_type:
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
            if value_column:
                agg_fn = agg_type.upper() if agg_type else "SUM"
                pivot["valueColumns"] = [{"column": value_column, "function": agg_fn}]
            elif agg_type:
                # agg_type without value_column — set on existing valueColumns
                for vc in pivot.get("valueColumns", []):
                    vc["function"] = agg_type.upper()
            settings.save()
            info(
                f"Pivot config: row={row_key}, column={column_key}, value={value_column}, agg={agg_type}"
            )

        _auto_apply_schema(proj, recipe_name)
        success(f"Created pivot recipe '{recipe_name}' in {project_key}")
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
    method: str = typer.Option(
        "RANDOM_FIXED_NB",
        "--method",
        "-m",
        help="Sampling method: RANDOM_FIXED_NB, RANDOM_FIXED_RATIO, HEAD_SEQUENTIAL, STRATIFIED, CLASS_REBALANCE",
    ),
    size: int | None = typer.Option(
        None, "--size", "-n", help="Sample size (for RANDOM_FIXED_NB)"
    ),
    ratio: float | None = typer.Option(
        None, "--ratio", help="Sample ratio 0.0-1.0 (for RANDOM_FIXED_RATIO)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Sampling recipe. Takes a random, stratified, or head sample.

    Use this instead of df.sample() in Python. For row filtering by condition,
    use create-filter instead.

    Example: dku recipe create-sampling sample_1k -i big_data --output-ds sample --size 1000 -P PROJ
    """
    project_key = resolve_project(project)
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
        selection["samplingMethod"] = method.upper()
        if size is not None:
            selection["maxRecords"] = size
        if ratio is not None:
            selection["targetRatio"] = ratio
        settings.save()

        _auto_apply_schema(proj, recipe_name)
        success(f"Created sampling recipe '{recipe_name}' ({method}) in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# GenAI recipe creation commands
# ---------------------------------------------------------------------------


@app.command("create-embed")
def create_embed(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(..., "--input", "-i", help="Input dataset name"),
    output_kb: str = typer.Option(
        ..., "--output-kb", help="Output knowledge bank name or ID"
    ),
    embedding_llm: str = typer.Option(
        ...,
        "--embedding-llm",
        help="Embedding LLM ID (e.g. openai:text-embedding-3-small)",
    ),
    vector_store_type: str = typer.Option(
        "CHROMA", "--vector-store-type", help="Vector store type (default: CHROMA)"
    ),
    embed_column: str = typer.Option(
        None,
        "--embed-column",
        help="Column name to embed (required for dataset embedding)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Embed Dataset recipe (embeds text columns into a Knowledge Bank).

    Use --embed-column to set which text column to embed. If omitted, you must
    configure the embedding column via set-definition before building the KB.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("nlp_llm_rag_embedding", recipe_name)
        builder.with_input(input_ds)

        # Check if KB already exists to avoid creating duplicates
        kb_exists = False
        try:
            proj.get_knowledge_bank(output_kb)
            kb_exists = True
        except Exception as exc:
            if not is_not_found_error(exc):
                raise  # Re-raise auth/network errors; only swallow not-found

        if kb_exists:
            info(f"Using existing knowledge bank '{output_kb}'")
        builder.with_output_knowledge_bank(output_kb, embedding_llm, vector_store_type)

        builder.build()

        # Set embedding column if provided
        if embed_column:
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            payload = _get_recipe_payload(settings)
            payload["knowledgeColumn"] = embed_column
            settings.save()
            info(f"Embedding column set to '{embed_column}'")
        else:
            warn(
                "No --embed-column specified. Set the embedding column via "
                "'dku recipe set-definition' before building the knowledge bank."
            )

        success(f"Created embed recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("create-embed-docs")
def create_embed_docs(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", help="Input dataset with document columns"
    ),
    output_kb: str = typer.Option(
        ..., "--output-kb", help="Output knowledge bank name"
    ),
    embedding_llm: str = typer.Option(..., "--embedding-llm", help="Embedding LLM ID"),
    vlm: str = typer.Option(
        None, "--vlm", help="Vision LLM ID for document understanding"
    ),
    vector_store_type: str = typer.Option(
        "CHROMA", "--vector-store-type", help="Vector store type (default: CHROMA)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Embed Documents recipe (extracts and embeds document content into a Knowledge Bank)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("embed_documents", recipe_name)
        builder.with_input(input_ds)
        if vlm:
            builder.with_vlm(vlm)
        builder.with_output_knowledge_bank(output_kb, embedding_llm, vector_store_type)
        builder.build()
        success(f"Created embed-docs recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("create-extract")
def create_extract(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", help="Input dataset with documents"
    ),
    output_ds: str = typer.Option(..., "--output-ds", help="Output dataset name"),
    vlm: str = typer.Option(..., "--vlm", help="Vision LLM ID for content extraction"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Extract Content recipe (extracts structured content from documents using a VLM)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("extract_content", recipe_name)
        builder.with_input(input_ds)
        builder.with_vlm(vlm)
        builder.with_existing_output(output_ds)
        builder.build()
        success(f"Created extract recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("create-llm-eval")
def create_llm_eval(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", help="Input dataset with LLM outputs to evaluate"
    ),
    eval_store: str = typer.Option(..., "--eval-store", help="LLM evaluation store ID"),
    output_ds: str = typer.Option(
        None, "--output-ds", help="Output scored dataset name"
    ),
    output_metrics: str = typer.Option(
        None, "--output-metrics", help="Metrics dataset name"
    ),
    task_type: str = typer.Option(
        None, "--task-type", help="Task type (e.g. QUESTION_ANSWERING, SUMMARIZATION)"
    ),
    metrics: str = typer.Option(
        None,
        "--metrics",
        help="Comma-separated metrics (e.g. answerRelevancy,faithfulness)",
    ),
    input_col: str = typer.Option(
        None, "--input-col", help="Input/question column name"
    ),
    output_col: str = typer.Option(
        None, "--output-col", help="LLM output/answer column name"
    ),
    ground_truth_col: str = typer.Option(
        None, "--ground-truth-col", help="Ground truth column name"
    ),
    context_col: str = typer.Option(None, "--context-col", help="Context column name"),
    completion_llm: str = typer.Option(
        None, "--completion-llm", help="Completion LLM ID for evaluation logic"
    ),
    embedding_llm: str = typer.Option(
        None, "--embedding-llm", help="Embedding LLM ID for similarity metrics"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an LLM Evaluation recipe (evaluates LLM outputs with metrics like relevancy, faithfulness)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        if output_ds:
            _require_existing_dataset(proj, output_ds, project_key, "Output")
        if output_metrics:
            _require_existing_dataset(
                proj, output_metrics, project_key, "Metrics output"
            )
        try:
            recipe = _create_eval_recipe_raw(
                client,
                proj,
                recipe_name,
                "nlp_llm_evaluation",
                input_ds,
                eval_store,
                output_ds,
                output_metrics,
            )
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "does not exist" in msg:
                raise  # Let handle_api_error process not-found errors
            if "eval" in msg or "evaluation" in msg or "store" in msg:
                exit_with_error(
                    f"Failed to create LLM eval recipe — eval store '{eval_store}' may not exist.",
                    code="eval_store_not_found",
                    details=[
                        "Evaluation stores must be created in the DSS UI before use.",
                        "Verify the eval store ID in: Administration > Evaluation Stores",
                    ],
                )
            raise  # Re-raise network/auth/other errors unchanged

        # Post-creation payload configuration
        settings = recipe.get_settings()
        payload = _get_recipe_payload(settings)
        if task_type:
            payload["taskType"] = task_type
        if metrics:
            payload["metrics"] = [m.strip() for m in metrics.split(",")]
        if input_col:
            payload["inputColumnName"] = input_col
        if output_col:
            payload["outputColumnName"] = output_col
        if ground_truth_col:
            payload["groundTruthColumnName"] = ground_truth_col
        if context_col:
            payload["contextColumnName"] = context_col
        if completion_llm:
            payload["completionLLMId"] = completion_llm
        if embedding_llm:
            payload["embeddingLLMId"] = embedding_llm
        if any(
            [
                task_type,
                metrics,
                input_col,
                output_col,
                ground_truth_col,
                context_col,
                completion_llm,
                embedding_llm,
            ]
        ):
            settings.save()

        success(f"Created LLM eval recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-agent-eval")
def create_agent_eval(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", help="Input dataset with agent outputs"
    ),
    eval_store: str = typer.Option(
        ..., "--eval-store", help="Agent evaluation store ID"
    ),
    output_ds: str = typer.Option(
        None, "--output-ds", help="Output scored dataset name"
    ),
    output_metrics: str = typer.Option(
        None, "--output-metrics", help="Metrics dataset name"
    ),
    metrics: str = typer.Option(
        None,
        "--metrics",
        help="Comma-separated metrics (e.g. toolCallExactMatch,agentGoalAccuracyWithoutReference)",
    ),
    completion_llm: str = typer.Option(
        None, "--completion-llm", help="Completion LLM ID"
    ),
    embedding_llm: str = typer.Option(None, "--embedding-llm", help="Embedding LLM ID"),
    input_format: str = typer.Option(
        "AGENT_EXECUTION",
        "--input-format",
        help="Input format: AGENT_EXECUTION or PROMPT_RECIPE",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Agent Evaluation recipe (evaluates agent tool-calling accuracy)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        if output_ds:
            _require_existing_dataset(proj, output_ds, project_key, "Output")
        if output_metrics:
            _require_existing_dataset(
                proj, output_metrics, project_key, "Metrics output"
            )
        try:
            recipe = _create_eval_recipe_raw(
                client,
                proj,
                recipe_name,
                "nlp_agent_evaluation",
                input_ds,
                eval_store,
                output_ds,
                output_metrics,
            )
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "does not exist" in msg:
                raise  # Let handle_api_error process not-found errors
            if "eval" in msg or "evaluation" in msg or "store" in msg:
                exit_with_error(
                    f"Failed to create agent eval recipe — eval store '{eval_store}' may not exist.",
                    code="eval_store_not_found",
                    details=[
                        "Evaluation stores must be created in the DSS UI before use.",
                        "Verify the eval store ID in: Administration > Evaluation Stores",
                    ],
                )
            raise  # Re-raise network/auth/other errors unchanged

        # Post-creation payload configuration
        settings = recipe.get_settings()
        payload = _get_recipe_payload(settings)
        payload["inputFormat"] = input_format
        if metrics:
            payload["metrics"] = [m.strip() for m in metrics.split(",")]
        if completion_llm:
            payload["completionLLMId"] = completion_llm
        if embedding_llm:
            payload["embeddingLLMId"] = embedding_llm
        settings.save()

        success(f"Created agent eval recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

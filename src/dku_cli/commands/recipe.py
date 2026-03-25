"""dku recipe — list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output, plus GenAI recipe creation."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer

from dku_cli.errors import (
    exit_with_error,
    handle_api_error,
    is_already_exists_error,
    is_not_found_error,
)
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
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
    }
)


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
    payload = settings.obj_payload
    if payload is None:
        payload = {}
        settings.obj_payload = payload
    return payload


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
        help="Recipe type: python, sql, join, group, sort, distinct, topn, window, stack, split, prepare, filter, sync",
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
        help="Output dataset name (auto-created for code recipes)",
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
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe(type_name, recipe_name)
        builder.with_input(input_ds)
        # CodeRecipeCreator (python, sql_script, etc.) only has with_output(),
        # while visual recipe creators have with_existing_output().
        if hasattr(builder, "with_existing_output"):
            builder.with_existing_output(output_ds)
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
                    f"Delete it first: dku dataset delete {output_ds} -P {project_key} --yes",
                    "Or use a different --output-ds name.",
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
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Definition JSON (string, @file.json, or '-' for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the definition of a recipe from JSON."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        new_def = read_json_input(definition)
        raw = settings.get_recipe_raw_definition()
        raw.update(new_def)
        settings.save()
        success(f"Updated definition for recipe '{recipe_name}'")
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
# Visual recipe creation commands (prefer these over Python)
# ---------------------------------------------------------------------------


def _ensure_output_dataset(client, proj, dataset_name: str, project_key: str) -> None:
    """Create a managed output dataset if it doesn't exist (visual recipes need it).

    Discovers the first connection with allowManagedDatasets=True.
    Falls back to 'filesystem_managed' if discovery fails (admin-only API).
    """
    try:
        proj.get_dataset(dataset_name).get_definition()
    except Exception as e:
        if is_not_found_error(e):
            conn_name = "filesystem_managed"
            try:
                conns = client.list_connections()
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
                f"Auto-created managed output dataset '{dataset_name}' on '{conn_name}' in {project_key}"
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
        help="Join key: 'col' (same name both sides) or 'left=right'. Repeatable.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Join recipe. NEVER use Python for joins — use this instead.

    Join keys: auto-detected from matching column names, or set explicitly
    with --join-key. Use --join-key col (same name both sides) or
    --join-key left_col=right_col (different names). Repeatable for composite keys.
    """
    project_key = resolve_project(project)
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

        # Configure join keys if provided
        if join_key:
            from dataikuapi.dss.recipe import JoinRecipeSettings

            recipe_obj = proj.get_recipe(recipe_name)
            join_settings = recipe_obj.get_settings()
            joins = join_settings.raw_joins
            if joins:
                target_join = joins[0]
                for key_spec in join_key:
                    if "=" in key_spec:
                        col1, col2 = key_spec.split("=", 1)
                    else:
                        col1 = col2 = key_spec
                    JoinRecipeSettings.add_condition_to_join(
                        target_join,
                        type="EQ",
                        column1=col1.strip(),
                        column2=col2.strip(),
                    )
                join_settings.save()
                info(f"Join keys: {', '.join(join_key)}")
            else:
                warn("No joins found in recipe settings — join keys not applied")

        _auto_apply_schema(proj, recipe_name)
        success(f"Created join recipe '{recipe_name}' in {project_key}")
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
    group_key: str = typer.Option(
        None,
        "--group-key",
        "-k",
        help="Column to group by (add more via set-definition)",
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
    Without --agg, defaults to COUNT per group. Use -k for the group key.
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
            builder.with_group_key(group_key)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure aggregation functions if provided
        if agg:
            recipe_obj = proj.get_recipe(recipe_name)
            group_settings = recipe_obj.get_settings()
            for agg_spec in agg:
                col, funcs_str = agg_spec.split(":", 1)
                funcs = {f.strip().lower() for f in funcs_str.split(",")}
                group_settings.set_column_aggregations(
                    col.strip(),
                    **{f: (f in funcs) for f in _VALID_AGGS},
                )
            group_settings.save()
            info(f"Aggregations: {', '.join(agg)}")

        _auto_apply_schema(proj, recipe_name)
        success(f"Created group recipe '{recipe_name}' in {project_key}")
        if group_key:
            info(f"Grouped by: {group_key}")
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
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Sort recipe.

    Use this instead of df.sort_values() in Python.
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
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Sample/Filter recipe. Filters rows by condition.

    Use this instead of df[df.col > X] in Python. Configure the filter
    condition in the DSS UI or via set-definition.
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
        _auto_apply_schema(proj, recipe_name)
        success(f"Created filter recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


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
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Window recipe. Computes window/analytic functions (rank, lag, cumsum).

    Use this instead of df.groupby().transform() in Python.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("window", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created window recipe '{recipe_name}' in {project_key}")
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
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Top N recipe. Returns the top/bottom N rows.

    Use this instead of df.nlargest() or df.head() in Python.
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
        _auto_apply_schema(proj, recipe_name)
        success(f"Created topn recipe '{recipe_name}' in {project_key}")
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
        ..., "--output-kb", help="Output knowledge bank name"
    ),
    embedding_llm: str = typer.Option(
        ...,
        "--embedding-llm",
        help="Embedding LLM ID (e.g. openai:text-embedding-3-small)",
    ),
    vector_store_type: str = typer.Option(
        "CHROMA", "--vector-store-type", help="Vector store type (default: CHROMA)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Embed Dataset recipe (embeds text columns into a Knowledge Bank)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("nlp_llm_rag_embedding", recipe_name)
        builder.with_input(input_ds)
        builder.with_output_knowledge_bank(output_kb, embedding_llm, vector_store_type)
        builder.build()
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

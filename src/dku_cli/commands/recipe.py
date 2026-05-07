"""dku recipe — list, get, get-definition, run, create, delete, set-code, get-code, set-definition, add-input, add-output, rename, status, plus GenAI recipe creation."""

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
    resolve_recipe_input_ref,
    resolve_saved_model,
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

# Code recipe types that support creation without an input dataset (data generation use case).
_INPUT_OPTIONAL_TYPES = frozenset(
    {"python", "r", "shell", "pyspark", "cpython", "sparkr"}
)

# Visual recipe types routed via `with_existing_output()` in the generic
# `dku recipe create` path. sync and sql_query inherit
# SingleOutputRecipeCreator.with_new_output(name, connection, ...) and
# auto-create the output on the target connection, so they're excluded.
_SCORING_RECIPE_TYPES = frozenset(
    {
        "prediction_scoring",
        "clustering_scoring",
        "evaluation",
        "standalone_evaluation",
    }
)

_VISUAL_RECIPE_TYPES = frozenset(
    {
        "join",
        "group",
        "sort",
        "distinct",
        "topn",
        "window",
        "stack",
        "split",
        "shaker",
        "prepare",
        "filter",
        "pivot",
        "sampling",
        "sample",
        "geojoin",
        "fuzzyjoin",
    }
)


def _is_plugin_recipe_type(type_name: str) -> bool:
    """Plugin recipe types follow the pattern CustomCode_<recipeComponentId>."""
    return type_name.startswith("CustomCode_") and len(type_name) > len("CustomCode_")


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


def _get_recipe_or_exit(proj, recipe_name: str, project_key: str):
    """Return a recipe object or exit with prescriptive guidance when missing.

    proj.get_recipe() is lazy — it returns a handle without contacting DSS. The
    existence check happens on the first call that hits the API (usually
    get_settings()), which raises KeyError('recipe') when the recipe doesn't
    exist because dataikuapi does data["recipe"]["type"] unchecked. We force
    that check up front so the error is prescriptive instead of a raw KeyError.
    """
    recipe = proj.get_recipe(recipe_name)
    try:
        recipe.get_settings()
    except Exception as e:
        if is_not_found_error(e) or str(e).strip("'") == "recipe":
            exit_with_error(
                f"Recipe '{recipe_name}' not found in project '{project_key}'.",
                code="not_found",
                status=3,
                details=[
                    f"List recipes: dku recipe list -P {project_key}",
                    f"Inspect the project flow: dku project inspect {project_key} -o json",
                ],
            )
        raise
    return recipe


def _create_eval_recipe(
    proj,
    recipe_name: str,
    recipe_type: str,
    input_ds: str,
    eval_store: str,
    output_ds: str | None,
    output_metrics: str | None,
):
    """Create an LLM or Agent evaluation recipe using the public dataikuapi builder."""
    builder = proj.new_recipe(recipe_type, recipe_name)
    builder.with_input(input_ds)
    builder.with_output_evaluation_store(eval_store)
    if output_ds:
        builder.with_output(output_ds)
    if output_metrics:
        builder.with_output_metrics(output_metrics)
    return builder.build()


# Recipe types whose payload is raw source text (Python / SQL / R / shell),
# not a JSON object. For these, `obj_payload` raises a JSON decode error.
_TEXT_PAYLOAD_RECIPE_TYPES = frozenset(
    {
        "python",
        "r",
        "shell",
        "sql_query",
        "sql_script",
        "spark_sql_query",
        "pyspark",
        "sparkr",
        "spark_scala",
        "cpython",
    }
)


def _is_text_payload_recipe(settings) -> bool:
    """True if the recipe's payload is raw code text, not a JSON object."""
    try:
        rtype = settings.get_recipe_raw_definition().get("type", "")
    except Exception:
        return False
    return rtype in _TEXT_PAYLOAD_RECIPE_TYPES


def _get_text_payload(settings) -> str:
    """Read the raw string payload of a code recipe (sql_query, python, etc.)."""
    # dataikuapi stores the string payload in _str_payload; obj_payload getter
    # tries to json.loads it, which crashes on SQL / code recipes.
    if getattr(settings, "_str_payload", None) is not None:
        return settings._str_payload
    # Fallback: the data dict may hold it under "payload"
    data = getattr(settings, "data", None)
    if isinstance(data, dict) and isinstance(data.get("payload"), str):
        return data["payload"]
    return ""


def _get_recipe_payload(settings) -> dict:
    """Get or init the recipe payload, handling read-only obj_payload property.

    For code recipes (sql_query, python, etc.), the payload is raw source text,
    not a dict — callers should use `_get_text_payload` instead. This helper
    is only for visual recipes whose payload is JSON.
    """
    try:
        payload = settings.obj_payload
        if payload is not None:
            return payload
    except (AttributeError, TypeError, KeyError, json.JSONDecodeError, ValueError):
        pass

    # obj_payload is read-only in real dataikuapi. Try to seed an empty JSON
    # payload via str_payload (the public setter), then re-read obj_payload.
    if hasattr(settings, "str_payload"):
        try:
            settings.str_payload = "{}"
            seeded = settings.obj_payload
            if seeded is not None:
                return seeded
        except (AttributeError, TypeError, ValueError):
            pass

    # Fall through to raw_params (engine settings, etc.) — used by some recipe
    # types that store config there instead of in payload.
    if hasattr(settings, "raw_params"):
        try:
            settings.raw_params.setdefault("payload", {})
            return settings.raw_params["payload"]
        except (KeyError, TypeError, AttributeError):
            pass

    # Last resort: manipulate the raw recipe definition dict
    raw = settings.get_recipe_raw_definition()
    raw.setdefault("params", {}).setdefault("payload", {})
    return raw["params"]["payload"]


def _deep_merge_dict(base: dict, patch: dict) -> dict:
    """Recursively merge *patch* into *base*. Non-dict values in *patch* replace *base*."""
    merged = dict(base)
    for key, value in patch.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_pipeline_filter(expression: str) -> dict:
    """Construct a preFilter/postFilter dict from a GREL expression.

    DSS evaluates the top-level ``expression`` field when ``uiData.mode == "CUSTOM"``;
    placing the expression only inside ``uiData`` makes DSS fall through to the
    empty ``conditions[]`` array and silently match all rows. See
    ``dataiku/references/visual-conditions.md`` § Formula Mode for the canonical
    shape the DSS UI saves.
    """
    return {
        "enabled": True,
        "distinct": False,
        "uiData": {
            "mode": "CUSTOM",
            "$latestOperator": "&&",
            "$filterOptions": "CUSTOM",
            "conditions": [],
        },
        "expression": expression,
    }


def _parse_computed_cols(specs: list[str] | None) -> list[dict]:
    """Parse --computed-col 'name=expr[:type]' specs into payload entries.

    Default mode is GREL; default type is string. Pass type via the trailing
    ':TYPE' suffix (string, bigint, double, boolean, date, ...).
    """
    out: list[dict] = []
    if not specs:
        return out
    for spec in specs:
        if "=" not in spec:
            from dku_cli.errors import exit_with_error

            exit_with_error(
                f"Invalid --computed-col '{spec}'. Expected 'name=expr[:type]'.",
                code="invalid_argument",
            )
        name, rest = spec.split("=", 1)
        col_type = "string"
        expr = rest
        if ":" in rest:
            # Allow ':' inside the expression by anchoring the type-suffix to the
            # tail when its value is in a known set.
            tail_expr, tail_type = rest.rsplit(":", 1)
            if tail_type.strip().lower() in {
                "string",
                "bigint",
                "double",
                "float",
                "int",
                "boolean",
                "date",
                "tinyint",
                "smallint",
                "decimal",
            }:
                expr = tail_expr
                col_type = tail_type.strip()
        out.append(
            {"mode": "GREL", "name": name.strip(), "expr": expr, "type": col_type}
        )
    return out


def _parse_renames(specs: list[str] | None) -> dict[str, str]:
    """Parse --rename 'SRC:DST' specs into a {src: dst} map.

    Used for outputColumnNameOverrides — replaces a downstream Prepare
    add-rename step on visual recipes that auto-name aggregate / window
    output columns.
    """
    out: dict[str, str] = {}
    if not specs:
        return out
    from dku_cli.errors import exit_with_error

    for spec in specs:
        if ":" not in spec:
            exit_with_error(
                f"Invalid --rename '{spec}'. Expected 'SRC:DST'.",
                code="invalid_argument",
            )
        src, dst = spec.split(":", 1)
        out[src.strip()] = dst.strip()
    return out


_VALID_ENGINE_TYPES = frozenset({"DSS", "SQL", "SPARK_SQL", "IMPALA", "HIVE"})


def _validate_engine_type(engine: str | None) -> str | None:
    """Validate --engine value. Returns the upper-cased value or None."""
    if engine is None:
        return None
    eu = engine.upper()
    if eu not in _VALID_ENGINE_TYPES:
        exit_with_error(
            f"Unknown --engine: '{engine}'.",
            code="invalid_argument",
            details=[f"Valid: {', '.join(sorted(_VALID_ENGINE_TYPES))}"],
        )
    return eu


def _apply_engine_type(payload: dict, engine: str | None) -> dict:
    """Set payload.engineType — the top-level engine selector for visual recipes.

    Distinct from engineParams.<engine>.executionEngine. Setting only one of
    the two leaves DSS in an inconsistent state — engineType wins. Defaults
    to DSS when a recipe is created via the SDK; pass --engine SQL to push
    down to Snowflake/Postgres/Redshift, or --engine SPARK_SQL for Spark.
    """
    if engine is not None:
        payload["engineType"] = engine
    return payload


def _apply_pipeline_options(
    payload: dict,
    *,
    pre_filter: str | None = None,
    post_filter: str | None = None,
    computed_cols: list[str] | None = None,
    renames: list[str] | None = None,
) -> dict:
    """Apply the 4-stage pipeline options (preFilter/computedColumns/postFilter)
    plus outputColumnNameOverrides to a recipe's payload dict.

    Returns the payload (modified in place) so callers can chain.
    """
    if pre_filter:
        payload["preFilter"] = _build_pipeline_filter(pre_filter)
    if post_filter:
        payload["postFilter"] = _build_pipeline_filter(post_filter)
    parsed_cc = _parse_computed_cols(computed_cols)
    if parsed_cc:
        existing = payload.get("computedColumns") or []
        payload["computedColumns"] = existing + parsed_cc
    parsed_renames = _parse_renames(renames)
    if parsed_renames:
        existing = payload.get("outputColumnNameOverrides") or {}
        existing.update(parsed_renames)
        payload["outputColumnNameOverrides"] = existing
    return payload


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
    recipe = _get_recipe_or_exit(proj, recipe_name, project_key)
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

        builder = proj.new_job(job_type or "NON_RECURSIVE_FORCED_BUILD")
        for ref in output_refs:
            builder.with_output(ref)
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
    container_mode: str | None = typer.Option(
        None,
        "--container-mode",
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
    env_mode: str | None = typer.Option(
        None,
        "--env-mode",
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
    must already exist. Use --params to pass initial configuration:

      dku recipe create my_step -t CustomCode_my-recipe \\
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
        # Validate --input is provided for types that require it
        if not inputs and type_name.lower() not in _INPUT_OPTIONAL_TYPES:
            exit_with_error(
                f"--input is required for recipe type '{type_name}'.",
                code="missing_input",
                details=[
                    "Only code recipes (python, r, shell, pyspark, cpython, sparkr) support creation without an input dataset.",
                    f"Example: dku recipe create {recipe_name} -t {type_name} -i <INPUT_DS> --output-ds {output_ds} -P {project_key}",
                ],
            )
        if _is_plugin_recipe_type(type_name):
            # Plugin recipes: project.new_recipe() returns None for unknown types.
            # Use DSSRecipeCreator directly in raw mode.
            from dataikuapi.dss.recipe import DSSRecipeCreator

            builder = DSSRecipeCreator(type_name, recipe_name, proj)
            builder.set_raw_mode()
            for _input in inputs:
                builder.with_input(_input, role=input_role)
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
                        "Plugin recipe types use format: CustomCode_<recipeComponentId>",
                        "Discover plugin recipes: dku plugin recipes",
                    ],
                )
            for _input in inputs:
                builder.with_input(_input)
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
            if connection and hasattr(builder, "with_new_output_dataset"):
                builder.with_new_output_dataset(output_ds, connection)
            elif connection and hasattr(builder, "with_new_output"):
                builder.with_new_output(output_ds, connection)
            elif is_visual and hasattr(builder, "with_existing_output"):
                builder.with_existing_output(output_ds)
            else:
                builder.with_output(output_ds)
            builder.build()
        # Scoring recipes need the saved model wired as a "model"-role input
        # (the server errors at run time otherwise).
        if is_scoring_type and resolved_model_id is not None:
            recipe = proj.get_recipe(recipe_name)
            recipe_settings = recipe.get_settings()
            recipe_settings.add_input("model", resolved_model_id)
            recipe_settings.save()
        # Container / env-mode pinning for code recipes.
        valid_container_modes = {
            "INHERIT",
            "NONE",
            "EXPLICIT_CONTAINER",
            "EXPLICIT_K8S",
            "KUBERNETES",
        }
        valid_env_modes = {"INHERIT", "USE_BUILTIN_MODE", "EXPLICIT_ENV"}
        if container_mode is not None:
            cm_upper = container_mode.upper()
            if cm_upper not in valid_container_modes:
                exit_with_error(
                    f"Invalid --container-mode '{container_mode}'.",
                    code="invalid_argument",
                    details=[f"Valid: {', '.join(sorted(valid_container_modes))}"],
                )
            if cm_upper == "EXPLICIT_CONTAINER" and not container_conf:
                exit_with_error(
                    "--container-mode EXPLICIT_CONTAINER requires --container-conf.",
                    code="invalid_argument",
                )
        if env_mode is not None:
            em_upper = env_mode.upper()
            if em_upper not in valid_env_modes:
                exit_with_error(
                    f"Invalid --env-mode '{env_mode}'.",
                    code="invalid_argument",
                    details=[f"Valid: {', '.join(sorted(valid_env_modes))}"],
                )
            if em_upper == "EXPLICIT_ENV" and not env_name:
                exit_with_error(
                    "--env-mode EXPLICIT_ENV requires --env-name.",
                    code="invalid_argument",
                )
        if container_mode or env_mode:
            recipe = proj.get_recipe(recipe_name)
            recipe_settings = recipe.get_settings()
            rp = recipe_settings.get_recipe_params() or {}
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
                    f"Output dataset '{output_ds}' does not exist. Visual recipes require the output dataset to be created first.",
                    code="output_not_found",
                    details=[
                        f"Create it first: dku dataset create {output_ds} --type Filesystem -c filesystem_managed -P {project_key}",
                        f"Then retry: dku recipe create {recipe_name} -t {type_name} {' '.join(f'-i {i}' for i in inputs)} --output-ds {output_ds} -P {project_key}",
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
                        f"Example: dku recipe create {recipe_name} -t {type_name} {' '.join(f'-i {i}' for i in inputs)} --output-ds {output_ds} --connection filesystem_managed -P {project_key}",
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
) -> None:
    """Show recipe status: engine, severity, and check messages.

    Reports which engine DSS selected for the recipe, the overall
    status severity, and any warnings or errors from recipe checks.

    Example:
      dku recipe status compute_data -P PROJ
      dku recipe status compute_data -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        recipe_status = recipe.get_status()

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
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )

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
    """Get the code payload of a code recipe.

    Only works on code recipes (python, sql, r, shell, etc.). For visual
    recipes (prepare, join, group, etc.) use 'dku recipe get-settings' to
    inspect the recipe definition.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("text", "json"), default="text")
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        if not _is_text_payload_recipe(settings):
            rtype = settings.get_recipe_raw_definition().get("type", "")
            exit_with_error(
                f"Recipe '{recipe_name}' is type '{rtype}', which has no code payload.",
                code="wrong_recipe_type",
                status=2,
                details=[
                    "get-code only works on code recipes (python, sql, r, shell, etc.).",
                    f"Inspect visual recipes with: dku recipe get-settings {recipe_name} -P {project_key}",
                ],
            )
        payload = settings.get_payload()
        if output == "json":
            render_raw({"code": payload}, output_format="json")
        else:
            print(payload)
    except typer.Exit:
        raise
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
    deep_merge: bool = typer.Option(
        False,
        "--deep-merge",
        help="Recursively merge nested payload objects instead of replacing top-level keys. Use with --payload to patch deep config without losing sibling fields.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the definition or payload of a recipe from JSON.

    Use --definition to update recipe-level settings (I/O mappings, connection info).
    Use --payload to update the visual recipe configuration (aggregations, window
    computations, join keys, filter conditions, etc.). These are mutually exclusive.

    Default --payload merge is shallow (top-level keys replaced). Use --deep-merge
    for recursive merge of nested objects — patch one field without losing siblings.

    Examples:
      dku recipe set-definition my_topn --payload '{"topN": 5}' -P PROJ
      dku recipe set-definition my_join --payload '{"postFilter": {"enabled": true}}' --deep-merge -P PROJ
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
    if deep_merge and not payload_json:
        exit_with_error(
            "--deep-merge can only be used with --payload.",
            code="invalid_argument",
        )
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        if definition:
            new_def = read_json_input(definition)
            raw = settings.get_recipe_raw_definition()
            raw.update(new_def)
            target = "definition"
        else:
            new_payload = read_json_input(payload_json)
            current = _get_recipe_payload(settings)
            if deep_merge:
                merged = _deep_merge_dict(current, new_payload)
                current.clear()
                current.update(merged)
            else:
                current.update(new_payload)
            target = "payload"
        settings.save()
        success(
            f"Updated {target} for recipe '{recipe_name}'"
            + (" (deep-merged)" if deep_merge else "")
        )
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

    Output contract for `payload`:
      - Visual recipes (join, group, window, prepare, ...): always a parsed
        JSON object (dict). Safe to navigate with `jq '.payload.virtualInputs'`
        without an extra `fromjson` step.
      - Text-payload recipes (python, r, sql_query, sql_script, pyspark,
        sparkr, spark_scala, shell, cpython): always a string (the raw script
        body).
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        # Build complete settings dict: definition + parsed payload
        full = dict(raw_def)
        # Text-payload recipes (python / r / sql_query / ...) store the recipe
        # body as a raw string — `settings.obj_payload` tries `json.loads` on
        # it and raises ValueError. Detect those and read `_str_payload`
        # directly, same pattern as `recipe get-definition`.
        if _is_text_payload_recipe(settings):
            full["payload"] = _get_text_payload(settings)
        else:
            full["payload"] = _normalize_visual_payload(settings)
        render_raw(full, output_format=output)
    except Exception as e:
        handle_api_error(e)


def _normalize_visual_payload(settings) -> dict:
    """Return the visual recipe payload as a parsed dict, regardless of how
    dataikuapi stored it.

    Some visual recipe types store the payload as a JSON-encoded string in
    `raw_params['payload']`; others surface it as a dict on `obj_payload`.
    Empty payloads come back as None / "" / {}. Always returns a dict so
    callers don't have to second-guess the shape.
    """
    # First: try obj_payload (parsed dict for most visual types)
    try:
        payload = settings.obj_payload
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str) and payload.strip():
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
    except (AttributeError, TypeError, ValueError):
        pass
    # Fallback: raw_params['payload'] may be a JSON string or a dict
    raw_params = getattr(settings, "raw_params", None)
    if isinstance(raw_params, dict):
        raw_payload = raw_params.get("payload")
        if isinstance(raw_payload, dict):
            return raw_payload
        if isinstance(raw_payload, str) and raw_payload.strip():
            try:
                parsed = json.loads(raw_payload)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
    # No payload found — return empty dict so consumers can rely on the type
    return {}


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
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        new_settings = read_json_input(settings_json)

        # Update definition (everything except payload)
        raw = settings.get_recipe_raw_definition()
        for k, v in new_settings.items():
            if k != "payload":
                raw[k] = v

        # Update payload (visual recipe config) — shallow merge at top level
        if "payload" in new_settings:
            new_payload = new_settings["payload"]
            if not isinstance(new_payload, dict):
                exit_with_error(
                    "Recipe payload must be a JSON object, not a "
                    f"{type(new_payload).__name__}.",
                    code="payload_type",
                    details=[
                        "`get-settings -o json` already returns `payload` as a "
                        "parsed object — do NOT re-stringify it with "
                        "`json.dumps(payload)` before sending to `set-settings`.",
                        "",
                        "Fix: keep `payload` as a nested dict in your input "
                        "JSON. Example with jq:",
                        "  dku recipe get-settings R -P PROJ -o json \\\\",
                        "    | jq '.payload.engineType = \"SQL\"' \\\\",
                        "    | dku recipe set-settings R -P PROJ -s -",
                    ],
                    status=2,
                )
            payload = _get_recipe_payload(settings)
            payload.update(new_payload)

        settings.save()
        success(f"Updated settings for recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("add-input")
def add_input(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    ref: str = typer.Argument(
        help="Dataset, managed folder, or saved model reference (name or ID)"
    ),
    role: str | None = typer.Option(
        None,
        "--role",
        help="Input role. Defaults to 'main' for datasets/folders, 'model' for saved models",
    ),
    input_type: str | None = typer.Option(
        None,
        "--type",
        help="Input type: DATASET | MANAGED_FOLDER | SAVED_MODEL. Auto-detected if omitted.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an input to a recipe.

    The REF can be a dataset name, managed folder (name or ID), or saved model
    (ID or name). When --type is omitted, the CLI probes the project and
    resolves automatically, erroring on ambiguity. Folder/model names are
    resolved to IDs before being written — DSS stores those refs as IDs.

    For saved models, --role defaults to 'model' (what scoring recipes expect).

    For visual recipes that use payload.virtualInputs[] (join, stack, pivot,
    window, distinct, ...), this also appends a matching virtualInputs entry
    so the new input is visible to the payload. Without the sync, the recipe
    errors 'Input index: N out of range' when any downstream payload edit
    references the new input.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kind, resolved_ref = resolve_recipe_input_ref(proj, ref, input_type)
        if role is None:
            role = "model" if kind == "SAVED_MODEL" else "main"
        recipe = _get_recipe_or_exit(proj, recipe_name, project_key)
        settings = recipe.get_settings()
        settings.add_input(role, resolved_ref)

        # Visual recipes store a parallel view of inputs in payload.virtualInputs.
        # settings.add_input() only touches the top-level inputs dict, so we
        # need to patch the payload explicitly when the recipe is visual.
        if role == "main" and kind == "DATASET":
            try:
                payload = settings.obj_payload
            except (AttributeError, TypeError, ValueError):
                payload = None
            if isinstance(payload, dict) and "virtualInputs" in payload:
                vi = payload.setdefault("virtualInputs", [])
                existing_indices = {v.get("index") for v in vi}
                # Compute new index = len(inputs.main.items) - 1 after add_input
                main_items = (
                    settings.get_recipe_raw_definition()
                    .get("inputs", {})
                    .get("main", {})
                    .get("items", [])
                )
                new_index = len(main_items) - 1
                if new_index not in existing_indices:
                    vi.append({"index": new_index})

        settings.save()
        label = {
            "DATASET": "dataset",
            "MANAGED_FOLDER": "folder",
            "SAVED_MODEL": "saved model",
        }[kind]
        success(
            f"Added {label} '{resolved_ref}' (role={role}) to recipe '{recipe_name}'"
        )
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
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        settings.add_output(role, ref)
        settings.save()
        success(f"Added output '{ref}' to recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("replace-input")
def replace_input(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    old_ref: str = typer.Argument(help="Existing input dataset reference to swap out"),
    new_ref: str = typer.Argument(help="New dataset reference"),
    role: str = typer.Option(
        "main",
        "--role",
        help="Input role (default: main).",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Swap an input dataset reference on a recipe.

    Updates inputs[role].items[i].ref where i matches OLD_REF, leaving roles
    and ordering otherwise intact. Use to retarget a recipe at a different
    upstream dataset (e.g. when you've recreated the source) without
    rewriting the whole settings dict via set-definition.

    Cross-project refs use the PROJECT.DATASET form.

    Example:
        dku recipe replace-input compute_features old_orders new_orders -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipe = _get_recipe_or_exit(proj, recipe_name, project_key)
        settings = recipe.get_settings()
        raw = settings.get_recipe_raw_definition()
        inputs = raw.get("inputs") or {}
        role_obj = inputs.get(role)
        if not role_obj:
            exit_with_error(
                f"Recipe '{recipe_name}' has no input role '{role}'.",
                code="not_found",
                details=[
                    f"Available roles: {', '.join(sorted(inputs.keys())) or '(none)'}.",
                    f"List inputs: dku recipe get-definition {recipe_name} -P {project_key} | jq .inputs",
                ],
            )
        items = role_obj.get("items") or []
        replaced = False
        for item in items:
            if item.get("ref") == old_ref:
                item["ref"] = new_ref
                replaced = True
        if not replaced:
            existing = ", ".join(it.get("ref", "?") for it in items) or "(empty)"
            exit_with_error(
                f"Recipe '{recipe_name}' role '{role}' has no input '{old_ref}'.",
                code="not_found",
                details=[f"Existing refs in role '{role}': {existing}"],
            )

        # Visual recipes mirror the inputs in payload.virtualInputs[].dataset.
        # When the dataset reference is stored there too, keep them in sync.
        try:
            payload = settings.obj_payload
        except (AttributeError, TypeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            for vi in payload.get("virtualInputs") or []:
                if isinstance(vi, dict) and vi.get("dataset") == old_ref:
                    vi["dataset"] = new_ref

        settings.save()
        success(
            f"Replaced input '{old_ref}' → '{new_ref}' on recipe '{recipe_name}' (role={role})"
        )
    except typer.Exit:
        raise
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
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        updates = recipe.compute_schema_updates()

        if output == "json":
            render_raw(updates.data, output_format="json")
        else:
            data = []
            for comp in updates.data.get("computables", []):
                cols = comp.get("newSchema", {}).get("columns", [])
                incompat = comp.get("incompatibilities", []) or []
                data.append(
                    {
                        "output": comp.get("datasetName", comp.get("id", "")),
                        "type": comp.get("type", ""),
                        "columns": str(len(cols)),
                        "needs_update": "yes" if incompat else "no",
                    }
                )
            render(
                data,
                ["output", "type", "columns", "needs_update"],
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
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
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

        # Catch the "Empty column name" trap: several date processors use
        # inCol/outCol, but agents often pass column/outputColumn from older
        # docs. DSS returns a misleading "Empty column name" error that makes
        # agents assume the processor doesn't exist.
        _INCOL_PROCESSORS = {
            "DateFormatter": ("format", "yyyy-MM-dd HH:mm:ss"),
            "DateTruncate": ("datePart", "MONTH"),
            "UNIXTimestampParser": ("milliseconds", False),
        }
        if step_type in _INCOL_PROCESSORS and isinstance(parsed_params, dict):
            has_wrong = "column" in parsed_params or "outputColumn" in parsed_params
            has_right = "inCol" in parsed_params
            if has_wrong and not has_right:
                extra_key, extra_val = _INCOL_PROCESSORS[step_type]
                example = {
                    "inCol": parsed_params.get("column", "COL"),
                    "outCol": parsed_params.get("outputColumn", "NEW_COL"),
                    extra_key: extra_val,
                }
                exit_with_error(
                    f"Processor '{step_type}' expects 'inCol'/'outCol' (not 'column'/'outputColumn').",
                    code="wrong_param_names",
                    details=[
                        "DSS returns a misleading 'Empty column name' error when these field names are wrong.",
                        f"Correct params: {json.dumps(example)}",
                        "See: dataiku skill's references/prepare-processors.md",
                    ],
                )

        # Catch param-key typos that DSS silently accepts (unknown keys are
        # ignored by the processor, leaving the step a no-op). The recipe
        # builds and runs "successfully", but the column appears in the
        # output schema as empty — surfaces only when real data arrives.
        _PARAM_KEY_TYPOS: dict[str, dict[str, str]] = {
            # add-formula --expr maps to params.expression; agents passing
            # raw --params often write "expr" instead of "expression".
            "CreateColumnWithGREL": {"expr": "expression"},
        }
        if step_type in _PARAM_KEY_TYPOS and isinstance(parsed_params, dict):
            for wrong, right in _PARAM_KEY_TYPOS[step_type].items():
                if wrong in parsed_params and right not in parsed_params:
                    exit_with_error(
                        f"Processor '{step_type}' expects '{right}', got '{wrong}'.",
                        code="wrong_param_key",
                        details=[
                            "DSS silently ignores unknown processor params — "
                            "the formula never executes but the recipe runs successfully "
                            "and the output schema gains an empty column.",
                            f"Fix: rename '{wrong}' to '{right}' in --params, or use the "
                            "shortcut 'add-formula --expr ... --column ...'.",
                        ],
                    )

        # Warn about DateParser without outCol (silently produces all nulls)
        if step_type == "DateParser" and "outCol" not in parsed_params:
            warn(
                "DateParser without 'outCol' silently produces all nulls. "
                "Add outCol to write to a new column."
            )

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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove one or more steps from a prepare recipe by index.

    When removing multiple steps, they are removed in descending order
    internally to avoid index shifting.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="recipe.remove_step",
        subject=f"step(s) {sorted(index)} from prepare recipe '{recipe_name}' in {project_key}",
        yes=yes,
        prompt=f"Remove step(s) {sorted(index)} from prepare recipe '{recipe_name}'?",
    )
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


@app.command("replace-step")
def replace_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: int = typer.Option(
        ...,
        "--index",
        help="Step index to replace (0-based). Use 'list-steps' to see indices.",
    ),
    step_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Replacement processor type (e.g. CreateColumnWithGREL). Use with --params.",
    ),
    params: str | None = typer.Option(
        None,
        "--params",
        help="Replacement step params: JSON string, @file.json, or '-' for stdin. Pair with --type.",
    ),
    name: str | None = typer.Option(
        None, "--name", help="Optional step display name (used with --type)"
    ),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="Full replacement step JSON: literal, @file.json, or '-' for stdin. Overrides --type/--params/--name.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Replace one prepare-recipe step at the given index in a single operation.

    Equivalent to `remove-step --index N --yes` then `add-step --at N` but
    atomic — no index drift between calls. Use this when iterating on a
    single processor's params without re-shuffling the rest of the pipeline.

    Provide either --type + --params (and optionally --name), OR --definition
    with the full step JSON.

    Example:
      dku recipe replace-step my_prep --index 2 \\
        --type CreateColumnWithGREL \\
        --params '{"column":"price_log","expression":"log(price)"}' -P PROJ
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    if not definition and not (step_type and params):
        exit_with_error(
            "Provide either --definition or both --type and --params.",
            details=[
                'Example: dku recipe replace-step my_prep --index 2 --type ColumnRenamer --params \'{"renamings":[{"from":"a","to":"b"}]}\' -P PROJ',
                "Example: dku recipe replace-step my_prep --index 2 --definition @step.json -P PROJ",
            ],
        )
    guard(
        ctx,
        tier=Tier.DELETE,
        action="recipe.replace_step",
        subject=f"step at index {index} in prepare recipe '{recipe_name}' in {project_key}",
        yes=yes,
        prompt=f"Replace step at index {index} in prepare recipe '{recipe_name}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        _validate_step_index(steps, index, recipe_name)

        if definition:
            new_step = read_json_input(definition)
            if not isinstance(new_step, dict):
                exit_with_error(
                    "--definition must be a JSON object describing one step.",
                    code="invalid_step",
                )
            # Default the metaType so callers don't have to remember it
            new_step.setdefault("metaType", "PROCESSOR")
            display_type = new_step.get("type", "<unknown>")
        else:
            parsed_params = read_json_input(params)
            new_step = {
                "metaType": "PROCESSOR",
                "type": step_type,
                "params": parsed_params,
            }
            if name:
                new_step["name"] = name
            display_type = step_type

        steps[index] = new_step
        settings.save()
        success(
            f"Replaced step at index {index} in '{recipe_name}' with {display_type}"
        )
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
        "KEEP_ROW",
        "--action",
        help="KEEP_ROW (keep matching, default — matches create-filter), REMOVE_ROW (drop matching), CLEAR_CELL, or FLAG",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a filter step to remove or keep rows matching conditions.

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
            "FilterOnCustomFormula",
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
            "FilterOnValue",
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
    column: list[str] = typer.Option(
        None,
        "--column",
        "-c",
        help="Column to fill (repeatable: '-c HBO -c Netflix' produces ONE step covering both with the same --value).",
    ),
    columns: str = typer.Option(
        None,
        "--columns",
        help="Comma-separated columns (alternative to repeating --column). Same --value applied to all.",
    ),
    value: str = typer.Option(..., "--value", help="Value to fill empty cells with"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a step that fills empty/null values in one or more columns with a fixed value.

    Use instead of df.fillna() in Python. For SAS-style 'if X=. then X=0' defaulting
    over many columns, pass --column repeatedly OR a single --columns CSV — both produce
    ONE step covering all columns with the same fill value.
    """
    cols: list[str] = list(column or [])
    if columns:
        cols.extend(c.strip() for c in columns.split(",") if c.strip())
    if not cols:
        exit_with_error(
            "Provide at least one column via --column (repeatable) or --columns CSV.",
            code="missing_column",
        )

    params: dict
    if len(cols) == 1:
        params = {
            "appliesTo": "SINGLE_COLUMN",
            "columns": cols,
            "value": value,
        }
    else:
        params = {
            "appliesTo": "COLUMNS",
            "columns": cols,
            "value": value,
        }

    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "FillEmptyWithValue",
        params,
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


@app.command("add-reorder")
def add_reorder(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    column: list[str] = typer.Option(
        None,
        "--column",
        "-c",
        help="Column(s) to move. Repeatable for multi-column moves.",
    ),
    columns: str = typer.Option(
        None,
        "--columns",
        help="Comma-separated columns (alternative to repeating --column).",
    ),
    mode: str = typer.Option(
        ...,
        "--mode",
        "-m",
        help="Reorder mode: AT_THE_BEGINNING | AT_THE_END | BEFORE_COLUMN | AFTER_COLUMN.",
    ),
    anchor: str | None = typer.Option(
        None,
        "--anchor",
        "-a",
        help="Reference column for BEFORE_COLUMN / AFTER_COLUMN modes.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a ColumnReorder step. Auto-fills `appliesTo` so DSS doesn't reject
    the step with 'Applies mode not selected'.

    Closes the recurring footgun: the generic `add-step --type ColumnReorder`
    omits `appliesTo`, which DSS silently accepts but renders as broken.
    Multi-column moves work correctly when `appliesTo: COLUMNS` is set.

    Examples:
      Move one column to the start:
        dku recipe add-reorder my_prep -c price --mode AT_THE_BEGINNING -P PROJ

      Move multiple columns before an anchor:
        dku recipe add-reorder my_prep -c a -c b --mode BEFORE_COLUMN \\
          --anchor c -P PROJ
    """
    valid_modes = {"AT_THE_BEGINNING", "AT_THE_END", "BEFORE_COLUMN", "AFTER_COLUMN"}
    mode_upper = mode.upper()
    if mode_upper not in valid_modes:
        exit_with_error(
            f"Invalid --mode '{mode}'. Must be one of: "
            f"{', '.join(sorted(valid_modes))}.",
            code="invalid_mode",
        )
    if mode_upper in {"BEFORE_COLUMN", "AFTER_COLUMN"} and not anchor:
        exit_with_error(
            f"--mode {mode_upper} requires --anchor (the reference column).",
            code="missing_anchor",
            details=[
                "AT_THE_BEGINNING / AT_THE_END do not need --anchor.",
                "BEFORE_COLUMN / AFTER_COLUMN do.",
            ],
        )

    cols: list[str] = list(column or [])
    if columns:
        cols.extend(c.strip() for c in columns.split(",") if c.strip())
    if not cols:
        exit_with_error(
            "Provide at least one column via --column (repeatable) or --columns CSV.",
            code="missing_column",
        )

    applies_to = "SINGLE_COLUMN" if len(cols) == 1 else "COLUMNS"
    params: dict = {
        "appliesTo": applies_to,
        "columns": cols,
        "reorderAction": mode_upper,
    }
    if anchor:
        params["referenceColumn"] = anchor

    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "ColumnReorder",
        params,
    )


@app.command("add-find-replace")
def add_find_replace(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    column: str = typer.Option(..., "--column", "-c", help="Column to search in"),
    find: str = typer.Option(..., "--find", help="Value to find"),
    replace: str = typer.Option(..., "--replace", help="Replacement value"),
    matching: str = typer.Option(
        "SUBSTRING",
        "--matching",
        help="Match mode: SUBSTRING (default), FULL_STRING (exact cell match), or PATTERN (regex).",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a find-and-replace step on a column."""
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
            "MultiColumnFold",
            {
                "columns": col_list,
                "foldNameColumn": key_column,
                "foldValueColumn": value_column,
                "foldRemoveFoldedColumns": True,
            },
        )
    else:
        _add_prepare_step(
            ctx,
            recipe_name,
            project,
            "MultiColumnByPrefixFold",
            {
                "columnNamePattern": pattern,
                "columnNameColumn": key_column,
                "columnContentColumn": value_column,
                "foldRemoveFoldedColumns": True,
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
    unit: str = typer.Option(
        "MILES",
        "--unit",
        "-u",
        help="Output unit: MILES or KILOMETERS",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Compute distance between two geopoint/geometry columns.

    Use instead of haversine calculations in Python. Both columns must be
    geopoint or geometry type (use add-geopoint first if needed).

    Example: dku recipe add-geodistance prep1 --from origin --to destination -P PROJ
    """
    unit_upper = unit.upper()
    if unit_upper not in {"MILES", "KILOMETERS"}:
        exit_with_error(
            f"Invalid --unit '{unit}'. Use MILES or KILOMETERS.",
            status=2,
        )
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "GeoDistanceProcessor",
        {
            "input1": from_column,
            "input2": to_column,
            "output": output_column,
            "outputUnit": unit_upper,
            "compareTo": "COLUMN",
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
        help=(
            "Join type: LEFT, INNER, RIGHT, FULL, CROSS, LEFT_ANTI, RIGHT_ANTI, "
            "ADVANCED. LEFT_ANTI = left rows with NO match in right ('candidates "
            "minus positives' pattern). RIGHT_ANTI = symmetric. FULL = outer join. "
            "ADVANCED = expression-based ON clause via --advanced-condition. "
            "Applied to all join pairs. Default: LEFT."
        ),
    ),
    auto_cast: bool = typer.Option(
        False,
        "--auto-cast",
        help=(
            "Set enableAutoCastInJoinConditions=true so DSS auto-casts "
            "join keys with mismatched types (e.g. string vs bigint)."
        ),
    ),
    cols: list[str] | None = typer.Option(
        None,
        "--cols",
        help=(
            "Per-input column projection: 'INDEX:c1,c2,c3' — only the listed "
            "columns from input INDEX flow through. Sets that virtualInput's "
            "outputColumnsSelectionMode=MANUAL + selectedColumns. Repeatable. "
            "Replaces a downstream Prepare add-delete-columns."
        ),
    ),
    engine: str | None = typer.Option(
        None,
        "--engine",
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Top-level field, separate from engineParams.<engine>.executionEngine. "
            "Set SQL for Snowflake/Postgres pushdown."
        ),
    ),
    case_insensitive: bool = typer.Option(
        False,
        "--case-insensitive",
        help="Set caseInsensitive=true on every EQ join condition (compares 'Foo' == 'foo').",
    ),
    normalize_text: bool = typer.Option(
        False,
        "--normalize-text",
        help="Set normalizeText=true on every EQ condition (lowercases + trims before compare). Implies case-insensitive.",
    ),
    max_matches: int | None = typer.Option(
        None,
        "--max-matches",
        help=(
            "maxMatches per join condition. Limits fan-out: cap the number of right rows joined per left row. "
            "Default 1 in DSS payload, 0 disables the cap."
        ),
    ),
    max_distance: int | None = typer.Option(
        None,
        "--max-distance",
        help=(
            "Levenshtein maxDistance on EQ conditions — fuzzy match without leaving create-join "
            "(e.g. 1 = at most one edit). Set on each EQ condition's payload."
        ),
    ),
    date_window: str | None = typer.Option(
        None,
        "--date-window",
        help=(
            "Date-tolerance match. Format: 'FROM:TO[:UNIT]' (UNIT default DAY). "
            "Example: '-7:7:DAY' joins rows whose date columns differ by ≤ 7 days. "
            "Maps to windowFrom/windowTo/dateDiffUnit on every EQ condition. "
            "Replaces the Cross+Filter / Python pattern for SAS PROC SQL date-band joins."
        ),
    ),
    outer_join_on_left: bool | None = typer.Option(
        None,
        "--outer-join-on-left/--outer-join-on-right",
        help=(
            "Override outerJoinOnTheLeft on every join pair. By default LEFT joins keep left, "
            "RIGHT joins keep right. Use --outer-join-on-right to flip a LEFT join's preserve side."
        ),
    ),
    right_limit_max_matches: int | None = typer.Option(
        None,
        "--right-limit-max-matches",
        help=(
            "Enable rightLimit on every join pair, keeping at most N right matches per left row. "
            "Pair with --right-limit-keep / --right-limit-decision-column for "
            "'keep first/last/largest match' semantics on regular EQ joins."
        ),
    ),
    right_limit_decision_column: str | None = typer.Option(
        None,
        "--right-limit-decision-column",
        help=(
            "Column on the right side of the join used as the rightLimit tiebreaker. "
            "Required for KEEP_LARGEST / KEEP_SMALLEST. "
            "Example: --right-limit-decision-column record_date with --right-limit-keep KEEP_LARGEST."
        ),
    ),
    right_limit_keep: str | None = typer.Option(
        None,
        "--right-limit-keep",
        help="rightLimit.type: KEEP_LARGEST | KEEP_SMALLEST | KEEP_FIRST | KEEP_LAST. Default in DSS: KEEP_LARGEST.",
    ),
    right_limit_strict: bool = typer.Option(
        False,
        "--right-limit-strict",
        help="rightLimit.strict=true — drop right rows whose decisionColumn value is NULL.",
    ),
    strict_eq: bool = typer.Option(
        False,
        "--strict-eq",
        help=(
            "Set strict=true on every EQ condition. Without this, NULL=NULL "
            "matches (DSS default — surprising for SQL agents). With "
            "--strict-eq, only non-null values match — matches SQL semantics "
            "where NULL=NULL is unknown."
        ),
    ),
    conditions_mode: str | None = typer.Option(
        None,
        "--conditions-mode",
        help=(
            "Inter-condition combinator: AND (default — all ON conditions "
            "must match) or OR (any matches — equivalent to "
            "LEFT JOIN ... ON (a.x=b.x OR a.y=b.y), the SAS PROC SQL "
            "alternation pattern, replaces a 2-Joins+Stack workaround). "
            "Sets joins[].conditionsMode."
        ),
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

    Advanced match modes (apply to every EQ condition on every pair):
      --case-insensitive / --normalize-text     fuzzy text matching
      --max-distance N                           Levenshtein fuzzy EQ (1 edit = N=1)
      --date-window -7:7:DAY                     date-tolerance band match
      --max-matches N                            cap right matches per left row

    rightLimit (deduplicate to first/best match) — works on EQ joins, not just spatial:
      --right-limit-max-matches 1 \\
      --right-limit-decision-column record_date \\
      --right-limit-keep KEEP_LARGEST [--right-limit-strict]
    """
    _VALID_JOIN_TYPES = {
        "LEFT",
        "INNER",
        "RIGHT",
        "FULL",
        "CROSS",
        "LEFT_ANTI",
        "RIGHT_ANTI",
        "ADVANCED",
    }
    _VALID_RIGHT_LIMIT_KEEP = {
        "KEEP_LARGEST",
        "KEEP_SMALLEST",
        "KEEP_FIRST",
        "KEEP_LAST",
    }
    project_key = resolve_project(project)
    engine_upper = _validate_engine_type(engine)
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

    # Validate --date-window FROM:TO[:UNIT]
    parsed_date_window: tuple[int, int, str] | None = None
    if date_window:
        parts = date_window.split(":")
        if len(parts) not in (2, 3):
            exit_with_error(
                f"Invalid --date-window '{date_window}'. Expected 'FROM:TO[:UNIT]'.",
                code="invalid_argument",
                details=[
                    "Example: --date-window -7:7:DAY (rows whose dates differ by ≤ 7 days)"
                ],
            )
        try:
            wf, wt = int(parts[0]), int(parts[1])
        except ValueError:
            exit_with_error(
                f"--date-window '{date_window}': FROM and TO must be integers.",
                code="invalid_argument",
            )
        unit = parts[2].upper() if len(parts) == 3 else "DAY"
        _VALID_DATE_UNITS = {
            "YEAR",
            "QUARTER",
            "MONTH",
            "WEEK",
            "DAY",
            "HOUR",
            "MINUTE",
            "SECOND",
            "MILLISECOND",
        }
        if unit not in _VALID_DATE_UNITS:
            exit_with_error(
                f"--date-window unit '{unit}' is not valid.",
                code="invalid_argument",
                details=[f"Valid units: {', '.join(sorted(_VALID_DATE_UNITS))}"],
            )
        parsed_date_window = (wf, wt, unit)

    # Validate --right-limit-keep
    rl_keep_upper: str | None = None
    if right_limit_keep:
        rl_keep_upper = right_limit_keep.upper()
        if rl_keep_upper not in _VALID_RIGHT_LIMIT_KEEP:
            exit_with_error(
                f"--right-limit-keep '{right_limit_keep}' is not valid.",
                code="invalid_argument",
                details=[f"Valid: {', '.join(sorted(_VALID_RIGHT_LIMIT_KEEP))}"],
            )

    # rightLimit cross-checks: KEEP_LARGEST/SMALLEST need a decisionColumn.
    right_limit_enabled = (
        right_limit_max_matches is not None
        or right_limit_decision_column is not None
        or right_limit_keep is not None
        or right_limit_strict
    )
    if right_limit_enabled:
        if (
            rl_keep_upper in {"KEEP_LARGEST", "KEEP_SMALLEST"}
            and not right_limit_decision_column
        ):
            exit_with_error(
                f"--right-limit-keep {rl_keep_upper} requires --right-limit-decision-column.",
                code="invalid_argument",
                details=[
                    "KEEP_LARGEST / KEEP_SMALLEST need a column to compare. "
                    "Use --right-limit-decision-column COL (the right-side tiebreaker column)."
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

        # DSS's builder may pre-create a single default join pair when there are
        # 2+ inputs, leaving `joins` at length 1 regardless of input count.
        # Extend to exactly N-1 join pairs so --join-key 1:col, 2:col, ... all
        # resolve to a valid target. Each join fans out from table 0 (the main
        # table) to table i+1 (each subsequent input).
        # Only extend when raw_joins is a real list (not a test MagicMock).
        if isinstance(joins, list):
            target_pairs = max(0, len(inputs) - 1)
            existing_pairs = len(joins)
            for i in range(existing_pairs, target_pairs):
                joins.append(
                    {
                        "table1": 0,
                        "table2": i + 1,
                        "conditionsMode": "AND",
                        "type": jt,
                        "outerJoinOnTheLeft": True,
                        "on": [],
                    }
                )

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

        # --auto-cast: enable enableAutoCastInJoinConditions on the payload
        if auto_cast:
            join_settings.obj_payload["enableAutoCastInJoinConditions"] = True
            info("Auto-cast in join conditions: enabled")

        # --conditions-mode AND/OR overrides every join pair's combinator.
        cm_upper: str | None = None
        if conditions_mode is not None:
            cm_upper = conditions_mode.upper()
            if cm_upper not in {"AND", "OR"}:
                exit_with_error(
                    f"Invalid --conditions-mode '{conditions_mode}'.",
                    code="invalid_argument",
                    details=["Valid: AND, OR"],
                )
            if isinstance(joins, list):
                for j in joins:
                    j["conditionsMode"] = cm_upper
                info(f"Conditions mode: {cm_upper}")

        # Apply per-condition advanced match modes across all joins.
        any_condition_extra = (
            case_insensitive
            or normalize_text
            or max_matches is not None
            or max_distance is not None
            or parsed_date_window is not None
            or strict_eq
        )
        if any_condition_extra and isinstance(joins, list):
            for j in joins:
                for cond in j.get("on", []):
                    if cond.get("type") != "EQ":
                        continue
                    if case_insensitive or normalize_text:
                        cond["caseInsensitive"] = True
                    if normalize_text:
                        cond["normalizeText"] = True
                    if strict_eq:
                        cond["strict"] = True
                    if max_matches is not None:
                        cond["maxMatches"] = max_matches
                    if max_distance is not None:
                        cond["maxDistance"] = max_distance
                    if parsed_date_window is not None:
                        wf, wt, unit = parsed_date_window
                        cond["windowFrom"] = wf
                        cond["windowTo"] = wt
                        cond["dateDiffUnit"] = unit
            modes = []
            if case_insensitive or normalize_text:
                modes.append("case-insensitive")
            if normalize_text:
                modes.append("normalize-text")
            if strict_eq:
                modes.append("strict-eq")
            if max_distance is not None:
                modes.append(f"levenshtein≤{max_distance}")
            if parsed_date_window is not None:
                modes.append(
                    f"date-window {parsed_date_window[0]}:{parsed_date_window[1]}:{parsed_date_window[2]}"
                )
            if max_matches is not None:
                modes.append(f"maxMatches={max_matches}")
            info("Match mode: " + ", ".join(modes))

        # --outer-join-on-left override on every join pair.
        if outer_join_on_left is not None and isinstance(joins, list):
            for j in joins:
                j["outerJoinOnTheLeft"] = bool(outer_join_on_left)
            info(f"outerJoinOnTheLeft: {bool(outer_join_on_left)}")

        # rightLimit block: applies to every join pair uniformly.
        if right_limit_enabled and isinstance(joins, list):
            for j in joins:
                rl = j.setdefault("rightLimit", {})
                rl["enabled"] = True
                if right_limit_max_matches is not None:
                    rl["maxMatches"] = right_limit_max_matches
                if rl_keep_upper is not None:
                    rl["type"] = rl_keep_upper
                if right_limit_decision_column is not None:
                    rl["decisionColumn"] = {
                        "name": right_limit_decision_column,
                        "table": j.get("table2", 1),
                    }
                if right_limit_strict:
                    rl["strict"] = True
            details = []
            if right_limit_max_matches is not None:
                details.append(f"maxMatches={right_limit_max_matches}")
            if rl_keep_upper:
                details.append(rl_keep_upper)
            if right_limit_decision_column:
                details.append(f"by={right_limit_decision_column}")
            if right_limit_strict:
                details.append("strict")
            info("rightLimit: " + ", ".join(details))

        _apply_engine_type(join_settings.obj_payload, engine_upper)
        if engine_upper:
            info(f"Engine: {engine_upper}")

        # --cols INDEX:a,b,c: per-input MANUAL column projection
        if cols:
            virtual_inputs = join_settings.obj_payload.get("virtualInputs", [])
            for entry in cols:
                if ":" not in entry:
                    exit_with_error(
                        f"Invalid --cols '{entry}'. Expected 'INDEX:c1,c2,c3'.",
                        code="invalid_argument",
                    )
                idx_str, cols_str = entry.split(":", 1)
                try:
                    idx = int(idx_str)
                except ValueError:
                    exit_with_error(
                        f"Invalid input index in --cols '{entry}'.",
                        code="invalid_argument",
                    )
                if idx < 0 or idx >= len(inputs):
                    exit_with_error(
                        f"--cols index {idx} out of range (0..{len(inputs) - 1}).",
                        code="invalid_argument",
                    )
                col_list = [c.strip() for c in cols_str.split(",") if c.strip()]
                # Pad virtualInputs if needed (some setups create them lazily).
                while len(virtual_inputs) <= idx:
                    virtual_inputs.append({"index": len(virtual_inputs)})
                vi = virtual_inputs[idx]
                vi["outputColumnsSelectionMode"] = "MANUAL"
                vi["selectedColumns"] = col_list
                info(f"Cols input {idx}: {', '.join(col_list)}")

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
    join_type: str = typer.Option(
        "LEFT",
        "--join-type",
        "-j",
        help="Join type: LEFT (default, keep all left rows), INNER, RIGHT, FULL.",
    ),
    max_matches: int | None = typer.Option(
        None,
        "--max-matches",
        help=(
            "Limit the right-side matches per left row (e.g. 1 to keep one "
            "best match per left row instead of fanning-out)."
        ),
    ),
    right_limit_strategy: str | None = typer.Option(
        None,
        "--right-limit-strategy",
        help=(
            "When --max-matches is set, how to pick the surviving matches: "
            "KEEP_LARGEST (default if unset), KEEP_SMALLEST, KEEP_FIRST, KEEP_LAST."
        ),
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

        jt = (join_type or "LEFT").upper()
        if jt not in {"LEFT", "INNER", "RIGHT", "FULL"}:
            exit_with_error(
                f"Invalid --join-type '{join_type}'.",
                code="invalid_argument",
                details=["Use LEFT, INNER, RIGHT, or FULL."],
            )
        geo_join["type"] = jt

        if max_matches is not None:
            strategy = (right_limit_strategy or "KEEP_LARGEST").upper()
            if strategy not in {
                "KEEP_LARGEST",
                "KEEP_SMALLEST",
                "KEEP_FIRST",
                "KEEP_LAST",
            }:
                exit_with_error(
                    f"Invalid --right-limit-strategy '{right_limit_strategy}'.",
                    code="invalid_argument",
                    details=[
                        "Use KEEP_LARGEST, KEEP_SMALLEST, KEEP_FIRST, or KEEP_LAST.",
                    ],
                )
            geo_join["rightLimit"] = {
                "enabled": True,
                "maxMatches": max_matches,
                "type": strategy,
            }
        elif right_limit_strategy:
            warn("--right-limit-strategy ignored without --max-matches.")

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
    engine: str | None = typer.Option(
        None,
        "--engine",
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Top-level field, separate from engineParams.<engine>.executionEngine. "
            "Required for SQL pushdown on Snowflake/Postgres/Redshift — without it, "
            "DSS may pick the slower DSS engine."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Group (aggregate) recipe. NEVER use Python for aggregations — use this instead.

    Use --agg to configure aggregation functions: --agg 'amount:sum,avg' --agg 'id:count'.
    Without --agg, defaults to COUNT per group. Use -k for group keys (repeatable: -k col1 -k col2).

    Aggregation functions: sum, avg, min, max, count, count_distinct, concat, stddev,
    first, last, first_last_not_null, concat_distinct, sum2.

    By default DSS adds a 'count' column (rows per group). Pass --no-global-count
    to suppress it when only the explicit aggregates should appear in the output.
    """
    project_key = resolve_project(project)
    engine_upper = _validate_engine_type(engine)
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
    # Parse --agg-order col=order_col  (and --agg-separator col=sep)
    agg_order_map: dict[str, str] = {}
    for entry in agg_order:
        if "=" not in entry:
            exit_with_error(
                f"Invalid --agg-order '{entry}'. Expected 'col=order_col'.",
                code="invalid_argument",
            )
        c, o = entry.split("=", 1)
        agg_order_map[c.strip()] = o.strip()
    agg_sep_map: dict[str, str] = {}
    for entry in agg_separator:
        if "=" not in entry:
            exit_with_error(
                f"Invalid --agg-separator '{entry}'. Expected 'col=sep' (sep may be empty).",
                code="invalid_argument",
            )
        c, sep = entry.split("=", 1)
        agg_sep_map[c.strip()] = sep
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
                for agg_spec in agg:
                    col, funcs_str = agg_spec.split(":", 1)
                    funcs = {f.strip().lower() for f in funcs_str.split(",")}
                    cs = group_settings.set_column_aggregations(
                        col.strip(),
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
    engine: str | None = typer.Option(
        None,
        "--engine",
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Top-level field, separate from engineParams.<engine>.executionEngine. "
            "Set SQL for Snowflake/Postgres pushdown."
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
    engine_upper = _validate_engine_type(engine)
    if len(inputs) < 2:
        exit_with_error(
            "Stack recipes need at least 2 input datasets.",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-stack NAME -i ds1 -i ds2 --output-ds out -P PROJ"
            ],
        )
    if origin_labels and not origin_column:
        exit_with_error(
            "--origin-label requires --origin-column.",
            code="invalid_argument",
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
                    code="invalid_argument",
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
                    code="invalid_argument",
                )
            if idx < 0 or idx >= len(inputs):
                exit_with_error(
                    f"--origin-label index {idx} out of range (0..{len(inputs) - 1}).",
                    code="invalid_argument",
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
                    code="invalid_argument",
                )
        else:
            exit_with_error(
                f"Invalid --mode '{mode}'.",
                code="invalid_argument",
                details=[
                    "Use UNION (default), INTERSECT, FROM_DATASET:NAME, "
                    "FROM_INDEX:N, or REMAP.",
                    "Only FROM_DATASET / FROM_INDEX accept a ':' suffix.",
                ],
            )
    else:
        mode_upper = mode_value.upper()
    if mode_upper not in {"UNION", "INTERSECT", "FROM_DATASET", "FROM_INDEX", "REMAP"}:
        exit_with_error(
            f"Invalid --mode '{mode}'.",
            code="invalid_argument",
            details=[
                "Use UNION (default), INTERSECT, FROM_DATASET:NAME, FROM_INDEX:N, or REMAP.",
            ],
        )
    if mode_upper == "FROM_DATASET" and not from_dataset_name:
        exit_with_error(
            "--mode FROM_DATASET requires the dataset name: --mode FROM_DATASET:DS.",
            code="invalid_argument",
        )
    if mode_upper == "FROM_DATASET" and from_dataset_name not in inputs:
        exit_with_error(
            f"--mode FROM_DATASET:{from_dataset_name} references a dataset that is not an input.",
            code="invalid_argument",
            details=[
                f"Inputs in order: {', '.join(inputs)}",
                "Use one of the -i/--input dataset names after FROM_DATASET:.",
            ],
        )
    if mode_upper == "FROM_INDEX":
        if from_index_value is None:
            exit_with_error(
                "--mode FROM_INDEX requires an integer index: --mode FROM_INDEX:0.",
                code="invalid_argument",
            )
        if from_index_value < 0 or from_index_value >= len(inputs):
            exit_with_error(
                f"--mode FROM_INDEX:{from_index_value} out of range "
                f"(0..{len(inputs) - 1}).",
                code="invalid_argument",
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
                    code="invalid_argument",
                )
            idx_str, cols_str = entry.split(":", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                exit_with_error(
                    f"Invalid input index in --columns-match '{entry}': '{idx_str}' is not an integer.",
                    code="invalid_argument",
                )
            if idx < 0 or idx >= len(inputs):
                exit_with_error(
                    f"--columns-match index {idx} out of range (0..{len(inputs) - 1}).",
                    code="invalid_argument",
                )
            columns_match_map[idx] = [c.strip() for c in cols_str.split(",")]

    input_filter_map: dict[int, str] = {}
    if input_filters:
        for entry in input_filters:
            if ":" not in entry:
                exit_with_error(
                    f"Invalid --input-filter '{entry}'. Expected 'INDEX:GREL_EXPR'.",
                    code="invalid_argument",
                )
            idx_str, expr = entry.split(":", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                exit_with_error(
                    f"Invalid input index in --input-filter '{entry}': '{idx_str}' is not an integer.",
                    code="invalid_argument",
                )
            if idx < 0 or idx >= len(inputs):
                exit_with_error(
                    f"--input-filter index {idx} out of range (0..{len(inputs) - 1}).",
                    code="invalid_argument",
                )
            input_filter_map[idx] = expr

    if mode_upper == "REMAP":
        if not columns_list:
            exit_with_error(
                "--mode REMAP requires --columns 'a,b,c' to define the output schema.",
                code="invalid_argument",
                details=[
                    "REMAP aligns mis-named columns into one output schema. The schema is the "
                    "list of output column names; --columns-match positionally maps each input.",
                    "Example: --mode REMAP --columns 'id,amount' --columns-match 0:src_id,total --columns-match 1:sale_id,price",
                ],
            )
        if not columns_match_map:
            exit_with_error(
                "--mode REMAP requires at least one --columns-match INDEX:c1,c2,c3.",
                code="invalid_argument",
            )
        for idx, src_cols in columns_match_map.items():
            if len(src_cols) != len(columns_list):
                exit_with_error(
                    f"--columns-match {idx}: got {len(src_cols)} source columns "
                    f"but --columns has {len(columns_list)} output columns.",
                    code="invalid_argument",
                    details=[
                        "The number of source columns per input MUST equal the number of output columns.",
                        "Use an empty slot (',,') if an input does not provide a given output column.",
                    ],
                )
    elif columns_match:
        exit_with_error(
            "--columns-match is only valid with --mode REMAP.",
            code="invalid_argument",
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
            "--on col2 to dedup only on a subset of columns."
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
    engine: str | None = typer.Option(
        None,
        "--engine",
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Top-level field; set SQL for Snowflake/Postgres pushdown."
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
    engine_upper = _validate_engine_type(engine)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("distinct", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure distinct keys. Default behavior is "distinct on ALL columns"
        # to match df.drop_duplicates() semantics. Without this, DSS defaults to
        # keys=[first_col] + selectAllColumns=false, which silently produces a
        # single-column output (the first column) — an anti-pattern that looks
        # like distinct but is actually a projection.
        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)

        if on:
            key_cols = list(on)
        else:
            # Resolve all columns from the input dataset schema.
            try:
                input_schema = (
                    proj.get_dataset(input_ds).get_schema().get("columns", [])
                )
                key_cols = [c["name"] for c in input_schema]
            except Exception:
                # If we can't read the schema (e.g. input not yet built),
                # fall back to DSS defaults — better than crashing.
                key_cols = []

        if key_cols:
            payload["keys"] = [{"column": c} for c in key_cols]
            payload["selectAllColumns"] = True
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
    except Exception as e:
        handle_api_error(e)


def _raw_create_recipe(
    proj,
    recipe_type: str,
    name: str,
    inputs: list[tuple[str, str]],
    outputs: list[tuple[str, str]],
):
    """Create a recipe of an arbitrary type via raw create_recipe + rawCreation.

    Used for built-in DSS recipe types not dispatched by `proj.new_recipe()` —
    namely `update`, `merge_folder`, `list_folder_contents`, `eda_univariate`,
    `prompt`, and `nlp_llm_user_provided_classification`. Inputs and outputs are
    (ref, role) pairs.
    """
    proto = {
        "name": name,
        "type": recipe_type,
        "inputs": {},
        "outputs": {},
    }
    for ref, role in inputs:
        proto["inputs"].setdefault(role, {"items": []})["items"].append({"ref": ref})
    for ref, role in outputs:
        proto["outputs"].setdefault(role, {"items": []})["items"].append(
            {"ref": ref, "appendMode": False}
        )
    return proj.create_recipe(proto, {"rawCreation": True})


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
                code="missing_output",
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
            "Use 'dku dq list-checks DATASET -P PROJ' to discover IDs. "
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
    engine: str | None = typer.Option(
        None,
        "--engine",
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Set SQL for Snowflake/Postgres pushdown."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Extract-Failed-Rows recipe (built-in DSS recipe type).

    Quarantines rows that violated dataset checks on the input.

    The input dataset MUST have checks defined (`dku dq add-check ...`).
    Without --rule-id, the recipe extracts rows failing ANY enabled rule.

    Example:
        dku recipe create-extract-failed-rows quarantine_customers \\
            -i customers --output-ds customers_failed \\
            --rule-id customer_id_not_null --rule-id email_format -P PROJ
    """
    project_key = resolve_project(project)
    engine_upper = _validate_engine_type(engine)

    rule_column_map: dict[str, str] = {}
    for entry in rule_column:
        if ":" not in entry:
            exit_with_error(
                f"Invalid --rule-column '{entry}'. Expected 'RULE_ID:column'.",
                code="invalid_argument",
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
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-list-folder-contents")
def create_list_folder_contents(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    folder: str = typer.Option(
        ..., "--folder", help="Source managed folder ID or name"
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
    conflict_handling: str = typer.Option(
        "OVERWRITE",
        "--conflict",
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
    if conflict_handling not in {"OVERWRITE", "SKIP", "FAIL"}:
        exit_with_error(
            f"Invalid --conflict '{conflict_handling}'. Use OVERWRITE, SKIP, or FAIL.",
            code="invalid_argument",
        )
    project_key = resolve_project(project)
    try:
        from dku_cli.helpers import resolve_folder

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        input_ids = [resolve_folder(proj, ref).id for ref in inputs]

        # Auto-create the destination folder if it doesn't exist.
        folders_listing = proj.list_managed_folders()
        existing = {f.get("id"): f for f in folders_listing}
        existing_names = {f.get("name"): f for f in folders_listing}
        if output_folder in existing:
            out_id = output_folder
        elif output_folder in existing_names:
            out_id = existing_names[output_folder].get("id")
        else:
            out_id = proj.create_managed_folder(output_folder).id
            info(f"Auto-created destination folder '{output_folder}' (id={out_id})")

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
            "conflictHandling": conflict_handling,
        }
        settings.save()
        success(
            f"Created merge_folder recipe '{recipe_name}' in {project_key} "
            f"({len(input_ids)} source(s) → {output_folder})"
        )
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
                code="invalid_argument",
                details=[f"Valid providers: {', '.join(sorted(_VALID_PROVIDERS))}"],
            )
        provider, url = entry.split(":", 1)
        provider_upper = provider.strip().upper()
        if provider_upper not in _VALID_PROVIDERS:
            exit_with_error(
                f"Invalid --source provider '{provider}'.",
                code="invalid_argument",
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
        folders_listing = proj.list_managed_folders()
        existing = {f.get("id"): f for f in folders_listing}
        existing_names = {f.get("name"): f for f in folders_listing}
        if output_folder in existing:
            out_id = output_folder
        elif output_folder in existing_names:
            out_id = existing_names[output_folder].get("id")
        else:
            out_id = proj.create_managed_folder(output_folder).id
            info(f"Auto-created destination folder '{output_folder}' (id={out_id})")

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
    format: str = typer.Option(
        "csv",
        "--format",
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
    _VALID_FORMATS = {"csv", "excel", "json", "parquet", "avro", "tsv"}
    fmt_lower = format.lower()
    if fmt_lower not in _VALID_FORMATS:
        exit_with_error(
            f"Invalid --format '{format}'.",
            code="invalid_argument",
            details=[f"Valid: {', '.join(sorted(_VALID_FORMATS))}"],
        )
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # Auto-create the destination folder.
        folders_listing = proj.list_managed_folders()
        existing = {f.get("id"): f for f in folders_listing}
        existing_names = {f.get("name"): f for f in folders_listing}
        if output_folder in existing:
            out_id = output_folder
        elif output_folder in existing_names:
            out_id = existing_names[output_folder].get("id")
        else:
            out_id = proj.create_managed_folder(output_folder).id
            info(f"Auto-created destination folder '{output_folder}' (id={out_id})")

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
        builder.build()

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
            code="invalid_argument",
        )
    parsed_custom_metrics: list[dict] = []
    if custom_metric:
        for spec in custom_metric:
            if "=" not in spec:
                exit_with_error(
                    f"Invalid --custom-metric '{spec}'. Expected 'NAME=GREL_OR_PYTHON'.",
                    code="invalid_argument",
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
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


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
    except typer.Exit:
        raise
    except Exception as e:
        if is_already_exists_error(e):
            exit_with_error(
                f"Output dataset '{output_ds}' already exists in {project_key}.",
                code="already_exists",
                details=[
                    "Sync auto-creates its output dataset.",
                    f"Delete it first: dku dataset delete {output_ds} -P {project_key}",
                    "Or use a different --output-ds name.",
                ],
            )
        if is_connection_required_error(e):
            exit_with_error(
                f"Project {project_key} has no default managed connection.",
                code="no_default_connection",
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
        settings = recipe_obj.get_settings()
        if hasattr(settings, "set_payload"):
            settings.set_payload(body)
        else:
            settings.obj_payload = body
        settings.save()
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
        builder.build()
        _auto_apply_schema(proj, recipe_name)
        success(
            f"Created clustering_scoring recipe '{recipe_name}' in {project_key} (model={model})"
        )
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
        && dku recipe add-formula clean --output total --expr 'price * qty' -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("shaker", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created prepare recipe '{recipe_name}' in {project_key}")
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
    engine: str | None = typer.Option(
        None,
        "--engine",
        help="payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE.",
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
    engine_upper = _validate_engine_type(engine)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("sort", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
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
    action: str = typer.Option(
        "KEEP_ROW",
        "--action",
        help="KEEP_ROW (keep matching) or REMOVE_ROW (drop matching)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a filter recipe (rows matching the formula).

    Builds a Prepare recipe with a single FilterOnCustomFormula step.
    Prefer this over the Sampling recipe type, whose filter schema is unstable
    and which silently drops the filter expression on many DSS versions.

    Use instead of df[df.col > X] in Python.
    """
    project_key = resolve_project(project)
    action = action.upper()
    if action not in {"KEEP_ROW", "REMOVE_ROW"}:
        exit_with_error(
            f"Invalid --action '{action}'. Must be KEEP_ROW or REMOVE_ROW.",
            code="invalid_argument",
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("shaker", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
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
# These are top-level booleans in the DSS payload, not per-column
_TOP_LEVEL_WINDOW_TYPES = frozenset({"rank", "denseRank", "rowNumber"})
# These are per-column boolean flags in the values[] array
_COLUMN_WINDOW_TYPES = frozenset(
    {
        "lag",
        "lead",
        "lagDiff",
        "leadDiff",
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
_VALID_LAG_DATE_UNITS = frozenset(
    {
        "YEAR",
        "QUARTER",
        "MONTH",
        "WEEK",
        "DAY",
        "HOUR",
        "MINUTE",
        "SECOND",
        "MILLISECOND",
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


def _parse_offsets_spec(specs: list[str], flag: str) -> dict[str, list[int]]:
    """Parse 'COL:1,2,3' multi-offset specs."""
    parsed: dict[str, list[int]] = {}
    for spec in specs:
        if ":" not in spec:
            exit_with_error(
                f"Invalid {flag} '{spec}'. Expected 'COL:OFFSET[,OFFSET...]'.",
                code="invalid_argument",
            )
        col, offsets_str = spec.split(":", 1)
        offsets: list[int] = []
        for part in offsets_str.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                offsets.append(int(part))
            except ValueError:
                exit_with_error(
                    f"Invalid {flag} '{spec}': offsets must be integers (got '{part}').",
                    code="invalid_argument",
                )
        if not offsets:
            exit_with_error(
                f"Invalid {flag} '{spec}': at least one integer offset is required.",
                code="invalid_argument",
            )
        parsed[col.strip()] = offsets
    return parsed


def _apply_offset_specs(
    payload: dict, offsets_by_col: dict[str, list[int]], op: str
) -> None:
    """Apply lag/lead multi-offset specs to a Window payload values[] entry.

    DSS uses `lagValues` / `leadValues` as a comma-separated string on the
    per-column entry, plus the boolean `lag` / `lead` flag set to true.
    """
    if not offsets_by_col:
        return
    values = payload.setdefault("values", [])
    for col, offsets in offsets_by_col.items():
        col_entry = None
        for v in values:
            if v.get("column") == col:
                col_entry = v
                break
        if col_entry is None:
            col_entry = {"column": col, "value": False}
            values.append(col_entry)
        col_entry[op] = True
        col_entry[f"{op}Values"] = ",".join(str(o) for o in offsets)


def _apply_window_computations(
    payload: dict, computations: list[dict], recipe_name: str = ""
) -> None:
    """Apply parsed --compute specs to a Window recipe obj_payload.

    DSS Window recipes use two mechanisms:
    - Top-level booleans: rowNumber, rank, denseRank (global, not per-column)
    - values[] array: per-column flags like lag, lead, sum, avg, etc.

    **DSS does not support custom output column names for window computations.**
    Top-level computations produce fixed names (`rownumber`, `rank`, `denserank`).
    Per-column computations produce `${col}_${func}`. If the user provided a
    third colon segment (e.g. `rowNumber::my_rn`), we warn and point at the
    post-recipe rename workaround.
    """
    values = payload.setdefault("values", [])
    custom_names: list[tuple[str, str, str]] = []  # (type, source, requested_name)

    for comp in computations:
        comp_type = comp["type"]
        output_col = comp.get("outputColumn") or ""
        source_col = comp.get("column") or ""

        # Work out what DSS is going to name this column given the payload.
        if comp_type in _TOP_LEVEL_WINDOW_TYPES:
            dss_name = comp_type.lower()
            # Enable the top-level flag
            payload[comp_type] = True
        else:
            # Per-column flag — DSS generates `${col}_${func}`
            dss_name = f"{source_col}_{comp_type.lower()}"
            # Find or create the column entry in values[]
            col_entry = None
            for v in values:
                if v.get("column") == source_col:
                    col_entry = v
                    break
            if col_entry is None:
                col_entry = {"column": source_col, "value": False}
                values.append(col_entry)
            col_entry[comp_type] = True

        # If the user asked for a custom name that doesn't match what DSS
        # will produce, queue a warning.
        if output_col and output_col != dss_name:
            custom_names.append((comp_type, source_col, output_col))

    if custom_names:
        target = recipe_name or "<recipe>"
        warn(
            "DSS does not support custom output column names for window "
            "computations — the column will be named by the computation type, "
            "not by your third --compute segment."
        )
        for comp_type, source_col, requested in custom_names:
            actual = (
                comp_type.lower()
                if comp_type in _TOP_LEVEL_WINDOW_TYPES
                else f"{source_col}_{comp_type.lower()}"
            )
            info(
                f"  --compute '{comp_type}:{source_col}:{requested}' → column '{actual}'"
            )
        info(
            "To rename after build, chain a Prepare recipe: "
            f"dku recipe create rename_{target} -t prepare -i OUTPUT_DS --output-ds OUTPUT_DS_renamed -P PROJ "
            "&& dku recipe add-rename rename_<recipe> --from <actual> --to <desired> -P PROJ"
        )


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
            "Window computation. Format: TYPE:column[:output_column]. "
            "Column optional for rank/denseRank/rowNumber (use TYPE::output). "
            "Types: lag, lead, lagDiff, leadDiff, rank, denseRank, rowNumber, "
            "sum, avg, min, max, count, countDistinct, first, last, "
            "firstLastNotNull, stddev, concat, concatDistinct. "
            "lagDiff/leadDiff = current value MINUS lag/lead value (delta). "
            "firstLastNotNull = first non-null value in ordering (handles "
            "gappy timeseries). concat/concatDistinct = string aggregation "
            "(LISTAGG-equivalent within partition). "
            "NOTE: the output_column segment is advisory — DSS names columns by "
            "type (top-level: 'rownumber'/'rank'/'denserank') or "
            "'<col>_<type>' (per-column: 'price_lag', 'price_avg'). "
            "To force a different name, use --rename SRC:DST. Repeatable."
        ),
    ),
    lag_offsets: list[str] | None = typer.Option(
        None,
        "--lag-offsets",
        help=(
            "Multi-offset lag: 'COL:1,2,3' produces COL_lag1, COL_lag2, "
            "COL_lag3 in one recipe. Replaces the multi-recipe workaround "
            "for moving averages with N preceding values. Repeatable per "
            "column."
        ),
    ),
    lead_offsets: list[str] | None = typer.Option(
        None,
        "--lead-offsets",
        help="Multi-offset lead: 'COL:1,2,3'. Same shape as --lag-offsets.",
    ),
    lag_date_unit: str | None = typer.Option(
        None,
        "--lag-date-unit",
        help=(
            "When lagging/leading a date column, the unit DSS uses to compute the "
            "offset (DAY, HOUR, MONTH, ...). Sets dateDiffUnit on each affected "
            "values[] entry. Default in DSS: DAY."
        ),
    ),
    rename: list[str] | None = typer.Option(
        None,
        "--rename",
        help=(
            "Rename a generated window output column: 'SRC:DST'. Writes "
            "outputColumnNameOverrides. Use to disambiguate when two Window "
            "recipes feed the same downstream and would collide on default "
            "names. Repeatable."
        ),
    ),
    frame_preceding: int | None = typer.Option(
        None,
        "--frame-preceding",
        help="Window frame: number of preceding rows (sets precedingRows + limitPreceding=true).",
    ),
    frame_following: int | None = typer.Option(
        None,
        "--frame-following",
        help="Window frame: number of following rows (sets followingRows + limitFollowing=true).",
    ),
    frame_unbounded: bool = typer.Option(
        False,
        "--frame-unbounded",
        help="Window frame: unbounded preceding & following (sets enableLimits=false).",
    ),
    frame_mode: str | None = typer.Option(
        None,
        "--frame-mode",
        help=(
            "Frame interpretation: ROWS (default — N rows around current row) "
            "or RANGE (value-based on the order column — e.g. 'all rows whose "
            "order_date is within 30 days of current'). Sets "
            "windows[0].windowLimitMode. RANGE is the only way to express "
            "date-range windows without padding to one-row-per-day."
        ),
    ),
    range_lower: int | None = typer.Option(
        None,
        "--range-lower",
        help=(
            "Lower bound for --frame-mode RANGE (negative = past). E.g. "
            "--range-lower -30 with --order-key order_date counts rows whose "
            "order_date is up to 30 days before the current row's. Sets "
            "windows[0].windowLowerBound."
        ),
    ),
    range_upper: int | None = typer.Option(
        None,
        "--range-upper",
        help=(
            "Upper bound for --frame-mode RANGE. E.g. --range-upper 0 means "
            "'up to current row'. Sets windows[0].windowUpperBound."
        ),
    ),
    enable_cume_dist: bool = typer.Option(
        False,
        "--enable-cume-dist",
        help="Enable cumulative distribution column (`cumeDist`). Top-level boolean.",
    ),
    enable_ntile: int | None = typer.Option(
        None,
        "--enable-ntile",
        help="Enable NTILE bucketing with this many buckets. Sets ntile=true + ntileValues=N.",
    ),
    global_agg: bool = typer.Option(
        False,
        "--global-agg",
        help="Compute global aggregations (over all rows, not partition).",
    ),
    pre_filter: str | None = typer.Option(
        None,
        "--pre-filter",
        help="GREL formula applied BEFORE windowing (filters input rows).",
    ),
    post_filter: str | None = typer.Option(
        None,
        "--post-filter",
        help=(
            "GREL formula applied AFTER windowing. Common pattern: drop "
            "boundary rows after a Lag/Lead computation. Replaces a "
            "downstream Filter recipe."
        ),
    ),
    computed_col: list[str] | None = typer.Option(
        None,
        "--computed-col",
        help=(
            "Add a computed column before windowing: 'name=expr[:type]'. "
            "Repeatable. Default type: string."
        ),
    ),
    keep_columns: str | None = typer.Option(
        None,
        "--keep-columns",
        help=(
            "Project the output to only these input columns plus window "
            "outputs (comma-separated). Sets retrievedColumnsSelectionMode="
            "EXPLICIT. Replaces a downstream Prepare ColumnsSelector."
        ),
    ),
    engine: str | None = typer.Option(
        None,
        "--engine",
        help="payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Window recipe. Computes window/analytic functions (rank, lag, cumsum).

    Use this instead of df.groupby().transform() in Python.
    Use --partition-key for PARTITION BY, --order-key for ORDER BY,
    and --compute for window functions.

    Examples:
      dku recipe create-window ranked -i data --output-ds ranked -k stock \\
        --order-key date --compute 'rowNumber::rn' -P PROJ

      Multi-offset lag (replaces N separate Window recipes for an N-row MA):
        dku recipe create-window mw -i data --output-ds out -k stock \\
          --order-key date --lag-offsets 'price:1,2,3,4,5' -P PROJ

      Frame (3-row trailing average):
        dku recipe create-window roll -i data --output-ds out -k stock \\
          --order-key date --compute 'avg:price:' --frame-preceding 2 --frame-following 0 -P PROJ

      Avoid output-name collision between two Window recipes on same column:
        dku recipe create-window w1 ... --compute 'lag:Value:' --rename Value_lag1:lag1_w1
    """
    project_key = resolve_project(project)
    engine_upper = _validate_engine_type(engine)
    # Validate --compute format early (before any API calls)
    parsed_computations = _parse_compute_specs(compute) if compute else []
    parsed_lag_offsets = (
        _parse_offsets_spec(lag_offsets, "--lag-offsets") if lag_offsets else {}
    )
    parsed_lead_offsets = (
        _parse_offsets_spec(lead_offsets, "--lead-offsets") if lead_offsets else {}
    )
    parsed_renames: dict[str, str] = {}
    if rename:
        for entry in rename:
            if ":" not in entry:
                exit_with_error(
                    f"Invalid --rename '{entry}'. Expected 'SRC:DST'.",
                    code="invalid_argument",
                )
            src, dst = entry.split(":", 1)
            parsed_renames[src.strip()] = dst.strip()
    lag_date_unit_upper: str | None = None
    if lag_date_unit:
        lag_date_unit_upper = lag_date_unit.upper()
        if lag_date_unit_upper not in _VALID_LAG_DATE_UNITS:
            exit_with_error(
                f"--lag-date-unit '{lag_date_unit}' is not valid.",
                code="invalid_argument",
                details=[f"Valid: {', '.join(sorted(_VALID_LAG_DATE_UNITS))}"],
            )
    frame_mode_upper: str | None = None
    if frame_mode:
        frame_mode_upper = frame_mode.upper()
        if frame_mode_upper not in {"ROWS", "RANGE"}:
            exit_with_error(
                f"--frame-mode '{frame_mode}' is not valid.",
                code="invalid_argument",
                details=["Valid: ROWS, RANGE"],
            )
    if frame_mode_upper == "RANGE" and (range_lower is None and range_upper is None):
        exit_with_error(
            "--frame-mode RANGE requires --range-lower and/or --range-upper.",
            code="invalid_argument",
            details=[
                "Example: --frame-mode RANGE --range-lower -30 --range-upper 0 "
                "(last 30 days incl. current row, paired with --order-key date_col)."
            ],
        )
    if (
        range_lower is not None or range_upper is not None
    ) and frame_mode_upper != "RANGE":
        exit_with_error(
            "--range-lower/--range-upper require --frame-mode RANGE.",
            code="invalid_argument",
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder = proj.new_recipe("window", recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure partition/order keys and computations (WindowRecipeSettings has no helpers).
        # DSS reads partitioning and ordering from payload.windows[0] and requires the
        # enablePartitioning / enableOrdering boolean flags. Writing to the top-level
        # partitioningColumns / orders fields (without the enable flags inside windows[0])
        # silently produces GLOBAL aggregations instead of per-partition ones.
        needs_save = bool(
            partition_key
            or order_key
            or parsed_computations
            or parsed_lag_offsets
            or parsed_lead_offsets
            or parsed_renames
            or frame_preceding is not None
            or frame_following is not None
            or frame_unbounded
            or frame_mode_upper
            or enable_cume_dist
            or enable_ntile is not None
            or global_agg
            or pre_filter
            or post_filter
            or computed_col
            or keep_columns
            or engine_upper
            or lag_date_unit_upper
        )
        if needs_save:
            recipe_obj = proj.get_recipe(recipe_name)
            win_settings = recipe_obj.get_settings()
            payload = _get_recipe_payload(win_settings)

            # Ensure windows[0] exists — DSS's builder creates it by default, but
            # guard against an empty list just in case.
            windows = payload.setdefault("windows", [])
            if isinstance(windows, list):
                if not windows:
                    windows.append({})
                win0 = windows[0]
            else:
                win0 = None

            if partition_key:
                if isinstance(win0, dict):
                    win0["enablePartitioning"] = True
                    win0["partitioningColumns"] = list(partition_key)
                # Keep the top-level field for forward compat with DSS versions
                # that inspect it alongside windows[0].
                payload["partitioningColumns"] = [
                    {"column": col} for col in partition_key
                ]
                info(f"Partition by: {', '.join(partition_key)}")
            if order_key:
                parsed_orders = _parse_order_specs(order_key)
                if isinstance(win0, dict):
                    win0["enableOrdering"] = True
                    win0["orders"] = parsed_orders
                payload["orders"] = parsed_orders
                info(f"Order by: {', '.join(order_key)}")
            if parsed_computations:
                _apply_window_computations(
                    payload, parsed_computations, recipe_name=recipe_name
                )
                info(
                    f"Computations: {', '.join(c['type'] for c in parsed_computations)}"
                )
            if parsed_lag_offsets or parsed_lead_offsets:
                _apply_offset_specs(payload, parsed_lag_offsets, "lag")
                _apply_offset_specs(payload, parsed_lead_offsets, "lead")
                if parsed_lag_offsets:
                    info(
                        "Multi-lag: "
                        + ", ".join(f"{c}={o}" for c, o in parsed_lag_offsets.items())
                    )
                if parsed_lead_offsets:
                    info(
                        "Multi-lead: "
                        + ", ".join(f"{c}={o}" for c, o in parsed_lead_offsets.items())
                    )
            # --lag-date-unit applies dateDiffUnit to every per-column entry
            # that has lag/lead/lagDiff/leadDiff enabled (date columns lagged by
            # date unit, not row count).
            if lag_date_unit_upper:
                values = payload.setdefault("values", [])
                target_flags = {"lag", "lead", "lagDiff", "leadDiff"}
                for v in values:
                    if any(v.get(f) for f in target_flags):
                        v["dateDiffUnit"] = lag_date_unit_upper
                info(f"Lag date unit: {lag_date_unit_upper}")
            if parsed_renames:
                payload["outputColumnNameOverrides"] = dict(parsed_renames)
                info(
                    "Rename: "
                    + ", ".join(f"{s}→{d}" for s, d in parsed_renames.items())
                )
            if frame_mode_upper == "RANGE":
                if isinstance(win0, dict):
                    win0["enableLimits"] = True
                    win0["windowLimitMode"] = "RANGE"
                    if range_lower is not None:
                        win0["windowLowerBound"] = range_lower
                        win0["limitPreceding"] = True
                    if range_upper is not None:
                        win0["windowUpperBound"] = range_upper
                        win0["limitFollowing"] = True
                info(
                    f"Frame: RANGE mode, lower={range_lower}, upper={range_upper} "
                    "(value-based on order column)"
                )
            elif frame_unbounded:
                if isinstance(win0, dict):
                    win0["enableLimits"] = True
                    win0["limitPreceding"] = False
                    win0["limitFollowing"] = False
                payload["legacyUnboundedWindowStreamBehavior"] = True
                info("Frame: unbounded preceding & following (full partition)")
            else:
                if frame_preceding is not None and isinstance(win0, dict):
                    win0["enableLimits"] = True
                    win0["limitPreceding"] = True
                    win0["precedingRows"] = frame_preceding
                if frame_following is not None and isinstance(win0, dict):
                    win0["enableLimits"] = True
                    win0["limitFollowing"] = True
                    win0["followingRows"] = frame_following
                if frame_preceding is not None or frame_following is not None:
                    info(
                        f"Frame: preceding={frame_preceding}, following={frame_following}"
                    )
            if enable_cume_dist:
                payload["cumeDist"] = True
                info("Cumulative distribution enabled")
            if enable_ntile is not None:
                payload["ntile"] = True
                payload["ntileValues"] = enable_ntile
                info(f"NTILE: {enable_ntile} buckets")
            if global_agg:
                payload["globalAggregations"] = True
                info("Global aggregations enabled")
            _apply_pipeline_options(
                payload,
                pre_filter=pre_filter,
                post_filter=post_filter,
                computed_cols=computed_col,
                renames=None,  # already handled above via --rename
            )
            if pre_filter:
                info(f"Pre-filter: {pre_filter}")
            if post_filter:
                info(f"Post-filter: {post_filter}")
            if computed_col:
                info(f"Computed cols: {len(computed_col)}")
            if keep_columns:
                kept = [c.strip() for c in keep_columns.split(",") if c.strip()]
                payload["retrievedColumnsSelectionMode"] = "EXPLICIT"
                # DSS represents per-column kept-or-not as `values[]` boolean flags;
                # initialize a list of {column, value:true} so EXPLICIT mode has a
                # source of truth. Columns not listed default to value:false and
                # get dropped from the output.
                payload["retrievedColumns"] = [
                    {"column": c, "value": True} for c in kept
                ]
                info(f"Keep columns: {', '.join(kept)}")
            _apply_engine_type(payload, engine_upper)
            if engine_upper:
                info(f"Engine: {engine_upper}")
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
    output_ds: list[str] = typer.Option(
        ...,
        "--output-ds",
        "--output-dataset",
        help=(
            "Output dataset name. Repeatable — Split recipes need 2+ outputs. "
            "The 0-based position is the OUT_INDEX referenced by --value-split etc."
        ),
    ),
    mode: str = typer.Option(
        "VALUES",
        "--mode",
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
            "VALUES mode: 'VAL=OUT_INDEX' — rows where --column == VAL go to "
            "output at OUT_INDEX. Repeatable. Example: --value-split active=0 "
            "--value-split lapsed=1."
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
    engine: str | None = typer.Option(
        None,
        "--engine",
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
    mode_upper = mode.strip().upper()
    if mode_upper not in {"VALUES", "RANDOM", "RANGE", "FILTER", "CENTILE"}:
        exit_with_error(
            f"Invalid --mode '{mode}'.",
            code="invalid_argument",
            details=[
                "Use VALUES, RANDOM, RANGE, FILTER, or CENTILE.",
            ],
        )

    def _parse_index_kv(
        entries: list[str], flag: str, sep: str
    ) -> list[tuple[int, str]]:
        out = []
        for entry in entries:
            if sep not in entry:
                exit_with_error(
                    f"Invalid {flag} '{entry}'. Expected 'KEY{sep}OUT_INDEX' "
                    "(or 'OUT_INDEX:VALUE' for shares).",
                    code="invalid_argument",
                )
            head, tail = (
                entry.rsplit(sep, 1)
                if flag != "--random-share"
                else entry.split(sep, 1)
            )
            try:
                idx = int(tail) if flag != "--random-share" else int(head)
            except ValueError:
                exit_with_error(
                    f"Invalid output index in {flag} '{entry}'.",
                    code="invalid_argument",
                )
            if idx < 0 or idx >= len(output_ds):
                exit_with_error(
                    f"{flag} index {idx} out of range (0..{len(output_ds) - 1}).",
                    code="invalid_argument",
                )
            value = head if flag != "--random-share" else tail
            out.append((idx, value))
        return out

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
                splits.append(
                    {
                        "outputIndex": idx,
                        "filter": {
                            "enabled": True,
                            "distinct": False,
                            "uiData": {"mode": "CUSTOM", "expression": expr},
                        },
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
        engine_upper = _validate_engine_type(engine)
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
    engine: str | None = typer.Option(
        None,
        "--engine",
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
    engine_upper = _validate_engine_type(engine)
    if bottom is not None and bottom < 0:
        exit_with_error(
            "--bottom must be a non-negative integer.", code="invalid_argument"
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
    value_limit: str = typer.Option(
        "TOP_N",
        "--value-limit",
        help="Modality value limit: TOP_N (default, keeps top N by frequency), NO_LIMIT (keep every distinct column-key value), or AT_LEAST_N_OCC (keep only modalities with at least N occurrences). DSS crashes at build time if this field is missing from the payload.",
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
    modality_slugification: str | None = typer.Option(
        None,
        "--modality-slugification",
        help="Modality column-name slugification: NONE (default, preserves spaces/punct), SOFT_SLUGIFY, HARD_SLUGIFY. Sets payload.modalitySlugification.",
    ),
    no_sort_modalities: bool = typer.Option(
        False,
        "--no-sort-modalities",
        help="Disable alphabetic sort of pivot output columns. Sets payload.sortModalities=false.",
    ),
    identifier_mode: str | None = typer.Option(
        None,
        "--identifier-mode",
        help="Row-key selection mode: EXPLICIT (default — only --row-key columns) or AUTO (all input columns become identifiers). Sets payload.identifierColumnsSelection.",
    ),
    engine: str | None = typer.Option(
        None,
        "--engine",
        help="payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE.",
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
    _VALID_PIVOT_AGGS = frozenset(
        {
            "SUM",
            "AVG",
            "MIN",
            "MAX",
            "COUNT",
            "COUNT_DISTINCT",
            "CONCAT",
            "CONCAT_DISTINCT",
            "STDDEV",
            "FIRST",
            "LAST",
            "FIRST_LAST_NOT_NULL",
        }
    )
    _PIVOT_AGGS_REQUIRING_ORDER = frozenset({"FIRST", "LAST", "FIRST_LAST_NOT_NULL"})
    _VALID_VALUE_LIMITS = frozenset({"TOP_N", "NO_LIMIT", "AT_LEAST_N_OCC", "EXPLICIT"})
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
    _VALID_SLUGIFICATION = frozenset({"NONE", "SOFT_SLUGIFY", "HARD_SLUGIFY"})
    _VALID_IDENTIFIER_MODE = frozenset({"EXPLICIT", "AUTO", "ALL"})
    if agg_type and agg_type.upper() not in _VALID_PIVOT_AGGS:
        exit_with_error(
            f"Unknown aggregation type: '{agg_type}'.",
            code="invalid_argument",
            details=[f"Valid: {', '.join(sorted(_VALID_PIVOT_AGGS))}"],
        )
    if (
        agg_type
        and agg_type.upper() in _PIVOT_AGGS_REQUIRING_ORDER
        and not order_column
    ):
        exit_with_error(
            f"--agg-type {agg_type.upper()} requires --order-column.",
            code="invalid_argument",
            details=[
                "FIRST/LAST/FIRST_LAST_NOT_NULL need a deterministic ordering column.",
                "Example: --agg-type LAST --value-column reading --order-column timestamp",
            ],
        )
    if order_column and (
        not agg_type or agg_type.upper() not in _PIVOT_AGGS_REQUIRING_ORDER
    ):
        exit_with_error(
            "--order-column only applies when --agg-type is FIRST, LAST, or FIRST_LAST_NOT_NULL.",
            code="invalid_argument",
        )
    if value_limit.upper() not in _VALID_VALUE_LIMITS:
        exit_with_error(
            f"Unknown --value-limit: '{value_limit}'.",
            code="invalid_argument",
            details=[f"Valid: {', '.join(sorted(_VALID_VALUE_LIMITS))}"],
        )
    if value_limit.upper() == "EXPLICIT" and not explicit_values:
        exit_with_error(
            "--value-limit EXPLICIT requires at least one --explicit-values entry.",
            code="invalid_argument",
            details=[
                "Pass --explicit-values once per modality to whitelist, e.g.:",
                "  --value-limit EXPLICIT --explicit-values 2024 --explicit-values 2025",
            ],
        )
    if explicit_values and value_limit.upper() != "EXPLICIT":
        exit_with_error(
            "--explicit-values requires --value-limit EXPLICIT.",
            code="invalid_argument",
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
                    code="invalid_argument",
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
                    code="invalid_argument",
                    details=[f"Valid: {', '.join(sorted(_VALID_OTHER_AGGS))}"],
                )
            if agg_str in {"FIRST", "LAST", "FIRST_LAST_NOT_NULL"} and not order_col:
                exit_with_error(
                    f"--other-column {agg_str} on '{col}' requires an ORDER_COL: --other-column '{col}:{agg_str}:order_col'.",
                    code="invalid_argument",
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
        slug_upper = modality_slugification.upper()
        if slug_upper not in _VALID_SLUGIFICATION:
            exit_with_error(
                f"Invalid --modality-slugification '{modality_slugification}'.",
                code="invalid_argument",
                details=[f"Valid: {', '.join(sorted(_VALID_SLUGIFICATION))}"],
            )
    id_mode_upper: str | None = None
    if identifier_mode:
        id_mode_upper = identifier_mode.upper()
        if id_mode_upper == "ALL":
            id_mode_upper = "AUTO"
        if id_mode_upper not in _VALID_IDENTIFIER_MODE:
            exit_with_error(
                f"Invalid --identifier-mode '{identifier_mode}'.",
                code="invalid_argument",
                details=["Valid: EXPLICIT, AUTO"],
            )
    project_key = resolve_project(project)
    engine_upper = _validate_engine_type(engine)
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
            agg_fn = agg_type.upper() if agg_type else "SUM"
            pivot["valueColumns"] = [
                _build_value_column(value_column, agg_fn, order_column)
            ]
        elif agg_type:
            # agg_type without value_column — toggle the boolean flag on existing entries
            flag = _AGG_FLAG_MAP[agg_type.upper()]
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
        vl_upper = value_limit.upper()
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
    partition_selection: str | None = typer.Option(
        None,
        "--partition-selection",
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
    method_upper = method.upper()
    valid_methods = {
        "RANDOM_FIXED_NB",
        "RANDOM_FIXED_RATIO",
        "HEAD_SEQUENTIAL",
        "STRATIFIED",
        "CLASS_REBALANCE",
        "FULL",
    }
    if method_upper not in valid_methods:
        exit_with_error(
            f"Invalid --method '{method}'.",
            code="invalid_argument",
            details=[f"Valid: {', '.join(sorted(valid_methods))}"],
        )
    valid_partition_selections = {"ALL", "LATEST_N", "EXPLICIT"}
    partition_selection_upper: str | None = None
    if partition_selection:
        partition_selection_upper = partition_selection.upper()
        if partition_selection_upper not in valid_partition_selections:
            exit_with_error(
                f"Invalid --partition-selection '{partition_selection}'.",
                code="invalid_argument",
                details=[f"Valid: {', '.join(sorted(valid_partition_selections))}"],
            )
    if partition_selection_upper == "LATEST_N" and latest_partitions is None:
        exit_with_error(
            "--partition-selection LATEST_N requires --latest-partitions N.",
            code="invalid_argument",
        )
    if latest_partitions is not None and partition_selection_upper not in {
        "LATEST_N",
        None,
    }:
        exit_with_error(
            "--latest-partitions only applies with --partition-selection LATEST_N.",
            code="invalid_argument",
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
        help="Column name to embed (required for dataset embedding). Maps to payload.knowledgeColumn.",
    ),
    metadata_col: list[str] | None = typer.Option(
        None,
        "--metadata-col",
        help=(
            "Carry-through column kept alongside each chunk for downstream RAG "
            "retrieval (source attribution). Maps to payload.metadataColumns[]. "
            "Repeatable: --metadata-col title --metadata-col url. "
            "Without this, retrieved chunks lose their source — RAG citations break."
        ),
    ),
    chunk_size: int | None = typer.Option(
        None,
        "--chunk-size",
        help="Chunk size in characters. Sets payload.chunkSizeCharacters.",
    ),
    chunk_overlap: int | None = typer.Option(
        None,
        "--chunk-overlap",
        help="Chunk overlap in characters. Sets payload.chunkOverlapCharacters.",
    ),
    document_splitting_mode: str | None = typer.Option(
        None,
        "--document-splitting-mode",
        help="How records are chunked. e.g. CHARACTERS_BASED (default), SECTIONS_BASED. Sets payload.documentSplittingMode.",
    ),
    vector_store_update_method: str | None = typer.Option(
        None,
        "--vector-store-update-method",
        help="How the vector store reacts to recipe re-runs (SMART_OVERWRITE, FULL_REBUILD, OVERWRITE). Sets payload.vectorStoreUpdateMethod.",
    ),
    clear_vector_store: bool = typer.Option(
        False,
        "--clear-vector-store",
        help="Wipe the vector store before the next build (one-shot). Sets payload.clearVectorStore=true.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Embed Dataset recipe (embeds text columns into a Knowledge Bank).

    Use --embed-column to set which text column to embed. If omitted, you must
    configure the embedding column via set-definition before building the KB.

    The right field is `knowledgeColumn` (NOT `embedColumn`); the CLI handles
    that mapping. For source attribution in RAG retrieval, pass --metadata-col
    for every column you want carried alongside each chunk (title, url, etc.).
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

        any_payload_change = bool(
            embed_column
            or metadata_col
            or chunk_size is not None
            or chunk_overlap is not None
            or document_splitting_mode is not None
            or vector_store_update_method is not None
            or clear_vector_store
        )
        if any_payload_change:
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            payload = _get_recipe_payload(settings)
            if embed_column:
                payload["knowledgeColumn"] = embed_column
                info(f"Embedding column set to '{embed_column}'")
            if metadata_col:
                payload["metadataColumns"] = list(metadata_col)
                info(f"Metadata columns: {', '.join(metadata_col)}")
            if chunk_size is not None:
                payload["chunkSizeCharacters"] = chunk_size
            if chunk_overlap is not None:
                payload["chunkOverlapCharacters"] = chunk_overlap
            if document_splitting_mode is not None:
                payload["documentSplittingMode"] = document_splitting_mode
            if vector_store_update_method is not None:
                payload["vectorStoreUpdateMethod"] = vector_store_update_method
            if clear_vector_store:
                payload["clearVectorStore"] = True
            settings.save()
        if not embed_column:
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
        ...,
        "--input",
        "-i",
        help="Input FilesInFolder dataset wrapping a managed folder of documents (build one with `dku folder create-dataset`).",
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
    chunk_size: int | None = typer.Option(
        None,
        "--chunk-size",
        help="Chunk size in characters (default 3000). Sets payload.chunkSizeCharacters.",
    ),
    chunk_overlap: int | None = typer.Option(
        None,
        "--chunk-overlap",
        help="Chunk overlap in characters (default 120). Sets payload.chunkOverlapCharacters.",
    ),
    vector_store_update_method: str | None = typer.Option(
        None,
        "--vector-store-update-method",
        help="How the vector store reacts to recipe re-runs. Default: SMART_OVERWRITE (re-embed only changed docs). Other DSS values include FULL_REBUILD, OVERWRITE.",
    ),
    clear_vector_store: bool = typer.Option(
        False,
        "--clear-vector-store",
        help="Wipe the existing vector store contents before the next build (one-shot).",
    ),
    document_splitting_mode: str | None = typer.Option(
        None,
        "--document-splitting-mode",
        help="How documents are chunked. Default: CHARACTERS_BASED. DSS also exposes SECTIONS_BASED for structured PDFs.",
    ),
    extraction_mode: str | None = typer.Option(
        None,
        "--extraction-mode",
        help="Document extraction strategy. MANAGED_TEXT_ONLY (default — managed text-only) or CUSTOM_RULES (per-file-type rules in params.rules). DSS normalises any other value to CUSTOM_RULES — use that path when chaining a VLM, then template the rules with set-definition.",
    ),
    rule: str | None = typer.Option(
        None,
        "--rule",
        help=(
            "Custom-rules JSON: literal, @file.json, or '-' stdin. "
            "Sets params.rules[]. Implies extraction-mode CUSTOM_RULES if not set."
        ),
    ),
    input_folder: str | None = typer.Option(
        None,
        "--input-folder",
        help="Optional managed-folder ID to attach as 'documents' input role (in addition to the FilesInFolder dataset).",
    ),
    output_images_folder: str | None = typer.Option(
        None,
        "--output-images-folder",
        help="Managed-folder ID where extracted page images are written (used by VLM/SECTIONS_BASED modes).",
    ),
    default_vlm: str | None = typer.Option(
        None,
        "--default-vlm",
        help="Default VLM ID applied across all rules (instead of per-rule). Sets payload.defaultVlmId.",
    ),
    rule_vlm: str | None = typer.Option(
        None,
        "--rule-vlm",
        help="VLM ID to inject as the vlmId on every rule (overrides any per-rule vlm). Useful with --rule @file.json.",
    ),
    rule_prompt: str | None = typer.Option(
        None,
        "--rule-prompt",
        help="Per-rule VLM prompt: literal, @file.txt, or '-' stdin. Injects 'prompt' into every rule.",
    ),
    ocr_engine: str | None = typer.Option(
        None,
        "--ocr-engine",
        help="OCR engine for scanned PDFs (TESSERACT, AZURE_DOCUMENT_INTELLIGENCE, etc.). Sets payload.ocrEngine.",
    ),
    ocr_languages: str | None = typer.Option(
        None,
        "--ocr-languages",
        help="Comma-separated OCR language codes (eng,fra,...). Sets payload.ocrLanguages[].",
    ),
    max_section_depth: int | None = typer.Option(
        None,
        "--max-section-depth",
        help="SECTIONS_BASED splitting: maximum nested heading depth. Sets payload.maxSectionDepth.",
    ),
    enable_image_classification_filtering: bool = typer.Option(
        False,
        "--enable-image-classification-filtering",
        help="Filter out images that don't pass classification threshold. Sets payload.enableImageClassificationFiltering=true.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Embed Documents recipe (extracts + chunks + embeds documents into a KB).

    The input must be a FilesInFolder dataset that points at a managed folder
    of documents — `dku folder create-dataset` builds that wrapper. Pass `--vlm`
    only when documents contain figures/tables that warrant a vision pass; for
    pure text the default text extractor is faster and cheaper.

    Knob mapping (recipe payload fields):
      --chunk-size                  → payload.chunkSizeCharacters
      --chunk-overlap               → payload.chunkOverlapCharacters
      --vector-store-update-method  → payload.vectorStoreUpdateMethod
      --clear-vector-store          → payload.clearVectorStore (one-shot wipe)
      --document-splitting-mode     → payload.documentSplittingMode
      --extraction-mode             → params.extractionMode

    Example:
        dku recipe create-embed-docs index_pdfs -i pdf_files \\
            --output-kb pdf_kb --embedding-llm openai:openai:text-embedding-3-small \\
            --chunk-size 1500 --chunk-overlap 150 \\
            --vector-store-update-method SMART_OVERWRITE -P PROJ
    """
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

        # Parse --rule body once (and infer extraction_mode if user didn't set it)
        parsed_rules: list[dict] | None = None
        effective_extraction_mode = extraction_mode
        if rule:
            rule_body = read_json_input(rule)
            if isinstance(rule_body, dict):
                parsed_rules = [rule_body]
            elif isinstance(rule_body, list):
                parsed_rules = rule_body
            else:
                exit_with_error(
                    "--rule must be a JSON object or array.",
                    code="invalid_argument",
                )
            if effective_extraction_mode is None:
                effective_extraction_mode = "CUSTOM_RULES"

        # Inject rule-level overrides if requested
        rule_prompt_body = read_text_input(rule_prompt) if rule_prompt else None
        if parsed_rules and (rule_vlm or rule_prompt_body):
            for r in parsed_rules:
                if rule_vlm:
                    r["vlmId"] = rule_vlm
                if rule_prompt_body:
                    r["prompt"] = rule_prompt_body

        # Apply post-build payload knobs.
        any_payload_change = (
            chunk_size is not None
            or chunk_overlap is not None
            or vector_store_update_method is not None
            or clear_vector_store
            or document_splitting_mode is not None
            or default_vlm is not None
            or ocr_engine is not None
            or ocr_languages is not None
            or max_section_depth is not None
            or enable_image_classification_filtering
            or output_images_folder is not None
        )
        any_params_change = (
            effective_extraction_mode is not None or parsed_rules is not None
        )
        any_io_change = input_folder is not None or output_images_folder is not None
        if any_payload_change or any_params_change or any_io_change:
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            if any_payload_change:
                payload = _get_recipe_payload(settings)
                if chunk_size is not None:
                    payload["chunkSizeCharacters"] = chunk_size
                if chunk_overlap is not None:
                    payload["chunkOverlapCharacters"] = chunk_overlap
                if vector_store_update_method is not None:
                    payload["vectorStoreUpdateMethod"] = vector_store_update_method
                if clear_vector_store:
                    payload["clearVectorStore"] = True
                if document_splitting_mode is not None:
                    payload["documentSplittingMode"] = document_splitting_mode
                if default_vlm is not None:
                    payload["defaultVlmId"] = default_vlm
                if ocr_engine is not None:
                    payload["ocrEngine"] = ocr_engine
                if ocr_languages is not None:
                    payload["ocrLanguages"] = [
                        lang.strip()
                        for lang in ocr_languages.split(",")
                        if lang.strip()
                    ]
                if max_section_depth is not None:
                    payload["maxSectionDepth"] = max_section_depth
                if enable_image_classification_filtering:
                    payload["enableImageClassificationFiltering"] = True
            if any_params_change:
                raw_def = settings.get_recipe_raw_definition()
                params = raw_def.setdefault("params", {})
                if effective_extraction_mode is not None:
                    params["extractionMode"] = effective_extraction_mode
                if parsed_rules is not None:
                    params["rules"] = parsed_rules
            if any_io_change:
                raw_def = settings.get_recipe_raw_definition()
                if input_folder is not None:
                    inputs = raw_def.setdefault("inputs", {})
                    inputs.setdefault("documents", {"items": []})["items"].append(
                        {"ref": input_folder}
                    )
                if output_images_folder is not None:
                    outputs = raw_def.setdefault("outputs", {})
                    outputs.setdefault("images", {"items": []})["items"].append(
                        {"ref": output_images_folder, "appendMode": False}
                    )
            settings.save()
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
    bleu_tokenizer: str | None = typer.Option(
        None,
        "--bleu-tokenizer",
        help="BLEU/ROUGE tokenizer (e.g. 'whitespace', '13a', 'intl'). Sets payload.bleuTokenizer.",
    ),
    bertscore_model: str | None = typer.Option(
        None,
        "--bertscore-model",
        help="HuggingFace model used by BERTScore. Sets payload.bertScoreModel.",
    ),
    input_format: str | None = typer.Option(
        None,
        "--input-format",
        help="Input record format: SINGLE_TURN (default), CHAT, etc. Sets payload.inputFormat.",
    ),
    fail_on_errors: bool = typer.Option(
        False,
        "--fail-on-errors",
        help="Fail the build on metric errors instead of skipping. Sets payload.failOnErrors=true.",
    ),
    temperature: float | None = typer.Option(
        None,
        "--temperature",
        help="Completion temperature for LLM-judged metrics. Sets payload.completionSettings.temperature.",
    ),
    max_records: int | None = typer.Option(
        None,
        "--max-records",
        help="Cap the number of input records evaluated. Sets payload.sampling.selection.maxRecords.",
    ),
    sampling_method: str | None = typer.Option(
        None,
        "--sampling-method",
        help="Input sampling method (HEAD_SEQUENTIAL, RANDOM_FIXED_NB, ...). Sets payload.sampling.selection.samplingMethod.",
    ),
    seed: int | None = typer.Option(
        None,
        "--seed",
        help="Random seed for sampling reproducibility. Sets payload.sampling.selection.seed.",
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
            recipe = _create_eval_recipe(
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
                        f"Create one first: dku evaluation-store create MY_STORE --flavor LLM -P {project_key}",
                        f"Then retry: dku recipe create-llm-eval {recipe_name} --eval-store MY_STORE --input {input_ds} -P {project_key}",
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
        if bleu_tokenizer:
            payload["bleuTokenizer"] = bleu_tokenizer
        if bertscore_model:
            payload["bertScoreModel"] = bertscore_model
        if input_format:
            payload["inputFormat"] = input_format
        if fail_on_errors:
            payload["failOnErrors"] = True
        if temperature is not None:
            payload.setdefault("completionSettings", {})["temperature"] = temperature
        if max_records is not None or sampling_method is not None or seed is not None:
            sampling = payload.setdefault("sampling", {}).setdefault("selection", {})
            if max_records is not None:
                sampling["maxRecords"] = max_records
            if sampling_method is not None:
                sampling["samplingMethod"] = sampling_method
            if seed is not None:
                sampling["seed"] = seed
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
                bleu_tokenizer,
                bertscore_model,
                input_format,
                fail_on_errors,
                temperature is not None,
                max_records is not None,
                sampling_method is not None,
                seed is not None,
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
            recipe = _create_eval_recipe(
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
                        f"Create one first: dku evaluation-store create MY_STORE --flavor AGENT -P {project_key}",
                        f"Then retry: dku recipe create-agent-eval {recipe_name} --eval-store MY_STORE --input {input_ds} -P {project_key}",
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
    statements_mode: str | None = typer.Option(
        None,
        "--statements-mode",
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
    _VALID_STATEMENTS_MODES = frozenset({"SPLIT", "UNIFIED", "RAW"})
    if statements_mode is not None:
        sm = statements_mode.upper()
        if sm not in _VALID_STATEMENTS_MODES:
            exit_with_error(
                f"Invalid --statements-mode '{statements_mode}'.",
                code="invalid_argument",
                details=[f"Valid: {', '.join(sorted(_VALID_STATEMENTS_MODES))}"],
            )
    else:
        sm = None
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
        rp = settings.get_recipe_params() or {}
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
        ..., "--completion-llm", help="Completion LLM ID."
    ),
    prompt_mode: str = typer.Option(
        "STRUCTURED",
        "--prompt-mode",
        help=(
            "Prompt structure: STRUCTURED (default — few-shot, single-brace {var} "
            "substitutions in --structured-prefix), TEXT (free-form, double-brace "
            "{{var}} in --prompt), or CHAT (multi-turn). "
            "Different modes use different placeholder syntax AND different storage "
            "paths in the payload."
        ),
    ),
    prompt_text: str | None = typer.Option(
        None,
        "--prompt",
        help=(
            "TEXT-mode prompt body. Supports literal, @file.txt, or '-' stdin. "
            "Stored at payload.prompt. {{var}} placeholders substitute from input columns "
            "or --input-var mappings."
        ),
    ),
    structured_prefix: str | None = typer.Option(
        None,
        "--structured-prefix",
        help=(
            "STRUCTURED-mode prompt prefix (NOT payload.prompt — DSS stores this at "
            "payload.prompt.structuredPromptPrefix). Single-brace {var} placeholders. "
            "Literal, @file.txt, or '-' stdin."
        ),
    ),
    structured_example: list[str] | None = typer.Option(
        None,
        "--structured-example",
        help=(
            "STRUCTURED-mode few-shot example, format 'INPUT||OUTPUT'. "
            "Repeatable. Appended to payload.prompt.structuredExamples[]."
        ),
    ),
    input_var: list[str] | None = typer.Option(
        None,
        "--input-var",
        help=(
            "Input variable mapping for placeholder substitution: 'NAME=COLUMN[:TYPE]'. "
            "Repeatable. TYPE defaults to STRING. Example: --input-var customer=customer_name."
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

    Different prompt modes use different storage and placeholder syntax — the
    CLI maps them so agents don't fall into the trap of writing payload.prompt
    for STRUCTURED mode (which silently produces an empty no-op recipe).

    STRUCTURED mode (default — most reliable for canned tasks):
      dku recipe create-prompt summarise -i articles --output-ds summaries \\
        --completion-llm openai:gpt-4o-mini \\
        --structured-prefix 'Summarize: {body}' \\
        --input-var body=article_body \\
        --response-format json -P PROJ

    TEXT mode (use {{var}} placeholders):
      dku recipe create-prompt q -i prompts --output-ds answers \\
        --completion-llm openai:gpt-4o-mini --prompt-mode TEXT \\
        --prompt 'Answer: {{question}}' \\
        --input-var question=user_question -P PROJ
    """
    _VALID_PROMPT_MODES = {"STRUCTURED", "TEXT", "CHAT"}
    pm_upper = prompt_mode.upper()
    if pm_upper not in _VALID_PROMPT_MODES:
        exit_with_error(
            f"Invalid --prompt-mode '{prompt_mode}'.",
            code="invalid_argument",
            details=[f"Valid: {', '.join(sorted(_VALID_PROMPT_MODES))}"],
        )
    if pm_upper == "STRUCTURED" and not structured_prefix:
        exit_with_error(
            "STRUCTURED mode requires --structured-prefix.",
            code="invalid_argument",
            details=[
                "Pass --structured-prefix '...{var}...' or switch to --prompt-mode TEXT and pass --prompt."
            ],
        )
    if pm_upper == "TEXT" and not prompt_text:
        exit_with_error(
            "TEXT mode requires --prompt.",
            code="invalid_argument",
            details=[
                "Pass --prompt '...{{var}}...' or switch to --prompt-mode STRUCTURED."
            ],
        )

    parsed_input_vars: list[dict] = []
    if input_var:
        for spec in input_var:
            if "=" not in spec:
                exit_with_error(
                    f"Invalid --input-var '{spec}'. Expected 'NAME=COLUMN[:TYPE]'.",
                    code="invalid_argument",
                )
            name, rhs = spec.split("=", 1)
            if ":" in rhs:
                col, type_ = rhs.split(":", 1)
                type_ = type_.strip().upper() or "STRING"
            else:
                col, type_ = rhs, "STRING"
            parsed_input_vars.append(
                {"name": name.strip(), "column": col.strip(), "type": type_}
            )

    parsed_examples: list[dict] = []
    if structured_example:
        for spec in structured_example:
            if "||" not in spec:
                exit_with_error(
                    f"Invalid --structured-example '{spec}'. Expected 'INPUT||OUTPUT'.",
                    code="invalid_argument",
                )
            ex_in, ex_out = spec.split("||", 1)
            parsed_examples.append({"input": ex_in.strip(), "output": ex_out.strip()})

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
        recipe_obj = _raw_create_recipe(
            proj,
            "prompt",
            recipe_name,
            inputs=[(input_ds, "main")],
            outputs=[(output_ds, "main")],
        )
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)
        payload["completionLLMId"] = completion_llm
        payload["promptMode"] = pm_upper

        if pm_upper == "STRUCTURED":
            prefix_body = (
                read_text_input(structured_prefix) if structured_prefix else ""
            )
            payload["prompt"] = {
                "structuredPromptPrefix": prefix_body,
                "structuredExamples": parsed_examples,
            }
        elif pm_upper == "TEXT":
            text_body = read_text_input(prompt_text) if prompt_text else ""
            payload["prompt"] = text_body

        if parsed_input_vars:
            payload["inputs"] = parsed_input_vars
        if rf_normalized:
            payload.setdefault("completionSettings", {})["responseFormat"] = (
                rf_normalized
            )
        # Force payload serialisation — DSS rawCreation returns payload=None
        # and the SDK's save() only emits payload when _obj_payload was changed
        # via the obj_payload setter (which doesn't exist publicly).
        if hasattr(settings, "str_payload"):
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

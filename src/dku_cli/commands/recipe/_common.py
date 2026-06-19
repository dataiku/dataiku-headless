"""dku recipe — list, get, get-definition, run, create, delete, set-code, get-code, set-definition, add-input, add-output, rename, status, plus GenAI recipe creation."""

from __future__ import annotations

# ruff: noqa: F401

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
    resolve_build_output_types,
    resolve_folder,
    resolve_project,
    resolve_recipe_input_ref,
    resolve_saved_model,
)
from dku_cli.output import (
    filter_fields,
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS recipes.")


def recipe_created_hint(recipe_name: str, project_key: str) -> None:
    hint(f"dku recipe run {recipe_name} -P {project_key}")


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
                status=3,
                details=[
                    f"List recipes: dku recipe list -P {project_key}",
                    f"Inspect the project flow: dku project inspect {project_key}",
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


def _get_or_create_recipe_params(settings) -> dict:
    """Mutable `params` dict ATTACHED to the recipe definition.

    `settings.get_recipe_params()` returns None when the definition has no
    `params` key (e.g. right after a bare code-recipe create), so the common
    `get_recipe_params() or {}` idiom hands back a DETACHED dict: every write
    lands in it, `settings.save()` persists nothing, and the command reports
    success. Seed the key in the raw definition instead.
    """
    raw = settings.get_recipe_raw_definition()
    params = raw.get("params")
    if not isinstance(params, dict):
        params = {}
        raw["params"] = params
    return params


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
            )
        src, dst = spec.split(":", 1)
        out[src.strip()] = dst.strip()
    return out


def _enum_value(member) -> str | None:
    """Unwrap an optional enum option to its payload string (None-safe).

    Typer hands command bodies the enum MEMBER for ``Enum | None`` options;
    DSS payloads need the canonical ``.value`` string. One helper instead of
    repeating ``x.value if x is not None else None`` at every call site.
    """
    return member.value if member is not None else None


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
                details=[
                    f"Add steps first: dku recipe add-step {recipe_name} --type <TYPE> --params '<JSON>' -P <PROJ>"
                ],
            )
        else:
            exit_with_error(
                f"Step index {index} out of range. Recipe '{recipe_name}' has {count} steps (0–{count - 1}).",
                details=[f"List steps: dku recipe list-steps {recipe_name} -P <PROJ>"],
            )


# Shared visual recipe creation helpers.
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


def _ensure_output_folder(proj, output_folder: str) -> str:
    """Resolve a managed folder by id-or-name, auto-creating it if missing.

    Returns the resolved folder id. ``output_folder`` may be either an existing
    folder's id, an existing folder's name, or a brand-new name (in which case
    the folder is created). Used by the folder-output visual recipes
    (create-merge-folder / create-download / create-export).
    """
    folders_listing = proj.list_managed_folders()
    existing = {f.get("id"): f for f in folders_listing}
    existing_names = {f.get("name"): f for f in folders_listing}
    if output_folder in existing:
        return output_folder
    if output_folder in existing_names:
        return existing_names[output_folder].get("id")
    out_id = proj.create_managed_folder(output_folder).id
    info(f"Auto-created destination folder '{output_folder}' (id={out_id})")
    return out_id


def _wire_single_output(
    client, proj, builder, output_ds: str, project_key: str, connection: str | None
) -> None:
    """Wire a visual recipe builder's single output dataset.

    With --connection, the output is created as a managed dataset on that
    connection via SingleOutputRecipeCreator.with_new_output (one-call
    in-database pipelines, e.g. Snowflake pushdown). Without it, the output is
    auto-created on the default managed connection and attached.
    """
    if connection:
        builder.with_new_output(output_ds, connection)
    else:
        _ensure_output_dataset(client, proj, output_ds, project_key)
        builder.with_existing_output(output_ds)


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


def _reconcile_scoring_name(recipe, requested_name: str) -> str:
    """Rename a freshly-built scoring recipe from DSS's auto name to the requested one.

    DSS auto-names ML scoring recipes ``score_<input>`` server-side, IGNORING the
    name passed to the recipe creator. Left unreconciled this is a silent footgun:
    every follow-up call (``_auto_apply_schema``, ``proj.get_recipe(name)``, the
    agent's later ``recipe run``) targets a recipe that does not exist under the
    requested name, so the output schema is never applied and the first build dies
    with ``Schema incompatibility: N columns in data, 0 columns in target dataset``.

    ``recipe`` is the handle returned by ``builder.build()``; it carries the REAL
    name. Rename it to the requested name so the agent can operate on the recipe by
    the name it chose, and return the name callers should use downstream.
    """
    created = getattr(recipe, "recipe_name", None) or getattr(recipe, "name", None)
    if created and created != requested_name:
        try:
            recipe.rename(requested_name)
        except Exception as exc:  # noqa: BLE001
            warn(
                f"DSS created the scoring recipe as '{created}' (could not rename to "
                f"'{requested_name}': {exc}). Use '{created}' for follow-up commands."
            )
            return created
    return requested_name


def _build_scoring_recipe(builder, requested_name: str) -> str:
    """Build a scoring recipe and reconcile DSS's auto-generated recipe name."""
    return _reconcile_scoring_name(builder.build(), requested_name)


# Shared low-level recipe creation helper.
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


# Explicit public surface for `from ._common import *`. Lists exactly the
# symbols the sibling recipe modules import (re-exported third-party / stdlib
# helpers plus the shared module-level helpers and constants). Keep this in sync
# when a recipe submodule starts or stops using a `_common` symbol — a glob over
# globals() would silently re-export every import and mask accidental shadowing.
__all__ = [
    # Re-exported stdlib / third-party so submodules can `from ._common import *`.
    "Path",
    "json",
    "sys",
    "time",
    "typer",
    # dataikuapi recipe creators (also imported explicitly by __init__.py).
    "FuzzyJoinRecipeCreator",
    "GeoJoinRecipeCreator",
    # Error helpers.
    "exit_with_error",
    "handle_api_error",
    "is_already_exists_error",
    "is_connection_required_error",
    "is_not_found_error",
    # Project / client / input helpers.
    "get_client_from_ctx",
    "read_json_input",
    "read_text_input",
    "resolve_build_output_types",
    "resolve_folder",
    "resolve_project",
    "resolve_recipe_input_ref",
    "resolve_saved_model",
    # Output helpers.
    "filter_fields",
    "info",
    "render",
    "render_raw",
    "resolve_output_format",
    "recipe_created_hint",
    "success",
    "warn",
    # The shared Typer app.
    "app",
    # Recipe-type constants.
    "_INPUT_OPTIONAL_TYPES",
    "_KNOWN_RECIPE_TYPES",
    "_SCORING_RECIPE_TYPES",
    "_TEXT_PAYLOAD_RECIPE_TYPES",
    "_VISUAL_RECIPE_TYPES",
    # Shared recipe helpers.
    "_apply_engine_type",
    "_apply_pipeline_options",
    "_auto_apply_schema",
    "_build_pipeline_filter",
    "_build_scoring_recipe",
    "_create_eval_recipe",
    "_deep_merge_dict",
    "_ensure_output_dataset",
    "_get_or_create_recipe_params",
    "_ensure_output_folder",
    "_enum_value",
    "_ensure_steps_array",
    "_get_prepare_settings",
    "_get_recipe_or_exit",
    "_get_recipe_payload",
    "_get_text_payload",
    "_is_plugin_recipe_type",
    "_is_text_payload_recipe",
    "_parse_computed_cols",
    "_parse_order_specs",
    "_raw_create_recipe",
    "_reconcile_scoring_name",
    "_require_existing_dataset",
    "_validate_step_index",
    "_wire_single_output",
]

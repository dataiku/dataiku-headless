"""Generic recipe management tools (create/read/update existing recipes)."""

from __future__ import annotations

import inspect
from typing import Any

from dataikuapi.dss.recipe import DSSRecipeCreator
from fastmcp import Context

from .. import config, mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.parsing import (
    coerce_json_array as _coerce_json_array,
    coerce_json_object as _coerce_json_object,
    deep_merge_dict as _deep_merge_dict,
    get_bool_value as _get_bool_value,
)
from .utils.serialization import columnar, compact_json, is_empty
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_list as _require_non_empty_list,
)

CODE_RECIPE_TYPES = {
    "python",
    "r",
    "sql_query",
    "sql_script",
    "pyspark",
    "sparkr",
    "spark_scala",
    "shell",
    "spark_sql_query",
    "cpython",
    "ksql",
    "streaming_spark_scala",
}

# Recipe types whose SDK builder accepts role= on with_input/with_output directly.
FLEXIBLE_BUILDER_TYPES = {"python"}

# Output roles that map to dedicated builder/settings methods rather than with_output().
SPECIAL_OUTPUT_ROLES = {"metrics", "evaluationStore", "knowledge_bank"}


def _normalize_output_specs(outputs: list) -> list[dict[str, Any]]:
    outputs = _require_non_empty_list(outputs, "outputs")

    normalized: list[dict[str, Any]] = []
    for i, output in enumerate(outputs):
        if isinstance(output, str):
            normalized.append({"name": output, "appendMode": False, "role": "main"})
            continue
        try:
            name = output.get("name")
            role = output.get("role", "main")
            append = output.get(
                "appendMode", role == "metrics"
            )  # metrics default true; all others false
        except Exception as exc:
            raise ValueError(
                f"'outputs[{i}]' must be either a string or an object with name/appendMode/role"
            ) from exc
        normalized_output = dict(output)
        normalized_output.update({"name": name, "appendMode": append, "role": role})
        normalized.append(normalized_output)

    return normalized


def _normalize_input_specs(inputs: list) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for i, input_spec in enumerate(inputs):
        if isinstance(input_spec, str):
            normalized.append(
                {"name": input_spec, "role": "main", "partition_deps": []}
            )
            continue
        try:
            name = input_spec.get("name")
            role = input_spec.get("role", "main")
            partition_deps = input_spec.get("partition_deps", [])
        except Exception as exc:
            raise ValueError(
                f"'inputs[{i}]' must be either a string or an object with name/role/partition_deps"
            ) from exc
        normalized_input = dict(input_spec)
        normalized_input.update(
            {"name": name, "role": role, "partition_deps": list(partition_deps)}
        )
        normalized.append(normalized_input)

    return normalized


def _apply_special_output_to_builder(builder, output: dict[str, Any]) -> None:
    # Some recipe outputs are not plain "main" datasets. Dispatch those semantic
    # output roles to the dedicated Dataiku builder methods instead of with_output().
    role = output.get("role", "main")
    ref = output["name"]
    append = output.get("appendMode", False)

    if role == "metrics":
        if "append" in inspect.signature(builder.with_output_metrics).parameters:
            builder.with_output_metrics(ref, append=append)
        else:
            builder.with_output_metrics(ref)
        return

    if role == "evaluationStore":
        builder.with_output_evaluation_store(ref)
        return

    if role == "knowledge_bank":
        embedding_llm = (
            output.get("embedding_llm")
            or config.get_current_instance().default_embedding_llm
        )
        if not isinstance(embedding_llm, str) or not embedding_llm.strip():
            raise ValueError(
                "Knowledge-bank outputs require 'embedding_llm' in the output object "
                "or DKU_DEFAULT_EMBEDDING_LLM to be set"
            )
        vector_store_type = output.get("vector_store_type", "CHROMA")
        vector_store_params = output.get("vector_store_params")
        if vector_store_params is not None and not isinstance(
            vector_store_params, dict
        ):
            raise ValueError("'vector_store_params' must be an object when provided")
        builder.with_output_knowledge_bank(
            ref,
            embedding_llm.strip(),
            vector_store_type=vector_store_type,
            vector_store_params=vector_store_params,
        )
        return

    raise ValueError(f"Unsupported special output role '{role}'")


def _group_inputs_by_role(
    inputs: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for input_spec in inputs:
        role = input_spec.get("role", "main")
        grouped.setdefault(role, []).append(
            {
                "ref": input_spec["name"],
                "deps": input_spec.get("partition_deps", []),
            }
        )
    return grouped


def _group_outputs_by_role(
    outputs: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for output in outputs:
        role = output.get("role") or "main"
        grouped.setdefault(role, []).append(
            {"ref": output["name"], "appendMode": output.get("appendMode", False)}
        )
    return grouped


def _safe_copy_io_roles(raw_roles: dict | None) -> dict[str, list[dict[str, Any]]]:
    if raw_roles is None:
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for role, role_obj in raw_roles.items():
        items = role_obj.get("items", [])
        result[role] = [dict(item) for item in items]
    return result


def _get_inputs_by_role(settings) -> dict[str, list[dict[str, Any]]]:
    return _safe_copy_io_roles(settings.get_recipe_inputs())


def _get_outputs_by_role(settings) -> dict[str, list[dict[str, Any]]]:
    return _safe_copy_io_roles(settings.get_recipe_outputs())


def _get_recipe_type(settings) -> str:
    return settings.get_recipe_raw_definition().get("type", "unknown")


def _get_current_recipe_params(settings) -> dict:
    return settings.get_recipe_params()


def _changed_slice(persisted: dict, patch: dict, merge: bool) -> dict:
    """Persisted values for the keys a set wrote (whole dict on full replace)."""
    keys = patch.keys() if merge else persisted.keys()
    return {k: persisted[k] for k in keys if k in persisted}


def _set_recipe_payload(
    *,
    project_key: str,
    recipe_name: str,
    payload_obj: dict,
    merge: bool,
    deep_merge: bool,
    apply_schema_updates: bool,
) -> dict:
    recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
    settings = recipe.get_settings()
    recipe_type = _get_recipe_type(settings)

    if recipe_type in CODE_RECIPE_TYPES:
        raise ValueError(
            f"Recipe '{recipe_name}' is a code recipe (type '{recipe_type}'). "
            "Use set_recipe_settings with action='set_code' for code updates."
        )

    new_payload = payload_obj
    if merge:
        current_payload = settings.get_json_payload()
        if deep_merge:
            new_payload = _deep_merge_dict(current_payload, payload_obj)
        else:
            new_payload = {**current_payload, **payload_obj}

    settings.set_json_payload(new_payload)
    settings.save()

    result = {
        "type": recipe_type,
        "merge": merge,
        "deep_merge": deep_merge,
    }

    # Read back touched keys from DSS so the caller skips a validation get and
    # sees any normalization or silent drop.
    try:
        persisted = recipe.get_settings().get_json_payload()
        if isinstance(persisted, dict):
            result["payload"] = _changed_slice(persisted, payload_obj, merge)
    except Exception as exc:
        result["payload_readback_warning"] = str(exc)

    if apply_schema_updates:
        try:
            schema_updates = recipe.compute_schema_updates()
            if schema_updates.any_action_required():
                schema_updates.apply()
                result["schema_updates_applied"] = True
        except Exception as exc:
            result["schema_update_warning"] = str(exc)

    return result


def _set_recipe_outputs(
    *,
    project_key: str,
    recipe_name: str,
    outputs_obj: list[dict[str, Any]],
    mode: str,
    apply_schema_updates: bool,
) -> dict:
    mode = _require_allowed_value(mode, "mode", {"add", "replace"})
    outputs_obj = _normalize_output_specs(outputs_obj)

    project = get_dss_client().get_project(project_key)
    recipe = project.get_recipe(recipe_name)
    settings = recipe.get_settings()
    recipe_type = _get_recipe_type(settings)

    if mode == "add":
        current_outputs = settings.get_recipe_outputs()
        for output in outputs_obj:
            role = output.get("role") or "main"
            ref = output["name"]
            append_mode = output.get("appendMode", False)

            role_obj = current_outputs.get(role, {})
            items = role_obj.get("items", [])
            existing_item = None
            for item in items:
                if item.get("ref") == ref:
                    existing_item = item
                    break

            if existing_item is None:
                settings.add_output(role=role, ref=ref, append_mode=append_mode)
            else:
                existing_item["appendMode"] = append_mode
    else:
        desired = _group_outputs_by_role(outputs_obj)
        current_outputs = settings.get_recipe_outputs()
        current_outputs.clear()
        for role, items in desired.items():
            current_outputs[role] = {"items": items}

    settings.save()

    result = {
        "type": recipe_type,
        "mode": mode,
        "outputs": _get_outputs_by_role(settings),
    }

    if apply_schema_updates:
        try:
            schema_updates = recipe.compute_schema_updates()
            if schema_updates.any_action_required():
                schema_updates.apply()
                result["schema_updates_applied"] = True
        except Exception as exc:
            result["schema_update_warning"] = str(exc)

    return result


def _set_recipe_inputs(
    *,
    project_key: str,
    recipe_name: str,
    inputs_obj: list[dict[str, Any]],
    mode: str,
    apply_schema_updates: bool,
) -> dict:
    mode = _require_allowed_value(mode, "mode", {"add", "replace"})

    project = get_dss_client().get_project(project_key)
    recipe = project.get_recipe(recipe_name)
    settings = recipe.get_settings()
    recipe_type = _get_recipe_type(settings)

    if mode == "add":
        current_inputs = settings.get_recipe_inputs()
        for input_spec in inputs_obj:
            role = input_spec.get("role", "main")
            ref = input_spec["name"]
            partition_deps = input_spec.get("partition_deps", [])

            role_obj = current_inputs.get(role, {})
            items = role_obj.get("items", [])
            existing_item = None
            for item in items:
                if item.get("ref") == ref:
                    existing_item = item
                    break

            if existing_item is None:
                settings.add_input(role=role, ref=ref, partition_deps=partition_deps)
            else:
                existing_item["deps"] = partition_deps
    else:
        desired = _group_inputs_by_role(inputs_obj)
        current_inputs = settings.get_recipe_inputs()
        current_inputs.clear()
        for role, items in desired.items():
            current_inputs[role] = {"items": items}

    settings.save()

    result = {
        "type": recipe_type,
        "mode": mode,
        "inputs": _get_inputs_by_role(settings),
    }

    if apply_schema_updates:
        try:
            schema_updates = recipe.compute_schema_updates()
            if schema_updates.any_action_required():
                schema_updates.apply()
                result["schema_updates_applied"] = True
        except Exception as exc:
            result["schema_update_warning"] = str(exc)

    return result


def _set_recipe_code(
    *,
    project_key: str,
    recipe_name: str,
    code: str,
) -> dict:
    recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
    settings = recipe.get_settings()
    recipe_type = _get_recipe_type(settings)

    if recipe_type not in CODE_RECIPE_TYPES:
        raise ValueError(
            f"Recipe '{recipe_name}' is type '{recipe_type}', not a code recipe."
        )

    if hasattr(settings, "set_code"):
        settings.set_code(code)
    else:
        # sql_query uses base DSSRecipeSettings; SQL lives in the raw payload.
        settings.set_payload(code)
    settings.save()
    return {"type": recipe_type}


def _set_recipe_code_env(
    *,
    project_key: str,
    recipe_name: str,
    env_mode: str,
    env_name: str | None,
) -> dict:
    valid_modes = {"EXPLICIT_ENV", "INHERIT", "USE_BUILTIN_MODE"}
    if env_mode not in valid_modes:
        raise ValueError(f"'env_mode' must be one of: {sorted(valid_modes)}")
    if env_mode == "EXPLICIT_ENV" and not env_name:
        raise ValueError("'env_name' is required when env_mode is 'EXPLICIT_ENV'")

    recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
    settings = recipe.get_settings()
    recipe_type = _get_recipe_type(settings)

    if hasattr(settings, "set_code_env"):
        settings.set_code_env(
            code_env=env_name if env_mode == "EXPLICIT_ENV" else None,
            inherit=(env_mode == "INHERIT"),
            use_builtin=(env_mode == "USE_BUILTIN_MODE"),
        )
    else:
        params = settings.get_recipe_params()
        if not params or "envSelection" not in params:
            raise ValueError(
                f"Recipe type '{recipe_type}' does not support code env configuration"
            )
        params["envSelection"] = (
            {"envMode": env_mode, "envName": env_name}
            if env_mode == "EXPLICIT_ENV"
            else {"envMode": env_mode}
        )

    settings.save()
    result = {
        "type": recipe_type,
        "env_mode": env_mode,
    }
    # Lever 4: env_name is None for INHERIT / USE_BUILTIN_MODE; omit when empty.
    if not is_empty(env_name):
        result["env_name"] = env_name
    return result


def _set_recipe_params(
    *,
    project_key: str,
    recipe_name: str,
    params_obj: dict,
    merge: bool,
    apply_schema_updates: bool,
) -> dict:
    recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
    settings = recipe.get_settings()
    current_params = _get_current_recipe_params(settings)

    updated_params = params_obj if not merge else {**current_params, **params_obj}
    recipe_settings = settings.recipe_settings
    recipe_settings["params"] = updated_params
    settings.save()

    result = {
        "type": _get_recipe_type(settings),
        "merge": merge,
        "params": None,
    }

    # Read back persisted params from DSS (not the computed merge) so the caller
    # sees any normalization or silent drop. engineParams dropped like the view.
    try:
        persisted = _get_current_recipe_params(recipe.get_settings())
        if isinstance(persisted, dict):
            persisted = {k: v for k, v in persisted.items() if k != "engineParams"}
            result["params"] = _changed_slice(persisted, params_obj, merge)
    except Exception as exc:
        result["params_readback_warning"] = str(exc)

    if apply_schema_updates:
        try:
            schema_updates = recipe.compute_schema_updates()
            if schema_updates.any_action_required():
                schema_updates.apply()
                result["schema_updates_applied"] = True
        except Exception as exc:
            result["schema_update_warning"] = str(exc)

    return result


def _run_recipe_settings_operation(
    *,
    project_key: str,
    recipe_name: str,
    operation: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    action = operation.get("action")

    try:
        if action == "set_inputs":
            inputs = operation.get("inputs")
            if inputs is None:
                raise ValueError(f"'operations[{index}].inputs' is required")
            inputs_obj = _normalize_input_specs(inputs)
            mode = operation.get("mode", "add").lower()
            apply_schema_updates = _get_bool_value(
                operation.get("apply_schema_updates"),
                f"operations[{index}].apply_schema_updates",
                False,
            )
            result = _set_recipe_inputs(
                project_key=project_key,
                recipe_name=recipe_name,
                inputs_obj=inputs_obj,
                mode=mode,
                apply_schema_updates=apply_schema_updates,
            )
        elif action == "set_outputs":
            outputs = operation.get("outputs")
            if outputs is None:
                raise ValueError(f"'operations[{index}].outputs' is required")
            outputs_obj = _normalize_output_specs(outputs)
            mode = operation.get("mode", "add").lower()
            apply_schema_updates = _get_bool_value(
                operation.get("apply_schema_updates"),
                f"operations[{index}].apply_schema_updates",
                False,
            )
            result = _set_recipe_outputs(
                project_key=project_key,
                recipe_name=recipe_name,
                outputs_obj=outputs_obj,
                mode=mode,
                apply_schema_updates=apply_schema_updates,
            )
        elif action == "set_payload":
            payload = operation.get("payload")
            if payload is None:
                raise ValueError(f"'operations[{index}].payload' is required")
            payload_obj = _coerce_json_object(payload, f"operations[{index}].payload")
            merge = _get_bool_value(
                operation.get("merge"),
                f"operations[{index}].merge",
                False,
            )
            deep_merge = _get_bool_value(
                operation.get("deep_merge"),
                f"operations[{index}].deep_merge",
                False,
            )
            apply_schema_updates = _get_bool_value(
                operation.get("apply_schema_updates"),
                f"operations[{index}].apply_schema_updates",
                True,
            )
            result = _set_recipe_payload(
                project_key=project_key,
                recipe_name=recipe_name,
                payload_obj=payload_obj,
                merge=merge,
                deep_merge=deep_merge,
                apply_schema_updates=apply_schema_updates,
            )
        elif action == "set_code":
            code = operation.get("code")
            result = _set_recipe_code(
                project_key=project_key,
                recipe_name=recipe_name,
                code=code,
            )
        elif action == "set_params":
            params = operation.get("params")
            if params is None:
                raise ValueError(f"'operations[{index}].params' is required")
            params_obj = _coerce_json_object(params, f"operations[{index}].params")
            merge = _get_bool_value(
                operation.get("merge"),
                f"operations[{index}].merge",
                True,
            )
            apply_schema_updates = _get_bool_value(
                operation.get("apply_schema_updates"),
                f"operations[{index}].apply_schema_updates",
                False,
            )
            result = _set_recipe_params(
                project_key=project_key,
                recipe_name=recipe_name,
                params_obj=params_obj,
                merge=merge,
                apply_schema_updates=apply_schema_updates,
            )
        elif action == "set_code_env":
            env_mode = operation.get("env_mode")
            if not env_mode:
                raise ValueError(f"'operations[{index}].env_mode' is required")
            env_name = operation.get("env_name")
            result = _set_recipe_code_env(
                project_key=project_key,
                recipe_name=recipe_name,
                env_mode=env_mode,
                env_name=env_name,
            )
        else:
            return {
                "index": index,
                "action": action,
                "status": "error",
                "error": (
                    "Unsupported action. Allowed values: "
                    "set_inputs, set_outputs, set_payload, set_code, set_params, set_code_env"
                ),
            }
    except Exception as exc:
        return {
            "index": index,
            "action": action,
            "status": "error",
            "error": str(exc),
        }

    if result.get("error"):
        return {
            "index": index,
            "action": action,
            "status": "error",
            "error": result["error"],
        }

    return {
        "index": index,
        "action": action,
        "status": "success",
        "result": result,
    }


@mcp.tool()
async def list_recipes(project_key: str, ctx: Context) -> str:
    """List the recipes in the project with their types, inputs, and outputs."""
    raw_recipes = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_recipes()
    )

    result = [
        {
            "name": r["name"],
            "type": r.get("type", ""),
            "inputs": r.get("inputs", {}),
            "outputs": r.get("outputs", {}),
        }
        for r in raw_recipes
    ]
    return compact_json(columnar(result, ["name", "type", "inputs", "outputs"]))


@mcp.tool()
async def create_recipe(
    project_key: str,
    recipe_type: str,
    inputs: list,
    outputs: list,
    ctx: Context,
    recipe_name: str | None = None,
    code: str | None = None,
    code_recipe_justification: str | None = None,
) -> str:
    """Create a recipe by type using existing inputs and outputs.

    Args:
        recipe_type: A DSS recipe type (see the recipes skill for the full list)
        inputs: List of input names or {"name": ..., "role": ..., "partition_deps": ...} objects. Role defaults to "main".
        outputs: List of output names or {"name": ..., "role": ..., "appendMode": ...} objects. Role defaults to "main".
        recipe_name: Optional explicit recipe name (auto-generated if omitted)
        code: Initial code for code recipes only (python, r, sql_script, etc.); must be None for visual recipes
        code_recipe_justification: Required for code recipes. The only valid justification is that a user explicitly
        requested a code recipe.
    """
    inputs_obj = _normalize_input_specs(inputs)
    outputs = _normalize_output_specs(outputs)

    if code is not None and recipe_type not in CODE_RECIPE_TYPES:
        raise ValueError(
            f"The 'code' parameter is only valid for code recipe types, not '{recipe_type}'"
        )
    if recipe_type in CODE_RECIPE_TYPES:
        code_recipe_justification = (code_recipe_justification or "").strip()
        if not code_recipe_justification:
            raise ValueError(
                "Code recipes are discouraged unless specifically requested by the user; "
                "provide a non-empty 'code_recipe_justification' when creating a code recipe."
            )

    builder_mode = "flexible" if recipe_type in FLEXIBLE_BUILDER_TYPES else "default"

    await ctx.info(
        f"Creating recipe '{recipe_name or '[auto]'}' of type '{recipe_type}'..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)

        try:
            builder = project.new_recipe(recipe_type, name=recipe_name)
        except ValueError:
            builder = None

        if builder is None:
            # Some recipe types are not backed by a typed SDK builder. Depending on
            # the SDK/version, new_recipe() may either raise ValueError or return
            # None. Fall back to the generic creator in both cases.
            builder = DSSRecipeCreator(recipe_type, recipe_name, project)

        model_inputs = [i for i in inputs_obj if i.get("role", "main") == "model"]
        primary_inputs = [i for i in inputs_obj if i.get("role", "main") != "model"]

        if builder_mode == "flexible":
            for inp in inputs_obj:
                builder.with_input(inp["name"], role=inp.get("role", "main"))
        else:
            for inp in primary_inputs:
                builder.with_input(inp["name"])
            for inp in model_inputs:
                builder.with_input_model(inp["name"])

        main_outputs = [o for o in outputs if o.get("role", "main") == "main"]
        special_role_outputs = [
            o for o in outputs if o.get("role", "main") in SPECIAL_OUTPUT_ROLES
        ]
        non_main_outputs = [
            o
            for o in outputs
            if o.get("role", "main") not in {"main"} | SPECIAL_OUTPUT_ROLES
        ]

        # Require at least one output that gets registered on the builder before create():
        # either a main output or a special-role output (knowledge_bank, metrics, evaluationStore).
        # Non-main non-special outputs (e.g. images folders) are added post-creation and don't count.
        if (
            builder_mode != "flexible"
            and len(main_outputs) == 0
            and len(special_role_outputs) == 0
        ):
            raise ValueError(
                "At least one output with role 'main' or a special role "
                "(knowledge_bank, metrics, evaluationStore) is required at recipe creation time."
            )

        if builder_mode == "flexible":
            for out in outputs:
                builder.with_output(
                    out["name"],
                    append=out.get("appendMode", False),
                    role=out.get("role", "main"),
                )
        else:
            # Builder API on some recipe creators (notably join) doesn't accept role in with_output.
            # Always create main output(s) first, then add non-main outputs through settings.add_output.
            for out in main_outputs:
                builder.with_output(out["name"], append=out.get("appendMode", False))

            for out in special_role_outputs:
                _apply_special_output_to_builder(builder, out)

        # CodeRecipeCreator-backed builders accept .with_script(); sql_query's
        # SQLQueryRecipeCreator doesn't, so its SQL is set after create() below.
        defer_code: str | None = None
        if recipe_type in CODE_RECIPE_TYPES and code:
            if hasattr(builder, "with_script"):
                builder.with_script(code)
            else:
                defer_code = code

        recipe = builder.create()

        settings = recipe.get_settings()
        needs_save = False

        # Some generic-creator recipe types (for example geojoin) can be created
        # successfully but persist with no saved inputs even though with_input()
        # was called on the builder. Rehydrate the declared inputs on the saved
        # settings so downstream get/set/build calls observe the intended wiring.
        if not _get_inputs_by_role(settings) and inputs_obj:
            current_inputs = settings.get_recipe_inputs()
            current_inputs.clear()
            for role, items in _group_inputs_by_role(inputs_obj).items():
                current_inputs[role] = {"items": items}
            needs_save = True

        if defer_code is not None:
            if hasattr(settings, "set_code"):
                settings.set_code(defer_code)
            else:
                # sql_query uses base DSSRecipeSettings; SQL lives in the raw payload.
                settings.set_payload(defer_code)
            needs_save = True

        if non_main_outputs and builder_mode != "flexible":
            for out in non_main_outputs:
                settings.add_output(
                    role=out.get("role", "main"),
                    ref=out["name"],
                    append_mode=out.get("appendMode", False),
                )
            needs_save = True

        if needs_save:
            settings.save()

        # Read back the persisted recipe so the caller skips a follow-up get and
        # sees DSS outcomes like inputs that failed to persist. Flattened to match
        # the get_recipe_settings shape so agents can edit directly without nesting.
        result = {
            "recipe_name": recipe.recipe_name,
            **_settings_view(recipe.get_settings()),
        }
        if code_recipe_justification is not None:
            result["code_recipe_justification"] = code_recipe_justification
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def delete_recipe(
    project_key: str,
    recipe_name: str,
    ctx: Context,
) -> str:
    """Delete the recipe."""
    await run_blocking(
        lambda: (
            get_dss_client().get_project(project_key).get_recipe(recipe_name).delete()
        )
    )
    return compact_json({"deleted": True})


def _settings_view(settings, include_engine_params: bool = False) -> dict:
    """Persisted settings view. Shared by get_recipe_settings + the create echo
    so the caller sees one shape and skips a follow-up get."""
    recipe_type = _get_recipe_type(settings)
    result: dict[str, Any] = {
        "type": recipe_type,
        "params": None,
        "payload": None,
        "code": None,
    }
    warnings: list[str] = []
    try:
        result["inputs_by_role"] = _get_inputs_by_role(settings)
    except Exception as exc:
        warnings.append(f"inputs unavailable: {exc}")
    try:
        result["outputs_by_role"] = _get_outputs_by_role(settings)
    except Exception as exc:
        warnings.append(f"outputs unavailable: {exc}")
    try:
        params = settings.get_recipe_params()
        if not include_engine_params and isinstance(params, dict):
            params = {k: v for k, v in params.items() if k != "engineParams"}
        result["params"] = params
    except Exception as exc:
        warnings.append(f"params unavailable: {exc}")
    try:
        result["payload"] = settings.get_json_payload()
    except Exception as exc:
        # Code recipes don't have a JSON payload — silence the noisy warning.
        if recipe_type not in CODE_RECIPE_TYPES:
            warnings.append(f"payload unavailable: {exc}")
    if recipe_type in CODE_RECIPE_TYPES:
        try:
            # sql_query uses base DSSRecipeSettings; SQL lives in the raw payload.
            result["code"] = (
                settings.get_code()
                if hasattr(settings, "get_code")
                else settings.get_payload()
            )
        except Exception as exc:
            warnings.append(f"code unavailable: {exc}")
    if warnings:
        result["warnings"] = warnings
    # Lever 4: drop optional config blocks that carry no information when empty
    # (empty reads as absent); identity stays, and the empty set excludes False/0.
    _empty = (None, "", [], {})
    for _opt in ("params", "payload", "code"):
        if result.get(_opt) in _empty:
            result.pop(_opt, None)
    return result


@mcp.tool()
async def get_recipe_settings(
    project_key: str,
    recipe_name: str,
    ctx: Context,
    include_engine_params: bool = False,
) -> str:
    """Get the recipe's settings (type, inputs/outputs by role, params, payload, code)."""

    def _run():
        recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
        return _settings_view(
            recipe.get_settings(), include_engine_params=include_engine_params
        )

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_recipe_settings(
    project_key: str,
    recipe_name: str,
    operations,
    ctx: Context,
) -> str:
    """Apply an ordered list of update operations to a recipe.

    Supported actions: set_inputs, set_outputs, set_payload, set_code, set_params, set_code_env.
    """
    try:
        operations_obj = _coerce_json_array(operations, "operations")
        operations_obj = _require_non_empty_list(operations_obj, "operations")
    except ValueError as exc:
        return compact_json({"error": str(exc)})

    await ctx.info(
        f"Applying {len(operations_obj)} recipe setting operations for {recipe_name}..."
    )

    def _run():
        recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
        recipe_type = _get_recipe_type(recipe.get_settings())

        action_results: list[dict[str, Any]] = []
        actions_succeeded = 0
        actions_failed = 0

        for index, operation in enumerate(operations_obj):
            if not hasattr(operation, "get"):
                action_results.append(
                    {
                        "index": index,
                        "action": None,
                        "status": "error",
                        "error": f"'operations[{index}]' must be an object",
                    }
                )
                actions_failed += 1
                continue

            op_result = _run_recipe_settings_operation(
                project_key=project_key,
                recipe_name=recipe_name,
                operation=operation,
                index=index,
            )
            action_results.append(op_result)
            if op_result["status"] == "success":
                actions_succeeded += 1
            else:
                actions_failed += 1

        if actions_failed == 0:
            overall_status = "success"
        elif actions_succeeded == 0:
            overall_status = "failed"
        else:
            overall_status = "partial_success"

        return {
            "status": overall_status,
            "type": recipe_type,
            "results": columnar(
                action_results, ["index", "action", "status", "result", "error"]
            ),
        }

    return compact_json(await run_blocking(_run))

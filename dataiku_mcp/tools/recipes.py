# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Recipe inspection tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context

from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.validation import require_allowed_value, require_non_empty_string

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
_CONTAINER_MODES = {"INHERIT", "NONE", "EXPLICIT_CONTAINER"}


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


def _get_container_selection(settings) -> dict:
    params = settings.get_recipe_params() or {}
    selection = params.get("containerSelection")
    if isinstance(selection, dict):
        return selection

    engine_params = params.get("engineParams") or {}
    selection = engine_params.get("containerSelection")
    if isinstance(selection, dict):
        return selection

    if _get_recipe_type(settings) not in CODE_RECIPE_TYPES:
        payload = settings.get_json_payload() or {}
        engine_params = payload.get("engineParams") or {}
        selection = engine_params.get("containerSelection")
        if isinstance(selection, dict):
            return selection

    raise ValueError("This recipe does not expose a container execution override")


def _set_container_selection(
    selection: dict, container_mode: str, container_config: str | None
) -> None:
    selection["containerMode"] = container_mode
    if container_mode == "EXPLICIT_CONTAINER":
        selection["containerConf"] = container_config
    else:
        selection.pop("containerConf", None)


def _settings_view(settings, include_engine_params: bool = False) -> dict:
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
            params = {
                key: value for key, value in params.items() if key != "engineParams"
            }
        result["params"] = params
    except Exception as exc:
        warnings.append(f"params unavailable: {exc}")
    try:
        result["payload"] = settings.get_json_payload()
    except Exception as exc:
        if recipe_type not in CODE_RECIPE_TYPES:
            warnings.append(f"payload unavailable: {exc}")
    if recipe_type in CODE_RECIPE_TYPES:
        try:
            result["code"] = (
                settings.get_code()
                if hasattr(settings, "get_code")
                else settings.get_payload()
            )
        except Exception as exc:
            warnings.append(f"code unavailable: {exc}")
    if warnings:
        result["warnings"] = warnings
    for key in ("params", "payload", "code"):
        if result.get(key) in (None, "", [], {}):
            result.pop(key, None)
    return result


@mcp.tool(
    title="List Recipes",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_recipes(project_key: str, ctx: Context) -> str:
    """Map a project's recipes and what each one reads and writes."""
    raw_recipes = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_recipes()
    )
    result = [
        {
            "name": recipe["name"],
            "type": recipe.get("type", ""),
            "inputs": recipe.get("inputs", {}),
            "outputs": recipe.get("outputs", {}),
        }
        for recipe in raw_recipes
    ]
    return compact_json(columnar(result, ["name", "type", "inputs", "outputs"]))


@mcp.tool(
    title="Get Recipe Settings",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_recipe_settings(
    project_key: str,
    recipe_name: str,
    ctx: Context,
    include_engine_params: bool = False,
) -> str:
    """Read one recipe's logic, code, and IO, to ground a Cobuild change to it."""

    def _run():
        recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
        return _settings_view(
            recipe.get_settings(), include_engine_params=include_engine_params
        )

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_recipe_container_exec_config(
    project_key: str,
    recipe_name: str,
    container_mode: str,
    ctx: Context,
    container_config: str | None = None,
) -> str:
    """Set one existing recipe's container execution override.

    INHERIT uses the project default, NONE runs without a container, and
    EXPLICIT_CONTAINER requires container_config.
    """
    project_key = require_non_empty_string(project_key, "project_key")
    recipe_name = require_non_empty_string(recipe_name, "recipe_name")
    container_mode = require_allowed_value(
        container_mode, "container_mode", _CONTAINER_MODES
    )
    if container_mode == "EXPLICIT_CONTAINER":
        container_config = require_non_empty_string(
            container_config, "container_config"
        )
    elif container_config is not None:
        raise ValueError(
            "'container_config' is only valid with container_mode='EXPLICIT_CONTAINER'"
        )
    await ctx.info(
        f"Setting container execution for recipe '{recipe_name}' in {project_key}..."
    )

    def _run():
        recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        selection = _get_container_selection(settings)
        _set_container_selection(selection, container_mode, container_config)
        settings.save()
        saved_settings = recipe.get_settings()
        return {
            "project_key": project_key,
            "recipe_name": recipe_name,
            "recipe_type": _get_recipe_type(saved_settings),
            "container_selection": _get_container_selection(saved_settings),
        }

    return compact_json(await run_blocking(_run))

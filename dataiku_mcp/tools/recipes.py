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

"""Recipe inspection tools and Python recipe code-environment selection."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastmcp import Context
from pydantic import Field

from ..instance_policy import PROJECT_EDIT_POLICY, PROJECT_READ_POLICY
from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string

PythonEnvMode = Literal["INHERIT", "EXPLICIT_ENV", "USE_BUILTIN_MODE"]
PythonEnvName = Annotated[
    str | None,
    Field(
        description=(
            "Python environment name from list_code_envs, copied exactly; "
            "only with env_mode='EXPLICIT_ENV'."
        )
    ),
]

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


def _python_env_selection(settings, recipe_name: str) -> dict:
    """Return the live code-environment selection of one Python recipe.

    The selection is a reference into the settings, so replacing it in the
    params and calling ``settings.save()`` writes back only the environment
    choice; the code, inputs, outputs, and other params are saved unchanged.
    """
    recipe_type = _get_recipe_type(settings)
    if recipe_type != "python":
        raise ValueError(
            f"Recipe '{recipe_name}' is a '{recipe_type}' recipe; only Python "
            "recipes are supported"
        )
    params = settings.get_recipe_params()
    selection = params.get("envSelection") if isinstance(params, dict) else None
    if not isinstance(selection, dict):
        raise ValueError(
            f"Recipe '{recipe_name}' does not expose a code environment selection"
        )
    return selection


def _require_python_env(client, env_name: str) -> None:
    """Refuse an unknown name, which Dataiku can store and only reject at run time."""
    if not any(
        env.get("envName") == env_name and env.get("envLang") == "PYTHON"
        for env in client.list_code_envs()
    ):
        raise ValueError(
            f"No Python code environment named '{env_name}'. Use "
            "list_code_envs(language='PYTHON') and copy a returned name exactly"
        )


@mcp.tool(
    meta=PROJECT_READ_POLICY,
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
    meta=PROJECT_READ_POLICY,
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


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Set Recipe Code Environment",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def set_recipe_code_env(
    project_key: str,
    recipe_name: str,
    env_mode: PythonEnvMode,
    ctx: Context,
    env_name: PythonEnvName = None,
) -> str:
    """Select which code environment one existing Python recipe runs with."""
    project_key = require_non_empty_string(project_key, "project_key")
    recipe_name = require_non_empty_string(recipe_name, "recipe_name")
    if env_mode == "EXPLICIT_ENV":
        env_name = require_non_empty_string(env_name, "env_name")
        selection = {"envMode": env_mode, "envName": env_name}
    elif env_name is not None:
        raise ValueError("'env_name' is only valid with env_mode='EXPLICIT_ENV'")
    else:
        selection = {"envMode": env_mode}
    await ctx.info(
        f"Setting the code environment of recipe '{recipe_name}' in {project_key}..."
    )

    def _run():
        client = get_dss_client()
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        previous = dict(_python_env_selection(settings, recipe_name))
        if env_mode == "EXPLICIT_ENV":
            _require_python_env(client, env_name)
        settings.get_recipe_params()["envSelection"] = selection
        settings.save()
        return {
            "project_key": project_key,
            "recipe_name": recipe_name,
            "previous_env_selection": previous,
            "env_selection": _python_env_selection(recipe.get_settings(), recipe_name),
        }

    return compact_json(await run_blocking(_run))

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

"""Recipe inspection tools, plus direct R recipe writes that Cobuild cannot build."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import Context
from pydantic import Field

from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string as _require_non_empty_string

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


@mcp.tool(
    title="Create R Recipe",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_r_recipe(
    project_key: str,
    recipe_name: str,
    code: str,
    output_dataset: Annotated[
        str, Field(description="Created as a managed dataset when it does not exist.")
    ],
    ctx: Context,
    inputs: list[str] | None = None,
    output_connection: Annotated[
        str, Field(description="Connection that stores a newly created output dataset.")
    ] = "filesystem_managed",
) -> str:
    """Create an R recipe, which Cobuild cannot build. Use only when the user asks for R."""
    project_key = _require_non_empty_string(project_key, "project_key")
    recipe_name = _require_non_empty_string(recipe_name, "recipe_name")
    _require_non_empty_string(code, "code")
    output_dataset = _require_non_empty_string(output_dataset, "output_dataset")
    await ctx.info(f"Creating R recipe '{recipe_name}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        # Check first: a new output dataset is created immediately and would be
        # orphaned if the recipe name then clashed.
        if any(recipe["name"] == recipe_name for recipe in project.list_recipes()):
            raise ValueError(
                f"Recipe '{recipe_name}' already exists in {project_key}; "
                "use update_r_recipe to change it."
            )
        creator = project.new_recipe("r", recipe_name).with_script(code)
        for name in inputs or []:
            creator.with_input(name)
        output_created = not project.get_dataset(output_dataset).exists()
        if output_created:
            creator.with_new_output_dataset(output_dataset, output_connection)
        else:
            creator.with_output(output_dataset)
        creator.create()
        return {
            "recipe_name": recipe_name,
            "inputs": inputs or [],
            "output_dataset": output_dataset,
            "output_created": output_created,
        }

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="Update R Recipe",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def update_r_recipe(
    project_key: str,
    recipe_name: str,
    ctx: Context,
    code: Annotated[str | None, Field(description="Replaces the whole script.")] = None,
    inputs: Annotated[
        list[str] | None,
        Field(description="Replaces the main input datasets."),
    ] = None,
) -> str:
    """Replace an existing R recipe's code or inputs, which Cobuild cannot edit."""
    project_key = _require_non_empty_string(project_key, "project_key")
    recipe_name = _require_non_empty_string(recipe_name, "recipe_name")
    if code is None and inputs is None:
        raise ValueError("Provide code, inputs, or both.")
    if code is not None:
        _require_non_empty_string(code, "code")
    await ctx.info(f"Updating R recipe '{recipe_name}' in {project_key}...")

    def _run():
        recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        recipe_type = _get_recipe_type(settings)
        if recipe_type != "r":
            raise ValueError(
                f"Recipe '{recipe_name}' is a '{recipe_type}' recipe; only R recipes "
                "are written directly. Route other recipe changes through Cobuild."
            )
        if code is not None:
            settings.set_code(code)
        if inputs is not None:
            settings.get_recipe_raw_definition().setdefault("inputs", {})["main"] = {
                "items": [{"ref": name, "deps": []} for name in inputs]
            }
        settings.save()
        return {
            "recipe_name": recipe_name,
            "code_updated": code is not None,
            "inputs": [
                item["ref"] for item in _get_inputs_by_role(settings).get("main", [])
            ],
        }

    return compact_json(await run_blocking(_run))

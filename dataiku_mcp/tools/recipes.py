"""Recipe inspection tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json

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


@mcp.tool()
async def list_recipes(project_key: str, ctx: Context) -> str:
    """List the recipes in the project with their types, inputs, and outputs."""
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


@mcp.tool()
async def get_recipe_settings(
    project_key: str,
    recipe_name: str,
    ctx: Context,
    include_engine_params: bool = False,
) -> str:
    """Get a recipe's settings (type, inputs/outputs by role, params, payload, code)."""

    def _run():
        recipe = get_dss_client().get_project(project_key).get_recipe(recipe_name)
        return _settings_view(
            recipe.get_settings(), include_engine_params=include_engine_params
        )

    return compact_json(await run_blocking(_run))

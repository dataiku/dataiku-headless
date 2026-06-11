"""Recipe schema commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from ._common import *

# ---------------------------------------------------------------------------
# Schema inspection commands
# ---------------------------------------------------------------------------


@app.command("check-schema")
def check_schema(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Check if recipe outputs need schema updates.

    Exit code 0 = no changes needed, 1 = changes needed.
    Note: does not work for code recipes (Python, R) — only visual recipes.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
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
) -> None:
    """Compute and apply required schema updates to recipe outputs.

    Note: does not work for code recipes (Python, R) — only visual recipes.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )

        # Pre-check recipe type: code recipes set their output schema at
        # run-time (Python via `dataiku.Dataset(...).write_with_schema()`,
        # R / shell similarly). DSS raises `DontWantToCompute` from
        # compute_schema_updates() in that case; emit prescriptive guidance
        # BEFORE the call instead of letting the raw exception bubble up.
        rtype = recipe.get_settings().get_recipe_raw_definition().get("type", "")
        if rtype in {"python", "r", "shell", "pyspark", "sparkr", "spark_scala"}:
            exit_with_error(
                f"Recipe '{recipe_name}' is type '{rtype}' — code recipes set "
                "their output schema at run-time, not via apply-schema.",
                status=2,
                details=[
                    "Code recipes write their output schema inside the recipe body:",
                    '  Python: `dataiku.Dataset("OUT").write_with_schema(df)` propagates df.dtypes',
                    '  R:      `dkuWriteDataset(df, "OUT")` does the same',
                    "",
                    "To materialize the output schema, run the recipe instead:",
                    f"  dku recipe run {recipe_name} --wait -P {project_key}",
                    "",
                    "apply-schema is for visual recipes (prepare, join, group, …)",
                    "where DSS can derive the output schema from the recipe config.",
                ],
            )

        updates = recipe.compute_schema_updates()

        if not updates.any_action_required():
            success(f"No schema updates needed for '{recipe_name}'")
            return

        results = updates.apply()
        render_raw(results, output_format=output)
        success(f"Applied schema updates for '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

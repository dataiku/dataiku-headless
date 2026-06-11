"""Recipe lint commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from ._common import *

# ---------------------------------------------------------------------------
# Recipe lint / validation commands
# ---------------------------------------------------------------------------


def _lint_from_status(
    client, project_key: str, recipe_name: str, recipe_type_label: str, fmt: str
) -> None:
    """Run recipe status check and report errors/warnings as lint output.
    dataikuapi has no compile/lint method, so we use DSS's built-in recipe
    status checks which validate engine compatibility and recipe configuration.
    """
    from dku_cli.output import info as lint_info

    recipe = _get_recipe_or_exit(
        client.get_project(project_key), recipe_name, project_key
    )
    settings = recipe.get_settings()
    raw_def = settings.get_recipe_raw_definition()
    actual_type = raw_def.get("type", "")

    lint_info(
        f"Linting {recipe_type_label} recipe '{recipe_name}' (type: {actual_type})..."
    )

    recipe_status = recipe.get_status()
    severity = recipe_status.get_status_severity()
    messages = recipe_status.get_status_messages()

    lint_passed = severity not in ("ERROR", "FATAL")

    if fmt == "json":
        render_raw(
            {
                "recipe": recipe_name,
                "type": actual_type,
                "severity": severity,
                "messages": messages,
                "lint_passed": lint_passed,
            },
            output_format="json",
        )
        if not lint_passed:
            raise typer.Exit(1)
        return

    errors = [m for m in messages if m.get("severity") in ("ERROR", "FATAL")]
    warnings = [m for m in messages if m.get("severity") == "WARNING"]

    if errors:
        from dku_cli.output import error as lint_err

        lint_err(f"Found {len(errors)} error(s):")
        for e in errors:
            lint_err(
                f"  [{e.get('code', '?')}] {e.get('title', '')}: {e.get('message', '')}"
            )
        if warnings:
            from dku_cli.output import warn as lint_warn

            lint_warn(f"Plus {len(warnings)} warning(s)")
        raise typer.Exit(1)
    elif warnings:
        from dku_cli.output import warn as lint_warn

        lint_warn(f"Found {len(warnings)} warning(s):")
        for w in warnings:
            lint_warn(
                f"  [{w.get('code', '?')}] {w.get('title', '')}: {w.get('message', '')}"
            )
    else:
        from dku_cli.output import success as lint_ok

        lint_ok("No errors or warnings found.")

    return


@app.command("lint-formula")
def lint_formula(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Lint a prepare recipe — validate formula/GREL expressions and step config.

    Runs DSS recipe status checks to validate the prepare recipe's formula
    expressions, step configuration, and engine compatibility. Reports any
    errors or warnings detected by the DSS engine.

    Example:
      dku recipe lint-formula my_prepare -P PROJ
      dku recipe lint-formula my_prepare -P PROJ
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        _lint_from_status(client, resolve_project(project), recipe_name, "formula", fmt)
    except Exception as e:
        handle_api_error(e)


@app.command("lint-sql")
def lint_sql(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="SQL recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Lint an SQL recipe — validate syntax and engine configuration.

    Runs DSS recipe status checks to validate the SQL query, engine
    compatibility, and output schema. Reports any SQL errors or warnings.

    Example:
      dku recipe lint-sql my_query -P PROJ
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        _lint_from_status(client, resolve_project(project), recipe_name, "SQL", fmt)
    except Exception as e:
        handle_api_error(e)


@app.command("lint-python")
def lint_python(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Python recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Lint a Python recipe — validate code env and engine configuration.

    Runs DSS recipe status checks to validate the Python code env,
    container selection, and engine compatibility. Reports any errors
    or warnings detected.

    Example:
      dku recipe lint-python my_script -P PROJ
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        _lint_from_status(client, resolve_project(project), recipe_name, "Python", fmt)
    except Exception as e:
        handle_api_error(e)

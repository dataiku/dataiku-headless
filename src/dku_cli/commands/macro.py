"""dku macro — list, run."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import info, render, resolve_output_format, success

app = typer.Typer(help="Manage DSS macros.")


@app.command("list")
def list_macros(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List available macros in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        macros = proj.list_macros()

        data = []
        for m in macros:
            meta = m.get("meta", {})
            data.append(
                {
                    "id": m.get("runnableType", ""),
                    "label": meta.get("label", ""),
                    "plugin": m.get("ownerPluginId", ""),
                }
            )

        render(
            data,
            ["id", "label", "plugin"],
            output_format=output,
            title=f"Macros ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def run(
    ctx: typer.Context,
    macro_id: str = typer.Argument(help="Macro ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    params: str = typer.Option(None, "--params", help="Macro params as JSON string"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
) -> None:
    """Run a macro."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        macro = proj.get_macro(macro_id)

        run_params = {}
        if params:
            run_params = json.loads(params)

        result = macro.run(run_params, wait=wait)

        if wait:
            success(f"Macro '{macro_id}' completed")
            if result:
                print(json.dumps(result, indent=2, default=str))
        else:
            success(f"Macro '{macro_id}' started")
            info("Use --wait to wait for completion")
    except json.JSONDecodeError:
        from dku_cli.output import error

        error("Invalid JSON in --params")
        raise typer.Exit(1)
    except Exception as e:
        handle_api_error(e)

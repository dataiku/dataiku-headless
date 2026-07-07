"""dku macro — list, run, result."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import (
    info,
    print_text,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage DSS macros.")

# Result types whose payload is JSON (per DSSMacro.get_result as_type contract).
_JSON_RESULT_TYPES = {"RESULT_TABLE", "JSON_OBJECT"}


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


def _print_macro_result(macro, macro_id: str, run_id: str) -> None:
    """Fetch and print a macro run's result, honoring its declared resultType.

    RESULT_TABLE / JSON_OBJECT results print as JSON; everything else
    (HTML, plain text, URL, file contents) prints verbatim.
    """
    result_type = (macro.get_definition() or {}).get("resultType", "")
    if result_type in _JSON_RESULT_TYPES:
        render_raw(macro.get_result(run_id, as_type="json"), output_format="json")
        return
    payload = macro.get_result(run_id, as_type="string")
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    print_text(payload)


@app.command()
def run(
    ctx: typer.Context,
    macro_id: str = typer.Argument(help="Macro ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    params: str = typer.Option(None, "--params", help="Macro params as JSON string"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
    print_result: bool = typer.Option(
        False,
        "--print-result",
        help="Wait, then print the run's rendered result (implies --wait). "
        "Note: fetching the result consumes the run.",
    ),
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

        wait = wait or print_result
        run_id = macro.run(run_params, wait=wait)

        if wait:
            success(f"Macro '{macro_id}' completed (run {run_id})")
            if print_result:
                _print_macro_result(macro, macro_id, run_id)
            else:
                print_text(run_id)
                info(
                    f"Fetch its result: dku macro result {macro_id} {run_id} "
                    f"-P {project_key}"
                )
        else:
            success(f"Macro '{macro_id}' started (run {run_id})")
            print_text(run_id)
            info(
                "Use --wait to wait for completion, --print-result to also print the result"
            )
    except json.JSONDecodeError:
        from dku_cli.output import error

        error("Invalid JSON in --params")
        raise typer.Exit(1) from None
    except Exception as e:
        handle_api_error(e)


@app.command()
def result(
    ctx: typer.Context,
    macro_id: str = typer.Argument(
        help="Macro ID (the runnableType, from 'dku macro list')"
    ),
    run_id: str = typer.Argument(help="Run ID (from 'dku macro run')"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Print the rendered result of a finished macro run.

    RESULT_TABLE / JSON_OBJECT macros print JSON; HTML/text macros print
    verbatim. Fetching the result consumes the run — a second call fails.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        macro = proj.get_macro(macro_id)
        _print_macro_result(macro, macro_id, run_id)
    except Exception as e:
        handle_api_error(e)

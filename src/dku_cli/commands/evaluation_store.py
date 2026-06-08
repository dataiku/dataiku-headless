"""dku evaluation-store — manage model evaluation stores."""

from __future__ import annotations

import json

import typer

from dku_cli.enums import EvalFlavor
from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS evaluation stores (TABULAR, LLM, AGENT).")


@app.command("list")
def list_stores(
    ctx: typer.Context,
    flavor: EvalFlavor | None = typer.Option(
        None,
        "--flavor",
        "-f",
        case_sensitive=False,
        help="Filter by flavor: TABULAR, LLM, or AGENT",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List evaluation stores in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        stores = proj.list_evaluation_stores(flavor=flavor.upper() if flavor else None)

        data = []
        for s in stores:
            raw = s.get_settings().get_raw()
            data.append(
                {
                    "id": s.id,
                    "name": raw.get("name", ""),
                    "flavor": raw.get("mesFlavor", raw.get("flavor", "TABULAR")),
                }
            )

        render(
            data,
            ["id", "name", "flavor"],
            output_format=output,
            title=f"Evaluation Stores ({project_key})",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Name for the evaluation store"),
    flavor: EvalFlavor = typer.Option(
        EvalFlavor.TABULAR,
        "--flavor",
        "-f",
        case_sensitive=False,
        help="Store flavor: TABULAR, LLM, or AGENT",
    ),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if a store with this name already exists"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new evaluation store (TABULAR, LLM, or AGENT)."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    flavor_upper = flavor.upper()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.create_evaluation_store(name, flavor=flavor_upper)
        result = {"id": store.id, "flavor": flavor_upper}
        render_raw(result, output)
        success(f"Created {flavor_upper} evaluation store {store.id}")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            success(f"Evaluation store '{name}' already exists, skipping.")
            return
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show evaluation store settings."""
    project_key = resolve_project(project)
    resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        raw = store.get_settings().get_raw()
        print(json.dumps(raw, indent=2, default=str))
    except Exception as e:
        handle_api_error(e)


@app.command()
def evaluations(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List evaluations in a model evaluation store."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        evals = store.list_model_evaluations()

        # DSSModelEvaluation objects have .evaluation_id
        data = [{"evaluation_id": e.evaluation_id} for e in evals]

        render(
            data,
            ["evaluation_id"],
            output_format=output,
            title=f"Evaluations ({store_id})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def latest(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the latest evaluation in a store."""
    project_key = resolve_project(project)
    resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        ev = store.get_latest_model_evaluation()

        if ev is None:
            exit_with_error(
                "No evaluations in this store.",
                details=[
                    f"Build the store first: dku evaluation-store build {store_id} -P {project_key}",
                ],
            )

        result = {"evaluation_id": ev.evaluation_id}
        full_info = ev.get_full_info()
        if hasattr(full_info, "get_raw"):
            result["info"] = full_info.get_raw()
        render_raw(result, "json")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


_EVAL_SYNTAX_HINT_TRIPLE_QUOTE = (
    r"unexpected character after line continuation character"
)


def _extract_eval_error_summary(log_text: str) -> list[str]:
    """Pull the most useful lines from a failed evaluation-store job log.

    Aim: surface the actual root cause (SyntaxError, ImportError, custom metric
    crash) within the first ~20 lines of output so agents don't have to
    `dku job log` separately. Recognises the canonical `\"\"\"` JSON-escape
    trap in custom metric code and tags it with a prescriptive fix line.
    """
    if not log_text:
        return []
    lines = log_text.splitlines()
    # Look for the most informative anchor: the first traceback or the first
    # line matching "Error|Exception|SyntaxError|Failed". If found, emit a
    # window of up to 20 lines around it.
    anchor = -1
    keywords = (
        "Traceback",
        "SyntaxError",
        "NameError",
        "TypeError",
        "ValueError",
        "ImportError",
        "ModuleNotFoundError",
        "AttributeError",
        "ERROR",
        "FAILED",
    )
    for i, line in enumerate(lines):
        if any(k in line for k in keywords):
            anchor = i
            break

    excerpt: list[str]
    if anchor == -1:
        # No obvious anchor — just take the tail. Agents will still get signal.
        excerpt = lines[-20:]
    else:
        start = max(0, anchor - 2)
        excerpt = lines[start : start + 20]

    out = ["", "Last activity-log excerpt:"] + [f"  {line}" for line in excerpt]

    # Heuristic: the canonical `"""` JSON-escape trap (custom metric code with
    # docstrings that survived `set_payload` JSON-encoding). Surface a
    # prescriptive fix when we see it.
    if any(_EVAL_SYNTAX_HINT_TRIPLE_QUOTE in line for line in lines) or any(
        '\\"\\"\\"' in line for line in lines
    ):
        out += [
            "",
            "Hint: this SyntaxError pattern usually means a custom metric's",
            'docstring used """ inside a JSON-encoded payload, which round-trips',
            "as \\\"\\\"\\\" — invalid Python. Replace with ''' triple-strings or # comments.",
        ]
    return out


@app.command()
def build(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for build to complete"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Build a model evaluation store.

    Runs the evaluation pipeline and waits for completion by default. On
    failure, automatically pulls the activity log excerpt so the agent can act
    without a separate `dku job log` call. Detects the common `\"\"\"` JSON-
    escape trap in custom metric code and suggests the fix.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        # Pass no_fail=True so we can pull the log ourselves and surface a
        # richer error message. Without this, dataikuapi raises a bare
        # DataikuException("Job run did not finish. Status: FAILED") and the
        # agent has to chase the activity log manually.
        if wait:
            job = store.build(wait=True, no_fail=True)
            status = {}
            try:
                status = job.get_status() or {}
            except Exception:
                pass
            state = (status.get("baseStatus", {}) or {}).get("state", "DONE")
            if state in ("FAILED", "ABORTED"):
                log_text = ""
                try:
                    log_text = job.get_log() or ""
                except Exception:
                    pass
                details = [
                    f"Job ID: {job.id}",
                    f"Status: {state}",
                    f"Full log: dku job log {job.id} -P {project_key}",
                ]
                details.extend(_extract_eval_error_summary(log_text))
                exit_with_error(
                    f"Build failed for evaluation store '{store_id}'.",
                    code="job_failed",
                    details=details,
                )
            success(f"Build complete for evaluation store {store_id} (job: {job.id})")
        else:
            job = store.build(wait=False)
            success(
                f"Build started. Check progress: dku job status {job.id} -P {project_key}"
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    store_id: str = typer.Argument(help="Evaluation store ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a model evaluation store."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="evaluation_store.delete",
        subject=f"evaluation store '{store_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete evaluation store '{store_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        store = proj.get_model_evaluation_store(store_id)
        store.delete()
        success(f"Deleted evaluation store {store_id}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

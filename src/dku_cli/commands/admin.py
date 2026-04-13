"""dku admin — logs, usage, instance-info, sanity-check for DSS instance administration."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="DSS instance administration (admin only).")


@app.command()
def logs(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List available log files."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        log_list = client.list_logs()

        if fmt == "json":
            render_raw(log_list, output_format="json")
        else:
            data = []
            for item in log_list:
                if isinstance(item, dict):
                    data.append(
                        {
                            "name": item.get("name", ""),
                            "size": str(item.get("totalSize", "")),
                        }
                    )
                else:
                    data.append({"name": str(item), "size": ""})
            render(
                data,
                ["name", "size"],
                output_format=fmt,
                title="Log Files",
                headers={"name": "NAME", "size": "SIZE"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command("get-log")
def get_log(
    ctx: typer.Context,
    name: str = typer.Argument(help="Log file name (from 'dku admin logs')"),
) -> None:
    """Get contents of a specific log file.

    Example:
      dku admin get-log backend.log
    """
    try:
        client = get_client_from_ctx(ctx)
        content = client.get_log(name)
        if isinstance(content, str):
            print(content)
        else:
            # Some versions return the log as a dict or other structure
            render_raw(content, output_format="json")
    except Exception as e:
        handle_api_error(e)


@app.command()
def usage(
    ctx: typer.Context,
    per_project: bool = typer.Option(
        False, "--per-project", help="Include per-project breakdown"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show global usage summary (projects, datasets, users, etc).

    Example:
      dku admin usage
      dku admin usage --per-project -o json
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        summary = client.get_global_usage_summary(with_per_project=per_project)
        raw = summary.raw

        if fmt == "json":
            render_raw(raw, output_format="json")
        else:
            data = [
                {"metric": k, "value": str(v)}
                for k, v in raw.items()
                if not isinstance(v, (dict, list))
            ]
            render(
                data,
                ["metric", "value"],
                output_format=fmt,
                title="Usage Summary",
                headers={"metric": "METRIC", "value": "VALUE"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command("instance-info")
def instance_info(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show DSS instance information (node ID, type, version, etc).

    Example:
      dku admin instance-info
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        info_obj = client.get_instance_info()
        raw = info_obj.raw

        if fmt == "json":
            render_raw(raw, output_format="json")
        else:
            data = [
                {"field": k, "value": str(v)}
                for k, v in raw.items()
                if not isinstance(v, (dict, list))
            ]
            render(
                data,
                ["field", "value"],
                output_format=fmt,
                title="Instance Info",
            )
    except Exception as e:
        handle_api_error(e)


@app.command("sanity-check")
def sanity_check(
    ctx: typer.Context,
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for completion"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Run an instance sanity check.

    Checks DSS configuration, connectivity, and health.

    Example:
      dku admin sanity-check
      dku admin sanity-check -o json
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        info("Running sanity check...")
        result = client.perform_instance_sanity_check(wait=wait)

        if not wait:
            success("Sanity check started (use --wait to see results)")
            return

        if fmt == "json":
            # DSSInfoMessages has a .messages property
            if hasattr(result, "messages"):
                render_raw(result.messages, output_format="json")
            else:
                render_raw(result, output_format="json")
        else:
            if hasattr(result, "messages"):
                msgs = result.messages
                if not msgs:
                    success("Sanity check passed — no issues found.")
                else:
                    data = []
                    for msg in msgs:
                        data.append(
                            {
                                "severity": msg.get("severity", ""),
                                "code": msg.get("code", ""),
                                "message": msg.get("message", msg.get("title", "")),
                            }
                        )
                    render(
                        data,
                        ["severity", "code", "message"],
                        output_format=fmt,
                        title="Sanity Check Results",
                        headers={
                            "severity": "SEVERITY",
                            "code": "CODE",
                            "message": "MESSAGE",
                        },
                    )
            else:
                success("Sanity check completed.")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)

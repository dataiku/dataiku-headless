"""dku govern — Govern commands: artifact, blueprint, signoff, role, custom-page, user, group, time-series, file."""

from __future__ import annotations

import typer

from dku_cli.commands import (
    govern_artifact,
    govern_blueprint,
    govern_custom_page,
    govern_file,
    govern_group,
    govern_role,
    govern_signoff,
    govern_time_series,
    govern_user,
)
from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import render_raw, resolve_output_format

app = typer.Typer(
    help="Govern commands: artifact, blueprint, signoff, role, custom-page, user, group, time-series, file."
)

# Register sub-command groups under `dku govern <group> <verb>`
app.add_typer(govern_artifact.app, name="artifact")
app.add_typer(govern_blueprint.app, name="blueprint")
app.add_typer(govern_custom_page.app, name="custom-page")
app.add_typer(govern_file.app, name="file")
app.add_typer(govern_group.app, name="group")
app.add_typer(govern_role.app, name="role")
app.add_typer(govern_signoff.app, name="signoff")
app.add_typer(govern_time_series.app, name="time-series")
app.add_typer(govern_user.app, name="user")


@app.command()
def whoami(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show current authenticated Govern user."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        auth_info = govern.get_auth_info()
        render_raw(auth_info, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def info(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show Govern instance information."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        inst = govern.get_instance_info()
        data = {
            "node_id": inst.node_id,
            "node_name": inst.node_name,
            "node_type": inst.node_type,
        }
        render_raw(data, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)

"""dku govern time-series — create, get, push-values, delete."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx, read_json_input
from dku_cli.output import hint, render_raw, resolve_output_format, success
from dku_cli.safety import Tier, guard

app = typer.Typer(help="Manage Govern time series.")


@app.command()
def create(
    ctx: typer.Context,
    datapoints: Optional[str] = typer.Option(
        None,
        "--datapoints",
        help='JSON array of datapoints (string, @file.json, or - for stdin). Each: {"timestamp": <epoch_ms>, "value": <obj>}',
    ),
) -> None:
    """Create a new time series, optionally with initial datapoints."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        dp = read_json_input(datapoints) if datapoints else []
        ts = govern.create_time_series(datapoints=dp)
        success(f"Created time series '{ts.time_series_id}'")
        hint(f"dku govern time-series get {ts.time_series_id}")
        render_raw({"id": ts.time_series_id}, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    time_series_id: str = typer.Argument(help="Time series ID"),
    min_timestamp: Optional[int] = typer.Option(
        None, "--min", help="Minimum timestamp (epoch ms)"
    ),
    max_timestamp: Optional[int] = typer.Option(
        None, "--max", help="Maximum timestamp (epoch ms)"
    ),
) -> None:
    """Get values from a time series."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        ts = govern.get_time_series(time_series_id)
        values = ts.get_values(min_timestamp=min_timestamp, max_timestamp=max_timestamp)
        render_raw(values, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("push-values")
def push_values(
    ctx: typer.Context,
    time_series_id: str = typer.Argument(help="Time series ID"),
    datapoints: str = typer.Option(
        ...,
        "--datapoints",
        help='JSON array of datapoints (string, @file.json, or - for stdin). Each: {"timestamp": <epoch_ms>, "value": <obj>}',
    ),
    no_upsert: bool = typer.Option(
        False, "--no-upsert", help="Don't overwrite existing timestamps"
    ),
) -> None:
    """Push datapoints into an existing time series."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        ts = govern.get_time_series(time_series_id)
        dp = read_json_input(datapoints)
        ts.push_values(dp, upsert=not no_upsert)
        success(f"Pushed {len(dp)} datapoint(s) to time series '{time_series_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    time_series_id: str = typer.Argument(help="Time series ID"),
    min_timestamp: Optional[int] = typer.Option(
        None, "--min", help="Minimum timestamp (epoch ms) — delete from this time"
    ),
    max_timestamp: Optional[int] = typer.Option(
        None, "--max", help="Maximum timestamp (epoch ms) — delete up to this time"
    ),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete time series values. Without --min/--max, deletes all values."""
    guard(
        ctx,
        tier=Tier.DELETE,
        action="govern.time_series.delete",
        subject=f"time series '{time_series_id}' values",
        yes=confirm,
        prompt=f"Delete values from Govern time series '{time_series_id}'?",
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        ts = govern.get_time_series(time_series_id)
        ts.delete(min_timestamp=min_timestamp, max_timestamp=max_timestamp)
        success(f"Deleted values from time series '{time_series_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)

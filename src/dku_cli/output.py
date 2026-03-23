"""Unified output formatting: table, json, csv."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Sequence

import typer
from rich.console import Console
from rich.table import Table

from dku_cli.brand import ICON

console = Console()
err_console = Console(stderr=True)

_quiet = False
_error_format = "text"


def set_quiet(value: bool) -> None:
    """Enable/disable quiet mode (suppresses info/success/warn on stderr)."""
    global _quiet
    _quiet = value


def is_quiet() -> bool:
    """Check if quiet mode is active."""
    return _quiet


def set_error_format(value: str) -> None:
    """Configure how errors are rendered ('text' or 'json')."""
    if value not in ("text", "json"):
        raise ValueError(f"Error format must be 'text' or 'json', got {value!r}")
    global _error_format
    _error_format = value


def get_error_format() -> str:
    """Return the active error rendering mode."""
    return _error_format


def resolve_output_format(
    output_format: str | None,
    *,
    allowed: Sequence[str] = ("table", "json", "csv"),
    default: str | None = None,
) -> str:
    """Resolve an output format from CLI input and persisted config."""
    if output_format is not None:
        resolved = output_format.lower()
        if resolved not in allowed:
            raise typer.BadParameter(
                f"Output format must be one of: {', '.join(allowed)}"
            )
        return resolved

    from dku_cli.config import get_default_output

    configured = str(get_default_output()).strip().lower()
    if configured in allowed:
        return configured

    return (default or allowed[0]).lower()


def render(
    data: Sequence[dict[str, Any]],
    columns: list[str],
    *,
    output_format: str = "table",
    title: str | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """Render data in the requested format.

    Args:
        data: List of dicts to display.
        columns: Keys to include, in order.
        output_format: "table", "json", or "csv".
        title: Optional table title.
        headers: Optional display name mapping {key: "Display Name"}.
    """
    if output_format == "json":
        _render_json(data, columns)
    elif output_format == "csv":
        _render_csv(data, columns, headers)
    else:
        _render_table(data, columns, title=title, headers=headers)


def _render_table(
    data: Sequence[dict[str, Any]],
    columns: list[str],
    *,
    title: str | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    headers = headers or {}
    table = Table(title=title, show_lines=False)
    for col in columns:
        table.add_column(headers.get(col, col.upper()))
    for row in data:
        table.add_row(*[str(row.get(col, "")) for col in columns])
    console.print(table)


def _render_json(
    data: Sequence[dict[str, Any]],
    columns: list[str],
) -> None:
    filtered = [{k: row.get(k, "") for k in columns} for row in data]
    # Print to stdout directly (not via Rich) for clean piping
    print(json.dumps(filtered, indent=2, default=str))


def _render_csv(
    data: Sequence[dict[str, Any]],
    columns: list[str],
    headers: dict[str, str] | None = None,
) -> None:
    headers = headers or {}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([headers.get(c, c) for c in columns])
    for row in data:
        writer.writerow([str(row.get(c, "")) for c in columns])
    print(buf.getvalue(), end="")


def success(msg: str) -> None:
    if not _quiet:
        err_console.print(f"[green]{ICON}[/green] {msg}")


def error(msg: str) -> None:
    err_console.print(f"[red]{ICON}[/red] {msg}")


def warn(msg: str) -> None:
    if not _quiet:
        err_console.print(f"[yellow]{ICON}[/yellow] {msg}")


def info(msg: str) -> None:
    if not _quiet:
        err_console.print(f"[dim]{msg}[/dim]")


def render_raw(data: Any, output_format: str = "json") -> None:
    """Render a single dict/list. JSON: dumps. Table: key-value pairs or auto-detected columns."""
    if output_format == "json":
        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, dict):
            rows = [{"key": k, "value": str(v)} for k, v in data.items()]
            render(rows, ["key", "value"], output_format="table")
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            # Auto-detect columns from first item for table rendering
            columns = list(data[0].keys())
            rows = [{k: str(v) for k, v in item.items()} for item in data]
            render(rows, columns, output_format="table")
        elif isinstance(data, list):
            print(json.dumps(data, indent=2, default=str))
        else:
            print(str(data))

"""dku sql — query."""

from __future__ import annotations

from pathlib import Path

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import render, resolve_output_format

app = typer.Typer(help="Run SQL queries on DSS connections.")


def _read_query(value: str) -> str:
    """Read SQL query from: literal string or @file.sql path."""
    if value.startswith("@"):
        path = Path(value[1:])
        if not path.exists():
            raise typer.BadParameter(f"File not found: {path}")
        return path.read_text()
    return value


@app.command()
def query(
    ctx: typer.Context,
    sql: str = typer.Argument(help="SQL query (literal or @file.sql)"),
    connection: str = typer.Option(..., "--connection", "-c", help="Connection name"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Execute a SQL query on a DSS connection."""
    output = resolve_output_format(output)
    query_text = _read_query(sql)
    try:
        client = get_client_from_ctx(ctx)
        result = client.sql_query(query_text, connection=connection)

        schema = result.get_schema()
        columns = [col["name"] for col in schema]
        rows = list(result.iter_rows())

        data = []
        for row in rows:
            data.append({col: val for col, val in zip(columns, row)})

        render(
            data,
            columns,
            output_format=output,
            title=f"Query Results ({connection})",
        )
    except Exception as e:
        handle_api_error(e)

"""dku sql — query."""

from __future__ import annotations

from pathlib import Path

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import render, resolve_output_format, success

app = typer.Typer(help="Run SQL queries on DSS connections.")


# DDL/DML keywords that require an explicit COMMIT to persist via the DSS
# sql_query endpoint. The endpoint runs every statement inside a streaming
# session that closes without committing JDBC transaction state, so CREATE /
# INSERT / UPDATE / etc. are silently rolled back unless we append COMMIT.
_DDL_DML_KEYWORDS = frozenset(
    {
        "CREATE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "GRANT",
        "REVOKE",
    }
)


def _read_query(value: str) -> str:
    """Read SQL query from: literal string or @file.sql path."""
    if value.startswith("@"):
        path = Path(value[1:])
        if not path.exists():
            raise typer.BadParameter(f"File not found: {path}")
        return path.read_text()
    return value


def _strip_leading_comments(sql: str) -> str:
    """Strip leading whitespace, line comments (--), and block comments (/* */)."""
    s = sql.lstrip()
    while True:
        if s.startswith("--"):
            nl = s.find("\n")
            s = (s[nl + 1 :] if nl != -1 else "").lstrip()
        elif s.startswith("/*"):
            end = s.find("*/")
            s = (s[end + 2 :] if end != -1 else "").lstrip()
        else:
            return s


def _is_ddl_or_dml(sql: str) -> bool:
    """Return True if the query's first token is a DDL/DML keyword.

    Honors leading whitespace and SQL comments so that commented-out
    SELECTs above a DDL statement don't hide it.
    """
    body = _strip_leading_comments(sql)
    if not body:
        return False
    first_token = body.split(None, 1)[0].upper()
    return first_token in _DDL_DML_KEYWORDS


@app.command()
def query(
    ctx: typer.Context,
    sql: str = typer.Argument(help="SQL query (literal or @file.sql)"),
    connection: str = typer.Option(..., "--connection", "-c", help="Connection name"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
    no_auto_commit: bool = typer.Option(
        False,
        "--no-auto-commit",
        help="Do not auto-append COMMIT on DDL/DML statements. Use when you want to test rollback behavior or run inside an explicit BEGIN/COMMIT block.",
    ),
) -> None:
    """Execute a SQL query on a DSS connection.

    Supports both SELECT (returns rows) and DDL/DML statements
    (CREATE/DROP/ALTER/TRUNCATE/INSERT/UPDATE/DELETE/MERGE/GRANT/REVOKE).

    For DDL/DML, the CLI automatically runs a COMMIT after the statement.
    Without this, DSS's sql_query endpoint opens a streaming session that
    closes without committing, and the change is silently rolled back.
    Pass --no-auto-commit to opt out (e.g., inside an explicit transaction).
    """
    output = resolve_output_format(output)
    query_text = _read_query(sql)
    is_mutation = _is_ddl_or_dml(query_text)
    post_queries = ["COMMIT"] if (is_mutation and not no_auto_commit) else None
    try:
        client = get_client_from_ctx(ctx)
        result = client.sql_query(
            query_text, connection=connection, post_queries=post_queries
        )

        # DDL / DML queries return no result set. Calling get_schema() /
        # iter_rows() on such a result raises an error — treat that as
        # success, not failure.
        try:
            schema = result.get_schema()
        except Exception:
            if post_queries:
                success(f"Committed on {connection}")
            else:
                success(f"Statement executed on {connection}")
            return

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

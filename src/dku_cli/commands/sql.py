"""dku sql — query."""

from __future__ import annotations

import re
from pathlib import Path

import typer

from dku_cli.errors import exit_with_error, handle_api_error
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

# Whole-table / whole-schema blast radius — these drop or restructure objects,
# so they get the CASCADE tier (--yes AND --confirm-name matching the
# connection). Everything else in _DDL_DML_KEYWORDS (INSERT / UPDATE / DELETE /
# MERGE / CREATE / GRANT / REVOKE) mutates rows or grants and gets the DELETE
# tier (--yes).
_CASCADE_KEYWORDS = frozenset({"DROP", "TRUNCATE", "ALTER"})


def _read_query(value: str) -> str:
    """Read SQL query from: literal string or @file.sql path."""
    if value.startswith("@"):
        path = Path(value[1:])
        if not path.exists():
            raise typer.BadParameter(f"File not found: {path}")
        return path.read_text()
    return value


# Verbs that introduce a statement. Used to resolve what a WITH-prefixed query
# actually does once its CTE list is skipped.
_STATEMENT_VERBS = _DDL_DML_KEYWORDS | {"SELECT", "WITH"}
_SQL_WORD = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def _strip_comments_and_strings(sql: str) -> str:
    """Replace comments, '...' strings, and "..." quoted identifiers with spaces.

    Keyword and statement-separator (`;`) detection runs on the result, so a
    `DROP` inside a string literal cannot trigger the guard and a `;` inside a
    comment cannot split a statement — neither can hide a mutation either.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        two = sql[i : i + 2]
        if two == "--":
            nl = sql.find("\n", i)
            if nl == -1:
                break
            out.append("\n")
            i = nl + 1
        elif two == "/*":
            end = sql.find("*/", i + 2)
            i = (end + 2) if end != -1 else n
            out.append(" ")
        elif sql[i] in "'\"":
            quote = sql[i]
            i += 1
            while i < n:
                if sql[i] == quote:
                    if sql[i + 1 : i + 2] == quote:  # doubled '' / "" escape
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" ")
        else:
            out.append(sql[i])
            i += 1
    return "".join(out)


def _strip_balanced_parens(sql: str) -> str:
    """Drop the contents of every parenthesized group, keeping depth-0 text.

    Skips a WITH statement's CTE definition list (which lives in parens) so the
    operative verb after it — SELECT vs DELETE/UPDATE/INSERT/MERGE — is visible.
    """
    out: list[str] = []
    depth = 0
    for ch in sql:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _keyword_tokens(sql: str) -> list[str]:
    return [match.group(0).upper() for match in _SQL_WORD.finditer(sql)]


def _statement_verbs(stmt: str) -> list[str]:
    """Operative verb of one statement, seeing through a WITH-prefixed CTE list.

    A data-modifying CTE (`WITH x AS (...) DELETE ...`) resolves to its real
    verb (DELETE) so it is guarded; a read-only `WITH x AS (...) SELECT ...`
    resolves to SELECT so it is not.
    """
    tokens = _keyword_tokens(stmt)
    if not tokens:
        return []
    first = tokens[0].upper()
    if first != "WITH":
        return [first]

    mutations = [token for token in tokens if token in _DDL_DML_KEYWORDS]
    if mutations:
        return mutations

    for token in _strip_balanced_parens(stmt).split():
        verb = token.upper()
        if verb in _STATEMENT_VERBS and verb != "WITH":
            return [verb]
    return ["WITH"]


def _operative_keywords(sql: str) -> list[str]:
    """Operative verb of every statement in the query.

    Sees through `;`-chaining, leading/embedded comments, string literals, and
    `WITH` CTE prefixes — the four ways a first-token check would miss a
    mutation hiding behind a leading SELECT or comment.
    """
    cleaned = _strip_comments_and_strings(sql)
    return [verb for stmt in cleaned.split(";") for verb in _statement_verbs(stmt)]


def _is_ddl_or_dml(sql: str) -> bool:
    """True if ANY statement mutates (DDL/DML), even when wrapped in a CTE or
    chained after a leading SELECT."""
    return any(kw in _DDL_DML_KEYWORDS for kw in _operative_keywords(sql))


def _mutation_tier(sql: str) -> tuple[str, str] | None:
    """Return (tier, keyword) for the highest-blast-radius mutation, or None.

    CASCADE (DROP/TRUNCATE/ALTER) outranks DELETE (other DDL/DML), so a
    `INSERT ...; DROP ...` chain is guarded at the DROP tier.
    """
    keywords = [kw for kw in _operative_keywords(sql) if kw in _DDL_DML_KEYWORDS]
    if not keywords:
        return None
    cascade = next((kw for kw in keywords if kw in _CASCADE_KEYWORDS), None)
    return ("CASCADE", cascade) if cascade else ("DELETE", keywords[0])


def _guard_mutation(
    ctx: typer.Context, query_text: str, connection: str, yes: bool, confirm_name: str
) -> None:
    """Safety-guard a mutating SQL statement before it runs.

    DROP/TRUNCATE/ALTER get the CASCADE tier (--yes + --confirm-name matching the
    connection); other DDL/DML gets the DELETE tier (--yes). Detection sees
    through `;`-chaining and WITH-prefixed CTEs, so `SELECT 1; DROP ...` or
    `WITH x AS (...) DELETE ...` cannot slip past as a read.
    """
    from dku_cli.safety import Tier, guard

    tier = _mutation_tier(query_text)
    if tier is None:
        return
    tier_name, keyword = tier
    if tier_name == "CASCADE":
        guard(
            ctx,
            tier=Tier.CASCADE,
            action="sql.query",
            subject=f"{keyword} statement on connection '{connection}'",
            yes=yes,
            target_id=connection,
            confirm_name=confirm_name,
            prompt=(
                f"Run a {keyword} statement on connection '{connection}'? "
                "This can destroy whole tables/schemas and cannot be undone."
            ),
        )
    else:
        guard(
            ctx,
            tier=Tier.DELETE,
            action="sql.query",
            subject=f"{keyword} statement on connection '{connection}'",
            yes=yes,
            prompt=(
                f"Run a {keyword} statement on connection '{connection}'? "
                "It commits immediately and mutates data."
            ),
        )


@app.command()
def query(
    ctx: typer.Context,
    sql: str = typer.Argument(help="SQL query (literal or @file.sql)"),
    connection: str = typer.Option(..., "--connection", "-c", help="Connection name"),
    project: str | None = typer.Option(
        None,
        "--project",
        "-P",
        help=(
            "Accepted and ignored — SQL queries are connection-scoped, not "
            "project-scoped. Find connections with: dku connection list"
        ),
    ),
    no_auto_commit: bool = typer.Option(
        False,
        "--no-auto-commit",
        help=(
            "Do not auto-append COMMIT on DDL/DML statements. Use when you want "
            "to test rollback behavior or run inside an explicit BEGIN/COMMIT block."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        "--confirm",
        help=(
            "Confirm a mutating (DDL/DML) statement. Required for "
            "INSERT/UPDATE/DELETE/MERGE/CREATE/GRANT/REVOKE; "
            "DROP/TRUNCATE/ALTER also need --confirm-name."
        ),
    ),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help=(
            "Must match the connection name to authorize a "
            "DROP/TRUNCATE/ALTER (tier-3 cascade guard)."
        ),
    ),
) -> None:
    """Execute a SQL query on a DSS connection.

    Supports both SELECT (returns rows) and DDL/DML statements
    (CREATE/DROP/ALTER/TRUNCATE/INSERT/UPDATE/DELETE/MERGE/GRANT/REVOKE).

    SELECT runs unguarded. Mutating statements run with auto-COMMIT and are
    safety-guarded: INSERT/UPDATE/DELETE/MERGE/CREATE/GRANT/REVOKE need --yes;
    DROP/TRUNCATE/ALTER (whole-table/schema blast radius) additionally need
    --confirm-name matching the connection name.

    The mutation check sees through comments, string literals, statement chains
    (`SELECT 1; DROP ...`), and data-modifying CTEs (`WITH x AS (...) DELETE
    ...`), so a destructive statement cannot hide behind a leading SELECT or
    comment. A chain is guarded at its highest tier (any DROP/TRUNCATE/ALTER
    forces --confirm-name).

    For DDL/DML, the CLI automatically runs a COMMIT after the statement.
    Without this, DSS's sql_query endpoint opens a streaming session that
    closes without committing, and the change is silently rolled back.
    Pass --no-auto-commit to opt out (e.g., inside an explicit transaction).

    SQL is connection-scoped: -P is accepted for muscle-memory consistency
    with other commands but has no effect.
    """
    del project  # accepted for ergonomic parity; SQL is connection-scoped
    output = resolve_output_format()
    query_text = _read_query(sql)
    is_mutation = _is_ddl_or_dml(query_text)

    if is_mutation:
        _guard_mutation(ctx, query_text, connection, yes, confirm_name)

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

        n = len(rows)
        render(
            data,
            columns,
            output_format=output,
            title=f"Query Results ({connection}) — {n} row(s)",
        )
    except typer.Exit:
        raise
    except Exception as e:
        msg = str(e)
        # Raw Java exceptions leak from DSS in several scenarios. Classify them
        # so agents get actionable guidance instead of "Cannot connect to DSS".
        if "Connection '" in msg and "does not exist" in msg:
            exit_with_error(
                f"Connection '{connection}' does not exist.",
                status=3,
                details=["List connections: dku connection list"],
            )
        if "Unexpected connection type" in msg or "AbstractSQLConnection" in msg:
            exit_with_error(
                f"Connection '{connection}' is not a SQL connection.",
                status=2,
                details=[
                    "dku sql query only works on SQL connections.",
                    "Filter SQL conns: dku connection list --type PostgreSQL (or your SQL type)",
                ],
            )
        if "PSQLException" in msg or "SQLException" in msg or "ERROR:" in msg:
            exit_with_error(
                "SQL query failed.",
                status=1,
                details=[f"Database: {msg.strip()}"],
            )
        handle_api_error(e)

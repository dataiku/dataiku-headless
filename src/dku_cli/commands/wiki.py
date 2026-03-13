"""dku wiki — list, create, get."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS wiki articles.")


def _read_body(value: str | None) -> str:
    """Read body content from: literal string, @file path, or stdin (-)."""
    if value is None:
        return ""
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        path = Path(value[1:])
        if not path.exists():
            raise typer.BadParameter(f"File not found: {path}")
        return path.read_text()
    return value


@app.command("list")
def list_articles(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List wiki articles in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        wiki = proj.get_wiki()
        articles = wiki.list_articles()

        data = []
        for a in articles:
            article = a.get("article", a)
            data.append({
                "id": article.get("id", a.get("id", "")),
                "title": article.get("name", ""),
            })

        render(
            data,
            ["id", "title"],
            output_format=output,
            title=f"Wiki Articles ({project_key})",
            headers={"id": "ID", "title": "TITLE"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    title: str = typer.Argument(help="Article title"),
    body: str = typer.Option("", "--body", "-b", help="Article body (literal, @file.md, or - for stdin)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a wiki article."""
    project_key = resolve_project(project)
    body_content = _read_body(body)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        wiki = proj.get_wiki()
        article = wiki.create_article(title, body_content)

        success(f"Created wiki article '{title}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    article_id: str = typer.Argument(help="Article ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get a wiki article's content."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        wiki = proj.get_wiki()
        article = wiki.get_article(article_id)
        data = article.get_data()

        if output == "json":
            render_raw(data, output_format="json")
        else:
            # Print the body/content for human-readable output
            body = data.get("body", "")
            article_meta = data.get("article", {})
            title = article_meta.get("name", article_id)
            print(f"# {title}\n")
            print(body)
    except Exception as e:
        handle_api_error(e)

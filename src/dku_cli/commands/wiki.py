"""dku wiki — list, create, get, update, delete."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from dku_cli.errors import handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import (
    hint,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS wiki articles.")


def _read_body(value: str | None) -> str:
    """Read body content from: literal string, @file path, or stdin (-)."""
    if value is None:
        return ""
    if value == "-":
        body = sys.stdin.read()
        if body == "":
            raise typer.BadParameter("stdin is empty")
        return body
    if value.startswith("@"):
        path = Path(value[1:])
        if not path.exists():
            raise typer.BadParameter(f"File not found: {path}")
        body = path.read_text()
        if body == "":
            raise typer.BadParameter(f"File is empty: {path}")
        return body
    return value


@app.command("list")
def list_articles(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List wiki articles in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        wiki = proj.get_wiki()
        articles = wiki.list_articles()

        data = []
        for a in articles:
            # DSSWikiArticle objects have .article_id; get_data() returns DSSWikiArticleData
            article_data = a.get_data()
            data.append(
                {
                    "id": a.article_id,
                    "title": article_data.get_name(),
                }
            )

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
    body: str = typer.Option(
        "",
        "--body",
        "--content",
        "-b",
        help="Article body (literal, @file.md, or - for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if article already exists"
    ),
) -> None:
    """Create a wiki article."""
    project_key = resolve_project(project)
    body_content = _read_body(body)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        wiki = proj.get_wiki()
        article = wiki.create_article(title, content=body_content)
        success(f"Created wiki article '{title}' in {project_key}")
        hint(f"dku wiki get {article.article_id} -P {project_key}")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(
                f"Wiki article '{title}' already exists in {project_key}, skipping create"
            )
            return
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    article_id: str = typer.Argument(help="Article ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get a wiki article's content."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        wiki = proj.get_wiki()
        article = wiki.get_article(article_id)
        data = article.get_data()

        if output == "json":
            # DSSWikiArticleData isn't directly JSON-serializable
            render_raw(
                {
                    "id": article_id,
                    "name": data.get_name(),
                    "body": data.get_body(),
                },
                output_format="json",
            )
        else:
            title = data.get_name() or article_id
            body = data.get_body() or ""
            print(f"# {title}\n")
            print(body)
    except Exception as e:
        handle_api_error(e)


@app.command()
def update(
    ctx: typer.Context,
    article_id: str = typer.Argument(help="Article ID"),
    body: str = typer.Option(
        None, "--body", "-b", help="New body (literal, @file.md, or - for stdin)"
    ),
    title: str = typer.Option(None, "--title", "-t", help="New title"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Update a wiki article's body and/or title."""
    project_key = resolve_project(project)
    if body is None and title is None:
        raise typer.BadParameter("Provide --body and/or --title to update.")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        wiki = proj.get_wiki()
        article = wiki.get_article(article_id)
        data = article.get_data()

        if title is not None:
            data.set_name(title)
        if body is not None:
            body_content = _read_body(body)
            data.set_body(body_content)

        data.save()
        success(f"Updated wiki article '{article_id}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    article_id: str = typer.Argument(help="Article ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(
        False, "--yes", "-y", "--confirm", help="Skip safety guard"
    ),
) -> None:
    """Delete a wiki article."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="wiki.delete",
        subject=f"wiki article '{article_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete wiki article '{article_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        wiki = proj.get_wiki()
        article = wiki.get_article(article_id)
        article.delete()
        success(f"Deleted wiki article '{article_id}' from {project_key}")
    except Exception as e:
        handle_api_error(e)

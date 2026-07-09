"""Wiki operations for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.auth import get_dss_client
from .utils.validation import require_non_empty_string as _require_non_empty_string


def _build_parent_map(taxonomy: list, parent_id: str | None = None) -> dict:
    """Recursively map article_id -> parent_id from the taxonomy tree."""
    result = {}
    for node in taxonomy:
        article_id = node.get("id")
        result[article_id] = parent_id
        result.update(_build_parent_map(node.get("children", []), article_id))
    return result


@mcp.tool()
async def list_wiki_articles(project_key: str, ctx: Context) -> str:
    """List the wiki articles in the project with their IDs, names, parent hierarchy, and home flag."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing wiki articles in {project_key}...")

    def _run():
        wiki = get_dss_client().get_project(project_key).get_wiki()
        settings = wiki.get_settings()
        parent_map = _build_parent_map(settings.get_taxonomy())
        home_id = settings.get_home_article_id()

        articles = [
            {
                "id": article.article_id,
                "name": article.get_data().get_name(),
                "parent_id": parent_map.get(article.article_id),
            }
            for article in wiki.list_articles()
        ]
        return {"home_article_id": home_id, "articles": articles}

    result = await run_blocking(_run)
    payload = {
        "home_article_id": result["home_article_id"],
        # columnar block left untouched (per-invocation emptiness, positional)
        "articles": columnar(
            result["articles"], ["id", "name", "parent_id"]
        ),
    }
    # LEVER 4: omit home_article_id when None (no home article set)
    payload = omit_empty(payload)
    return compact_json(payload)


@mcp.tool()
async def get_wiki_article(project_key: str, article_id: str, ctx: Context) -> str:
    """Get the wiki article's name and markdown body."""
    project_key = _require_non_empty_string(project_key, "project_key")
    article_id = _require_non_empty_string(article_id, "article_id")
    await ctx.info(f"Fetching wiki article {article_id} in {project_key}...")

    def _run():
        data = (
            get_dss_client()
            .get_project(project_key)
            .get_wiki()
            .get_article(article_id)
            .get_data()
        )
        return {"name": data.get_name(), "body": data.get_body()}

    result = await run_blocking(_run)
    payload = {**result}
    # LEVER 4: omit body (and any empty scalar) when "" / None — e.g. an empty article body
    payload = omit_empty(payload)
    return compact_json(payload)


@mcp.tool()
async def create_wiki_article(
    project_key: str,
    article_name: str,
    ctx: Context,
    body: str | None = None,
    parent_article_id: str | None = None,
) -> str:
    """Create a new wiki article in the project.

    Args:
        body: Optional markdown body content
        parent_article_id: Optional parent article ID; omit for a root-level article
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    article_name = _require_non_empty_string(article_name, "article_name")
    await ctx.info(f"Creating wiki article '{article_name}' in {project_key}...")

    def _run():
        wiki = get_dss_client().get_project(project_key).get_wiki()
        article = wiki.create_article(
            article_name, parent_id=parent_article_id, content=body
        )
        return article.article_id

    new_id = await run_blocking(_run)
    payload = {
        "article_id": new_id,
        "parent_article_id": parent_article_id,
    }
    # LEVER 4: omit parent_article_id when None (root-level article)
    payload = omit_empty(payload)
    return compact_json(payload)


@mcp.tool()
async def update_wiki_article(
    project_key: str,
    article_id: str,
    ctx: Context,
    name: str | None = None,
    body: str | None = None,
    new_parent_article_id: str | None = None,
    move_to_top_level: bool = False,
) -> str:
    """Update the wiki article's name, body, or hierarchy position. Pass only the fields to change (at least one).

    Args:
        name: New display name
        body: New markdown body (replaces the existing body entirely)
        new_parent_article_id: Move the article under this parent
        move_to_top_level: If true, remove the parent (makes the article top-level)
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    article_id = _require_non_empty_string(article_id, "article_id")

    if name is None and body is None and new_parent_article_id is None and not move_to_top_level:
        raise ValueError(
            "At least one of name, body, new_parent_article_id, or move_to_top_level must be provided."
        )

    await ctx.info(f"Updating wiki article {article_id} in {project_key}...")

    def _run():
        wiki = get_dss_client().get_project(project_key).get_wiki()
        updated = {}

        if name is not None or body is not None:
            data = wiki.get_article(article_id).get_data()
            if name is not None:
                data.set_name(name)
                updated["name"] = name
            if body is not None:
                data.set_body(body)
                updated["body_updated"] = True
            data.save()

        if move_to_top_level or new_parent_article_id is not None:
            settings = wiki.get_settings()
            parent = None if move_to_top_level else new_parent_article_id
            settings.move_article_in_taxonomy(article_id, parent)
            settings.save()
            updated["parent_article_id"] = parent

        return updated

    updated = await run_blocking(_run)
    return compact_json({
            "updated": updated,
        })


@mcp.tool()
async def delete_wiki_article(project_key: str, article_id: str, ctx: Context) -> str:
    """Delete the wiki article."""
    project_key = _require_non_empty_string(project_key, "project_key")
    article_id = _require_non_empty_string(article_id, "article_id")
    await ctx.info(f"Deleting wiki article {article_id} in {project_key}...")

    await run_blocking(
        lambda: get_dss_client()
        .get_project(project_key)
        .get_wiki()
        .get_article(article_id)
        .delete()
    )

    return compact_json({})

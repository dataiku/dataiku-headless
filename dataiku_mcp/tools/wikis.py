# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Wiki inspection for Dataiku."""

from fastmcp import Context

from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import require_non_empty_string as _require_non_empty_string


def _build_parent_map(taxonomy: list, parent_id: str | None = None) -> dict:
    result = {}
    for node in taxonomy:
        article_id = node.get("id")
        result[article_id] = parent_id
        result.update(_build_parent_map(node.get("children", []), article_id))
    return result


@mcp.tool(
    title="List Wiki Articles",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_wiki_articles(project_key: str, ctx: Context) -> str:
    """Map a project wiki's articles, their IDs, and how they nest."""
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
        "articles": columnar(result["articles"], ["id", "name", "parent_id"]),
    }
    payload = omit_empty(payload)
    return compact_json(payload)


@mcp.tool(
    title="Get Wiki Article",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_wiki_article(project_key: str, article_id: str, ctx: Context) -> str:
    """Read a wiki article's markdown body, for project context written by humans."""
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
    return compact_json(omit_empty({**result}))

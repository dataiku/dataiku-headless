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

"""Chart insight inspection for Dataiku."""

from fastmcp import Context

from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string as _require_non_empty_string


def _serialize_insight_list_item(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "type": item.type,
        "listed": item.listed,
        "owner": item.owner,
        "tags": item.tags,
    }


@mcp.tool(
    title="List Insights",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_insights(project_key: str, ctx: Context) -> str:
    """Find a project's insights and their exact IDs, types, and owners."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing insights in {project_key}...")

    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_insights()
    )
    insights = [_serialize_insight_list_item(item) for item in items]
    return compact_json(
        {
            "insights": columnar(
                insights,
                ["id", "name", "type", "listed", "owner", "tags"],
            )
        }
    )


@mcp.tool(
    title="Get Insight Settings",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_insight_settings(
    project_key: str,
    insight_id: str,
    ctx: Context,
) -> str:
    """Read one insight's full definition, to ground a Cobuild change to it."""
    project_key = _require_non_empty_string(project_key, "project_key")
    insight_id = _require_non_empty_string(insight_id, "insight_id")
    await ctx.info(f"Loading insight {insight_id} in {project_key}...")

    raw = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_insight(insight_id)
            .get_settings()
            .get_raw()
        )
    )
    return compact_json(raw)

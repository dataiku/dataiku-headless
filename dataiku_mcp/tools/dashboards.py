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

"""Dashboard inspection for Dataiku."""

from fastmcp import Context

from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string as _require_non_empty_string


def _serialize_dashboard_list_item(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "listed": item.listed,
        "owner": item.owner,
        "num_pages": item.num_pages,
        "num_tiles": item.num_tiles,
        "tags": item.tags,
    }


@mcp.tool(
    title="List Dashboards",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_dashboards(project_key: str, ctx: Context) -> str:
    """Find a project's dashboards and their exact IDs, owners, and sizes."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing dashboards in {project_key}...")

    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_dashboards()
    )
    dashboards = [_serialize_dashboard_list_item(item) for item in items]
    return compact_json(
        {
            "dashboards": columnar(
                dashboards,
                ["id", "name", "listed", "owner", "num_pages", "num_tiles", "tags"],
            )
        }
    )


@mcp.tool(
    title="Get Dashboard Settings",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_dashboard_settings(
    project_key: str,
    dashboard_id: str,
    ctx: Context,
) -> str:
    """Read one dashboard's full definition, including its pages and tiles."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dashboard_id = _require_non_empty_string(dashboard_id, "dashboard_id")
    await ctx.info(f"Loading dashboard {dashboard_id} in {project_key}...")

    raw = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_dashboard(dashboard_id)
            .get_settings()
            .get_raw()
        )
    )
    return compact_json(raw)

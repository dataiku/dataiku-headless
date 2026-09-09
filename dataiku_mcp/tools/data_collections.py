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

"""Data Collections — instance-wide curated catalog of datasets."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.auth import get_dss_client
from .utils.validation import require_non_empty_string as _require_non_empty_string


@mcp.tool(
    title="List Data Collections",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_data_collections(ctx: Context) -> str:
    """Discover the instance's curated data catalogs and their IDs."""
    await ctx.info("Listing data collections...")

    def _run():
        return [
            {
                "id": dc.id,
                "name": dc.display_name,
                "description": dc.description,
                "tags": dc.tags,
                "item_count": dc.item_count,
            }
            for dc in get_dss_client().list_data_collections()
        ]

    return compact_json(
        columnar(
            await run_blocking(_run),
            ["id", "name", "description", "tags", "item_count"],
        )
    )


@mcp.tool(
    title="List Data Collection Objects",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_data_collection_objects(collection_id: str, ctx: Context) -> str:
    """See which datasets a Data Collection catalogs, and the projects they live in."""
    collection_id = _require_non_empty_string(collection_id, "collection_id")
    await ctx.info(f"Listing objects in collection {collection_id}...")

    def _run():
        items = (
            get_dss_client()
            .get_data_collection(collection_id)
            .list_objects(as_type="dict")
        )
        for i in items:
            if "projectKey" in i:
                i["project_key"] = i.pop("projectKey")
        return items

    return compact_json(await run_blocking(_run))

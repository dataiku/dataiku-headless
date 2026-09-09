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

"""Saved model inspection tools."""

from fastmcp import Context

from ... import mcp
from ..utils.async_executor import run_blocking
from ..utils.auth import get_dss_client
from ..utils.serialization import columnar, compact_json
from ..utils.validation import require_non_empty_string as _require_non_empty_string


@mcp.tool(
    title="List Saved Models",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_saved_models(project_key: str, ctx: Context) -> str:
    """Find a project's deployed saved models and their IDs."""
    project_key = _require_non_empty_string(project_key, "project_key")
    raw_models = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_saved_models()
    )
    result = [
        {
            "id": model["id"],
            "name": model.get("name", ""),
            "type": model.get("type", ""),
            "miniTask": model.get("miniTask", {}).get("taskType", ""),
        }
        for model in raw_models
    ]
    return compact_json(columnar(result, ["id", "name", "type", "miniTask"]))


@mcp.tool(
    title="List Saved Model Versions",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_saved_model_versions(
    project_key: str,
    model_id: str,
    ctx: Context,
) -> str:
    """Find a saved model's versions and which one is active."""
    project_key = _require_non_empty_string(project_key, "project_key")
    model_id = _require_non_empty_string(model_id, "model_id")
    await ctx.info(f"Listing versions for saved model {model_id} in {project_key}...")

    versions = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_saved_model(model_id)
            .list_versions()
        )
    )
    return compact_json({"versions": versions})


@mcp.tool(
    title="Get Saved Model Version Details",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_saved_model_version_details(
    project_key: str,
    model_id: str,
    version_id: str,
    ctx: Context,
) -> str:
    """Read one saved model version's algorithm, features, and performance metrics."""
    project_key = _require_non_empty_string(project_key, "project_key")
    model_id = _require_non_empty_string(model_id, "model_id")
    version_id = _require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Fetching details for version {version_id} of saved model "
        f"{model_id} in {project_key}..."
    )

    def _run():
        details = (
            get_dss_client()
            .get_project(project_key)
            .get_saved_model(model_id)
            .get_version_details(version_id)
        )
        return {
            "details_class": details.__class__.__name__,
            "snippet": details.get_raw_snippet(),
        }

    return compact_json(await run_blocking(_run))

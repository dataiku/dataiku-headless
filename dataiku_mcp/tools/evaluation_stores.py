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

"""Inspection tools for Dataiku Evaluation Stores."""

from typing import Literal

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string


@mcp.tool(
    title="Get Evaluation Store Details",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_evaluation_store_details(
    project_key: str,
    evaluation_store_id: str,
    ctx: Context,
) -> str:
    """Read one evaluation store's metadata and the history of its evaluations."""
    project_key = require_non_empty_string(project_key, "project_key")
    evaluation_store_id = require_non_empty_string(
        evaluation_store_id, "evaluation_store_id"
    )
    await ctx.info(
        f"Getting evaluation store {evaluation_store_id} in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        try:
            store = project.get_model_evaluation_store(evaluation_store_id)
            store_settings = store.get_settings().settings
        except DataikuException as exc:
            raise ValueError(
                f"Evaluation store '{evaluation_store_id}' not found in project "
                f"'{project_key}': {exc}"
            ) from exc

        evaluations = []
        for evaluation in store.list_evaluations():
            try:
                info = evaluation.get_full_info()
                evaluations.append(
                    {
                        "evaluation_id": evaluation.evaluation_id,
                        "name": info.user_meta.get("name", ""),
                        "labels": info.user_meta.get("labels", []),
                        "created": info.creation_date,
                        "prediction_type": info.prediction_type,
                        "target_variable": info.target_variable,
                        "prediction_variable": info.prediction_variable,
                        "metrics": info.metrics,
                    }
                )
            except Exception as exc:
                evaluations.append(
                    {"evaluation_id": evaluation.evaluation_id, "error": str(exc)}
                )

        evaluations.sort(key=lambda item: item.get("created") or 0, reverse=True)
        return {
            "evaluation_store_id": evaluation_store_id,
            "name": store_settings.get("name", ""),
            "flavor": store_settings.get("mesFlavor", ""),
            "evaluations": evaluations,
        }

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="List Evaluation Stores",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_evaluation_stores(
    project_key: str,
    flavor: Literal["TABULAR", "AGENT", "LLM"],
    ctx: Context,
) -> str:
    """Find a project's evaluation stores of one flavor, with their IDs and evaluation counts."""
    project_key = require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing {flavor} evaluation stores in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        stores = project.list_evaluation_stores(flavor=flavor)
        result = []
        for store in stores:
            try:
                settings = store.get_settings().settings
                result.append(
                    {
                        "evaluation_store_id": store.id,
                        "name": settings.get("name", ""),
                        "flavor": settings.get("mesFlavor", ""),
                        "evaluation_count": len(store.list_evaluations()),
                    }
                )
            except DataikuException as exc:
                result.append({"evaluation_store_id": store.id, "error": str(exc)})
        return columnar(
            result,
            ["evaluation_store_id", "name", "flavor", "evaluation_count", "error"],
        )

    return compact_json(await run_blocking(_run))

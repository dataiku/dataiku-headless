# Copyright 2026 Dataiku
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

"""Inspection tools for Dataiku Agent Reviews."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import require_non_empty_string


@mcp.tool()
async def list_agent_reviews(project_key: str, ctx: Context) -> str:
    """List the agent reviews in the project."""
    project_key = require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing agent reviews in {project_key}...")

    def _run():
        items = get_dss_client().get_project(project_key).list_agent_reviews()
        rows = [
            {
                "id": item.id,
                "name": item.name,
                "agent_id": item.agent_id,
                "tags": item.data.get("tags", []),
            }
            for item in items
        ]
        return {"reviews": columnar(rows, ["id", "name", "agent_id", "tags"])}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_agent_review(
    project_key: str,
    review_id: str,
    ctx: Context,
) -> str:
    """Get an agent review's configuration including its traits."""
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    await ctx.info(f"Getting agent review {review_id} in {project_key}...")

    def _run():
        review = get_dss_client().get_project(project_key).get_agent_review(review_id)
        raw = review.get_raw()
        return omit_empty(
            {
                "id": raw.get("id"),
                "name": raw.get("name"),
                "agent_id": raw.get("agentSmartId"),
                "nb_executions": raw.get("nbExecutions"),
                "traits": raw.get("traits", []),
                "tags": raw.get("tags") or [],
            }
        )

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_agent_review_tests(
    project_key: str,
    review_id: str,
    ctx: Context,
) -> str:
    """List the tests in an agent review."""
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    await ctx.info(f"Listing tests for agent review {review_id} in {project_key}...")

    def _run():
        review = get_dss_client().get_project(project_key).get_agent_review(review_id)
        items = review.list_tests()
        rows = [
            {
                "id": item.id,
                "query": item.query,
                "has_reference": bool(item.reference_answer),
                "has_expectations": bool(item.expectations),
            }
            for item in items
        ]
        return {
            "tests": columnar(
                rows, ["id", "query", "has_reference", "has_expectations"]
            )
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_agent_review_runs(
    project_key: str,
    review_id: str,
    ctx: Context,
) -> str:
    """List the runs for an agent review."""
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    await ctx.info(f"Listing runs for agent review {review_id} in {project_key}...")

    def _run():
        review = get_dss_client().get_project(project_key).get_agent_review(review_id)
        items = review.list_runs(as_type="objects")
        rows = []
        for item in items:
            raw: dict = getattr(item, "data", {})
            rows.append(
                omit_empty(
                    {
                        "id": raw.get("id"),
                        "name": raw.get("name"),
                        "status": raw.get("status"),
                        "nb_executions": raw.get("nbExecutions"),
                        "created_by": raw.get("createdBy"),
                        "start_time": raw.get("startTimestamp"),
                        "end_time": raw.get("endTimestamp"),
                    }
                )
            )
        return {
            "runs": columnar(
                rows,
                [
                    "id",
                    "name",
                    "status",
                    "nb_executions",
                    "created_by",
                    "start_time",
                    "end_time",
                ],
            )
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_agent_review_run_results(
    project_key: str,
    review_id: str,
    run_id: str,
    ctx: Context,
) -> str:
    """Get the results of an agent review run."""
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    run_id = require_non_empty_string(run_id, "run_id")
    await ctx.info(f"Getting results for run {run_id} of agent review {review_id}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        review = project.get_agent_review(review_id)
        trait_names = {
            trait["id"]: trait.get("name", trait["id"])
            for trait in review.get_raw().get("traits", [])
        }
        run = review.get_run(run_id)
        result_items = run.list_results()
        results = []
        pass_count = 0
        fail_count = 0
        for item in result_items:
            status = item.status if hasattr(item, "status") else None
            if status == "PASS":
                pass_count += 1
            elif status == "FAIL":
                fail_count += 1
            trait_outcomes = {}
            statuses = (
                item.trait_status_per_trait_id
                if hasattr(item, "trait_status_per_trait_id")
                else {}
            )
            justifications = (
                item.trait_status_justification_per_trait_id
                if hasattr(item, "trait_status_justification_per_trait_id")
                else {}
            )
            for trait_id, trait_status in (statuses or {}).items():
                trait_name = trait_names.get(trait_id, trait_id)
                trait_outcomes[trait_name] = omit_empty(
                    {
                        "status": trait_status,
                        "justification": (justifications or {}).get(trait_id),
                    }
                )
            results.append(
                omit_empty(
                    {
                        "id": item.id,
                        "test_id": item.test_id,
                        "query": item.query,
                        "status": status,
                        "trait_outcomes": trait_outcomes or None,
                    }
                )
            )
        return {
            "run_id": run_id,
            "summary": {"PASS": pass_count, "FAIL": fail_count, "total": len(results)},
            "results": results,
        }

    return compact_json(await run_blocking(_run))

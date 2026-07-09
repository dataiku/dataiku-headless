"""Tools for managing Dataiku DSS Agent Reviews."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.auth import get_dss_client
from .utils.validation import require_non_empty_string



# ---------------------------------------------------------------------------
# Agent Review CRUD
# ---------------------------------------------------------------------------


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
        return omit_empty({
            "id": raw.get("id"),
            "name": raw.get("name"),
            "agent_id": raw.get("agentSmartId"),
            "nb_executions": raw.get("nbExecutions"),
            "traits": raw.get("traits", []),
            "tags": raw.get("tags") or [],
        })

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_agent_review(
    project_key: str,
    review_name: str,
    ctx: Context,
    agent_id: str = "",
    traits: list | None = None,
) -> str:
    """Create a new agent review.

    Args:
        review_name: Display name for the review
        agent_id: Bare agent ID (e.g. "jdcefvxV") — no project key prefix. Optional, can be set later.
        traits: Optional initial traits. Fields: {name, description, criteria, enabled, needsReference, needsExpectations, llmId}
    """
    project_key = require_non_empty_string(project_key, "project_key")
    review_name = require_non_empty_string(review_name, "review_name")
    await ctx.info(f"Creating agent review '{review_name}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        review = project.create_agent_review(review_name)
        raw = review.get_raw()
        needs_save = False
        if agent_id:
            raw["agentSmartId"] = agent_id
            needs_save = True
        if traits:
            raw["traits"] = traits
            needs_save = True
        if needs_save:
            review = review.save()
        return {"review_id": review.get_raw().get("id")}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def update_agent_review(
    project_key: str,
    review_id: str,
    ctx: Context,
    name: str | None = None,
    agent_id: str | None = None,
    traits: list | None = None,
) -> str:
    """Update an agent review's name, linked agent, or traits.

    Args:
        name: New display name
        agent_id: Bare agent ID (e.g. "jdcefvxV") — no project key prefix
        traits: Full replacement list. Include "id" for existing traits to preserve them; omit for new ones. Fields: {id?, name, description, criteria, enabled, needsReference, needsExpectations, llmId}
    """
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    await ctx.info(f"Updating agent review {review_id} in {project_key}...")

    def _run():
        review = get_dss_client().get_project(project_key).get_agent_review(review_id)
        raw = review.get_raw()
        updated = []
        if name is not None:
            raw["name"] = name
            updated.append("name")
        if agent_id is not None:
            raw["agentSmartId"] = agent_id
            updated.append("agent_id")
        if traits is not None:
            raw["traits"] = traits
            updated.append("traits")
        review.save()
        return {"updated_fields": updated}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def delete_agent_review(
    project_key: str,
    review_id: str,
    ctx: Context,
) -> str:
    """Delete an agent review."""
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    await ctx.info(f"Deleting agent review {review_id} in {project_key}...")

    def _run():
        get_dss_client().get_project(project_key).get_agent_review(review_id).delete()
        return {}

    return compact_json(await run_blocking(_run))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


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
        return {"tests": columnar(rows, ["id", "query", "has_reference", "has_expectations"])}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_agent_review_test(
    project_key: str,
    review_id: str,
    query: str,
    ctx: Context,
    reference_answer: str = "",
    expectations: str = "",
) -> str:
    """Create a test in an agent review.

    Args:
        query: The user query the agent will receive
        reference_answer: Expected answer — used by traits with needsReference=true
        expectations: Free-text expected behaviors — used by traits with needsExpectations=true
    """
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    query = require_non_empty_string(query, "query")
    await ctx.info(f"Creating test in agent review {review_id} in {project_key}...")

    def _run():
        review = get_dss_client().get_project(project_key).get_agent_review(review_id)
        test = review.create_test(
            query=query,
            reference_answer=reference_answer or None,
            expectations=expectations or None,
        )
        return {"test_id": test.id}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def update_agent_review_test(
    project_key: str,
    review_id: str,
    test_id: str,
    ctx: Context,
    query: str | None = None,
    reference_answer: str | None = None,
    expectations: str | None = None,
) -> str:
    """Update a test's query, reference answer, or expectations."""
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    test_id = require_non_empty_string(test_id, "test_id")
    await ctx.info(f"Updating test {test_id} in agent review {review_id}...")

    def _run():
        review = get_dss_client().get_project(project_key).get_agent_review(review_id)
        test = review.get_test(test_id)
        raw = test.get_raw()
        updated = []
        if query is not None:
            raw["query"] = query
            updated.append("query")
        if reference_answer is not None:
            raw["referenceAnswer"] = reference_answer
            updated.append("reference_answer")
        if expectations is not None:
            raw["expectations"] = expectations
            updated.append("expectations")
        test.save()
        return {"updated_fields": updated}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def delete_agent_review_test(
    project_key: str,
    review_id: str,
    test_id: str,
    ctx: Context,
) -> str:
    """Delete a test from an agent review."""
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    test_id = require_non_empty_string(test_id, "test_id")
    await ctx.info(f"Deleting test {test_id} from agent review {review_id}...")

    def _run():
        review = get_dss_client().get_project(project_key).get_agent_review(review_id)
        review.get_test(test_id).delete()
        return {}

    return compact_json(await run_blocking(_run))


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@mcp.tool()
async def perform_agent_review_run(
    project_key: str,
    review_id: str,
    ctx: Context,
    run_name: str = "",
    test_ids: list | None = None,
    wait_for_completion: bool = True,
) -> str:
    """Execute an agent review run against all tests (or a specified subset).

    Args:
        run_name: Optional display name for this run
        test_ids: Optional list of test IDs to run (defaults to all tests)
        wait_for_completion: If true, block until the run finishes; if false, return the run ID immediately
    """
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    await ctx.info(
        f"{'Running' if wait_for_completion else 'Triggering'} agent review {review_id} in {project_key}..."
    )

    def _run():
        review = get_dss_client().get_project(project_key).get_agent_review(review_id)
        result = review.perform_run(
            test_ids=test_ids or [],
            wait=wait_for_completion,
            run_name=run_name or None,
        )
        if wait_for_completion:
            raw = result.get_raw()
            return omit_empty({
                "run_id": raw.get("id"),
                "run_name": raw.get("name"),
                "status": raw.get("status"),
                "nb_executions": raw.get("nbExecutions"),
            })
        else:
            # Future .name is "agent-review-{project_key}-{review_id}-{run_id}"; strip the prefix to recover the run id.
            future_name = getattr(result, "name", "")
            prefix = f"agent-review-{project_key}-{review_id}-"
            run_id = future_name[len(prefix):] if future_name.startswith(prefix) else ""
            return omit_empty({
                "run_id": run_id,
                "status": "started",
                "hint": "Use list_agent_review_runs or get_agent_review_run_results to check progress.",
            })

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
            rows.append(omit_empty({
                "id": raw.get("id"),
                "name": raw.get("name"),
                "status": raw.get("status"),
                "nb_executions": raw.get("nbExecutions"),
                "created_by": raw.get("createdBy"),
                "start_time": raw.get("startTimestamp"),
                "end_time": raw.get("endTimestamp"),
            }))
        return {"runs": columnar(rows, ["id", "name", "status", "nb_executions", "created_by", "start_time", "end_time"])}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_agent_review_run_results(
    project_key: str,
    review_id: str,
    run_id: str,
    ctx: Context,
) -> str:
    """Get the results of an agent review run, with per-test trait outcomes and justifications."""
    project_key = require_non_empty_string(project_key, "project_key")
    review_id = require_non_empty_string(review_id, "review_id")
    run_id = require_non_empty_string(run_id, "run_id")
    await ctx.info(f"Getting results for run {run_id} of agent review {review_id}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        review = project.get_agent_review(review_id)
        trait_names = {t["id"]: t.get("name", t["id"]) for t in review.get_raw().get("traits", [])}

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
            statuses = item.trait_status_per_trait_id if hasattr(item, "trait_status_per_trait_id") else {}
            justifications = item.trait_status_justification_per_trait_id if hasattr(item, "trait_status_justification_per_trait_id") else {}
            for trait_id, trait_status in (statuses or {}).items():
                trait_name = trait_names.get(trait_id, trait_id)
                trait_outcomes[trait_name] = omit_empty({
                    "status": trait_status,
                    "justification": (justifications or {}).get(trait_id),
                })

            results.append(omit_empty({
                "id": item.id,
                "test_id": item.test_id,
                "query": item.query,
                "status": status,
                "trait_outcomes": trait_outcomes or None,
            }))

        return {
            "run_id": run_id,
            "summary": {"PASS": pass_count, "FAIL": fail_count, "total": len(results)},
            "results": results,
        }

    return compact_json(await run_blocking(_run))

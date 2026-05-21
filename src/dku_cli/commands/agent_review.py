"""dku agent-review — manage agent reviews, tests, and evaluation runs."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    resolve_agent_review,
    resolve_project,
)
from dku_cli.output import render, render_raw, resolve_output_format, success, warn

app = typer.Typer(
    help="Manage agent reviews — evaluate agent quality with traits, tests, and runs."
)


@app.command("list")
def list_reviews(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List agent reviews in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        reviews = proj.list_agent_reviews()

        data = []
        for r in reviews:
            data.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "agent_id": getattr(r, "data", {}).get("agentSmartId", ""),
                    "owner": getattr(r, "data", {}).get("owner", ""),
                }
            )

        render(
            data,
            ["id", "name", "agent_id", "owner"],
            output_format=output,
            title=f"Agent Reviews ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Review name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new agent review."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = proj.create_agent_review(name)
        success(f"Created agent review '{name}' (id={review.id})")
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show agent review settings. Accepts review ID or name."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        render_raw(review.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete an agent review. Accepts review ID or name."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="agent_review.delete",
        subject=f"agent review '{review_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete agent review '{review_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        review.delete()
        success(f"Deleted agent review '{review_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-agent")
def set_agent(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    agent: str = typer.Option(
        ..., "--agent", help="Agent ID to associate with this review"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Link an agent review to an agent."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        review.agent_id = agent
        review.save()
        success(f"Set agent '{agent}' on review '{review_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("set-llm")
def set_llm(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    llm: str = typer.Option(
        ..., "--llm", help="LLM ID for trait evaluation (e.g. 'openai:...:gpt-4o')"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the helper LLM used for trait evaluation.

    Also auto-populates per-trait llmId on any trait that lacks one — DSS 14.5.1+
    rejects runs with a NullPointerException if a trait has null llmId, even when
    the review-level helperLLMId is set.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        review.helper_llm_id = llm
        # Backfill per-trait llmId so DSS 14.5.1+ runs don't NPE on null traits.
        raw = review.get_raw()
        patched = 0
        for trait in raw.get("traits", []):
            if not trait.get("llmId"):
                trait["llmId"] = llm
                patched += 1
        review.save()
        if patched:
            success(
                f"Set helper LLM '{llm}' on review '{review_id}' (auto-populated {patched} trait(s))"
            )
        else:
            success(f"Set helper LLM '{llm}' on review '{review_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("add-trait")
def add_trait(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    name: str = typer.Option(
        ..., "--name", help="Trait name (e.g. 'Accuracy', 'Helpfulness')"
    ),
    description: str = typer.Option("", "--description", help="Trait description"),
    criteria: str = typer.Option(
        "", "--criteria", help="Evaluation criteria/prompt for the LLM judge"
    ),
    llm: str = typer.Option(
        None,
        "--llm",
        help="LLM ID for this specific trait (overrides review-level LLM)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an evaluation trait to a review.

    Traits define what the LLM judge evaluates. Each trait has a name, description,
    and criteria prompt. The criteria tells the judge how to score the agent's response.

    Examples:
      dku agent-review add-trait REV1 --name "Accuracy" --criteria "Does the answer match the reference?" -P PROJ
      dku agent-review add-trait REV1 --name "Tone" --description "Professional tone" --criteria "Is the response professional and courteous?" -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)

        trait = {
            "name": name,
            "description": description,
            "criteria": criteria,
            "enabled": True,
        }
        # Default trait llmId to the review's helper LLM so DSS 14.5.1+ doesn't
        # NPE at run time. Explicit --llm takes precedence.
        if llm:
            trait["llmId"] = llm
        elif review.helper_llm_id:
            trait["llmId"] = review.helper_llm_id

        review.add_trait(trait)
        review.save()
        success(f"Added trait '{name}' to review '{review_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("list-tests")
def list_tests(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List tests in an agent review."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        tests = review.list_tests(as_type="objects")

        data = []
        for t in tests:
            data.append(
                {
                    "id": t.id,
                    "query": (t.query or "")[:80],
                    "reference_answer": (t.reference_answer or "")[:40],
                    "expectations": (t.expectations or "")[:40],
                }
            )

        render(
            data,
            ["id", "query", "reference_answer", "expectations"],
            output_format=output,
            title=f"Tests ({review.id})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-test")
def create_test(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    query: str = typer.Option(
        ..., "--query", "-q", help="Test query to send to the agent"
    ),
    reference: str = typer.Option(
        None, "--reference", "-r", help="Reference answer for comparison"
    ),
    expectations: str = typer.Option(
        None, "--expectations", "-e", help="Expectations on the answer"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a single test case for an agent review.

    Examples:
      dku agent-review create-test REV1 --query "What is our refund policy?" --reference "30-day money back" -P PROJ
      dku agent-review create-test REV1 -q "Summarize Q4 results" -e "Should mention revenue and headcount" -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        test = review.create_test(
            query=query,
            reference_answer=reference,
            expectations=expectations,
        )
        success(f"Created test (id={test.id}) in review '{review_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("import-tests")
def import_tests(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    dataset: str = typer.Option(
        ...,
        "--dataset",
        "-d",
        help="Source dataset name (full name, e.g. 'PROJ.dataset_name')",
    ),
    query_column: str = typer.Option(
        ..., "--query-column", help="Column containing test queries"
    ),
    reference_column: str = typer.Option(
        None, "--reference-column", help="Column containing reference answers"
    ),
    expectations_column: str = typer.Option(
        None, "--expectations-column", help="Column containing expectations"
    ),
    top_n: int = typer.Option(None, "--top-n", help="Only import the first N rows"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Import tests from a dataset into an agent review.

    Bulk-creates test cases from dataset rows. Each row becomes one test case.

    Examples:
      dku agent-review import-tests REV1 --dataset test_questions --query-column question --reference-column answer -P PROJ
      dku agent-review import-tests REV1 -d eval_set --query-column q --top-n 50 -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        result = review.create_tests_from_dataset(
            full_dataset_name=dataset,
            query_column=query_column,
            reference_answer_column=reference_column,
            expectations_column=expectations_column,
            top_n=top_n,
        )
        created_ids = result.get("createdTestIds", [])
        err = result.get("error")
        if err:
            warn(f"Import completed with error: {err}")
        success(f"Imported {len(created_ids)} tests into review '{review_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("export-tests")
def export_tests(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    dataset: str = typer.Option(..., "--dataset", "-d", help="Target dataset name"),
    create_new: bool = typer.Option(
        False,
        "--create-new",
        help="Create a new dataset (otherwise overwrites existing)",
    ),
    connection: str = typer.Option(
        None, "--connection", "-c", help="Connection for new dataset"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Export tests from an agent review to a dataset."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        result = review.export_tests_to_dataset(
            full_dataset_name=dataset,
            create_new_dataset=create_new,
            target_connection=connection,
        )
        count = result.get("exportedTestCount", 0)
        success(
            f"Exported {count} tests from review '{review_id}' to dataset '{dataset}'"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("run")
def run_review(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for run to complete"
    ),
    run_name: str = typer.Option(None, "--name", help="Optional name for this run"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Execute a review run — evaluates the agent against all tests.

    Runs all tests in the review, sending each query to the agent and
    evaluating responses against configured traits. Uses --wait by default.

    Examples:
      dku agent-review run REV1 -P PROJ
      dku agent-review run REV1 --no-wait --name "nightly-eval" -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        result = review.perform_run(wait=wait, run_name=run_name)

        if wait:
            run_id = result.id if hasattr(result, "id") else "unknown"
            status = result.status if hasattr(result, "status") else "completed"
            success(f"Run complete (id={run_id}, status={status})")
        else:
            success(
                f"Run started. Check progress: dku agent-review list-runs {review_id} -P {project_key}"
            )
    except Exception as e:
        handle_api_error(e)


@app.command("list-runs")
def list_runs(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List runs of an agent review."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        runs = review.list_runs(as_type="objects")

        data = []
        for r in runs:
            data.append(
                {
                    "id": r.id,
                    "name": r.name or "",
                    "status": r.status or "",
                    "agent_id": r.agent_id or "",
                }
            )

        render(
            data,
            ["id", "name", "status", "agent_id"],
            output_format=output,
            title=f"Runs ({review.id})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("results")
def results(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    run: str = typer.Option(..., "--run", help="Run ID to get results from"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show results of a review run — per-test trait evaluations.

    Examples:
      dku agent-review results REV1 --run RUN_ID -P PROJ
      dku agent-review results REV1 --run RUN_ID -P PROJ -o json
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        run_obj = review.get_run(run)
        result_items = run_obj.list_results(as_type="objects")

        data = []
        for r in result_items:
            data.append(
                {
                    "id": r.id,
                    "test_id": r.test_id,
                    "query": (r.query or "")[:60],
                    "status": r.status or "",
                }
            )

        render(
            data,
            ["id", "test_id", "query", "status"],
            output_format=output,
            title=f"Results (run={run})",
        )
    except Exception as e:
        handle_api_error(e)

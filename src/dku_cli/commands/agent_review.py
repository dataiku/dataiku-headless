"""dku agent-review — manage agent reviews, tests, and evaluation runs."""

from __future__ import annotations

import contextlib

import typer

from dku_cli.commands.agent import _activate_version, _deep_copy_version
from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    resolve_agent,
    resolve_agent_review,
    resolve_project,
)
from dku_cli.output import (
    emit_created,
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(
    help="Manage agent reviews — evaluate agent quality with traits, tests, and runs."
)


def _ensure_review_agent_version(proj, review) -> tuple[str | None, bool]:
    """Ensure the review is pinned to a saved agent version before execution."""
    review_raw = review.get_raw() if hasattr(review, "get_raw") else {}
    agent_id = review_raw.get("agentSmartId") or getattr(review, "agent_id", None)
    if not agent_id:
        # No bound agent → perform_run builds an empty agent loc server-side and
        # dies with the opaque "Invalid loc: empty name". Fail prescriptively
        # here instead. (set-agent now verifies the binding sticks, so this is
        # the backstop for reviews created/bound before that fix.)
        exit_with_error(
            f"Agent review '{review.id}' has no agent bound — nothing to evaluate.",
            details=[
                f"Bind one: dku agent-review set-agent {review.id} --agent AGENT_ID -P {proj.project_key}",
                "The agent must have a published, active version to be reviewable.",
            ],
            status=3,
        )

    agent = resolve_agent(proj, agent_id)
    settings = agent.get_settings()
    agent_raw = settings.get_raw()
    versions = agent_raw.get("versions", [])
    version_ids = {v.get("versionId") for v in versions if v.get("versionId")}
    pinned_version = review_raw.get("agentVersion")
    if pinned_version and pinned_version in version_ids:
        return pinned_version, False

    source_vid = agent_raw.get("activeVersion")
    if source_vid is None and versions:
        source_vid = versions[0].get("versionId")
    if source_vid is None:
        exit_with_error(
            f"Agent '{agent_id}' has no version to publish for review execution.",
            details=[
                f"Create one first: dku agent create-version {agent_id} --activate -P {proj.project_key}",
            ],
        )

    _, new_vid = _deep_copy_version(settings, source_vid=source_vid)
    settings.save()
    _activate_version(proj, agent.id, new_vid)
    review_raw["agentVersion"] = new_vid
    review.save()
    return new_vid, True


@app.command("list")
def list_reviews(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List agent reviews in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        reviews = proj.list_agent_reviews()

        data = []
        for r in reviews:
            # DSSAgentReviewListItem has no get_raw(); its raw payload is the
            # documented `.data` attribute (and the item is a dict subclass).
            raw = getattr(r, "data", None) or (r if isinstance(r, dict) else {})
            data.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "agent_id": raw.get("agentSmartId", ""),
                    "owner": raw.get("owner", ""),
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
        emit_created(
            {"id": review.id, "name": name},
            message=f"Created agent review '{name}' (id={review.id})",
            next_command=f"dku agent-review get {review.id} -P {project_key}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show agent review settings. Accepts review ID or name."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        saved = review.save()
        # DSS silently drops agentSmartId when the agent can't be bound for
        # review — most commonly because it has no published/active version, so
        # it isn't a reviewable saved model. Without this check the CLI reports
        # a false success and the missing binding only surfaces later as the
        # opaque "Invalid loc: empty name" at `agent-review run`.
        bound = saved.get_raw().get("agentSmartId") if saved else None
        if not bound:
            exit_with_error(
                f"DSS did not bind agent '{agent}' to review '{review_id}'.",
                details=[
                    "The agent must have a published, active version to be reviewable.",
                    f"Publish one: dku agent create-version {agent} --activate -P {project_key}",
                    f"Confirm it runs: dku agent test {agent} -P {project_key}",
                    f"Then retry: dku agent-review set-agent {review_id} --agent {agent} -P {project_key}",
                ],
                status=3,
            )
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
    needs_reference: bool = typer.Option(
        True,
        "--needs-reference/--no-needs-reference",
        help=(
            "Give the judge the test's reference answer (default ON). "
            "Keep ON for accuracy/correctness traits; pass --no-needs-reference "
            "for tone/format/safety traits so they still score tests with no "
            "reference. A needs-reference trait is ONLY scored on tests that have "
            "a --reference."
        ),
    ),
    needs_expectations: bool = typer.Option(
        False,
        "--needs-expectations/--no-needs-expectations",
        help=(
            "Give the judge the test's expectations (default OFF). Pass "
            "--needs-expectations for traits scored against per-test --expectations."
        ),
    ),
    llm: str = typer.Option(
        None,
        "--llm",
        help="LLM ID for this specific trait (overrides review-level LLM)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an evaluation trait to a review.

    A trait pairs a criteria prompt with two wiring flags that decide which
    per-test fields the LLM judge actually sees:

      --needs-reference     judge gets the test's reference answer  (default ON)
      --needs-expectations  judge gets the test's expectations      (default OFF)

    These must match how you built your tests (create-test --reference /
    --expectations). DSS defaults EVERY trait to needs-reference=ON,
    needs-expectations=OFF, so without these flags a "Tone" trait wrongly requires
    a reference and an expectations-based trait never sees the expectations.

    Examples:
      # Correctness vs reference (defaults are already correct)
      dku agent-review add-trait REV1 --name "Accuracy" --criteria "Does the answer match the reference answer?" -P PROJ
      # Tone trait — no reference needed, scores every test
      dku agent-review add-trait REV1 --name "Tone" --criteria "Is the response professional and courteous?" --no-needs-reference -P PROJ
      # Trait scored against per-test expectations
      dku agent-review add-trait REV1 --name "Coverage" --criteria "Does the answer satisfy the stated expectations?" --needs-expectations --no-needs-reference -P PROJ
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
            "needsReference": needs_reference,
            "needsExpectations": needs_expectations,
        }
        # Default trait llmId to the review's helper LLM so DSS 14.5.1+ doesn't
        # NPE at run time. Explicit --llm takes precedence.
        if llm:
            trait["llmId"] = llm
        elif review.helper_llm_id:
            trait["llmId"] = review.helper_llm_id

        review.add_trait(trait)
        review.save()

        wired = [
            field
            for field, on in (
                ("reference", needs_reference),
                ("expectations", needs_expectations),
            )
            if on
        ]
        sees = ", ".join(wired) if wired else "neither reference nor expectations"
        success(f"Added trait '{name}' to review '{review_id}' (judge sees: {sees})")

        # Prescriptive nudge: criteria text names a field the trait isn't wired to,
        # so the judge would never receive it. Non-blocking — agents can ignore.
        lc = criteria.lower()
        if "expectation" in lc and not needs_expectations:
            warn(
                "Criteria mentions expectations but --needs-expectations is off — the "
                "judge will NOT see the test's expectations. Re-run with --needs-expectations."
            )
        if "reference" in lc and not needs_reference:
            warn(
                "Criteria mentions the reference answer but --no-needs-reference is set "
                "— the judge will NOT see the test's reference answer."
            )
    except Exception as e:
        handle_api_error(e)


@app.command("list-tests")
def list_tests(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List tests in an agent review."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        hint(f"dku agent-review run {review_id} -P {project_key}")
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
        hint(f"dku agent-review run {review_id} -P {project_key}")
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
        published_version, was_published = _ensure_review_agent_version(proj, review)
        if was_published:
            info(f"Published agent version '{published_version}' for review execution.")
        result = review.perform_run(wait=wait, run_name=run_name)

        if wait:
            run_id = result.id if hasattr(result, "id") else "unknown"
            status = result.status if hasattr(result, "status") else "completed"
            success(f"Run complete (id={run_id}, status={status})")
            hint(f"dku agent-review results {review_id} -P {project_key}")
        else:
            success("Run started.")
            hint(f"dku agent-review list-runs {review_id} -P {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("list-runs")
def list_runs(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List runs of an agent review."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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


def _trait_id_to_name(review) -> dict[str, str]:
    """Build a trait-id → trait-name map from a review's raw definition.

    Per-result aiStatusPerTraitId keys are trait IDs. The CLI surfaces names
    for human/agent readability.
    """
    raw = review.get_raw() if hasattr(review, "get_raw") else {}
    out: dict[str, str] = {}
    for t in raw.get("traits", []) or []:
        if isinstance(t, dict):
            tid = t.get("id") or t.get("traitId") or ""
            tname = t.get("name") or tid or ""
            if tid:
                out[tid] = tname
    return out


def _result_per_trait_status(result_obj) -> dict[str, str]:
    """Extract trait_id → status from one DSSAgentReviewRunResult.

    ``aiStatusPerTraitId`` lives on the raw dict, not the typed object. Each
    value is either a string ("PASSED"/"FAILED"/...) or a dict with a
    ``status`` key (DSS 14.5+ added per-trait justifications).
    """
    raw = result_obj.get_raw() if hasattr(result_obj, "get_raw") else {}
    by_trait = raw.get("aiStatusPerTraitId", {}) or {}
    out: dict[str, str] = {}
    for tid, val in by_trait.items():
        if isinstance(val, dict):
            out[tid] = val.get("status", "OTHER")
        else:
            out[tid] = str(val) if val is not None else "OTHER"
    return out


def _result_per_trait_justifications(result_obj) -> dict[str, str]:
    """Extract trait_id → justification from one DSSAgentReviewRunResult.

    DSS 14.5+ stores justifications under
    ``traitStatusJustificationPerTraitId`` (top-level on the raw result, not
    nested under aiStatusPerTraitId — verified DSS 14.5.0-beta3). Older / dict-
    shaped status entries with `justification` keys are also picked up as a
    fallback so this works across DSS versions.
    """
    raw = result_obj.get_raw() if hasattr(result_obj, "get_raw") else {}
    out: dict[str, str] = {}
    # DSS 14.5+ canonical location.
    sidecar = raw.get("traitStatusJustificationPerTraitId", {}) or {}
    for tid, val in sidecar.items():
        if isinstance(val, str) and val:
            out[tid] = val
        elif isinstance(val, dict):
            j = val.get("justification") or val.get("reason") or ""
            if j:
                out[tid] = j
    # Fallback: older shape where the dict was inside aiStatusPerTraitId.
    by_trait = raw.get("aiStatusPerTraitId", {}) or {}
    for tid, val in by_trait.items():
        if isinstance(val, dict):
            j = val.get("justification") or val.get("reason") or ""
            if j and tid not in out:
                out[tid] = j
    return out


def _result_per_trait_final_status(result_obj) -> dict[str, str]:
    """Extract trait_id → FINAL status from one result.

    ``traitStatusPerTraitId`` is the authoritative status after human trait
    overrides are applied; ``aiStatusPerTraitId`` keeps the original LLM-judge
    verdict. They differ exactly where a human overrode a trait (DSS 14.6).
    """
    raw = result_obj.get_raw() if hasattr(result_obj, "get_raw") else {}
    by_trait = raw.get("traitStatusPerTraitId", {}) or {}
    out: dict[str, str] = {}
    for tid, val in by_trait.items():
        if isinstance(val, dict):
            out[tid] = val.get("status", "OTHER")
        else:
            out[tid] = str(val) if val is not None else "OTHER"
    return out


def _verdict_label(like) -> str:
    """Map a human 'like' boolean to a PASS/FAIL/— label."""
    if like is True:
        return "PASS"
    if like is False:
        return "FAIL"
    return "—"


def _get_result(client, project_key: str, result_id: str):
    """Fetch a single agent-review result by ID.

    Results are addressable by ID within a project (the GET endpoint is
    ``/agent-reviews/results/{id}`` — no run ID needed), so a bare run handle is
    used purely as the SDK accessor. The returned result self-describes its
    review and run, which the human-verification writes rely on.
    """
    from dataikuapi.dss.agent_review import DSSAgentReviewRun

    return DSSAgentReviewRun(client, project_key, {}).get_result(result_id)


@app.command("results")
def results(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    run: str = typer.Option(..., "--run", help="Run ID to get results from"),
    by_trait: bool = typer.Option(
        False,
        "--by-trait",
        help=(
            "Pivot results to a trait×test grid with PASS/FAIL/OTHER cells. "
            "Reads per-trait status from each result's aiStatusPerTraitId raw field."
        ),
    ),
    show_justifications: bool = typer.Option(
        False,
        "--show-justifications",
        help=(
            "Include per-trait LLM-judge justifications (DSS 14.5+). Implies "
            "--by-trait. Best with --format json — table mode truncates."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show results of a review run — per-test trait evaluations.

    By default, shows one row per test: id, test_id, query, overall status.
    Use --by-trait to pivot to a trait×test grid (PASS/FAIL/OTHER cells per trait).
    Use --show-justifications to add LLM-judge reasoning (DSS 14.5+, JSON-friendly).

    Examples:
      dku agent-review results REV1 --run RUN_ID -P PROJ
      dku agent-review results REV1 --run RUN_ID --by-trait -P PROJ
      dku agent-review results REV1 --run RUN_ID --show-justifications -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    # --show-justifications implies --by-trait (pivot is the only structure
    # that has a meaningful place to surface them).
    if show_justifications:
        by_trait = True
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        run_obj = review.get_run(run)
        result_items = run_obj.list_results(as_type="objects")

        if not by_trait:
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
            return

        # --by-trait: pivot trait×test. Columns: id, test_id, query, status,
        # then one column per trait (display name). JSON mode preserves
        # additional metadata (justifications).
        trait_names = _trait_id_to_name(review)
        # Stable column order: traits in the order they appear in the review.
        ordered_trait_ids = list(trait_names.keys())
        # Fallback: any trait IDs found in results but missing from the review
        # definition (defensive — should not happen for healthy reviews).
        seen_ids: set[str] = set()
        for r in result_items:
            seen_ids.update(_result_per_trait_status(r).keys())
        for tid in seen_ids:
            if tid not in trait_names:
                ordered_trait_ids.append(tid)
                trait_names[tid] = tid

        data: list[dict] = []
        for r in result_items:
            statuses = _result_per_trait_status(r)
            row: dict = {
                "id": r.id,
                "test_id": r.test_id,
                "query": (r.query or "")[:60],
                "status": r.status or "",
            }
            for tid in ordered_trait_ids:
                row[trait_names[tid]] = statuses.get(tid, "OTHER")
            if show_justifications:
                row["justifications"] = _result_per_trait_justifications(r)
            data.append(row)

        base_cols = ["id", "test_id", "query", "status"]
        trait_cols = [trait_names[tid] for tid in ordered_trait_ids]
        columns = base_cols + trait_cols
        if show_justifications:
            columns = [*columns, "justifications"]

        render(
            data,
            columns,
            output_format=output,
            title=f"Results by trait (run={run})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("compare")
def compare_runs(
    ctx: typer.Context,
    review_id: str = typer.Argument(help="Review ID or name"),
    runs: str = typer.Option(
        ...,
        "--runs",
        help="Comma-separated run IDs to compare (e.g. RUN_A,RUN_B,RUN_C)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Compare trait pass/fail across multiple runs of the same review.

    Builds a trait×run matrix of pass rates. Each cell is "PASSED/TOTAL (PCT%)"
    in table mode or {passed, total, pct} in JSON mode.

    Use this to drive the agent iteration loop: baseline → prompt iter →
    architectural fix → re-eval, watching how each trait's pass rate moves.

    Examples:
      dku agent-review compare REV1 --runs RUN_A,RUN_B,RUN_C -P PROJ
      dku agent-review compare REV1 --runs RUN_A,RUN_B -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    run_ids = [r.strip() for r in runs.split(",") if r.strip()]
    if len(run_ids) < 2:
        from dku_cli.errors import exit_with_error

        exit_with_error(
            "Compare needs at least two runs.",
            details=[
                "Pass comma-separated run IDs, e.g.:",
                f"  dku agent-review compare {review_id} --runs RUN_A,RUN_B -P {project_key}",
                f"List runs first: dku agent-review list-runs {review_id} -P {project_key}",
            ],
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        review = resolve_agent_review(proj, review_id)
        trait_names = _trait_id_to_name(review)

        # For each run, aggregate per-trait PASSED/TOTAL.
        per_run_per_trait: dict[str, dict[str, dict]] = {}
        # also track any unknown trait IDs surfaced by results
        unknown_trait_ids: set[str] = set()
        for rid in run_ids:
            try:
                run_obj = review.get_run(rid)
            except Exception as exc:
                from dku_cli.errors import exit_with_error

                exit_with_error(
                    f"Run '{rid}' not found on review '{review_id}'.",
                    details=[
                        f"List runs: dku agent-review list-runs {review_id} -P {project_key}",
                        f"Underlying error: {exc}",
                    ],
                )
            counts: dict[str, dict] = {}
            for r in run_obj.list_results(as_type="objects"):
                statuses = _result_per_trait_status(r)
                for tid, st in statuses.items():
                    if tid not in trait_names:
                        unknown_trait_ids.add(tid)
                    bucket = counts.setdefault(tid, {"passed": 0, "total": 0})
                    # DSS surfaces three states per trait: PASS, FAIL, SKIP
                    # ("SKIPPED" in some older shapes). SKIP runs shouldn't
                    # count toward the denominator — they were skipped, not
                    # judged. Anything else that isn't a clear PASS counts
                    # as not-passed but DOES increment total.
                    st_norm = str(st).upper().strip()
                    if st_norm in ("SKIP", "SKIPPED"):
                        continue
                    bucket["total"] += 1
                    if st_norm in ("PASS", "PASSED"):
                        bucket["passed"] += 1
            per_run_per_trait[rid] = counts

        # Build ordered trait list (review-defined first, then any unknowns).
        ordered_tids = list(trait_names.keys())
        for tid in sorted(unknown_trait_ids):
            ordered_tids.append(tid)
            trait_names[tid] = tid

        if output == "json":
            payload = {
                "review_id": review.id,
                "runs": run_ids,
                "traits": [
                    {
                        "trait_id": tid,
                        "trait_name": trait_names[tid],
                        "per_run": {
                            rid: {
                                "passed": per_run_per_trait[rid]
                                .get(tid, {})
                                .get("passed", 0),
                                "total": per_run_per_trait[rid]
                                .get(tid, {})
                                .get("total", 0),
                                "pct": (
                                    100.0
                                    * per_run_per_trait[rid]
                                    .get(tid, {})
                                    .get("passed", 0)
                                    / per_run_per_trait[rid]
                                    .get(tid, {})
                                    .get("total", 0)
                                )
                                if per_run_per_trait[rid].get(tid, {}).get("total", 0)
                                else None,
                            }
                            for rid in run_ids
                        },
                    }
                    for tid in ordered_tids
                ],
            }
            render_raw(payload, output_format="json")
            return

        # Table mode: trait rows, run columns.
        data: list[dict] = []
        for tid in ordered_tids:
            row = {"trait": trait_names[tid]}
            for rid in run_ids:
                bucket = per_run_per_trait[rid].get(tid, {"passed": 0, "total": 0})
                if bucket["total"]:
                    pct = 100.0 * bucket["passed"] / bucket["total"]
                    row[rid] = f"{bucket['passed']}/{bucket['total']} ({pct:.0f}%)"
                else:
                    row[rid] = "—"
            data.append(row)

        render(
            data,
            ["trait", *run_ids],
            output_format=output,
            title=f"Trait pass-rate comparison ({review.id})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("get-result")
def get_result(
    ctx: typer.Context,
    result_id: str = typer.Argument(help="Result ID (from `agent-review results`)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show one result's detail with its human-verification state.

    Surfaces, per trait, the AI judge's verdict vs the FINAL verdict (they differ
    where a human overrode the trait), the LLM-judge justification, any human
    reviews (SME pass/fail + comment), and any trait overrides. This is the read
    side of DSS 14.6 human verification — pair it with `verify` and `override-trait`.

    Examples:
      dku agent-review get-result RESULT_ID -P PROJ
      dku agent-review get-result RESULT_ID -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        result = _get_result(client, project_key, result_id)

        # Best-effort trait-id → name map via the parent review.
        names: dict[str, str] = {}
        with contextlib.suppress(Exception):
            names = _trait_id_to_name(proj.get_agent_review(result.agent_review_id))

        ai = _result_per_trait_status(result)
        final = _result_per_trait_final_status(result)
        justif = _result_per_trait_justifications(result)
        traits = [
            {
                "trait_id": tid,
                "trait": names.get(tid, tid),
                "ai_status": ai.get(tid, "—"),
                "final_status": final.get(tid, ai.get(tid, "—")),
                "overridden": tid in final and final.get(tid) != ai.get(tid),
                "justification": justif.get(tid, ""),
            }
            for tid in sorted(set(ai) | set(final), key=lambda t: names.get(t, t))
        ]

        human_reviews = [
            {
                "verdict": _verdict_label(h.like),
                "comment": h.comment or "",
                "by": h.created_by or "",
            }
            for h in result.human_reviews
        ]
        overrides = [
            {
                "trait": names.get(tid, tid),
                "trait_id": tid,
                "verdict": _verdict_label(ov.like),
                "by": ov.created_by or "",
            }
            for tid, ovs in result.trait_overrides.items()
            for ov in ovs
        ]

        execs = result.execution_results
        answer = (execs[0].answer or "") if execs else ""

        if output == "json":
            render_raw(
                {
                    "id": result.id,
                    "test_id": result.test_id,
                    "run_id": result.run_id,
                    "query": result.query,
                    "status": result.status,
                    "answer": answer,
                    "traits": traits,
                    "human_reviews": human_reviews,
                    "trait_overrides": overrides,
                },
                output_format=output,
            )
            return

        info(f"Result {result.id}  status={result.status}  test={result.test_id}")
        if result.query:
            info(f"Query:  {result.query}")
        if answer:
            info(f"Answer: {answer[:400]}")
        table_traits = [
            {**t, "justification": (t["justification"] or "")[:80]} for t in traits
        ]
        render(
            table_traits,
            ["trait", "ai_status", "final_status", "overridden", "justification"],
            output_format=output,
            title="Traits (AI vs final)",
        )
        if human_reviews:
            render(
                human_reviews,
                ["verdict", "comment", "by"],
                output_format=output,
                title="Human reviews",
            )
        if overrides:
            render(
                overrides,
                ["trait", "verdict", "by"],
                output_format=output,
                title="Trait overrides",
            )
        if not human_reviews and not overrides:
            info(
                "No human verification yet — add one with `verify` or `override-trait`."
            )
    except Exception as e:
        handle_api_error(e)


@app.command("verify")
def verify(
    ctx: typer.Context,
    result_id: str = typer.Argument(help="Result ID (from `agent-review results`)"),
    verdict: bool = typer.Option(
        None,
        "--pass/--fail",
        help="Record a human PASS or FAIL verdict on this result.",
    ),
    comment: str = typer.Option(
        None, "--comment", "-c", help="Reviewer comment (SME notes)."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Record a human (SME) review on a result — DSS 14.6 human verification.

    Stores an overall pass/fail verdict plus an optional comment, capturing a
    human's judgement of the agent's answer alongside the AI judge. To correct a
    single trait's AI verdict instead, use `override-trait`.

    Examples:
      dku agent-review verify RESULT_ID --pass -c "SME: answer is correct" -P PROJ
      dku agent-review verify RESULT_ID --fail -c "Missed the refund window" -P PROJ
    """
    if verdict is None and not comment:
        exit_with_error(
            "Nothing to record for this human review.",
            details=[
                "Pass --pass or --fail (the human verdict), and/or --comment TEXT.",
                'Example: dku agent-review verify RESULT_ID --pass -c "looks good" -P PROJ',
            ],
        )
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        result = _get_result(client, project_key, result_id)
        result.create_human_review(comment=comment, like=verdict)
        success(
            f"Recorded human review on result '{result_id}' "
            f"(verdict={_verdict_label(verdict)})"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("override-trait")
def override_trait(
    ctx: typer.Context,
    result_id: str = typer.Argument(help="Result ID (from `agent-review results`)"),
    trait: str = typer.Option(
        ...,
        "--trait",
        help="Trait ID to override (see `get-result` or `get REVIEW`).",
    ),
    verdict: bool = typer.Option(
        ...,
        "--pass/--fail",
        help="Human PASS or FAIL for this trait — overrides the AI verdict.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Override one trait's AI verdict on a result with a human PASS/FAIL.

    This sets the trait's FINAL status; the AI verdict is preserved separately so
    you can measure AI-vs-human agreement. The trait ID must come from the result's
    review — list them with `get-result RESULT_ID` or `get REVIEW_ID`.

    Examples:
      dku agent-review override-trait RESULT_ID --trait TRAIT_ID --fail -P PROJ
      dku agent-review override-trait RESULT_ID --trait TRAIT_ID --pass -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        result = _get_result(client, project_key, result_id)
        result.create_trait_override(trait, like=verdict)
        success(
            f"Overrode trait '{trait}' on result '{result_id}' → "
            f"{_verdict_label(verdict)} (final status now reflects the human "
            f"verdict; AI verdict preserved)"
        )
    except Exception as e:
        handle_api_error(e)

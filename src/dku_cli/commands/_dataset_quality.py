"""Dataset metrics and data-quality subcommands."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_not_found_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import (
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

# ---------------------------------------------------------------------------
# dku dataset metrics — list configured probes, compute, fetch values, history.
# ---------------------------------------------------------------------------

metrics_app = typer.Typer(
    help=(
        "Inspect and compute dataset metrics (row count, size, custom SQL probes). "
        "DSS does NOT auto-recompute metrics on build. Run `dku dataset metrics run` "
        "after a recipe rebuild, otherwise downstream checks see stale numbers."
    )
)


@metrics_app.command("list")
def metrics_list(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "",
        "--partition",
        help="Partition identifier. 'ALL' for the whole dataset; default reads the non-partitioned partition.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List configured probes and their last computed values.

    Reads the probe list from `dataset.metrics.probes` (the
    `dataset get-definition` view) and joins it with the cached last
    metric values. A row marked '(not computed)' means the probe is
    configured but hasn't run since the last build — fix with
    `dku dataset metrics run`.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        defn = ds.get_definition()
        probes = defn.get("metrics", {}).get("probes", [])

        cached = None
        try:
            cached = ds.get_last_metric_values(partition=partition)
        except Exception:
            cached = None

        rows = []
        seen_ids: set[str] = set()
        if cached is not None:
            for m in cached.get_raw().get("metrics", []):
                meta = m.get("metric", {})
                metric_id = meta.get("id", "")
                seen_ids.add(metric_id)
                last_values = m.get("lastValues") or []
                if last_values:
                    target = last_values[0]
                    for v in last_values:
                        if v.get("partition") in ("NP", "ALL"):
                            target = v
                            break
                    value = target.get("value", "")
                    computed_at = target.get("computed", 0)
                else:
                    value = "(not computed)"
                    computed_at = 0
                rows.append(
                    {
                        "metric_id": metric_id,
                        "type": meta.get("metricType", ""),
                        "value": value,
                        "computed_at": computed_at,
                    }
                )
        for probe in probes:
            ptype = probe.get("type", "")
            if not probe.get("enabled", True):
                continue
            if ptype in ("basic", "records"):
                continue
            probe_id = probe.get("meta", {}).get("name", ptype)
            if probe_id in seen_ids:
                continue
            rows.append(
                {
                    "metric_id": probe_id,
                    "type": ptype,
                    "value": "(not computed)",
                    "computed_at": 0,
                }
            )

        render(
            rows,
            ["metric_id", "type", "value", "computed_at"],
            output_format=output,
            title=f"Metrics: {dataset_name}",
            headers={
                "metric_id": "METRIC ID",
                "type": "TYPE",
                "value": "VALUE",
                "computed_at": "COMPUTED AT",
            },
        )
        if not rows:
            info("No metrics configured. Add probes via the dataset's Metrics tab.")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@metrics_app.command("get")
def metrics_get(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    metric_id: str = typer.Argument(
        help="Metric ID (e.g. records:COUNT_RECORDS, basic:SIZE)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "",
        "--partition",
        help="Partition identifier. 'ALL' for the whole dataset.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the cached value of a single metric.

    Use `dku dataset metrics list` first to find the metric ID. Returns
    `(not computed)` if the probe is configured but hasn't run since the
    last build — re-run with `dku dataset metrics run`.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json", "table"), default="table")
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        cached = ds.get_last_metric_values(partition=partition)
        try:
            data = cached.get_metric_by_id(metric_id)
        except Exception:
            exit_with_error(
                f"Metric '{metric_id}' is not computed for dataset '{dataset_name}'.",
                code="metric_not_found",
                details=[
                    f"List metrics: dku dataset metrics list {dataset_name} -P {project_key}",
                    f"Compute metrics first: dku dataset metrics run {dataset_name} -P {project_key}",
                ],
            )
        if output == "json":
            render_raw(data, output_format="json")
        else:
            last_values = data.get("lastValues") or []
            if not last_values:
                info("(no values computed)")
                return
            rows = []
            for v in last_values:
                rows.append(
                    {
                        "partition": v.get("partition", ""),
                        "value": v.get("value", ""),
                        "data_type": v.get("dataType", ""),
                        "computed_at": v.get("computed", 0),
                    }
                )
            render(
                rows,
                ["partition", "value", "data_type", "computed_at"],
                output_format=output,
                title=f"Metric: {metric_id}",
                headers={
                    "partition": "PARTITION",
                    "value": "VALUE",
                    "data_type": "TYPE",
                    "computed_at": "COMPUTED AT",
                },
            )
    except typer.Exit:
        raise
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@metrics_app.command("run")
def metrics_run(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "",
        "--partition",
        help="Partition identifier. 'ALL' to compute on the whole dataset.",
    ),
    metric_ids: list[str] = typer.Option(
        [],
        "--metric-id",
        help="Restrict computation to these metric IDs (repeatable). Default: every configured probe.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Recompute metrics on the dataset.

    DSS does NOT auto-refresh metric values on rebuild — call this after
    every build that should produce fresh row-count / size numbers.

    Example:
        dku dataset metrics run my_data -P PROJ
        dku dataset metrics run my_data --metric-id records:COUNT_RECORDS -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ids = list(metric_ids) if metric_ids else None
        report = ds.compute_metrics(partition=partition, metric_ids=ids)
        if output == "json":
            render_raw(report, output_format="json")
            return
        success(f"Computed metrics on dataset '{dataset_name}'")
        # compute_metrics() returns {hasResult, aborted, ..., result: {computed,
        # skipped, ...}}. Older shapes flatten to the top level, so check both.
        body = (
            report.get("result") if isinstance(report.get("result"), dict) else report
        )
        computed = body.get("computed") or []
        skipped = body.get("skipped") or []
        errors = body.get("errors") or report.get("errors") or []
        info(
            f"Probes computed: {len(computed)}, skipped: {len(skipped)}, errors: {len(errors)}"
        )
        for err in errors[:5]:
            warn(f"  {err.get('message', err) if isinstance(err, dict) else err}")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@metrics_app.command("history")
def metrics_history(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    metric_id: str = typer.Argument(help="Metric ID (e.g. records:COUNT_RECORDS)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "",
        "--partition",
        help="Partition identifier. 'ALL' for the whole dataset.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the time-series history of a metric value.

    Useful for spotting drift — e.g. tracking `records:COUNT_RECORDS` over
    several builds to confirm a join hasn't started silently dropping rows.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        history = ds.get_metric_history(metric_id, partition=partition)
        render_raw(history, output_format=output)
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


# ---------------------------------------------------------------------------
# dku dataset checks — modern data-quality rules (DSSDataQualityRuleSet).
# ---------------------------------------------------------------------------

checks_app = typer.Typer(
    help=(
        "Inspect and compute data-quality rules. Modern API "
        "(DSSDataQualityRuleSet) — `compute_rules`, `list_rules`, "
        "`get_status`, `get_last_rules_results`. The legacy `runChecks` "
        "endpoint exposed pre-DSS-12 is intentionally NOT wired up here."
    )
)


@checks_app.command("list")
def checks_list(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "NP",
        "--partition",
        help="Partition identifier. Default 'NP' (non-partitioned). 'ALL' for full dataset.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List data-quality rules with their last results.

    Pulls the rule definitions then joins the last run's outcome
    (OK / WARNING / ERROR / EMPTY). Rules with no recent run show
    outcome='(no result)'.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ruleset = ds.get_data_quality_rules()
        rules = ruleset.list_rules(as_type="dict")
        results_by_id: dict[str, object] = {}
        try:
            last_results = ruleset.get_last_rules_results(partition=partition)
            results_by_id = {r.id: r for r in last_results}
        except Exception:
            pass

        rows = []
        for r in rules:
            rid = r.get("id", "")
            outcome = "(no result)"
            message = ""
            if rid in results_by_id:
                outcome = results_by_id[rid].outcome or "(no result)"
                message = results_by_id[rid].message or ""
            rows.append(
                {
                    "id": rid,
                    "name": r.get("displayName", ""),
                    "metric": r.get("metricId", "") or r.get("type", ""),
                    "outcome": outcome,
                    "message": (message[:60] + "…") if len(message) > 60 else message,
                }
            )

        render(
            rows,
            ["id", "name", "metric", "outcome", "message"],
            output_format=output,
            title=f"Data Quality Rules: {dataset_name}",
            headers={
                "id": "ID",
                "name": "NAME",
                "metric": "METRIC",
                "outcome": "OUTCOME",
                "message": "MESSAGE",
            },
        )
        if not rows:
            info("No data-quality rules configured.")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@checks_app.command("status")
def checks_status(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the overall data-quality status of the dataset.

    For partitioned datasets this is the worst result of the last
    computed partitions.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json", "table"), default="table")
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ruleset = ds.get_data_quality_rules()
        try:
            status = ruleset.get_status()
        except Exception as inner:
            # DSS's no-result response is unstructured: sometimes a 404 with the
            # 'There is no result for this dataset' body, sometimes an empty body
            # that surfaces as a JSON-decode error inside dataikuapi. Either way,
            # if the dataset itself exists, treat it as 'no result yet'.
            try:
                ds.get_definition()
                dataset_exists = True
            except Exception:
                dataset_exists = False
            if not dataset_exists:
                if is_not_found_error(inner):
                    exit_with_error(
                        f"Dataset '{dataset_name}' not found in {project_key}.",
                        code="not_found",
                        status=3,
                        details=[f"List datasets: dku dataset list -P {project_key}"],
                    )
                raise
            if output == "json":
                render_raw({"status": "NO_RESULT"}, output_format="json")
                return
            info(
                "No data-quality results yet. Run rules first: "
                f"dku dataset checks run {dataset_name} -P {project_key}"
            )
            return
        if output == "json":
            render_raw(status, output_format="json")
            return
        rows = []
        if isinstance(status, dict):
            for k, v in status.items():
                rows.append({"field": k, "value": str(v)})
        else:
            rows.append({"field": "status", "value": str(status)})
        render(
            rows,
            ["field", "value"],
            output_format=output,
            title=f"Data Quality Status: {dataset_name}",
        )
    except typer.Exit:
        raise
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


@checks_app.command("run")
def checks_run(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "NP",
        "--partition",
        help="Partition identifier. Default 'NP' (non-partitioned). 'ALL' for full dataset.",
    ),
    wait: bool = typer.Option(
        False, "--wait", "-w", help="Wait for the rule computation to finish."
    ),
) -> None:
    """Compute every enabled data-quality rule on the dataset.

    Returns a DSSFuture immediately; pass --wait to block until done. After
    completion, fetch results via `dku dataset checks list <DS>`.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        ds = client.get_project(project_key).get_dataset(dataset_name)
        ruleset = ds.get_data_quality_rules()
        future = ruleset.compute_rules(partition=partition)
        success(f"Started data-quality computation on '{dataset_name}'")
        if hasattr(future, "job_id") and future.job_id:
            info(f"Future ID: {future.job_id}")
        if wait:
            info("Waiting for computation to finish...")
            future.wait_for_result()
            success("Computation finished")
            info(
                f"Inspect results: dku dataset checks list {dataset_name} -P {project_key}"
            )
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' not found in {project_key}.",
                code="not_found",
                status=3,
                details=[f"List datasets: dku dataset list -P {project_key}"],
            )
        handle_api_error(e)


def register_dataset_quality_commands(app: typer.Typer) -> None:
    """Attach dataset metrics and data-quality subcommands."""
    app.add_typer(metrics_app, name="metrics")
    app.add_typer(checks_app, name="checks")

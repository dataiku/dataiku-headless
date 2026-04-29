"""dku dq — list, create, compute, status, results, delete, project-status."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(
    help="Manage data quality rules on DSS datasets (requires DSS 14.5+)."
)

# Rule types that have known compute bugs in DSS 14.5 beta
_BUGGY_TYPES = frozenset({"ColumnNotEmptyRule", "ColumnEmptyRule"})


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_ruleset(ctx: typer.Context, dataset_name: str, project: str | None):
    """Return (client, project_key, ruleset) tuple."""
    project_key = resolve_project(project)
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    ds = proj.get_dataset(dataset_name)
    return client, project_key, ds.get_data_quality_rules()


# Discovered DSS rule type names (DSS 14.5.0-beta2).
# Column rules use "columns" (array), NOT "column" (singular).
#
# Dataset-level: RecordCountInRangeRule, ColumnCountInRangeRule,
#   FileSizeInRangeRule, DatasetSchemaEqualsRule, DatasetSchemaContainsRule
# Column-level: ColumnNotEmptyRule, ColumnEmptyRule,
#   ColumnMinInRangeRule, ColumnMaxInRangeRule, ColumnAvgInRangeRule,
#   ColumnSumInRangeRule, ColumnMedianInRangeRule, ColumnStdDevInRangeRule
#
# "value-in-range" creates TWO rules (min + max) to ensure all values in bounds.
TYPE_MAP = {
    "record-count": "RecordCountInRangeRule",
    "not-empty": "ColumnNotEmptyRule",
    "column-min": "ColumnMinInRangeRule",
    "column-max": "ColumnMaxInRangeRule",
    "column-avg": "ColumnAvgInRangeRule",
    "column-sum": "ColumnSumInRangeRule",
}


def _build_rule_config(
    rule_type: str,
    column: str | None,
    name: str | None,
    min_val: float | None,
    max_val: float | None,
) -> dict | list[dict]:
    """Build rule config(s) from convenience flags.

    Returns a single dict for most types, or a list of two dicts for
    value-in-range (ColumnMinInRangeRule + ColumnMaxInRangeRule).
    """
    # Special: value-in-range creates a pair of rules
    if rule_type == "value-in-range":
        if not column:
            exit_with_error(
                "--column is required for rule type 'value-in-range'.",
                details=[
                    "Example: dku dq create DS --type value-in-range --column Latitude --min -90 --max 90"
                ],
            )
        configs = []
        base_name = name or f"{column} range"
        if min_val is not None:
            configs.append(
                {
                    "type": "ColumnMinInRangeRule",
                    "columns": [column],
                    "displayName": f"{base_name} (min >= {min_val})",
                    "softMinimum": min_val,
                    "softMinimumEnabled": True,
                }
            )
        if max_val is not None:
            configs.append(
                {
                    "type": "ColumnMaxInRangeRule",
                    "columns": [column],
                    "displayName": f"{base_name} (max <= {max_val})",
                    "softMaximum": max_val,
                    "softMaximumEnabled": True,
                }
            )
        if not configs:
            exit_with_error(
                "At least --min or --max is required for 'value-in-range'.",
                details=[
                    "Example: dku dq create DS --type value-in-range --column Latitude --min -90 --max 90"
                ],
            )
        return configs

    dss_type = TYPE_MAP.get(rule_type)
    if not dss_type:
        valid = ", ".join(sorted(list(TYPE_MAP.keys()) + ["value-in-range"]))
        raise typer.BadParameter(
            f"Unknown rule type '{rule_type}'. Valid types: {valid}"
        )

    config: dict = {"type": dss_type}

    if name:
        config["displayName"] = name

    # Column-level rules use "columns" array
    if rule_type in (
        "not-empty",
        "column-min",
        "column-max",
        "column-avg",
        "column-sum",
    ):
        if not column:
            exit_with_error(
                f"--column is required for rule type '{rule_type}'.",
                details=[f"Example: dku dq create DS --type {rule_type} --column COL"],
            )
        config["columns"] = [column]

    # Range thresholds
    if rule_type in (
        "record-count",
        "column-min",
        "column-max",
        "column-avg",
        "column-sum",
    ):
        if min_val is not None:
            config["softMinimum"] = min_val
            config["softMinimumEnabled"] = True
        if max_val is not None:
            config["softMaximum"] = max_val
            config["softMaximumEnabled"] = True

    return config


# ── Commands ─────────────────────────────────────────────────────────────


@app.command("list")
def list_rules(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(..., help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List data quality rules defined on a dataset."""
    output = resolve_output_format(output)
    try:
        _, project_key, ruleset = _get_ruleset(ctx, dataset_name, project)
        rules = ruleset.list_rules(as_type="dict")

        if output == "json":
            render_raw(rules, output_format="json")
        else:
            data = []
            for r in rules:
                data.append(
                    {
                        "id": r.get("id", ""),
                        "name": r.get("displayName", ""),
                        "type": r.get("type", ""),
                        "enabled": str(r.get("enabled", True)),
                    }
                )

            render(
                data,
                ["id", "name", "type", "enabled"],
                output_format=output,
                title=f"Data Quality Rules ({dataset_name})",
                headers={
                    "id": "ID",
                    "name": "NAME",
                    "type": "TYPE",
                    "enabled": "ENABLED",
                },
            )
    except Exception as e:
        handle_api_error(e)


@app.command("create")
def create_rule(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(..., help="Dataset name"),
    config: str | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Rule config JSON (literal, @file.json, or '-' for stdin). Use for any of the 35+ DSS rule types.",
    ),
    rule_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "Rule type shorthand: record-count, not-empty, value-in-range, "
            "column-min, column-max, column-avg, column-sum. "
            "Column rules need --column. Range rules need --min and/or --max."
        ),
    ),
    column: str | None = typer.Option(
        None, "--column", help="Column name (for column-level rules)"
    ),
    name: str | None = typer.Option(None, "--name", help="Rule display name"),
    min_val: float | None = typer.Option(
        None, "--min", help="Minimum threshold (warning level = softMinimum)"
    ),
    max_val: float | None = typer.Option(
        None, "--max", help="Maximum threshold (warning level = softMaximum)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a data quality rule on a dataset.

    Use --config for raw JSON (any DSS rule type), or --type for common rules:

    \b
      record-count   — total row count in range (dataset-level)
      not-empty      — column has no nulls/blanks (BUGGY in DSS 14.5 beta — prefer column-min)
      value-in-range — creates TWO rules (min + max) ensuring all values in bounds
      column-min     — minimum column value in range (numeric columns only)
      column-max     — maximum column value in range (numeric columns only)
      column-avg     — average column value in range (numeric columns only)
      column-sum     — sum of column values in range (numeric columns only)

    For unlisted types (median, stddev, schema, file-size), use --config with raw JSON.
    Full type catalog: docs/dq-rule-types.md
    """
    if config and rule_type:
        exit_with_error(
            "Provide --config OR --type, not both.",
            details=[
                "--config accepts raw JSON for any rule type.",
                "--type builds config from flags.",
            ],
        )
    if not config and not rule_type:
        exit_with_error(
            "Either --config or --type is required.",
            details=[
                'Raw JSON: dku dq create DS --config \'{"type":"RecordCountInRangeRule","softMinimum":1,"softMinimumEnabled":true}\'',
                "Shorthand: dku dq create DS --type not-empty --column CountryISO --name 'Country check'",
            ],
        )

    try:
        _, project_key, ruleset = _get_ruleset(ctx, dataset_name, project)

        if config:
            rule_configs = [read_json_input(config)]
        else:
            result = _build_rule_config(rule_type, column, name, min_val, max_val)
            rule_configs = result if isinstance(result, list) else [result]

        for rc in rule_configs:
            rule = ruleset.create_rule(rc)
            success(f"Created rule '{rule.name}' (id: {rule.id}) on {dataset_name}")
            if rc.get("type") in _BUGGY_TYPES:
                warn(
                    f"Known DSS 14.5 beta bug: {rc['type']} creates OK but compute "
                    "fails with 'Threshold type cannot be null'. "
                    "Workaround: use --type column-min --column COL --min 1 instead."
                )
    except Exception as e:
        handle_api_error(e)


@app.command("compute")
def compute_rules(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(..., help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option(
        "NP", "--partition", help="Partition name (NP for non-partitioned)"
    ),
    rule_id: str | None = typer.Option(
        None, "--rule-id", help="Compute a specific rule only"
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for computation to finish"
    ),
) -> None:
    """Compute data quality rules on a dataset."""
    try:
        _, project_key, ruleset = _get_ruleset(ctx, dataset_name, project)

        if rule_id:
            rules = ruleset.list_rules(as_type="objects")
            match = [r for r in rules if r.id == rule_id]
            if not match:
                exit_with_error(
                    f"Rule '{rule_id}' not found on {dataset_name}.",
                    details=[
                        f"List rules: dku dq list {dataset_name} -P {project_key}"
                    ],
                )
            future = match[0].compute(partition=partition)
        else:
            future = ruleset.compute_rules(partition=partition)

        if wait:
            future.wait_for_result()
            success(f"Data quality rules computed on {dataset_name}")
        else:
            info(f"Computation started on {dataset_name}")
    except Exception as e:
        handle_api_error(e)


@app.command("status")
def get_status(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(..., help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show data quality status for a dataset."""
    output = resolve_output_format(output)
    try:
        _, _, ruleset = _get_ruleset(ctx, dataset_name, project)
        status = ruleset.get_status()

        if output == "json":
            render_raw(status, output_format="json")
        else:
            if isinstance(status, dict):
                for k, v in status.items():
                    info(f"{k}: {v}")
            else:
                info(f"Status: {status}")
    except Exception as e:
        handle_api_error(e)


@app.command("results")
def get_results(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(..., help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option("NP", "--partition", help="Partition name"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show latest data quality rule results for a dataset."""
    output = resolve_output_format(output)
    try:
        _, _, ruleset = _get_ruleset(ctx, dataset_name, project)
        results = ruleset.get_last_rules_results(partition=partition)

        if output == "json":
            render_raw([r.get_raw() for r in results], output_format="json")
        else:
            data = []
            for r in results:
                data.append(
                    {
                        "id": r.id,
                        "name": r.name,
                        "outcome": r.outcome,
                        "message": r.message,
                        "compute_date": str(r.compute_date),
                    }
                )

            render(
                data,
                ["id", "name", "outcome", "message", "compute_date"],
                output_format=output,
                title=f"DQ Results ({dataset_name})",
                headers={
                    "id": "ID",
                    "name": "NAME",
                    "outcome": "OUTCOME",
                    "message": "MESSAGE",
                    "compute_date": "COMPUTED",
                },
            )
    except Exception as e:
        handle_api_error(e)


@app.command("delete")
def delete_rule(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(..., help="Dataset name"),
    rule_id: str = typer.Option(..., "--rule-id", help="Rule ID to delete"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a data quality rule from a dataset."""
    try:
        _, project_key, ruleset = _get_ruleset(ctx, dataset_name, project)
        rules = ruleset.list_rules(as_type="objects")
        match = [r for r in rules if r.id == rule_id]
        if not match:
            exit_with_error(
                f"Rule '{rule_id}' not found on {dataset_name}.",
                details=[f"List rules: dku dq list {dataset_name} -P {project_key}"],
            )

        rule = match[0]
        from dku_cli.safety import Tier, guard

        guard(
            ctx,
            tier=Tier.DELETE,
            action="dq.delete",
            subject=f"rule '{rule.name}' ({rule_id}) on {dataset_name}",
            yes=yes,
            prompt=f"Delete data quality rule '{rule.name}' ({rule_id}) from dataset {dataset_name}?",
        )

        rule.delete()
        success(f"Deleted rule '{rule.name}' ({rule_id}) from {dataset_name}")
    except Exception as e:
        handle_api_error(e)


@app.command("project-status")
def project_status(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    all_datasets: bool = typer.Option(
        False, "--all", help="Include non-monitored datasets"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show data quality status across all datasets in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        statuses = proj.get_data_quality_status(only_monitored=not all_datasets)

        if output == "json":
            render_raw(statuses, output_format="json")
        else:
            data = []
            for ds_name, ds_status in statuses.items():
                if isinstance(ds_status, dict):
                    data.append(
                        {
                            "dataset": ds_name,
                            "status": ds_status.get("status", str(ds_status)),
                        }
                    )
                else:
                    data.append({"dataset": ds_name, "status": str(ds_status)})

            render(
                data,
                ["dataset", "status"],
                output_format=output,
                title=f"Data Quality Status ({project_key})",
                headers={"dataset": "DATASET", "status": "STATUS"},
            )
    except Exception as e:
        handle_api_error(e)

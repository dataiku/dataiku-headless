"""dku dq — list, create, compute, status, results, delete, project-status,
rule-types, rule-schema."""

from __future__ import annotations

import contextlib

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

# ── Helpers ──────────────────────────────────────────────────────────────


def _get_ruleset(ctx: typer.Context, dataset_name: str, project: str | None):
    """Return (client, project_key, dataset, ruleset) tuple."""
    project_key = resolve_project(project)
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    ds = proj.get_dataset(dataset_name)
    return client, project_key, ds, ds.get_data_quality_rules()


# Discovered DSS rule type names (DSS 14.5.0-beta2).
# Column rules use "columns" (array), NOT "column" (singular).
#
# Dataset-level: RecordCountInRangeRule, ColumnCountInRangeRule,
#   FileSizeInRangeRule, DatasetSchemaEqualsRule, DatasetSchemaContainsRule
# Column-level: ColumnNotEmptyRule, ColumnEmptyRule,
#   ColumnMinInRangeRule, ColumnMaxInRangeRule, ColumnAvgInRangeRule,
#   ColumnSumInRangeRule, ColumnMedianInRangeRule, ColumnStdDevInRangeRule
#
# ColumnNotEmptyRule REQUIRES a thresholdType enum or compute fails with
# "Threshold type cannot be null". Verified live (DSS 14.6): the value
# "ENTIRE_COLUMN_NOT_EMPTY" makes the rule pass when the column has no blanks.
#
# "value-in-range" creates TWO rules (min + max) to ensure all values in bounds.
TYPE_MAP = {
    "record-count": "RecordCountInRangeRule",
    "column-count": "ColumnCountInRangeRule",
    "not-empty": "ColumnNotEmptyRule",
    "column-min": "ColumnMinInRangeRule",
    "column-max": "ColumnMaxInRangeRule",
    "column-avg": "ColumnAvgInRangeRule",
    "column-sum": "ColumnSumInRangeRule",
}


def _bounds(**overrides) -> dict:
    """Hard + soft range bounds shared by every *InRangeRule. Hard bounds fail
    (ERROR), soft bounds warn (WARNING); each side is inert until its
    *Enabled flag is true."""
    base = {
        "minimum": 0,
        "minimumEnabled": False,
        "maximum": 0,
        "maximumEnabled": False,
        "softMinimum": 0,
        "softMinimumEnabled": False,
        "softMaximum": 0,
        "softMaximumEnabled": False,
    }
    base.update(overrides)
    return base


_DRIFT_PARAMS = {
    "iqrFactor": 1.5,
    "iqrFactorEnabled": True,
    "softIqrFactor": 1.5,
    "softIqrFactorEnabled": False,
    "lookbackPeriod": 7,
    "periodUnit": "DAY",
    "learningPeriod": 5,
}


def _column_agg_template(dss_type: str, label: str) -> tuple[dict, str]:
    return (
        {
            "type": dss_type,
            "displayName": f"{label} of COLUMN_NAME in range",
            "columns": ["COLUMN_NAME"],
            **_bounds(minimumEnabled=True, maximumEnabled=True),
        },
        f"{label} of a numeric column within bounds",
    )


def _drift_column_template(dss_type: str, label: str) -> tuple[dict, str]:
    return (
        {
            "type": dss_type,
            "displayName": f"Drift on {label} of COLUMN_NAME",
            "columns": ["COLUMN_NAME"],
            "driftParams": dict(_DRIFT_PARAMS),
        },
        f"Flag when column {label} drifts vs. its recent history (IQR test)",
    )


# Curated config templates for the native DSS rule types. (template, description).
# Placeholders are UPPER_SNAKE — replace before `dq create --config`.
RULE_TEMPLATES: dict[str, tuple[dict, str]] = {
    "RecordCountInRangeRule": (
        {
            "type": "RecordCountInRangeRule",
            "displayName": "Record count in range",
            **_bounds(minimum=1, minimumEnabled=True),
        },
        "Total row count within bounds (dataset-level)",
    ),
    "ColumnCountInRangeRule": (
        {
            "type": "ColumnCountInRangeRule",
            "displayName": "Column count in range",
            **_bounds(minimumEnabled=True, maximumEnabled=True),
        },
        "Number of columns within bounds; exact = same min and max (dataset-level)",
    ),
    "ColumnNotEmptyRule": (
        {
            "type": "ColumnNotEmptyRule",
            "displayName": "COLUMN_NAME has no empty values",
            "columns": ["COLUMN_NAME"],
            "thresholdType": "ENTIRE_COLUMN_NOT_EMPTY",
        },
        "Column has no nulls/blanks (thresholdType is REQUIRED or compute fails)",
    ),
    "ColumnEmptyRule": (
        {
            "type": "ColumnEmptyRule",
            "displayName": "COLUMN_NAME is fully empty",
            "columns": ["COLUMN_NAME"],
        },
        "Column contains only nulls/blanks",
    ),
    "ColumnUniqueValuesRule": (
        {
            "type": "ColumnUniqueValuesRule",
            "displayName": "COLUMN_NAME values are unique",
            "columns": ["COLUMN_NAME"],
            "thresholdType": "ENTIRE_COLUMN",
        },
        "No duplicate values in the column (thresholdType ENTIRE_COLUMN)",
    ),
    "ValuesInSetRule": (
        {
            "type": "ValuesInSetRule",
            "displayName": "COLUMN_NAME values in allowed set",
            "columns": ["COLUMN_NAME"],
            "valueSet": ["VALUE_1", "VALUE_2"],
        },
        "Every value belongs to the enumerated valueSet",
    ),
    "ValuesInRangeRule": (
        {
            "type": "ValuesInRangeRule",
            "displayName": "COLUMN_NAME values in range",
            "columns": ["COLUMN_NAME"],
            **_bounds(minimumEnabled=True, maximumEnabled=True),
        },
        "Every value within bounds (per-row check, not an aggregate)",
    ),
    "DatasetSchemaContainsRule": (
        {
            "type": "DatasetSchemaContainsRule",
            "displayName": "Schema contains expected columns",
            "expectedSchema": {"columns": [{"name": "COLUMN_NAME", "type": "string"}]},
        },
        "Schema contains at least these columns (name + storage type)",
    ),
    "DatasetSchemaEqualsRule": (
        {
            "type": "DatasetSchemaEqualsRule",
            "displayName": "Schema equals expected schema",
            "expectedSchema": {"columns": [{"name": "COLUMN_NAME", "type": "string"}]},
        },
        "Schema exactly matches these columns (name + storage type, in order)",
    ),
    "ColumnMinInRangeRule": _column_agg_template("ColumnMinInRangeRule", "Min"),
    "ColumnMaxInRangeRule": _column_agg_template("ColumnMaxInRangeRule", "Max"),
    "ColumnAvgInRangeRule": _column_agg_template("ColumnAvgInRangeRule", "Avg"),
    "ColumnSumInRangeRule": _column_agg_template("ColumnSumInRangeRule", "Sum"),
    "ColumnMedianInRangeRule": _column_agg_template(
        "ColumnMedianInRangeRule", "Median"
    ),
    "ColumnStdDevInRangeRule": _column_agg_template(
        "ColumnStdDevInRangeRule", "StdDev"
    ),
    "DriftRecordCountRule": (
        {
            "type": "DriftRecordCountRule",
            "displayName": "Drift on record count",
            "driftParams": dict(_DRIFT_PARAMS),
        },
        "Flag when row count drifts vs. its recent history (IQR test, dataset-level)",
    ),
    "DriftColumnAvgRule": _drift_column_template("DriftColumnAvgRule", "avg"),
    "DriftColumnMinRule": _drift_column_template("DriftColumnMinRule", "min"),
    "DriftColumnMaxRule": _drift_column_template("DriftColumnMaxRule", "max"),
    "DriftColumnMedianRule": _drift_column_template("DriftColumnMedianRule", "median"),
    "DriftColumnSumRule": _drift_column_template("DriftColumnSumRule", "sum"),
    "DriftColumnStdDevRule": _drift_column_template("DriftColumnStdDevRule", "stddev"),
    "DriftColumnEmptyValueCountRule": _drift_column_template(
        "DriftColumnEmptyValueCountRule", "empty-value count"
    ),
    "DriftColumnUniqueValueCountRule": _drift_column_template(
        "DriftColumnUniqueValueCountRule", "unique-value count"
    ),
    "DriftMetricRule": (
        {
            "type": "DriftMetricRule",
            "displayName": "Drift on metric METRIC_ID",
            "metricId": "METRIC_ID",
            "driftParams": dict(_DRIFT_PARAMS),
        },
        "Flag when any computed metric drifts vs. its recent history (IQR test)",
    ),
}


def _rule_scope(dss_type: str) -> str:
    template = RULE_TEMPLATES[dss_type][0]
    return "column" if "columns" in template else "dataset"


# Rules whose evaluation reads a col_stats aggregate. Some engines/dataset
# types refuse to compute them ("Some required metrics can't be computed:
# col_stats:MIN:<col>") unless the dataset carries a col_stats probe with
# computeOnBuildMode WHOLE_DATASET — provisioned automatically before compute.
_COL_STATS_AGG_BY_RULE = {
    "ColumnMinInRangeRule": "MIN",
    "ColumnMaxInRangeRule": "MAX",
    "ColumnAvgInRangeRule": "AVG",
    "ColumnSumInRangeRule": "SUM",
    "ColumnMedianInRangeRule": "MEDIAN",
    "ColumnStdDevInRangeRule": "STDDEV",
}

_NUMERIC_STORAGE_TYPES = {
    "tinyint",
    "smallint",
    "int",
    "bigint",
    "float",
    "double",
}


def _required_col_stats(rules: list[dict]) -> list[tuple[str, str]]:
    """(column, aggregate) pairs the enabled rules need from col_stats."""
    required: list[tuple[str, str]] = []
    for rule in rules:
        agg = _COL_STATS_AGG_BY_RULE.get(rule.get("type", ""))
        if not agg or not rule.get("enabled", True):
            continue
        for col in rule.get("columns") or []:
            if (col, agg) not in required:
                required.append((col, agg))
    return required


def _ensure_col_stats_probe(ds, rules: list[dict]) -> None:
    """Provision/merge the col_stats probe the metric-backed rules require.

    Numeric aggregates targeting non-numeric columns are skipped with a
    warning instead of aborting the whole probe (one bad aggregate makes
    DSS refuse to compute all of them).
    """
    required = _required_col_stats(rules)
    if not required:
        return

    col_types = {
        c.get("name"): c.get("type", "") for c in ds.get_schema().get("columns", [])
    }
    keep: list[tuple[str, str]] = []
    for col, agg in required:
        ctype = col_types.get(col)
        if ctype is not None and ctype not in _NUMERIC_STORAGE_TYPES:
            warn(
                f"Skipping col_stats {agg} on '{col}': storage type '{ctype}' "
                "is not numeric — the rule will report it cannot be checked."
            )
            continue
        keep.append((col, agg))
    if not keep:
        return

    settings = ds.get_settings()
    metrics = settings.get_raw().setdefault("metrics", {})
    probes = metrics.setdefault("probes", [])
    probe = next((p for p in probes if p.get("type") == "col_stats"), None)
    if probe is None:
        probe = {
            "type": "col_stats",
            "enabled": True,
            "computeOnBuildMode": "WHOLE_DATASET",
            "meta": {"name": "Columns statistics", "level": 2},
            "configuration": {"aggregates": []},
        }
        probes.append(probe)
    aggregates = probe.setdefault("configuration", {}).setdefault("aggregates", [])
    existing = {(a.get("column"), a.get("aggregated")) for a in aggregates}
    changed = probe.get("enabled") is not True or (
        probe.get("computeOnBuildMode") != "WHOLE_DATASET"
    )
    probe["enabled"] = True
    probe["computeOnBuildMode"] = "WHOLE_DATASET"
    for col, agg in keep:
        if (col, agg) not in existing:
            aggregates.append({"column": col, "aggregated": agg})
            changed = True
    if changed:
        settings.save()


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
        valid = ", ".join(sorted([*list(TYPE_MAP.keys()), "value-in-range"]))
        raise typer.BadParameter(
            f"Unknown rule type '{rule_type}'. Valid types: {valid}"
        )

    config: dict = {"type": dss_type}

    if name:
        config["displayName"] = name
    else:
        # Without a name DSS shows "Created rule ''" and a blank NAME column
        # in results — derive a readable default from type + column.
        config["displayName"] = f"{rule_type} {column}".strip() if column else rule_type

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

    # ColumnNotEmptyRule needs an explicit thresholdType or compute returns
    # "Threshold type cannot be null". ENTIRE_COLUMN_NOT_EMPTY = no blanks
    # allowed anywhere in the column. Verified live against DSS 14.6.
    if rule_type == "not-empty":
        config["thresholdType"] = "ENTIRE_COLUMN_NOT_EMPTY"

    # column-count is a dataset-level rule. Use HARD bounds so an exact match
    # (--min N --max N) fails loudly when the column count differs.
    if rule_type == "column-count":
        if min_val is None and max_val is None:
            exit_with_error(
                "--min and/or --max is required for rule type 'column-count'.",
                details=[
                    "Exact count: dku dq create DS --type column-count --min 6 --max 6"
                ],
            )
        if min_val is not None:
            config["minimum"] = min_val
            config["minimumEnabled"] = True
        if max_val is not None:
            config["maximum"] = max_val
            config["maximumEnabled"] = True

    # Range thresholds (warning-level soft bounds)
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
) -> None:
    """List data quality rules defined on a dataset."""
    output = resolve_output_format()
    try:
        _, _project_key, _ds, ruleset = _get_ruleset(ctx, dataset_name, project)
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
            "Rule type shorthand: record-count, column-count, not-empty, "
            "value-in-range, column-min, column-max, column-avg, column-sum. "
            "Column rules need --column. Range/count rules need --min and/or --max."
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
      column-count   — number of columns in range (dataset-level); exact = --min N --max N
      not-empty      — column has no nulls/blanks (works on any column type)
      value-in-range — creates TWO rules (min + max) ensuring all values in bounds
      column-min     — minimum column value in range (numeric columns only)
      column-max     — maximum column value in range (numeric columns only)
      column-avg     — average column value in range (numeric columns only)
      column-sum     — sum of column values in range (numeric columns only)

    For unlisted types (median, stddev, schema, file-size), use --config with raw JSON.
    Payload reference: dataiku-mcp/skills/dku-cli/SKILL.md
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
        _, _project_key, _ds, ruleset = _get_ruleset(ctx, dataset_name, project)

        if config:
            rule_configs = [read_json_input(config)]
        else:
            result = _build_rule_config(rule_type, column, name, min_val, max_val)
            rule_configs = result if isinstance(result, list) else [result]

        for rc in rule_configs:
            rule = ruleset.create_rule(rc)
            success(f"Created rule '{rule.name}' (id: {rule.id}) on {dataset_name}")
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
    """Compute data quality rules on a dataset.

    Metric-backed rules (Column{Min,Max,Avg,Sum,Median,StdDev}InRangeRule)
    need a col_stats probe on the dataset; it is provisioned automatically
    before computing (aggregates on non-numeric columns are skipped with a
    warning instead of aborting the probe).
    """
    try:
        _, project_key, ds, ruleset = _get_ruleset(ctx, dataset_name, project)

        rule_dicts = ruleset.list_rules(as_type="dict")
        if rule_id:
            rule_dicts = [r for r in rule_dicts if r.get("id") == rule_id]
            if not rule_dicts:
                exit_with_error(
                    f"Rule '{rule_id}' not found on {dataset_name}.",
                    details=[
                        f"List rules: dku dq list {dataset_name} -P {project_key}"
                    ],
                )
        # Best-effort: a failed provisioning must not block compute — some
        # engines evaluate these rules without the probe.
        with contextlib.suppress(Exception):
            _ensure_col_stats_probe(ds, rule_dicts)

        if rule_id:
            rules = ruleset.list_rules(as_type="objects")
            match = [r for r in rules if r.id == rule_id]
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
) -> None:
    """Show data quality status for a dataset."""
    output = resolve_output_format()
    try:
        _, _, _ds, ruleset = _get_ruleset(ctx, dataset_name, project)
        status = ruleset.get_status()
        render_raw(status, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("results")
def get_results(
    ctx: typer.Context,
    dataset_name: str = typer.Argument(..., help="Dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    partition: str = typer.Option("NP", "--partition", help="Partition name"),
) -> None:
    """Show latest data quality rule results for a dataset."""
    output = resolve_output_format()
    try:
        _, _, _ds, ruleset = _get_ruleset(ctx, dataset_name, project)
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
        _, project_key, _ds, ruleset = _get_ruleset(ctx, dataset_name, project)
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
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("rule-types")
def rule_types(
    ctx: typer.Context,
) -> None:
    """List native DSS data quality rule type ids with scope and description.

    Get a ready-to-edit config template for any listed type with
    `dku dq rule-schema <TYPE>`, then create it with `dku dq create DS --config @file`.
    """
    output = resolve_output_format()
    rows = [
        {"type": t, "scope": _rule_scope(t), "description": desc}
        for t, (_tpl, desc) in sorted(RULE_TEMPLATES.items())
    ]
    render(
        rows,
        ["type", "scope", "description"],
        output_format=output,
        title="Data Quality Rule Types",
        headers={"type": "TYPE", "scope": "SCOPE", "description": "DESCRIPTION"},
    )


@app.command("rule-schema")
def rule_schema(
    ctx: typer.Context,
    rule_type: str = typer.Argument(
        help="Rule type id (see `dku dq rule-types`), case-insensitive"
    ),
) -> None:
    """Emit a config template JSON for a data quality rule type.

    Replace the UPPER_SNAKE placeholders (COLUMN_NAME, VALUE_1, METRIC_ID)
    and the threshold values, then create the rule:

        dku dq rule-schema ValuesInSetRule > rule.json
        dku dq create my_dataset --config @rule.json -P PROJ
    """
    by_lower = {t.lower(): t for t in RULE_TEMPLATES}
    canonical = by_lower.get(rule_type.lower())
    if canonical is None:
        exit_with_error(
            f"Unknown rule type '{rule_type}'.",
            details=[
                "List valid types: dku dq rule-types",
                "Valid: " + ", ".join(sorted(RULE_TEMPLATES)),
            ],
        )
    render_raw(RULE_TEMPLATES[canonical][0], output_format="json")


@app.command("project-status")
def project_status(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    all_datasets: bool = typer.Option(
        False, "--all", help="Include non-monitored datasets"
    ),
) -> None:
    """Show data quality status across all datasets in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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

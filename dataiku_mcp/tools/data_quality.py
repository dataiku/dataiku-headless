"""Data Quality inspection tools for DSS datasets."""

from typing import Any

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import compact_json, is_empty, omit_empty
from .utils.validation import require_non_empty_string as _require_non_empty_string


def _get_ruleset(project_key: str, dataset_name: str):
    dataset = get_dss_client().get_project(project_key).get_dataset(dataset_name)
    return dataset.get_data_quality_rules()


def _summarize_rule(raw_rule: dict) -> dict:
    summary = {
        "id": raw_rule.get("id"),
        "displayName": raw_rule.get("displayName"),
        "type": raw_rule.get("type"),
        "enabled": raw_rule.get("enabled"),
        "autoRun": raw_rule.get("autoRun"),
        "computeOnBuildMode": raw_rule.get("computeOnBuildMode"),
    }
    summary = omit_empty(summary)
    if "columns" in raw_rule:
        summary["columns"] = raw_rule.get("columns")
    if "columnSpecs" in raw_rule:
        summary["columnSpecs"] = raw_rule.get("columnSpecs")
    if "metricId" in raw_rule:
        summary["metricId"] = raw_rule.get("metricId")
    if "valueSet" in raw_rule:
        summary["valueSet_count"] = len(raw_rule.get("valueSet") or [])
    for key in ("driftParams", "expectedSchema", "code", "envSelection", "meta"):
        if key in raw_rule:
            summary[f"has_{key}"] = True
    return summary


def _safe_status(ruleset) -> tuple[Any, str | None]:
    try:
        return ruleset.get_status(), None
    except Exception as exc:
        return None, str(exc)


def _safe_status_by_partition(
    ruleset, include_all_partitions: bool
) -> tuple[Any, str | None]:
    try:
        return ruleset.get_status_by_partition(
            include_all_partitions=include_all_partitions
        ), None
    except Exception as exc:
        return None, str(exc)


@mcp.tool()
async def list_data_quality_rules(
    project_key: str,
    dataset_name: str,
    ctx: Context,
) -> str:
    """List Data Quality rules configured on a dataset with compact summaries."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    await ctx.info(f"Listing Data Quality rules for {dataset_name} in {project_key}...")

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        rules = ruleset.list_rules(as_type="dict")
        result = {"monitor": ruleset.ruleset.get("monitor"), "rules": []}
        result["rules"] = [_summarize_rule(rule) for rule in rules]
        if is_empty(result["monitor"]):
            del result["monitor"]
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_data_quality_status(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    include_partitions: bool = True,
    include_all_partitions: bool = False,
) -> str:
    """Get dataset-level Data Quality status, optionally with partition statuses."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    await ctx.info(f"Loading Data Quality status for {dataset_name} in {project_key}...")

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        status, status_warning = _safe_status(ruleset)
        result = {"status": status}
        if is_empty(result["status"]):
            del result["status"]
        warnings = []
        if status_warning:
            warnings.append(
                f"Could not read dataset Data Quality status: {status_warning}"
            )
        if include_partitions:
            partition_status, partition_warning = _safe_status_by_partition(
                ruleset, include_all_partitions
            )
            if not is_empty(partition_status):
                result["status_by_partition"] = partition_status
            if partition_warning:
                warnings.append(
                    "Could not read Data Quality status by partition: "
                    f"{partition_warning}"
                )
        if warnings:
            result["warnings"] = warnings
        return result

    return compact_json(await run_blocking(_run))

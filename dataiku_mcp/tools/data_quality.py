"""Data Quality rule operations for Dataiku DSS datasets."""

import time
from typing import Any

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import compact_json, is_empty, omit_empty
from .utils.auth import get_dss_client
from .utils.parsing import (
    coerce_json_array as _coerce_json_array,
    coerce_json_object as _coerce_json_object,
)
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)


DEFAULT_WAIT_TIMEOUT_SECONDS = 50
FUTURE_POLL_INTERVAL_SECONDS = 2


def _get_ruleset(project_key: str, dataset_name: str):
    dataset = get_dss_client().get_project(project_key).get_dataset(dataset_name)
    return dataset.get_data_quality_rules()


def _serialize_rule_result(result):
    if result is None:
        return None
    return result.get_raw()


def _summarize_rule(raw_rule: dict) -> dict:
    summary = {
        "id": raw_rule.get("id"),
        "displayName": raw_rule.get("displayName"),
        "type": raw_rule.get("type"),
        "enabled": raw_rule.get("enabled"),
        "autoRun": raw_rule.get("autoRun"),
        "computeOnBuildMode": raw_rule.get("computeOnBuildMode"),
    }
    # Omit base fields whose value carries no information (None/""/[]/{});
    # keep False booleans (enabled/autoRun) since those carry information.
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


def _find_rule(ruleset, rule_id: str):
    rules = ruleset.list_rules(as_type="objects")
    for rule in rules:
        if rule.id == rule_id:
            return rule
    raise ValueError(f"Data Quality rule '{rule_id}' was not found")


def _parse_rule_ids(rule_ids) -> list[str] | None:
    if rule_ids is None:
        return None
    parsed = _coerce_json_array(rule_ids, "rule_ids")
    result = []
    for i, value in enumerate(parsed):
        result.append(_require_non_empty_string(value, f"rule_ids[{i}]"))
    return result


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


def _wait_for_future_result(
    future,
    timeout_seconds: int,
) -> tuple[bool, dict]:
    deadline = time.monotonic() + timeout_seconds

    while True:
        state = future.peek_state()
        if state.get("hasResult", False):
            return False, state

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True, state

        time.sleep(min(FUTURE_POLL_INTERVAL_SECONDS, remaining))


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
        result = {
            "monitor": ruleset.ruleset.get("monitor"),
            "rules": [_summarize_rule(rule) for rule in rules],
        }
        # Omit monitor when it carries no information (None/""); keep the
        # rules list even when empty (absence of rules is itself a signal).
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
    """Get the dataset-level Data Quality status, optionally with partition statuses."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    await ctx.info(f"Loading Data Quality status for {dataset_name} in {project_key}...")

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        status, status_warning = _safe_status(ruleset)
        result = {
            "status": status,
        }
        # Omit status when empty (None/{}/"") — e.g. when it could not be read.
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
            # Omit partition status when empty (None/{}/"").
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


@mcp.tool()
async def get_data_quality_rule(
    project_key: str,
    dataset_name: str,
    rule_id: str,
    ctx: Context,
) -> str:
    """Get one raw Data Quality rule configuration by ID."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    rule_id = _require_non_empty_string(rule_id, "rule_id")
    await ctx.info(
        f"Loading Data Quality rule {rule_id} for {dataset_name} in {project_key}..."
    )

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        rule = _find_rule(ruleset, rule_id)
        return {
            "rule": rule.get_raw(),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_data_quality_rule_results(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    partition: str = "NP",
    rule_id: str | None = None,
) -> str:
    """Get the latest computed Data Quality rule result(s) for a dataset partition."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    partition = _require_non_empty_string(partition or "NP", "partition")
    if rule_id is not None:
        rule_id = _require_non_empty_string(rule_id, "rule_id")

    await ctx.info(
        f"Loading Data Quality rule results for {dataset_name} in {project_key} "
        f"(partition={partition}, rule_id={rule_id})..."
    )

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        if rule_id:
            rule = _find_rule(ruleset, rule_id)
            raw_results = [_serialize_rule_result(rule.get_last_result(partition))]
            raw_results = [item for item in raw_results if item is not None]
        else:
            raw_results = [
                _serialize_rule_result(result)
                for result in ruleset.get_last_rules_results(partition)
            ]
        result = {
            "partition": partition,
            "rule_id": rule_id,
            "results": raw_results,
        }
        # Omit rule_id when not supplied (None); keep results even if empty.
        if is_empty(result["rule_id"]):
            del result["rule_id"]
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_data_quality_rule_history(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    min_timestamp: int | None = None,
    max_timestamp: int | None = None,
    results_per_page: int = 100,
    page: int = 0,
    rule_ids=None,
) -> str:
    """Get recent Data Quality rule result history for a dataset.

    Args:
        rule_ids: Optional JSON array of rule IDs to filter, e.g. '["abc123"]'
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    if min_timestamp is not None:
        min_timestamp = _require_non_negative_int(min_timestamp, "min_timestamp")
    if max_timestamp is not None:
        max_timestamp = _require_non_negative_int(max_timestamp, "max_timestamp")
    results_per_page = min(
        _require_positive_int(results_per_page, "results_per_page"), 1000
    )
    page = _require_non_negative_int(page, "page")
    rule_ids_list = _parse_rule_ids(rule_ids)

    await ctx.info(
        f"Loading Data Quality rule history for {dataset_name} in {project_key} "
        f"(page={page}, results_per_page={results_per_page})..."
    )

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        results = ruleset.get_rules_history(
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            results_per_page=results_per_page,
            page=page,
            rule_ids=rule_ids_list,
        )
        raw_results = [_serialize_rule_result(result) for result in results]
        result = {
            "min_timestamp": min_timestamp,
            "max_timestamp": max_timestamp,
            "page": page,
            "results_per_page": results_per_page,
            "rule_ids": rule_ids_list,
            "results": raw_results,
        }
        # Omit unset filters whose value carries no information (None/[]);
        # keep page=0 and results_per_page (0 / non-empty defaults).
        for _key in ("min_timestamp", "max_timestamp", "rule_ids"):
            if is_empty(result[_key]):
                del result[_key]
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_data_quality_rule(
    project_key: str,
    dataset_name: str,
    rule_config,
    ctx: Context,
) -> str:
    """Create a Data Quality rule from a raw rule configuration object."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    config_obj = _coerce_json_object(rule_config, "rule_config")

    await ctx.info(f"Creating Data Quality rule on {dataset_name} in {project_key}...")

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        created_rule = ruleset.create_rule(config_obj)
        rules = ruleset.list_rules(as_type="dict")
        return {
            "rule": created_rule.get_raw(),
            "rule_count": len(rules),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def update_data_quality_rule(
    project_key: str,
    dataset_name: str,
    rule_id: str,
    rule_config,
    ctx: Context,
) -> str:
    """Replace a Data Quality rule with a full raw rule config.

    Args:
        rule_config: Full raw rule object, typically from get_data_quality_rule["rule"]
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    rule_id = _require_non_empty_string(rule_id, "rule_id")
    config_obj = _coerce_json_object(rule_config, "rule_config")

    await ctx.info(
        f"Updating Data Quality rule {rule_id} on {dataset_name} in {project_key}..."
    )

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        rule = _find_rule(ruleset, rule_id)
        updated = {**config_obj, "id": rule_id}

        rule.rule = updated
        rule.save()

        reread_ruleset = _get_ruleset(project_key, dataset_name)
        updated_rule = _find_rule(reread_ruleset, rule_id)
        return {
            "rule": updated_rule.get_raw(),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def compute_data_quality_rules(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    partition: str = "NP",
    rule_id: str | None = None,
    wait_for_completion: bool = True,
    timeout_seconds: int = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> str:
    """Compute enabled Data Quality rules for a dataset or one rule.

    Args:
        partition: Partition to compute; use "NP" for non-partitioned datasets
        rule_id: Optional rule ID to compute only one rule
        wait_for_completion: If true, wait for completion and return fresh status/results
        timeout_seconds: Max time to wait before returning in-progress future state
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    partition = _require_non_empty_string(partition or "NP", "partition")
    if rule_id is not None:
        rule_id = _require_non_empty_string(rule_id, "rule_id")
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")

    await ctx.info(
        f"Computing Data Quality rules for {dataset_name} in {project_key} "
        f"(partition={partition}, rule_id={rule_id}, "
        f"wait_for_completion={wait_for_completion}, timeout_seconds={timeout_seconds})..."
    )

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        if rule_id:
            rule = _find_rule(ruleset, rule_id)
            future = rule.compute(partition)
        else:
            future = ruleset.compute_rules(partition)

        future_state = future.peek_state()
        base = {
            "status": "compute_started",
            "partition": partition,
            "rule_id": rule_id,
            "future_id": future.job_id,
            "future_state": future_state,
        }
        # Omit rule_id when computing all rules (None); propagates to every
        # return below via {**base, ...}.
        if is_empty(base["rule_id"]):
            del base["rule_id"]

        if not wait_for_completion:
            base["hint"] = (
                "Use get_future_status(future_id, fetch_result=true) to inspect "
                "the DSSFuture result when it is ready."
            )
            return base

        timed_out, future_state = _wait_for_future_result(future, timeout_seconds)
        if timed_out:
            return {
                **base,
                "status": "compute_still_running",
                "future_state": future_state,
                "timeout_seconds": timeout_seconds,
                "hint": (
                    "Use get_future_status(future_id, fetch_result=true) to inspect "
                    "the DSSFuture result when it is ready."
                ),
            }

        future_result = future.get_result()
        refreshed_ruleset = _get_ruleset(project_key, dataset_name)
        status, status_warning = _safe_status(refreshed_ruleset)
        partition_status, partition_warning = _safe_status_by_partition(
            refreshed_ruleset, include_all_partitions=False
        )
        if rule_id:
            refreshed_rule = _find_rule(refreshed_ruleset, rule_id)
            raw_results = [
                _serialize_rule_result(refreshed_rule.get_last_result(partition))
            ]
            raw_results = [item for item in raw_results if item is not None]
        else:
            raw_results = [
                _serialize_rule_result(result)
                for result in refreshed_ruleset.get_last_rules_results(partition)
            ]

        warnings = []
        if status_warning:
            warnings.append(
                f"Could not read dataset Data Quality status: {status_warning}"
            )
        if partition_warning:
            warnings.append(
                "Could not read Data Quality status by partition: "
                f"{partition_warning}"
            )

        result = {
            **base,
            "status": "compute_completed",
            "future_state": future_state,
            "timeout_seconds": timeout_seconds,
            "future_result": future_result,
            "data_quality_status": status,
            "status_by_partition": partition_status,
            "results": raw_results,
        }
        # Omit empty optional blocks (None/{}/"") — e.g. status fields that
        # could not be read, or an empty future_result. Keep results even if
        # empty (a meaningful "nothing computed" signal).
        for _key in ("future_result", "data_quality_status", "status_by_partition"):
            if is_empty(result[_key]):
                del result[_key]
        if warnings:
            result["warnings"] = warnings
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def delete_data_quality_rule(
    project_key: str,
    dataset_name: str,
    rule_id: str,
    ctx: Context,
) -> str:
    """Delete one Data Quality rule from a dataset."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    rule_id = _require_non_empty_string(rule_id, "rule_id")
    await ctx.info(f"Deleting Data Quality rule {rule_id} on {dataset_name}...")

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        rule = _find_rule(ruleset, rule_id)
        deleted_rule = rule.get_raw()
        rule.delete()
        remaining_ruleset = _get_ruleset(project_key, dataset_name)
        remaining = remaining_ruleset.list_rules(as_type="dict")
        return {
            "deleted_rule": deleted_rule,
            "remaining_rule_count": len(remaining),
        }

    return compact_json(await run_blocking(_run))

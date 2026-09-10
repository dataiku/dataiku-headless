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

"""Data Quality inspection tools for Dataiku datasets."""

from typing import Annotated, Any

from fastmcp import Context
from pydantic import Field

from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.parsing import coerce_json_array as _coerce_json_array
from .utils.serialization import compact_json, is_empty, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_non_empty_strings as _require_non_empty_strings,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)


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
    return _require_non_empty_strings(parsed, "rule_ids")


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


@mcp.tool(
    title="List Data Quality Rules",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_data_quality_rules(
    project_key: str,
    dataset_name: str,
    ctx: Context,
) -> str:
    """See which data quality rules a dataset is checked against."""
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


@mcp.tool(
    title="Get Data Quality Status",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_data_quality_status(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    include_partitions: bool = True,
    include_all_partitions: Annotated[
        bool, Field(description="Adds partitions with no computed status.")
    ] = False,
) -> str:
    """Check whether a dataset currently passes its data quality rules."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    await ctx.info(
        f"Loading Data Quality status for {dataset_name} in {project_key}..."
    )

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


@mcp.tool(
    title="Get Data Quality Rule",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_data_quality_rule(
    project_key: str,
    dataset_name: str,
    rule_id: str,
    ctx: Context,
) -> str:
    """Read one data quality rule's raw configuration and thresholds."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    rule_id = _require_non_empty_string(rule_id, "rule_id")
    await ctx.info(
        f"Loading Data Quality rule {rule_id} for {dataset_name} in {project_key}..."
    )

    def _run():
        ruleset = _get_ruleset(project_key, dataset_name)
        rule = _find_rule(ruleset, rule_id)
        return {"rule": rule.get_raw()}

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="Get Data Quality Rule Results",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_data_quality_rule_results(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    partition: Annotated[
        str, Field(description='"NP" for a non-partitioned dataset.')
    ] = "NP",
    rule_id: Annotated[
        str | None, Field(description="Every rule when omitted.")
    ] = None,
) -> str:
    """Read the latest computed outcome for a dataset's rules."""
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
        result = {"partition": partition, "rule_id": rule_id, "results": raw_results}
        if is_empty(result["rule_id"]):
            del result["rule_id"]
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="Get Data Quality Rule History",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_data_quality_rule_history(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    min_timestamp: Annotated[
        int | None, Field(description="Epoch milliseconds.")
    ] = None,
    max_timestamp: Annotated[
        int | None, Field(description="Epoch milliseconds.")
    ] = None,
    results_per_page: Annotated[int, Field(description="Capped at 1000.")] = 100,
    page: Annotated[int, Field(description="Zero-based page index.")] = 0,
    rule_ids: Annotated[
        list[str] | str | None,
        Field(
            description="Rule ids, as a list or a JSON array. Every rule when omitted."
        ),
    ] = None,
) -> str:
    """Trace how a dataset's rule outcomes changed over time."""
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
        for key in ("min_timestamp", "max_timestamp", "rule_ids"):
            if is_empty(result[key]):
                del result[key]
        return result

    return compact_json(await run_blocking(_run))

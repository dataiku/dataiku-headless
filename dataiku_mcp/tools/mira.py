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

"""Complete access to the fixed MIRA public API surface."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import compact_json
from .utils.validation import require_non_empty_string


@dataclass(frozen=True)
class MiraOperation:
    method: str
    path: str
    domain: str
    description: str
    query_params: tuple[str, ...] = ()
    body: str = "none"  # none, optional, required, multipart
    response: str = "json"  # json, binary


def _op(
    method: str,
    path: str,
    domain: str,
    description: str,
    *,
    query_params: tuple[str, ...] = (),
    body: str = "none",
    response: str = "json",
) -> MiraOperation:
    return MiraOperation(
        method, path, domain, description, query_params, body, response
    )


# This catalog mirrors the public controllers under
# com.dataiku.dip.server.api.mira. Operation ids are stable agent-facing names;
# paths are never accepted from callers, preventing endpoint guessing or access
# outside MIRA.
MIRA_OPERATIONS: dict[str, MiraOperation] = {
    # Infrastructure
    "list_infras": _op(
        "GET", "/dam/infras", "infrastructures", "List readable infrastructures."
    ),
    "get_infra": _op(
        "GET",
        "/dam/infras/{infra_id}",
        "infrastructures",
        "Get infrastructure status.",
    ),
    "get_infra_settings": _op(
        "GET",
        "/dam/infras/{infra_id}/settings",
        "infrastructures",
        "Get infrastructure settings and revision.",
    ),
    "create_infra": _op(
        "POST",
        "/dam/infras",
        "infrastructures",
        "Create an infrastructure.",
        body="required",
    ),
    "update_infra_settings": _op(
        "PUT",
        "/dam/infras/{infra_id}/settings",
        "infrastructures",
        "Update infrastructure settings using the current revision.",
        body="required",
    ),
    "delete_infra": _op(
        "DELETE",
        "/dam/infras/{infra_id}",
        "infrastructures",
        "Delete an infrastructure.",
        query_params=("force",),
    ),
    # Agents
    "search_mira_agents": _op(
        "POST",
        "/dam/agents/search",
        "agents",
        "Search readable agents and return contextual facet counts.",
        body="required",
    ),
    "get_mira_agent": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}",
        "agents",
        "Get an agent summary.",
    ),
    "generate_agent_briefing": _op(
        "POST",
        "/dam/infras/{infra_id}/agents/{agent_id}/insights/briefing",
        "agents",
        "Generate and persist an agent briefing.",
    ),
    "get_mira_agent_status": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/status",
        "agents",
        "Get detailed agent status.",
    ),
    "get_mira_agent_settings": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/settings",
        "agents",
        "Get agent settings and revision.",
    ),
    "create_mira_agent": _op(
        "POST",
        "/dam/infras/{infra_id}/agents",
        "agents",
        "Create an agent.",
        body="required",
    ),
    "update_mira_agent_settings": _op(
        "PUT",
        "/dam/infras/{infra_id}/agents/{agent_id}/settings",
        "agents",
        "Update agent settings using the current revision.",
        body="required",
    ),
    "delete_mira_agent": _op(
        "DELETE",
        "/dam/infras/{infra_id}/agents/{agent_id}",
        "agents",
        "Delete an agent.",
    ),
    "get_mira_agent_history": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/history",
        "agents",
        "Get filtered agent history.",
        query_params=("from", "to", "fieldQuery"),
    ),
    "get_mira_agent_metrics": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/metrics",
        "agents",
        "Get performance, topic, or risk metrics.",
        query_params=("family", "timezone"),
    ),
    "get_mira_agent_uptime_results": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/uptime-results",
        "agents",
        "Get uptime-test results.",
        query_params=("from", "to"),
    ),
    "get_mira_agent_topic_modeling": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/topic-modeling",
        "agents",
        "Get topic-modeling results.",
        query_params=("periodicity",),
    ),
    "create_external_agent": _op(
        "POST",
        "/dam/infras/{infra_id}/agents/{agent_id}/actions/create-external-agent",
        "agents",
        "Create the external platform agent represented by a MIRA agent.",
        body="required",
    ),
    # Long-running operations
    "scan_infra": _op(
        "POST",
        "/dam/infras/{infra_id}/actions/scan",
        "operations",
        "Start an infrastructure scan.",
    ),
    "run_infra_uptime_tests": _op(
        "POST",
        "/dam/infras/{infra_id}/actions/run-uptime-tests",
        "operations",
        "Run uptime tests for all or selected agents.",
        body="optional",
    ),
    "fetch_agent_logs": _op(
        "POST",
        "/dam/infras/{infra_id}/agents/{agent_id}/actions/fetch-logs",
        "operations",
        "Queue an agent log fetch.",
    ),
    "validate_agent_log_fetch": _op(
        "POST",
        "/dam/infras/{infra_id}/agents/{agent_id}/log-fetch/actions/validate",
        "operations",
        "Validate the agent's stored or supplied log-fetch configuration.",
        body="optional",
    ),
    "fetch_agent_operational_metrics": _op(
        "POST",
        "/dam/infras/{infra_id}/agents/{agent_id}/actions/fetch-platform-operational-metrics",
        "operations",
        "Queue platform operational-metrics ingestion.",
    ),
    "setup_agent_log_fetch_dataset": _op(
        "POST",
        "/dam/infras/{infra_id}/agents/{agent_id}/actions/setup-log-fetch-dataset",
        "operations",
        "Create or configure the managed log-fetch dataset.",
        body="required",
    ),
    "search_mira_operations": _op(
        "POST",
        "/dam/operations/search",
        "operations",
        "Search readable operations across infrastructures and agents.",
        body="required",
    ),
    "get_agent_operation": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/operations/{operation_id}",
        "operations",
        "Get agent operation status.",
    ),
    "get_agent_operation_result": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/operations/{operation_id}/result",
        "operations",
        "Get a completed agent operation result.",
    ),
    "abort_agent_operation": _op(
        "POST",
        "/dam/infras/{infra_id}/agents/{agent_id}/operations/{operation_id}/actions/abort",
        "operations",
        "Abort an agent operation.",
    ),
    "get_infra_operation": _op(
        "GET",
        "/dam/infras/{infra_id}/operations/{operation_id}",
        "operations",
        "Get infrastructure operation status.",
    ),
    "get_infra_operation_result": _op(
        "GET",
        "/dam/infras/{infra_id}/operations/{operation_id}/result",
        "operations",
        "Get a completed infrastructure operation result.",
    ),
    "abort_infra_operation": _op(
        "POST",
        "/dam/infras/{infra_id}/operations/{operation_id}/actions/abort",
        "operations",
        "Abort an infrastructure operation.",
    ),
    # Risk
    "get_risk_exposure": _op(
        "GET", "/dam/risk-exposure", "risk", "Get portfolio risk exposure."
    ),
    "get_risk_taxonomy": _op(
        "GET",
        "/dam/risk-taxonomy",
        "risk",
        "Get the active risk taxonomy and revision.",
    ),
    "get_default_risk_taxonomy": _op(
        "GET", "/dam/risk-taxonomy/default", "risk", "Get the default risk taxonomy."
    ),
    "compute_risk_taxonomy_replacement_impact": _op(
        "POST",
        "/dam/risk-taxonomy/actions/compute-replacement-impact",
        "risk",
        "Compute impact before replacing the risk taxonomy.",
        body="required",
    ),
    "update_risk_taxonomy": _op(
        "PUT",
        "/dam/risk-taxonomy",
        "risk",
        "Replace the risk taxonomy after reviewing impact.",
        body="required",
    ),
    "get_agent_risk_assessment": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/risk-assessment",
        "risk",
        "Get an agent risk assessment and revision.",
    ),
    "update_agent_risk_assessment": _op(
        "PUT",
        "/dam/infras/{infra_id}/agents/{agent_id}/risk-assessment",
        "risk",
        "Update an assessment and optionally upload evidence documents.",
        body="multipart",
    ),
    "sign_off_agent_risk_assessment": _op(
        "POST",
        "/dam/infras/{infra_id}/agents/{agent_id}/risk-assessment/sign-off",
        "risk",
        "Sign off an agent risk assessment.",
    ),
    "remove_agent_risk_sign_off": _op(
        "DELETE",
        "/dam/infras/{infra_id}/agents/{agent_id}/risk-assessment/sign-off",
        "risk",
        "Remove risk-assessment sign-off.",
    ),
    "download_agent_risk_evidence": _op(
        "GET",
        "/dam/infras/{infra_id}/agents/{agent_id}/risk-assessment/evidences/{evidence_id}/content",
        "risk",
        "Download a risk-evidence document.",
        response="binary",
    ),
    # Global settings, KPIs, and topic families
    "get_mira_settings": _op(
        "GET", "/dam/settings", "settings", "Get global MIRA settings and revision."
    ),
    "update_mira_settings": _op(
        "PUT",
        "/dam/settings",
        "settings",
        "Update global MIRA settings using the current revision.",
        body="required",
    ),
    "list_business_kpis": _op(
        "GET",
        "/dam/settings/business-kpis",
        "settings",
        "List business KPI definitions.",
    ),
    "get_business_kpi": _op(
        "GET",
        "/dam/settings/business-kpis/{kpi_id}",
        "settings",
        "Get a business KPI definition.",
    ),
    "create_business_kpi": _op(
        "POST",
        "/dam/settings/business-kpis",
        "settings",
        "Create a business KPI definition.",
        body="required",
    ),
    "update_business_kpi": _op(
        "PUT",
        "/dam/settings/business-kpis/{kpi_id}",
        "settings",
        "Update a business KPI definition.",
        body="required",
    ),
    "delete_business_kpi": _op(
        "DELETE",
        "/dam/settings/business-kpis/{kpi_id}",
        "settings",
        "Delete an unused business KPI definition.",
    ),
    "list_topic_families": _op(
        "GET",
        "/dam/settings/topic-families",
        "settings",
        "List topic-modeling families.",
    ),
    "get_topic_family": _op(
        "GET",
        "/dam/settings/topic-families/{family_id}",
        "settings",
        "Get a topic-modeling family.",
    ),
    "create_topic_family": _op(
        "POST",
        "/dam/settings/topic-families",
        "settings",
        "Create a topic-modeling family.",
        body="required",
    ),
    "update_topic_family": _op(
        "PUT",
        "/dam/settings/topic-families/{family_id}",
        "settings",
        "Update a topic-modeling family.",
        body="required",
    ),
    "delete_topic_family": _op(
        "DELETE",
        "/dam/settings/topic-families/{family_id}",
        "settings",
        "Delete an unused topic-modeling family.",
    ),
    # Tags
    "list_mira_tags": _op(
        "GET", "/dam/tags", "tags", "List visible MIRA tag definitions."
    ),
    "update_mira_tag": _op(
        "PUT",
        "/dam/tags/{tag_name}",
        "tags",
        "Create or update a tag color.",
        body="required",
    ),
    "rename_mira_tag": _op(
        "POST",
        "/dam/tags/{tag_name}/actions/rename",
        "tags",
        "Rename a tag everywhere.",
        body="required",
    ),
    "delete_mira_tag": _op(
        "DELETE", "/dam/tags/{tag_name}", "tags", "Delete a tag everywhere."
    ),
}

_PATH_PARAM = re.compile(r"{([a-z_]+)}")
_DOMAINS = frozenset(operation.domain for operation in MIRA_OPERATIONS.values())


def _operation_summary(operation_id: str, operation: MiraOperation) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "method": operation.method,
        "path": operation.path,
        "domain": operation.domain,
        "description": operation.description,
        "path_params": _PATH_PARAM.findall(operation.path),
        "query_params": list(operation.query_params),
        "body": operation.body,
        "response": operation.response,
    }


def _resolve_path(operation: MiraOperation, path_params: dict[str, str]) -> str:
    required = set(_PATH_PARAM.findall(operation.path))
    supplied = set(path_params)
    missing = sorted(required - supplied)
    unexpected = sorted(supplied - required)
    if missing:
        raise ValueError(f"Missing path parameters: {missing}")
    if unexpected:
        raise ValueError(f"Unexpected path parameters: {unexpected}")
    path = operation.path
    for name in required:
        value = require_non_empty_string(path_params[name], f"path_params.{name}")
        path = path.replace("{" + name + "}", quote(value, safe=""))
    return path


def _validate_query(operation: MiraOperation, query_params: dict[str, Any]) -> None:
    unexpected = sorted(set(query_params) - set(operation.query_params))
    if unexpected:
        raise ValueError(
            f"Unexpected query parameters for this operation: {unexpected}. "
            f"Allowed: {list(operation.query_params)}"
        )


def _validate_payload(
    operation: MiraOperation,
    body: Any,
    form_params: dict[str, Any],
    file_paths: list[str],
) -> None:
    if operation.body == "required" and body is None:
        raise ValueError("This operation requires a JSON body")
    if operation.body in {"none", "multipart"} and body is not None:
        raise ValueError("This operation does not accept a JSON body")
    if operation.body != "multipart" and (form_params or file_paths):
        raise ValueError(
            "Form parameters and files are only valid for multipart operations"
        )
    if operation.body == "multipart":
        if not form_params.get("assessment"):
            raise ValueError(
                "Multipart risk-assessment updates require form_params.assessment"
            )
        evidence_ids = form_params.get("documentEvidenceIds") or []
        if isinstance(evidence_ids, str):
            evidence_ids = [evidence_ids]
        if len(evidence_ids) != len(file_paths):
            raise ValueError(
                "documentEvidenceIds and file_paths must have the same length"
            )


def _download_binary(
    client, path: str, query_params: dict[str, Any], output_path: str, overwrite: bool
) -> dict[str, Any]:
    absolute_path = os.path.realpath(os.path.expanduser(output_path))
    parent = os.path.dirname(absolute_path)
    if not os.path.isdir(parent):
        raise FileNotFoundError(f"Destination directory does not exist: {parent}")
    if os.path.lexists(absolute_path) and not overwrite:
        raise FileExistsError(
            f"Destination already exists: {absolute_path}. Set overwrite=true to replace it."
        )
    response = client._perform_raw("GET", path, params=query_params or None)
    temporary_path = None
    digest = hashlib.sha256()
    size = 0
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".mira-evidence-", suffix=".tmp", dir=parent, delete=False
        ) as handle:
            temporary_path = handle.name
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if os.path.lexists(absolute_path) and not overwrite:
            raise FileExistsError(
                f"Destination already exists: {absolute_path}. Set overwrite=true to replace it."
            )
        os.replace(temporary_path, absolute_path)
        temporary_path = None
    finally:
        response.close()
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
    return {
        "output_path": absolute_path,
        "size_bytes": size,
        "sha256": digest.hexdigest(),
        "content_type": response.headers.get("Content-Type"),
        "content_disposition": response.headers.get("Content-Disposition"),
    }


@mcp.tool(
    title="Get MIRA API Capabilities",
    description="Discover supported MIRA operations and their required inputs before calling one.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_mira_api_capabilities(ctx: Context, domain: str = "") -> str:
    """List every supported MIRA public API operation and its input shape.

    Args:
        domain: Optional domain filter: infrastructures, agents, operations, risk,
            settings, or tags. Leave empty to return the complete catalog.
    """
    domain = domain.strip()
    if domain and domain not in _DOMAINS:
        raise ValueError(
            f"Unknown MIRA domain '{domain}'. Available: {sorted(_DOMAINS)}"
        )
    await ctx.info("Loading the MIRA public API operation catalog...")
    operations = [
        _operation_summary(operation_id, operation)
        for operation_id, operation in MIRA_OPERATIONS.items()
        if not domain or operation.domain == domain
    ]
    return compact_json({"count": len(operations), "operations": operations})


@mcp.tool(
    title="Call MIRA API",
    description="Execute one fixed-catalog MIRA operation after discovering its input shape.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    },
)
async def call_mira_api(
    operation_id: str,
    ctx: Context,
    path_params: dict[str, str] | None = None,
    query_params: dict[str, Any] | None = None,
    body: Any = None,
    form_params: dict[str, Any] | None = None,
    file_paths: list[str] | None = None,
    output_path: str = "",
    overwrite: bool = False,
) -> str:
    """Execute a named operation from ``get_mira_api_capabilities``.

    Paths and HTTP methods come from the fixed catalog. JSON operations use
    ``body``. The risk-assessment update uses ``form_params`` plus matching
    ``documentEvidenceIds`` and ``file_paths``. Binary evidence downloads require
    ``output_path`` and never overwrite unless ``overwrite`` is true.
    """
    operation_id = require_non_empty_string(operation_id, "operation_id")
    try:
        operation = MIRA_OPERATIONS[operation_id]
    except KeyError:
        raise ValueError(
            f"Unknown MIRA operation '{operation_id}'. Call get_mira_api_capabilities first."
        ) from None
    path_params = dict(path_params or {})
    query_params = dict(query_params or {})
    form_params = dict(form_params or {})
    file_paths = list(file_paths or [])
    path = _resolve_path(operation, path_params)
    _validate_query(operation, query_params)
    _validate_payload(operation, body, form_params, file_paths)
    if operation.response == "binary":
        output_path = require_non_empty_string(output_path, "output_path")
    elif output_path:
        raise ValueError("output_path is only valid for binary download operations")

    await ctx.info(f"Calling MIRA operation '{operation_id}'...")

    def _run():
        client = get_dss_client()
        if operation.response == "binary":
            return _download_binary(client, path, query_params, output_path, overwrite)
        if operation.body == "multipart":
            handles = []
            files = []
            try:
                for local_path in file_paths:
                    absolute_path = os.path.realpath(os.path.expanduser(local_path))
                    handle = open(absolute_path, "rb")
                    handles.append(handle)
                    files.append(
                        ("documents", (os.path.basename(absolute_path), handle))
                    )
                return client._perform_json(
                    operation.method,
                    path,
                    params=query_params or None,
                    files=files or None,
                    raw_body=form_params,
                )
            finally:
                for handle in handles:
                    handle.close()
        return client._perform_json(
            operation.method,
            path,
            params=query_params or None,
            body=body,
        )

    result = await run_blocking(_run)
    return compact_json(result)

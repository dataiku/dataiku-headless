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

"""Agent Management adapters using only public dataiku-api-client methods."""

from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Annotated, Any, Callable, Literal

from dataikuapi.agentmanagement.agent import AgentFilter
from dataikuapi.utils import DataikuException
from pydantic import Field, StringConstraints, model_validator
from requests import RequestException

from ..auth import get_dss_client
from ..executors import run_blocking
from ..operation_registry import OperationArguments
from .utils.serialization import compact_json
from .utils.redaction import redact_sensitive_data
from .utils.validation import PathSegment

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveLimit = Annotated[int, Field(ge=1, le=10000)]
Definition = Annotated[
    dict[str, Any],
    Field(
        description="Backend-defined settings. Inspect current definitions and preserve unrelated fields."
    ),
]


class AgentSelection(OperationArguments):
    text_filter: NonEmpty | None = None
    agent_ids: list[PathSegment] | None = None
    scope_ids: list[NonEmpty] | None = None
    platform_types: list[NonEmpty] | None = None
    platform_ids: list[PathSegment] | None = None
    discovery_statuses: list[NonEmpty] | None = None
    risk_sign_offs: list[NonEmpty] | None = None
    tags: list[NonEmpty] | None = None
    states: list[NonEmpty] | None = None
    favorites: bool | None = None

    @model_validator(mode="after")
    def nonempty_criteria(self):
        for name in self.model_fields_set:
            if getattr(self, name) == []:
                raise ValueError("Filter lists must not be empty")
        return self

    def to_sdk(self):
        selection = AgentFilter()
        for name, value in self.model_dump(exclude_none=True).items():
            # Each mapping is a declared public AgentFilter builder method.
            method = getattr(selection, "with_" + name)
            method(*value) if isinstance(value, list) else method(value)
        return selection

    def is_filtered(self):
        return bool(self.model_dump(exclude_none=True))


class AlertEvaluationArguments(OperationArguments):
    agent_filter: AgentSelection | None = None
    scope: Literal["filtered", "all_writable_agents"] = "filtered"
    mode: Literal["DUE", "FORCE_LATEST", "FORCE_CATCH_UP"] = "DUE"

    @model_validator(mode="after")
    def explicit_scope(self):
        if (
            not (self.agent_filter and self.agent_filter.is_filtered())
            and self.scope != "all_writable_agents"
        ):
            raise ValueError("An empty filter requires scope=all_writable_agents")
        return self


@dataclass(frozen=True)
class AgentManagementOperation:
    handler: Callable
    domain: str
    effect: str
    example: dict
    destructive: bool = False
    local_file_fields: tuple[str, ...] = ()


AGENT_MANAGEMENT_OPERATIONS: dict[str, AgentManagementOperation] = {}


def _register(
    domain, effect="read", *, example=None, destructive=False, local_file_fields=()
):
    def register(handler):
        AGENT_MANAGEMENT_OPERATIONS[handler.__name__] = AgentManagementOperation(
            handler, domain, effect, example or {}, destructive, local_file_fields
        )
        return handler

    return register


def _selection(value):
    return value.to_sdk() if value is not None else None


def _agent(client, platform_id, agent_id):
    return client.get_agent(platform_id, agent_id)


def _started(operation):
    return {
        "platform_id": operation.platform_id,
        "agent_id": operation.agent_id,
        "operation_id": operation.id,
    }


def _save_settings(settings, changes, expected_revision):
    raw = settings.get_raw() if hasattr(settings, "get_raw") else settings.raw
    if not changes or "fetchedRevision" in changes:
        raise ValueError("Supply setting changes separately from expected_revision")
    # Patch named top-level fields of the freshly fetched definition, retaining
    # hidden credentials and unrelated configuration. Nested values are replacements.
    raw.update(changes)
    raw["fetchedRevision"] = expected_revision
    return settings


@_register("platforms")
def list_platforms(client):
    """List readable Agent Management platforms."""
    return [dict(item) for item in client.list_platforms()]


@_register("platforms", example={"platform_id": "discovered-platform"})
def get_platform(client, platform_id: PathSegment):
    """Read platform status."""
    return client.get_platform(platform_id).get_status().get_raw()


@_register("platforms", example={"platform_id": "discovered-platform"})
def get_platform_settings(client, platform_id: PathSegment):
    """Read platform settings and fetchedRevision."""
    return client.get_platform(platform_id).get_settings().raw


@_register(
    "platforms",
    "write",
    example={
        "platform_id": "requested-platform",
        "platform_type": "type-from-product",
        "display_name": "Requested platform",
    },
)
def create_platform(
    client,
    platform_id: PathSegment,
    platform_type: NonEmpty,
    display_name: NonEmpty,
    connection_name: NonEmpty | None = None,
    default_project_key: NonEmpty | None = None,
    permissions: list[Definition] | None = None,
    default_agent_permissions: list[Definition] | None = None,
):
    """Create an Agent Management platform with the public SDK."""
    platform = client.create_platform(
        platform_id,
        platform_type,
        display_name,
        connection_name=connection_name,
        default_project_key=default_project_key,
        permissions=permissions,
        default_agent_permissions=default_agent_permissions,
    )
    return {"platform_id": platform.id}


@_register(
    "platforms",
    "write",
    destructive=True,
    example={
        "platform_id": "discovered-platform",
        "changes": {"displayName": "Requested name"},
        "expected_revision": "revision-from-read",
    },
)
def update_platform_settings(
    client, platform_id: PathSegment, changes: Definition, expected_revision: NonEmpty
):
    """Replace named top-level platform settings fields, checking the inspected revision."""
    settings = _save_settings(
        client.get_platform(platform_id).get_settings(), changes, expected_revision
    )
    return settings.save().raw


@_register(
    "platforms",
    "write",
    destructive=True,
    example={"platform_id": "discovered-platform"},
)
def delete_platform(
    client,
    platform_id: PathSegment,
    allow_deletion_if_platform_contains_agents: bool = False,
):
    """Delete a platform, optionally including discovered or managed agents."""
    client.get_platform(platform_id).delete(
        allow_deletion_if_platform_contains_agents=allow_deletion_if_platform_contains_agents
    )
    return {"deleted": platform_id}


@_register("agents")
def search_agents(client, agent_filter: AgentSelection | None = None):
    """Search readable agents and contextual facet counts with typed SDK filters."""
    return client.search_agents(agent_filter=_selection(agent_filter))


@_register(
    "agents",
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def get_agent(client, platform_id: PathSegment, agent_id: PathSegment):
    """Read an agent summary using the public status accessor."""
    return _agent(client, platform_id, agent_id).get_status().get_light()


@_register(
    "agents",
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def get_agent_status(client, platform_id: PathSegment, agent_id: PathSegment):
    """Read full agent status using the public SDK."""
    return _agent(client, platform_id, agent_id).get_status().get_heavy()


@_register(
    "agents",
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def get_agent_settings(client, platform_id: PathSegment, agent_id: PathSegment):
    """Read agent settings and fetchedRevision."""
    return _agent(client, platform_id, agent_id).get_settings().get_raw()


@_register(
    "agents",
    "write",
    example={"platform_id": "discovered-platform", "agent_id": "requested-agent"},
)
def create_agent(
    client,
    platform_id: PathSegment,
    agent_id: PathSegment,
    display_name: str | None = None,
    description: str | None = None,
    tags: list[NonEmpty] | None = None,
    configuration: Definition | None = None,
    permissions: list[Definition] | None = None,
    agent_owner: Definition | None = None,
):
    """Create a monitored Agent Management record; remote discovery is usually preferred."""
    agent = client.get_platform(platform_id).create_agent(
        agent_id,
        display_name=display_name,
        description=description,
        tags=tags,
        configuration=configuration,
        permissions=permissions,
        agent_owner=agent_owner,
    )
    return {"platform_id": platform_id, "agent_id": agent.id}


@_register(
    "agents",
    "write",
    destructive=True,
    example={
        "platform_id": "discovered-platform",
        "agent_id": "discovered-agent",
        "changes": {"displayName": "Requested name"},
        "expected_revision": "revision-from-read",
    },
)
def update_agent_settings(
    client,
    platform_id: PathSegment,
    agent_id: PathSegment,
    changes: Definition,
    expected_revision: NonEmpty,
):
    """Replace named top-level agent settings fields using the inspected revision."""
    return (
        _save_settings(
            _agent(client, platform_id, agent_id).get_settings(),
            changes,
            expected_revision,
        )
        .save()
        .get_raw()
    )


@_register(
    "agents",
    "write",
    destructive=True,
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def delete_agent(client, platform_id: PathSegment, agent_id: PathSegment):
    """Delete a monitored agent record."""
    _agent(client, platform_id, agent_id).delete()
    return {"deleted": agent_id, "platform_id": platform_id}


@_register(
    "metrics",
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def get_agent_uptime_results(
    client,
    platform_id: PathSegment,
    agent_id: PathSegment,
    from_time: int | None = None,
    to_time: int | None = None,
):
    """Read uptime results within optional epoch-millisecond bounds."""
    return _agent(client, platform_id, agent_id).get_uptime_results(
        from_time=from_time, to_time=to_time
    )


@_register("metrics")
def get_available_metric_ids(client, agent_filter: AgentSelection | None = None):
    """Discover qualified metric IDs supported by readable agents."""
    return client.get_available_metric_ids(agent_filter=_selection(agent_filter))


@_register(
    "metrics", example={"metrics": ["qualified-metric-from-read"], "latest_only": True}
)
def get_metric_time_series(
    client,
    metrics: Annotated[list[NonEmpty], Field(min_length=1)],
    agent_filter: AgentSelection | None = None,
    from_time: int | None = None,
    to_time: int | None = None,
    latest_only: bool = False,
):
    """Read stored metric time series; discover qualified metric IDs first."""
    return client.get_metric_time_series(
        metrics,
        agent_filter=_selection(agent_filter),
        from_time=from_time,
        to_time=to_time,
        latest_only=latest_only,
    )


@_register(
    "metrics",
    example={
        "metrics": ["qualified-metric-from-read"],
        "bucket": "DAY",
        "from_time": 0,
        "to_time": 86400000,
    },
)
def get_metric_buckets(
    client,
    metrics: Annotated[list[NonEmpty], Field(min_length=1)],
    bucket: Literal["HOUR", "DAY", "WEEK", "MONTH"],
    from_time: int,
    agent_filter: AgentSelection | None = None,
    to_time: int | None = None,
):
    """Read bucketed metric values using qualified IDs and epoch-millisecond bounds."""
    result = client.get_metric_buckets(
        metrics,
        bucket,
        agent_filter=_selection(agent_filter),
        from_time=from_time,
        to_time=to_time,
    )
    return [
        series
        for platform, agent in result.agents()
        for series in result.raw_agent_data(platform, agent)
    ]


@_register(
    "operations", "write", destructive=True, example={"scope": "all_writable_agents"}
)
def evaluate_alerts(
    client,
    agent_filter: AgentSelection | None = None,
    scope: Literal["filtered", "all_writable_agents"] = "filtered",
    mode: Literal["DUE", "FORCE_LATEST", "FORCE_CATCH_UP"] = "DUE",
):
    """Queue native alert evaluation; forcing correction can invalidate historical alerts."""
    if (
        not (agent_filter and agent_filter.is_filtered())
        and scope != "all_writable_agents"
    ):
        raise ValueError("An empty filter requires scope=all_writable_agents")
    return {
        "queued_agent_count": client.evaluate_alerts(
            agent_filter=_selection(agent_filter), mode=mode
        )
    }


@_register("operations", "write", example={"platform_id": "discovered-platform"})
def scan_platform(client, platform_id: PathSegment):
    """Start platform discovery and return the operation identity for polling."""
    return _started(client.get_platform(platform_id).start_scan())


@_register("operations", "write", example={"platform_id": "discovered-platform"})
def run_platform_uptime_tests(
    client,
    platform_id: PathSegment,
    agent_ids: Annotated[list[PathSegment], Field(min_length=1)] | None = None,
):
    """Start uptime tests for selected agents or all eligible agents on a platform."""
    return _started(
        client.get_platform(platform_id).start_run_uptime_tests(agent_ids=agent_ids)
    )


@_register(
    "operations",
    "write",
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def fetch_agent_logs(client, platform_id: PathSegment, agent_id: PathSegment):
    """Queue agent log ingestion and return the operation identity."""
    return _started(_agent(client, platform_id, agent_id).start_fetch_logs())


@_register(
    "operations",
    "write",
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def fetch_agent_operational_metrics(
    client, platform_id: PathSegment, agent_id: PathSegment
):
    """Queue operational metric ingestion and return the operation identity."""
    return _started(
        _agent(client, platform_id, agent_id).start_fetch_platform_operational_metrics()
    )


@_register(
    "operations",
    "write",
    destructive=True,
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def setup_agent_monitoring(
    client,
    platform_id: PathSegment,
    agent_id: PathSegment,
    run_first_fetch: bool = True,
    include_in_uptime_tests: bool = True,
    project_key: NonEmpty | None = None,
    connection_name: NonEmpty | None = None,
    partitioning: Literal["NONE", "DAY"] | None = None,
):
    """Provision monitoring resources and enable supported ingestion and uptime capabilities."""
    options = {
        key: value
        for key, value in dict(
            project_key=project_key,
            connection_name=connection_name,
            partitioning=partitioning,
        ).items()
        if value is not None
    }
    return _agent(client, platform_id, agent_id).setup_monitoring(
        run_first_fetch=run_first_fetch,
        include_in_uptime_tests=include_in_uptime_tests,
        **options,
    )


@_register("operations")
def search_operations(
    client,
    agent_filter: AgentSelection | None = None,
    operation_types: list[NonEmpty] | None = None,
    statuses: list[NonEmpty] | None = None,
    triggers: list[NonEmpty] | None = None,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    limit: PositiveLimit | None = None,
    current_only: bool = False,
):
    """Search bounded operation history and report whether narrower filters are needed."""
    result = client.list_operations(
        agent_filter=_selection(agent_filter),
        operation_types=operation_types,
        statuses=statuses,
        triggers=triggers,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        limit=limit,
        current_only=current_only,
    )
    return {
        "operations": [dict(item) for item in result.operations],
        "has_more": result.has_more,
    }


@_register(
    "operations",
    example={
        "platform_id": "discovered-platform",
        "agent_id": "discovered-agent",
        "operation_id": "returned-operation",
    },
)
def get_agent_operation(
    client, platform_id: PathSegment, agent_id: PathSegment, operation_id: PathSegment
):
    """Read one agent operation status without waiting."""
    return (
        _agent(client, platform_id, agent_id)
        .get_operation(operation_id)
        .get_status()
        .get_raw()
    )


@_register(
    "operations",
    example={
        "platform_id": "discovered-platform",
        "agent_id": "discovered-agent",
        "operation_id": "returned-operation",
    },
)
def get_agent_operation_result(
    client, platform_id: PathSegment, agent_id: PathSegment, operation_id: PathSegment
):
    """Read a completed agent operation result."""
    return (
        _agent(client, platform_id, agent_id).get_operation(operation_id).get_result()
    )


@_register(
    "operations",
    "write",
    destructive=True,
    example={
        "platform_id": "discovered-platform",
        "agent_id": "discovered-agent",
        "operation_id": "returned-operation",
    },
)
def abort_agent_operation(
    client, platform_id: PathSegment, agent_id: PathSegment, operation_id: PathSegment
):
    """Request cancellation of an agent operation."""
    _agent(client, platform_id, agent_id).get_operation(operation_id).abort()
    return {"abort_requested": operation_id}


@_register(
    "operations",
    example={
        "platform_id": "discovered-platform",
        "operation_id": "returned-operation",
    },
)
def get_platform_operation(client, platform_id: PathSegment, operation_id: PathSegment):
    """Read one platform operation status without waiting."""
    return (
        client.get_platform(platform_id)
        .get_operation(operation_id)
        .get_status()
        .get_raw()
    )


@_register(
    "operations",
    example={
        "platform_id": "discovered-platform",
        "operation_id": "returned-operation",
    },
)
def get_platform_operation_result(
    client, platform_id: PathSegment, operation_id: PathSegment
):
    """Read a completed platform operation result."""
    return client.get_platform(platform_id).get_operation(operation_id).get_result()


@_register(
    "operations",
    "write",
    destructive=True,
    example={
        "platform_id": "discovered-platform",
        "operation_id": "returned-operation",
    },
)
def abort_platform_operation(
    client, platform_id: PathSegment, operation_id: PathSegment
):
    """Request cancellation of a platform operation."""
    client.get_platform(platform_id).get_operation(operation_id).abort()
    return {"abort_requested": operation_id}


@_register("risk")
def get_risk_exposure(client):
    """Read portfolio risk exposure."""
    return client.get_risk_exposure().raw


@_register("risk")
def get_risk_taxonomy(client):
    """Read risk taxonomy and fetchedRevision."""
    return client.get_risk_taxonomy().get_raw()


@_register("risk")
def get_default_risk_taxonomy(client):
    """Read the default risk taxonomy."""
    return client.get_default_risk_taxonomy().get_raw()


@_register("risk", example={"taxonomy": {}})
def compute_risk_taxonomy_replacement_impact(client, taxonomy: Definition):
    """Compute replacement impact for a proposed taxonomy without saving it."""
    settings = client.get_risk_taxonomy()
    settings.raw["taxonomy"] = taxonomy
    return settings.compute_replacement_impact()


@_register(
    "risk",
    "write",
    destructive=True,
    example={
        "taxonomy": {},
        "expected_revision": "revision-from-read",
        "impact": {"fingerprint": "fingerprint-from-impact"},
    },
)
def update_risk_taxonomy(
    client, taxonomy: Definition, expected_revision: NonEmpty, impact: Definition
):
    """Save a proposed taxonomy with the inspected revision and reviewed impact fingerprint."""
    settings = client.get_risk_taxonomy()
    settings.raw.update(taxonomy=taxonomy, fetchedRevision=expected_revision)
    return settings.save(impact).get_raw()


@_register(
    "risk",
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def get_agent_risk_assessment(client, platform_id: PathSegment, agent_id: PathSegment):
    """Read agent risk assessment and fetchedRevision."""
    return _agent(client, platform_id, agent_id).get_risk_assessment().get_raw()


@_register(
    "risk",
    "write",
    destructive=True,
    local_file_fields=("documents",),
    example={
        "platform_id": "discovered-platform",
        "agent_id": "discovered-agent",
        "assessment": {},
        "expected_revision": "revision-from-read",
    },
)
def update_agent_risk_assessment(
    client,
    platform_id: PathSegment,
    agent_id: PathSegment,
    assessment: Definition,
    expected_revision: NonEmpty,
    documents: dict[PathSegment, NonEmpty] | None = None,
):
    """Save an assessment with its inspected revision and optional evidence-ID to local-path mapping."""
    settings = _agent(client, platform_id, agent_id).get_risk_assessment()
    settings.raw.update(assessment=assessment, fetchedRevision=expected_revision)
    with ExitStack() as stack:
        uploads = {
            key: (
                os.path.basename(path),
                stack.enter_context(
                    open(os.path.realpath(os.path.expanduser(path)), "rb")
                ),
            )
            for key, path in (documents or {}).items()
        }
        return settings.save(documents=uploads or None).get_raw()


@_register(
    "risk",
    "write",
    destructive=True,
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def sign_off_agent_risk_assessment(
    client, platform_id: PathSegment, agent_id: PathSegment
):
    """Sign off the current agent risk assessment."""
    return (
        _agent(client, platform_id, agent_id)
        .set_risk_assessment_signed_off(True)
        .get_raw()
    )


@_register(
    "risk",
    "write",
    destructive=True,
    example={"platform_id": "discovered-platform", "agent_id": "discovered-agent"},
)
def remove_agent_risk_sign_off(client, platform_id: PathSegment, agent_id: PathSegment):
    """Remove current agent risk-assessment sign-off."""
    return (
        _agent(client, platform_id, agent_id)
        .set_risk_assessment_signed_off(False)
        .get_raw()
    )


def _download_binary(response, output_path, overwrite):
    absolute_path = os.path.realpath(os.path.expanduser(output_path))
    parent = os.path.dirname(absolute_path)
    temporary_path = None
    digest = hashlib.sha256()
    size = 0
    try:
        if not os.path.isdir(parent):
            raise FileNotFoundError("Destination directory does not exist")
        if os.path.lexists(absolute_path) and not overwrite:
            raise FileExistsError(
                "Destination exists; use overwrite=true to replace it"
            )
        with tempfile.NamedTemporaryFile(
            prefix=".agent-management-evidence-", dir=parent, delete=False
        ) as handle:
            temporary_path = handle.name
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        if overwrite:
            os.replace(temporary_path, absolute_path)
        else:
            os.link(temporary_path, absolute_path)
            os.unlink(temporary_path)
        temporary_path = None
    finally:
        response.close()
        if temporary_path is not None:
            os.unlink(temporary_path)
    return {
        "output_path": absolute_path,
        "size_bytes": size,
        "sha256": digest.hexdigest(),
        "content_type": response.headers.get("Content-Type"),
    }


@_register(
    "risk",
    "write",
    destructive=True,
    local_file_fields=("output_path",),
    example={
        "platform_id": "discovered-platform",
        "agent_id": "discovered-agent",
        "evidence_id": "discovered-evidence",
        "output_path": "/absolute/path/evidence.bin",
    },
)
def download_agent_risk_evidence(
    client,
    platform_id: PathSegment,
    agent_id: PathSegment,
    evidence_id: PathSegment,
    output_path: NonEmpty,
    overwrite: bool = False,
):
    """Download risk evidence locally; overwrite requires explicit intent."""
    response = (
        _agent(client, platform_id, agent_id)
        .get_risk_assessment()
        .get_risk_evidence_content(evidence_id)
    )
    return _download_binary(response, output_path, overwrite)


@_register("settings")
def get_settings(client):
    """Read global settings, including business KPI definitions and fetchedRevision."""
    return client.get_settings().get_raw()


@_register(
    "settings",
    "write",
    destructive=True,
    example={
        "changes": {"businessKPIs": []},
        "expected_revision": "revision-from-read",
    },
)
def update_settings(
    client,
    changes: Definition,
    expected_revision: NonEmpty,
    reset_incompatible_metrics: bool = False,
):
    """Replace named global settings fields; optionally allow deletion of incompatible metrics.

    The example sets businessKPIs=[] to remove all business KPI definitions.
    Use it only when clearing all definitions is intended.
    """
    return (
        _save_settings(client.get_settings(), changes, expected_revision)
        .save(confirm_metric_reset=reset_incompatible_metrics)
        .get_raw()
    )


@_register("tags")
def list_tags(client):
    """List visible tag names and colors."""
    return [{"name": item.name, "color": item.color} for item in client.list_tags()]


@_register(
    "tags",
    "write",
    destructive=True,
    example={"tag_name": "discovered-tag", "color": "requested-color"},
)
def update_tag(client, tag_name: PathSegment, color: NonEmpty):
    """Update an existing tag color; the SDK cannot create a tag handle for an absent tag."""
    tag = client.list_tags().tag(tag_name)
    tag.color = color
    tag.save()
    return {"name": tag.name, "color": tag.color}


@_register(
    "tags",
    "write",
    destructive=True,
    example={"tag_name": "discovered-tag", "new_name": "requested-tag"},
)
def rename_tag(client, tag_name: PathSegment, new_name: PathSegment):
    """Rename a tag everywhere it is used."""
    tag = client.list_tags().tag(tag_name).rename(new_name)
    return {"name": tag.name, "color": tag.color}


@_register("tags", "write", destructive=True, example={"tag_name": "discovered-tag"})
def delete_tag(client, tag_name: PathSegment):
    """Delete a tag everywhere it is used."""
    client.list_tags().tag(tag_name).delete()
    return {"deleted": tag_name}


def operation_handler(spec: AgentManagementOperation):
    async def execute(**params):
        def run():
            try:
                client = get_dss_client().get_agent_management_client()
                return redact_sensitive_data(spec.handler(client, **params))
            except (DataikuException, RequestException):
                raise RuntimeError(
                    "Agent Management request failed. Check SDK/server compatibility, permissions and IDs. Re-read state before retrying a write; it may have reached Dataiku. Conflicting revisions must not be retried automatically."
                ) from None

        return compact_json(await run_blocking(run))

    return execute

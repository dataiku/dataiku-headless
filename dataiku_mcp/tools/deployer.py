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

"""Project and API Deployer inspection and deployment operations."""

from typing import Annotated, Literal

from dataikuapi.utils import DataikuException
from pydantic import Field
from requests import RequestException

from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string
from .utils.validation import PathSegment as Identifier


DeployerType = Literal["project", "api"]
Version = Annotated[
    str, Field(description="Published bundle ID (project) or service version ID (api).")
]

# Raw Deployer status includes API keys, OAuth settings, scripts and endpoint code.
# Keep these allowlists explicit, including for nested objects.
_INFRA_FIELDS = ("id", "stage", "infraType", "governCheckPolicy", "canListHeavyStatus")
_ITEM_FIELDS = ("id", "name")
_DEPLOYMENT_FIELDS = (
    "id",
    "infraId",
    "publishedProjectKey",
    "deployedProjectKey",
    "bundleId",
    "publishedServiceId",
    "deployedServiceId",
    "enabled",
    "endpointId",
)
_PERMISSION_FIELDS = (
    "canDeploy",
    "canWrite",
    "isAdmin",
    "hasFullDeployPermissions",
    "isInfraAdmin",
    "neverEverDeployed",
)
_UPDATE_FIELDS = ("startTimestamp", "endTimestamp", "type", "status", "requester")


def _pick(raw: dict, fields: tuple) -> dict:
    return {key: raw[key] for key in fields if key in raw}


def _deployment_info(raw: dict) -> dict:
    result = _pick(raw, _DEPLOYMENT_FIELDS)
    mapping = raw.get("generationsMapping")
    if mapping is not None:
        result["generationsMapping"] = _pick(mapping, ("mode", "generation"))
        if "entries" in mapping:
            result["generationsMapping"]["entries"] = [
                _pick(entry, ("generation", "proba")) for entry in mapping["entries"]
            ]
    return result


def _summary(raw: dict) -> dict:
    result = _pick(raw, _PERMISSION_FIELDS)
    for key, fields in (
        ("infraBasicInfo", _INFRA_FIELDS),
        ("projectBasicInfo", _ITEM_FIELDS),
        ("serviceBasicInfo", _ITEM_FIELDS),
    ):
        if key in raw:
            result[key] = _pick(raw[key], fields)
    if "deploymentBasicInfo" in raw:
        result["deploymentBasicInfo"] = _deployment_info(raw["deploymentBasicInfo"])
    if "packages" in raw:
        result["packages"] = columnar(
            raw["packages"], ["id", "publishedOn", "publishedBy"]
        )
    if "deployments" in raw:
        result["deployments"] = [_deployment_info(item) for item in raw["deployments"]]
    if "infras" in raw:
        result["infras"] = [_pick(item, _INFRA_FIELDS) for item in raw["infras"]]
    return result


async def _execute(deployer_type: DeployerType, operation) -> str:
    def _run():
        client = get_dss_client()
        deployer = (
            client.get_projectdeployer()
            if deployer_type == "project"
            else client.get_apideployer()
        )
        try:
            return operation(deployer)
        except (DataikuException, RequestException):
            # SDK exception bodies may include node credentials or raw settings.
            raise RuntimeError(
                "Deployer request failed. Check node capabilities, permissions and object IDs. "
                "For a write, inspect current state and update history before retrying; "
                "the request may have reached Dataiku."
            ) from None

    return compact_json(await run_blocking(_run))


async def list_deployer_stages(deployer_type: DeployerType) -> str:
    """Discover configured infrastructure stages for a Project or API Deployer."""
    return await _execute(
        deployer_type,
        lambda deployer: {"stages": columnar(deployer.list_stages(), ["id", "desc"])},
    )


async def list_deployer_infrastructures(deployer_type: DeployerType) -> str:
    """Discover deployment targets and the current user’s deployment permissions."""
    return await _execute(
        deployer_type,
        lambda deployer: {
            "infrastructures": [
                _summary(raw) for raw in deployer.list_infras(as_objects=False)
            ]
        },
    )


async def get_deployer_infrastructure(
    deployer_type: DeployerType, infra_id: Identifier
) -> str:
    """Inspect an infrastructure’s summary and associated deployments without credentials."""
    infra_id = require_non_empty_string(infra_id, "infra_id")
    return await _execute(
        deployer_type,
        lambda deployer: _summary(deployer.get_infra(infra_id).get_status().get_raw()),
    )


async def list_deployer_published_items(deployer_type: DeployerType) -> str:
    """Discover published projects or API services available for deployment."""

    def _run(deployer):
        items = (
            deployer.list_projects(as_objects=False)
            if deployer_type == "project"
            else deployer.list_services(as_objects=False)
        )
        return {"items": [_summary(raw) for raw in items]}

    return await _execute(deployer_type, _run)


async def get_deployer_published_item(
    deployer_type: DeployerType, source_id: Identifier
) -> str:
    """Inspect a published project or API service and its available bundles or versions."""
    source_id = require_non_empty_string(source_id, "source_id")

    def _run(deployer):
        item = (
            deployer.get_project(source_id)
            if deployer_type == "project"
            else deployer.get_service(source_id)
        )
        return _summary(item.get_status().get_raw())

    return await _execute(deployer_type, _run)


async def list_deployer_deployments(deployer_type: DeployerType) -> str:
    """Discover deployment IDs and configured target versions; use detail for live health."""
    return await _execute(
        deployer_type,
        lambda deployer: {
            "deployments": [
                _summary(raw) for raw in deployer.list_deployments(as_objects=False)
            ]
        },
    )


async def get_deployer_deployment(
    deployer_type: DeployerType, deployment_id: Identifier
) -> str:
    """Inspect configured deployment version, current health and governance status."""
    deployment_id = require_non_empty_string(deployment_id, "deployment_id")

    def _run(deployer):
        deployment = deployer.get_deployment(deployment_id)
        status = deployment.get_status()
        governance = deployment.get_governance_status()
        # Only structured codes and severity: diagnostic free text can contain secrets.
        return {
            **_summary(status.get_light()),
            "settings": _deployment_info(deployment.get_settings().get_raw()),
            "health": status.get_health(),
            "health_messages": [
                _pick(message, ("severity", "isFatal", "code"))
                for message in status.get_health_messages().get("messages", [])
            ],
            "governance_messages": [
                _pick(message, ("severity", "isFatal", "code"))
                for message in governance.get("messages", [])
            ],
        }

    return await _execute(deployer_type, _run)


async def list_deployer_updates(
    deployer_type: DeployerType, deployment_id: Identifier
) -> str:
    """Find deployment update timestamps and outcomes for recovery and auditing."""
    deployment_id = require_non_empty_string(deployment_id, "deployment_id")
    return await _execute(
        deployer_type,
        lambda deployer: {
            "updates": [
                _pick(update.get_raw(), _UPDATE_FIELDS)
                for update in deployer.get_deployment(deployment_id).list_updates()
            ]
        },
    )


async def get_deployer_update(
    deployer_type: DeployerType,
    deployment_id: Identifier,
    timestamp: Identifier | None = None,
) -> str:
    """Inspect one deployment update outcome, using a timestamp or the latest update."""
    deployment_id = require_non_empty_string(deployment_id, "deployment_id")
    if timestamp is not None:
        timestamp = require_non_empty_string(timestamp, "timestamp")
    return await _execute(
        deployer_type,
        lambda deployer: _pick(
            deployer.get_deployment(deployment_id).get_update(timestamp).get_raw(),
            _UPDATE_FIELDS,
        ),
    )


async def create_deployer_deployment(
    deployer_type: DeployerType,
    deployment_id: Identifier,
    source_id: Identifier,
    infra_id: Identifier,
    version: Version,
    deployed_project_key: Identifier | None = None,
    project_folder_id: Identifier | None = None,
    endpoint_id: Identifier | None = None,
) -> str:
    """Create deployment configuration from a published version; start an update to apply it."""
    deployment_id = require_non_empty_string(deployment_id, "deployment_id")
    source_id = require_non_empty_string(source_id, "source_id")
    infra_id = require_non_empty_string(infra_id, "infra_id")
    version = require_non_empty_string(version, "version")
    if deployed_project_key is not None:
        deployed_project_key = require_non_empty_string(
            deployed_project_key, "deployed_project_key"
        )
    if project_folder_id is not None:
        project_folder_id = require_non_empty_string(
            project_folder_id, "project_folder_id"
        )
    if endpoint_id is not None:
        endpoint_id = require_non_empty_string(endpoint_id, "endpoint_id")
    if deployer_type == "project" and endpoint_id is not None:
        raise ValueError("endpoint_id is only supported for API deployments")
    if deployer_type == "api" and (
        deployed_project_key is not None or project_folder_id is not None
    ):
        raise ValueError(
            "deployed_project_key and project_folder_id are only supported for project deployments"
        )

    def _run(deployer):
        if deployer_type == "project":
            deployment = deployer.create_deployment(
                deployment_id,
                source_id,
                infra_id,
                version,
                deployed_project_key=deployed_project_key,
                project_folder_id=project_folder_id,
            )
        else:
            deployment = deployer.create_deployment(
                deployment_id, source_id, infra_id, version, endpoint_id=endpoint_id
            )
        return {
            "deployment_id": deployment.id,
            "status": "configuration_created",
            "update_started": False,
        }

    return await _execute(deployer_type, _run)


async def update_deployer_deployment(
    deployer_type: DeployerType,
    deployment_id: Identifier,
    version: Version | None = None,
    enabled: bool | None = None,
) -> str:
    """Save a target version or API enablement; an update is still needed to apply it."""
    deployment_id = require_non_empty_string(deployment_id, "deployment_id")
    if version is None and enabled is None:
        raise ValueError("Provide version or enabled")
    if version is not None:
        version = require_non_empty_string(version, "version")
    if enabled is not None and deployer_type != "api":
        raise ValueError("enabled is only supported for API deployments")

    def _run(deployer):
        settings = deployer.get_deployment(deployment_id).get_settings()
        if version is not None:
            if deployer_type == "project":
                settings.bundle_id = version
            else:
                settings.set_single_version(version)
        if enabled is not None:
            settings.set_enabled(enabled)
        settings.save()
        return {
            "deployment_id": deployment_id,
            "status": "configuration_saved",
            "update_started": False,
        }

    return await _execute(deployer_type, _run)


async def start_deployer_update(
    deployer_type: DeployerType, deployment_id: Identifier
) -> str:
    """Apply saved deployment settings asynchronously, potentially replacing running production assets."""
    deployment_id = require_non_empty_string(deployment_id, "deployment_id")

    def _run(deployer):
        future = deployer.get_deployment(deployment_id).start_update()
        return {
            "deployment_id": deployment_id,
            "future_id": future.job_id,
            "status": "update_submitted",
            "hint": "Poll get_future_status on this same instance, then re-read deployment health and update history. If future_id is null, inspect update history. Do not resubmit an uncertain update.",
        }

    return await _execute(deployer_type, _run)


async def get_deployer_future_status(future_id: Identifier) -> str:
    """Poll a deployment future without fetching potentially sensitive result payloads."""
    from dataikuapi.dss.future import DSSFuture

    def _run():
        try:
            state = DSSFuture(get_dss_client(), future_id).peek_state()
        except (DataikuException, RequestException):
            raise RuntimeError(
                "Deployer future polling failed. Inspect deployment health and update history on this instance; do not resubmit the deployment."
            ) from None
        fields = ("jobId", "hasResult", "aborted", "alive", "startTime", "endTime")
        return {"future_id": future_id, "state": _pick(state, fields)}

    return compact_json(await run_blocking(_run))

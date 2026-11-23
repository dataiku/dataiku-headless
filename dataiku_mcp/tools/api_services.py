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

"""Design API Service authoring and versioned publication via the public SDK."""

from typing import Annotated, Any

from dataikuapi.utils import DataikuException
from pydantic import Field
from requests import RequestException

from ..auth import get_dss_client
from ..config import request
from ..executors import run_blocking
from ..instance_policy import PROJECT_EDIT_POLICY
from ..server import mcp
from ..utils.redaction import (
    contains_redacted_values,
    redact_api_test_queries,
    redact_sensitive_data,
)
from ..utils.serialization import columnar, compact_json
from ..utils.validation import require_non_empty_string, require_path_segment


def _identity(project_key: str, service_id: str | None = None) -> dict:
    result = {
        "instance_name": request.get_pinned_instance().name,
        "project_key": require_path_segment(project_key, "project_key"),
    }
    if service_id is not None:
        result["service_id"] = require_path_segment(service_id, "service_id")
    return result


def _validate_endpoints(endpoints: list[dict] | None) -> list[dict]:
    if contains_redacted_values(endpoints):
        raise ValueError(
            "Do not submit redacted result placeholders as endpoint definitions; required hidden values must be resolved before replacement"
        )
    result = []
    seen = set()
    for endpoint in endpoints or []:
        endpoint = dict(endpoint)
        if any(not isinstance(endpoint.get(field), str) for field in ("id", "type")):
            raise ValueError("Each endpoint requires string id and type fields")
        endpoint["id"] = require_path_segment(endpoint.get("id"), "endpoint.id")
        endpoint["type"] = require_non_empty_string(
            endpoint.get("type"), "endpoint.type"
        )
        if endpoint["id"] in seen:
            raise ValueError("Endpoint IDs must be unique")
        seen.add(endpoint["id"])
        result.append(endpoint)
    return result


def _redact_endpoint_definitions(endpoints: Any) -> Any:
    redacted = redact_sensitive_data(endpoints)
    if not isinstance(endpoints, list) or not isinstance(redacted, list):
        return redacted
    for endpoint, redacted_endpoint in zip(endpoints, redacted):
        if not isinstance(endpoint, dict) or not isinstance(redacted_endpoint, dict):
            continue
        test_queries = endpoint.get("testQueries")
        if isinstance(test_queries, list):
            redacted_endpoint["testQueries"] = redact_api_test_queries(test_queries)
    return redacted


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="List API Services",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_api_services(project_key: str) -> str:
    """Discover a Design project's API Services and endpoint identifiers/types."""
    identity = _identity(project_key)

    def _run():
        try:
            return (
                get_dss_client()
                .get_project(identity["project_key"])
                .list_api_services()
            )
        except (DataikuException, RequestException):
            raise RuntimeError(
                "Could not list API services. Check the Design project and READ_CONF permission."
            ) from None

    services = await run_blocking(_run)
    return compact_json(
        {
            **identity,
            "services": columnar(
                [
                    {
                        "service_id": s.get("id"),
                        "name": s.get("name"),
                        "endpoints": [
                            {"id": e.get("id"), "type": e.get("type")}
                            for e in s.get("endpoints", [])
                        ],
                    }
                    for s in services
                ],
                ["service_id", "name", "endpoints"],
            ),
        }
    )


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Get API Service",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_api_service(project_key: str, service_id: str) -> str:
    """Read a Design API service's endpoint definitions, authentication mode and package versions."""
    identity = _identity(project_key, service_id)

    def _run():
        try:
            service = (
                get_dss_client()
                .get_project(identity["project_key"])
                .get_api_service(identity["service_id"])
            )
            raw = service.get_settings().get_raw()
            return {
                "name": raw.get("name"),
                "auth_method": raw.get("authMethod"),
                "endpoints": _redact_endpoint_definitions(raw.get("endpoints", [])),
                "packages": columnar(
                    [
                        {"package_id": p.get("id"), "created_on": p.get("createdOn")}
                        for p in service.list_packages()
                    ],
                    ["package_id", "created_on"],
                ),
            }
        except (DataikuException, RequestException):
            raise RuntimeError(
                "Could not read API service. Check the Design project, service ID and READ_CONF permission."
            ) from None

    return compact_json({**identity, **await run_blocking(_run)})


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Create API Service",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_api_service(project_key: str, service_id: str) -> str:
    """Create an empty API Service on Design; add endpoints with update_api_service."""
    identity = _identity(project_key, service_id)

    def _run():
        try:
            project = get_dss_client().get_project(identity["project_key"])
            if any(
                s.get("id") == identity["service_id"]
                for s in project.list_api_services()
            ):
                raise ValueError(
                    "API service already exists; inspect it before updating."
                )
            project.create_api_service(identity["service_id"])
        except (DataikuException, RequestException):
            raise RuntimeError(
                "API service creation could not be verified. Inspect list_api_services on this same Design instance before retrying; creation may have completed."
            ) from None

    await run_blocking(_run)
    return compact_json({**identity, "status": "created", "published": False})


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Update API Service",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def update_api_service(
    project_key: str,
    service_id: str,
    name: str | None = None,
    endpoints: Annotated[
        list[dict] | None,
        Field(
            description="Complete endpoint definitions (id/type required). Supplied IDs replace matching definitions or add new ones; omission does not remove endpoints."
        ),
    ] = None,
    remove_endpoint_ids: Annotated[
        list[str] | None,
        Field(
            description="Explicit existing endpoint IDs to remove. Cannot overlap IDs supplied in endpoints; omitted IDs otherwise stay unchanged."
        ),
    ] = None,
) -> str:
    """Rename an API Service, add/replace endpoints or remove selected endpoints while preserving authentication."""
    identity = _identity(project_key, service_id)
    definitions = _validate_endpoints(endpoints)
    removals = [
        require_path_segment(endpoint_id, "remove_endpoint_ids")
        for endpoint_id in remove_endpoint_ids or []
    ]
    if len(set(removals)) != len(removals):
        raise ValueError("remove_endpoint_ids must contain unique IDs")
    if set(removals) & {endpoint["id"] for endpoint in definitions}:
        raise ValueError("An endpoint cannot be replaced and removed in the same call")
    if name is not None:
        name = require_non_empty_string(name, "name")
    if name is None and not definitions and not removals:
        raise ValueError("Supply a name, endpoint definition, or endpoint ID to remove")

    def _run():
        try:
            service = (
                get_dss_client()
                .get_project(identity["project_key"])
                .get_api_service(identity["service_id"])
            )
            settings = service.get_settings()
            raw = settings.get_raw()
            replacements = {e["id"]: e for e in definitions}
            existing = raw.get("endpoints", [])
            existing_ids = {e["id"] for e in existing}
            if set(removals) - existing_ids:
                raise ValueError(
                    "An endpoint selected for removal does not exist; inspect get_api_service before retrying"
                )
            if name is not None:
                raw["name"] = name
            raw["endpoints"] = [
                replacements.get(e["id"], e)
                for e in existing
                if e["id"] not in removals
            ] + [e for e in definitions if e["id"] not in existing_ids]
            settings.save()
        except (DataikuException, RequestException):
            raise RuntimeError(
                "API service update could not be verified. Re-read get_api_service on this same Design instance before retrying; settings may already be saved."
            ) from None

    await run_blocking(_run)
    return compact_json({**identity, "status": "updated", "published": False})


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Create API Service Package",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_api_service_package(
    project_key: str,
    service_id: str,
    package_id: str,
    release_notes: str | None = None,
) -> str:
    """Package the current Design API service as a new immutable version for publication."""
    identity = _identity(project_key, service_id)
    package_id = require_path_segment(package_id, "package_id")

    def _run():
        try:
            service = (
                get_dss_client()
                .get_project(identity["project_key"])
                .get_api_service(identity["service_id"])
            )
            if any(p.get("id") == package_id for p in service.list_packages()):
                raise ValueError(
                    "Package ID already exists; choose a new ID only for a new version."
                )
            service.create_package(package_id, release_notes=release_notes)
        except (DataikuException, RequestException):
            raise RuntimeError(
                "API service packaging could not be verified. Inspect get_api_service on this same Design instance before retrying; packaging may still be running or may have completed."
            ) from None

    await run_blocking(_run)
    return compact_json(
        {**identity, "package_id": package_id, "status": "created", "published": False}
    )


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Publish API Service Package",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def publish_api_service_package(
    project_key: str,
    service_id: str,
    package_id: str,
    published_service_id: Annotated[
        str | None,
        Field(
            description="Target service on the Design node's configured API Deployer; defaults to the source service ID."
        ),
    ] = None,
) -> str:
    """Publish an existing Design API package to the configured API Deployer without activating it."""
    identity = _identity(project_key, service_id)
    package_id = require_path_segment(package_id, "package_id")
    if published_service_id is not None:
        published_service_id = require_path_segment(
            published_service_id, "published_service_id"
        )

    def _run():
        try:
            service = (
                get_dss_client()
                .get_project(identity["project_key"])
                .get_api_service(identity["service_id"])
            )
            if not any(p.get("id") == package_id for p in service.list_packages()):
                raise ValueError(
                    "Package must exist; inspect get_api_service before publishing."
                )
            service.publish_package(
                package_id, published_service_id=published_service_id
            )
        except (DataikuException, RequestException):
            raise RuntimeError(
                "API service publication could not be verified. Inspect the configured API Deployer's published service versions before retrying; publication may have completed."
            ) from None

    await run_blocking(_run)
    return compact_json(
        {
            **identity,
            "package_id": package_id,
            "published_service_id": published_service_id or identity["service_id"],
            "status": "published",
            "deployment_started": False,
        }
    )

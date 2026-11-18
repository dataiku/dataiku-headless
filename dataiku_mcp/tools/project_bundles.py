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

"""Design-node bundle discovery, creation, and publication through the public SDK."""

from typing import Annotated

from dataikuapi.utils import DataikuException
from pydantic import Field
from requests import RequestException

from ..auth import get_dss_client
from ..config import request
from ..executors import run_blocking
from ..instance_policy import PROJECT_EDIT_POLICY
from ..server import mcp
from ..utils.serialization import columnar, compact_json
from ..utils.redaction import redact_sensitive_data
from ..utils.validation import require_non_empty_string, require_path_segment


_BUNDLE_COLUMNS = [
    "bundle_id",
    "state",
    "size_bytes",
    "project_standards_skipped",
    "future_id",
    "published_project_key",
    "published_on",
    "published_by",
]


# Bundle payload selections (not the broader Design-project export switches).
_BUNDLE_SELECTION_FIELDS = {
    "includedDatasetsData": ("name",),
    "includedSavedModels": ("id",),
    "includedManagedFolders": ("id",),
    "includedModelEvaluationStores": ("id",),
    "includedKnowledgeBanks": ("id",),
    "includedLabelingTasks": ("id",),
    "includedCodeStudios": ("id",),
    "includedPromptStudiosHistories": ("promptStudioId", "promptId"),
}
_BUNDLE_BOOLEAN_OPTIONS = {
    "exportSavedModelsRequiredVersions",
    "exportDatasetResources",
    "exportProjectResources",
    "exportNotebooks",
    "exportNotebooksWithOutputs",
    "exportInsightsData",
    "exportAgentReviews",
}


def _validate_export_options(options: dict) -> dict:
    result = {}
    for key, value in options.items():
        if key in _BUNDLE_BOOLEAN_OPTIONS:
            if not isinstance(value, bool):
                raise ValueError(f"export_options.{key} must be a boolean")
            result[key] = value
        elif key in _BUNDLE_SELECTION_FIELDS:
            if not isinstance(value, list):
                raise ValueError(f"export_options.{key} must be a list")
            required = _BUNDLE_SELECTION_FIELDS[key]
            optional = {"type"} if key == "includedDatasetsData" else {"name"}
            if key == "includedPromptStudiosHistories":
                optional = {"promptStudioName"}
            entries = []
            for index, entry in enumerate(value):
                label = f"export_options.{key}[{index}]"
                if not isinstance(entry, dict) or not set(required) <= entry.keys():
                    raise ValueError(f"{label} requires {', '.join(required)}")
                if entry.keys() - set(required) - optional:
                    raise ValueError(f"{label} contains unsupported fields")
                if any(not isinstance(item, str) for item in entry.values()):
                    raise ValueError(f"{label} fields must be strings")
                entries.append(
                    {
                        field: require_non_empty_string(item, f"{label}.{field}")
                        for field, item in entry.items()
                    }
                )
            result[key] = entries
        else:
            raise ValueError(f"Unsupported bundle export option: {key}")
    return result


def _bundle_summary(raw: dict) -> dict:
    # Manifests, standards reports and future errors can carry secrets and code.
    published = raw.get("publishedBundleState") or {}
    future = raw.get("futureItem") or {}
    return {
        "bundle_id": raw.get("bundleId"),
        "state": raw.get("state"),
        "size_bytes": raw.get("sizeInBytes"),
        "project_standards_skipped": raw.get("projectStandardsSkipped"),
        "future_id": future.get("jobId"),
        "published_project_key": published.get("publishedProjectKey"),
        "published_on": published.get("publishedOn"),
        "published_by": published.get("publishedBy"),
    }


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="List Project Bundles",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_project_bundles(project_key: str) -> str:
    """Inspect a Design project's saved bundle content options and exported bundle states."""
    project_key = require_path_segment(project_key, "project_key")
    instance_name = request.get_pinned_instance().name

    def _run():
        try:
            project = get_dss_client().get_project(project_key)
            bundles = project.list_exported_bundles()
            settings = project.get_settings().get_raw()
            options = (settings.get("bundleExporterSettings") or {}).get(
                "exportOptions"
            ) or {}
            return bundles, redact_sensitive_data(options)
        except (DataikuException, RequestException):
            raise RuntimeError(
                "Could not list project bundles. Check the Design node, project key and bundle permissions."
            ) from None

    raw, export_options = await run_blocking(_run)
    return compact_json(
        {
            "instance_name": instance_name,
            "project_key": project_key,
            "export_options": export_options,
            "bundles": columnar(
                [_bundle_summary(item) for item in raw.get("bundles", [])],
                _BUNDLE_COLUMNS,
            ),
        }
    )


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Create Project Bundle",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_project_bundle(
    project_key: str,
    bundle_id: str,
    release_notes: str | None = None,
    export_options: Annotated[
        dict | None,
        Field(
            description="Dataiku bundle export option overrides, saved before creation. Omitted keys stay unchanged; supplied lists replace selections ([] clears)."
        ),
    ] = None,
) -> str:
    """Create a Design bundle, optionally selecting its content, and evaluate project standards."""
    project_key = require_path_segment(project_key, "project_key")
    bundle_id = require_path_segment(bundle_id, "bundle_id")
    overrides = (
        _validate_export_options(export_options) if export_options is not None else {}
    )
    instance_name = request.get_pinned_instance().name

    def _run():
        try:
            project = get_dss_client().get_project(project_key)
            existing = project.list_exported_bundles().get("bundles", [])
            if any(item.get("bundleId") == bundle_id for item in existing):
                raise ValueError(
                    "Bundle ID already exists. Inspect list_project_bundles; choose a new ID only for a new export."
                )
            if overrides:
                settings = project.get_settings()
                raw = settings.get_raw()
                exporter = raw.get("bundleExporterSettings") or {}
                options = exporter.get("exportOptions") or {}
                options.update(overrides)
                exporter["exportOptions"] = options
                raw["bundleExporterSettings"] = exporter
                settings.save()
            # This public SDK call waits for the server-side export to finish.
            project.export_bundle(
                bundle_id,
                release_notes=release_notes,
                evaluate_project_standards_checks=True,
            )
        except (DataikuException, RequestException):
            raise RuntimeError(
                "Bundle creation could not be verified. Inspect list_project_bundles on this same Design instance before retrying; the export may still be running or may have completed, and supplied content options may already be saved. Raw errors are omitted."
            ) from None

    await run_blocking(_run)
    return compact_json(
        {
            "instance_name": instance_name,
            "project_key": project_key,
            "bundle_id": bundle_id,
            "status": "created",
            "published": False,
        }
    )


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Publish Project Bundle",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def publish_project_bundle(
    project_key: str,
    bundle_id: str,
    published_project_key: Annotated[
        str | None,
        Field(
            description="Project key on the Design node's configured Deployer; defaults to the source project key."
        ),
    ] = None,
) -> str:
    """Publish an existing built bundle to the Design node's configured Project Deployer."""
    project_key = require_path_segment(project_key, "project_key")
    bundle_id = require_path_segment(bundle_id, "bundle_id")
    if published_project_key is not None:
        published_project_key = require_path_segment(
            published_project_key, "published_project_key"
        )
    instance_name = request.get_pinned_instance().name

    def _run():
        try:
            project = get_dss_client().get_project(project_key)
            existing = project.list_exported_bundles().get("bundles", [])
            bundle = next(
                (item for item in existing if item.get("bundleId") == bundle_id), None
            )
            if bundle is None or bundle.get("state") != "BUILT":
                raise ValueError(
                    "Bundle must exist in BUILT state. Inspect list_project_bundles before publishing."
                )
            return project.publish_bundle(
                bundle_id, published_project_key=published_project_key
            )
        except (DataikuException, RequestException):
            raise RuntimeError(
                "Bundle publication could not be verified. Inspect list_project_bundles and the configured Project Deployer before retrying; publication may have completed. Raw errors are omitted."
            ) from None

    raw = await run_blocking(_run)
    return compact_json(
        {
            "instance_name": instance_name,
            "project_key": project_key,
            "bundle_id": bundle_id,
            "status": "published",
            "published_project_key": raw.get("publishedProjectKey"),
            "published_on": raw.get("publishedOn"),
            "published_by": raw.get("publishedBy"),
            "deployment_started": False,
        }
    )

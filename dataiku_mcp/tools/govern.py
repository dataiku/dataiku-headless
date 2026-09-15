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

"""Single entry point to Dataiku Govern through the public Python SDK.

One tool, ``govern``, exposes a fixed catalog of operations. Each operation
maps by hand to one ``dataikuapi.GovernClient`` call chain, so the agent never
guesses SDK methods, REST paths, or payload envelopes. An empty ``operation``
returns the catalog itself.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dataikuapi.govern.artifact_search import (
    GovernArtifactFilterArchivedStatus,
    GovernArtifactFilterArtifacts,
    GovernArtifactFilterBlueprints,
    GovernArtifactFilterBlueprintVersions,
    GovernArtifactFilterFieldValue,
    GovernArtifactSearchQuery,
    GovernArtifactSearchSortField,
    GovernArtifactSearchSortFieldDefinition,
    GovernArtifactSearchSortName,
    GovernArtifactSearchSortWorkflow,
)
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_govern_client
from .utils.serialization import compact_json
from .utils.validation import require_non_empty_string

DOMAINS = (
    "artifacts",
    "signoffs",
    "blueprints",
    "roles",
    "custom_pages",
    "time_series",
    "files",
    "users",
    "instance",
)

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class GovernParam:
    name: str
    kind: str  # string, boolean, integer, object, list, any
    description: str
    required: bool = False


@dataclass(frozen=True)
class GovernOperation:
    domain: str
    kind: str  # read, write, delete
    description: str
    sdk: str
    params: tuple[GovernParam, ...]
    run: Callable[[Any, dict[str, Any]], Any]


GOVERN_OPERATIONS: dict[str, GovernOperation] = {}


def _register(
    operation_id: str,
    *,
    domain: str,
    kind: str,
    description: str,
    sdk: str,
    params: tuple[GovernParam, ...] = (),
):
    def decorator(func):
        GOVERN_OPERATIONS[operation_id] = GovernOperation(
            domain, kind, description, sdk, tuple(params), func
        )
        return func

    return decorator


def _p(name: str, kind: str, description: str, required: bool = False) -> GovernParam:
    return GovernParam(name, kind, description, required)


ARTIFACT_ID = _p("artifact_id", "string", "Artifact ID, for example ar.42.", True)
STEP_ID = _p("step_id", "string", "Workflow step ID that carries the signoff.", True)
BLUEPRINT_ID = _p(
    "blueprint_id",
    "string",
    "Blueprint ID, for example bp.system.govern_project.",
    True,
)
VERSION_ID = _p(
    "version_id", "string", "Blueprint version ID, for example bv.system.default.", True
)
ROLE_ID = _p("role_id", "string", "Role ID, for example ro.reviewer.", True)
CUSTOM_PAGE_ID = _p(
    "custom_page_id", "string", "Custom page ID, for example cp.1.", True
)
TIME_SERIES_ID = _p(
    "time_series_id", "string", "Time series ID, for example ts.7.", True
)
UPLOADED_FILE_ID = _p(
    "uploaded_file_id", "string", "Uploaded file ID, for example uf.3.", True
)
LOGIN = _p("login", "string", "User login.", True)
GROUP_NAME = _p("name", "string", "Group name.", True)
NEW_IDENTIFIER = _p(
    "new_identifier",
    "string",
    "Bare identifier for the new object; the server adds the type prefix.",
    True,
)
USERS_CONTAINER = _p(
    "users_container",
    "object",
    "Users container: {type: user|group|role|global-api-key, login|groupName|roleId|keyId}.",
    True,
)
COMMENT = _p("comment", "string", "Optional comment recorded with the decision.")


class _UsersContainer:
    """Adapter so a raw users-container dict satisfies the SDK build() contract."""

    def __init__(self, definition: dict[str, Any]):
        self.definition = definition

    def build(self) -> dict[str, Any]:
        return self.definition


def _users_container(value: Any) -> _UsersContainer:
    if not isinstance(value, dict) or not value.get("type"):
        raise ValueError(
            "users_container must be an object with a 'type' key: "
            "user, group, role or global-api-key"
        )
    return _UsersContainer(value)


def _replace_raw(definition, new_raw: dict[str, Any]):
    """Replace a mutable SDK definition in place so ``save()`` sends ``new_raw``."""
    raw = definition.get_raw()
    raw.clear()
    raw.update(new_raw)
    return definition


def _version_state(version) -> dict[str, Any]:
    return {
        "definition": version.get_definition().get_raw(),
        "trace": version.get_trace().get_raw(),
    }


def _signoff(client, params: dict[str, Any]):
    return client.get_artifact(params["artifact_id"]).get_signoff(params["step_id"])


def _admin_blueprint(client, params: dict[str, Any]):
    return client.get_blueprint_designer().get_blueprint(params["blueprint_id"])


def _admin_version(client, params: dict[str, Any]):
    return _admin_blueprint(client, params).get_version(params["version_id"])


def _roles(client):
    return client.get_roles_permissions_handler()


def _pages(client):
    return client.get_custom_pages_handler()


# ---------------------------------------------------------------------------
# artifacts
# ---------------------------------------------------------------------------


@_register(
    "search_artifacts",
    domain="artifacts",
    kind="read",
    description="Search artifacts with optional blueprint, version, artifact, field and archived filters.",
    sdk="GovernClient.new_artifact_search_request",
    params=(
        _p("blueprint_ids", "list", "Blueprint IDs to keep."),
        _p(
            "blueprint_version_ids",
            "list",
            "Blueprint version IDs to keep, each {blueprintId, versionId}.",
        ),
        _p("artifact_ids", "list", "Artifact IDs to keep."),
        _p(
            "field_filters",
            "list",
            "Field conditions, each {condition_type: EQUALS|CONTAINS|START_WITH|END_WITH, condition, field_id, negate, case_sensitive}; no field_id filters on the name.",
        ),
        _p("archived", "boolean", "true includes archived artifacts."),
        _p(
            "sort",
            "object",
            "Sort: {type: name|workflow|field, direction: ASC|DESC, fields: [{blueprint_id, field_id}]}.",
        ),
        _p("page_size", "integer", "Batch size per request (default 20)."),
        _p("max_results", "integer", "Maximum hits to return (default 100)."),
    ),
)
def _search_artifacts(client, p):
    filters = []
    if p.get("blueprint_ids"):
        filters.append(GovernArtifactFilterBlueprints(list(p["blueprint_ids"])))
    if p.get("blueprint_version_ids"):
        filters.append(
            GovernArtifactFilterBlueprintVersions(list(p["blueprint_version_ids"]))
        )
    if p.get("artifact_ids"):
        filters.append(GovernArtifactFilterArtifacts(list(p["artifact_ids"])))
    for field_filter in p.get("field_filters") or []:
        if not isinstance(field_filter, dict) or not field_filter.get("condition_type"):
            raise ValueError("Each field_filters entry needs a condition_type")
        filters.append(
            GovernArtifactFilterFieldValue(
                field_filter["condition_type"],
                condition=field_filter.get("condition"),
                field_id=field_filter.get("field_id"),
                negate_condition=field_filter.get("negate"),
                case_sensitive=field_filter.get("case_sensitive"),
            )
        )
    if p.get("archived") is not None:
        filters.append(GovernArtifactFilterArchivedStatus(bool(p["archived"])))

    sort = None
    sort_spec = p.get("sort")
    if sort_spec:
        sort_type = sort_spec.get("type", "name")
        direction = sort_spec.get("direction", "ASC")
        if sort_type == "name":
            sort = GovernArtifactSearchSortName(direction)
        elif sort_type == "workflow":
            sort = GovernArtifactSearchSortWorkflow(direction)
        elif sort_type == "field":
            fields = [
                GovernArtifactSearchSortFieldDefinition(
                    field["blueprint_id"], field["field_id"]
                )
                for field in sort_spec.get("fields") or []
            ]
            if not fields:
                raise ValueError("sort.fields is required when sort.type is field")
            sort = GovernArtifactSearchSortField(fields=fields, direction=direction)
        else:
            raise ValueError("sort.type must be name, workflow or field")

    page_size = int(p.get("page_size") or 20)
    max_results = int(p.get("max_results") or 100)
    if page_size <= 0 or max_results <= 0:
        raise ValueError("page_size and max_results must be positive")

    request = client.new_artifact_search_request(
        GovernArtifactSearchQuery(artifact_filters=filters, artifact_search_sort=sort)
    )
    hits: list[dict[str, Any]] = []
    has_more = False
    while True:
        batch = request.fetch_next_batch(page_size=page_size).get_response_hits()
        if not batch:
            break
        for hit in batch:
            if len(hits) >= max_results:
                has_more = True
                break
            hits.append(hit.get_raw())
        if has_more or len(batch) < page_size:
            break
    return {"count": len(hits), "has_more": has_more, "hits": hits}


@_register(
    "get_artifact",
    domain="artifacts",
    kind="read",
    description="Get an artifact definition: name, fields, workflow state and blueprint version.",
    sdk="GovernArtifact.get_definition",
    params=(ARTIFACT_ID,),
)
def _get_artifact(client, p):
    return client.get_artifact(p["artifact_id"]).get_definition().get_raw()


@_register(
    "create_artifact",
    domain="artifacts",
    kind="write",
    description="Create an artifact on an ACTIVE blueprint version.",
    sdk="GovernClient.create_artifact",
    params=(
        _p(
            "blueprint_id",
            "string",
            "Blueprint ID. Required unless definition is given.",
        ),
        _p(
            "version_id",
            "string",
            "ACTIVE blueprint version ID. Required unless definition is given.",
        ),
        _p("name", "string", "Artifact name. Required unless definition is given."),
        _p(
            "fields",
            "object",
            "Field values keyed by field ID; list fields take arrays.",
        ),
        _p(
            "definition",
            "object",
            "Complete artifact payload; overrides the other params.",
        ),
    ),
)
def _create_artifact(client, p):
    definition = p.get("definition")
    if definition is None:
        for key in ("blueprint_id", "version_id", "name"):
            if not p.get(key):
                raise ValueError(f"'{key}' is required when 'definition' is not given")
        definition = {
            "blueprintVersionId": {
                "blueprintId": p["blueprint_id"],
                "versionId": p["version_id"],
            },
            "name": p["name"],
            "fields": p.get("fields") or {},
        }
    return client.create_artifact(definition).get_definition().get_raw()


@_register(
    "update_artifact",
    domain="artifacts",
    kind="write",
    description="Replace the complete artifact definition; read it first and send everything back.",
    sdk="GovernArtifactDefinition.save",
    params=(
        ARTIFACT_ID,
        _p(
            "definition",
            "object",
            "Complete artifact definition from get_artifact.",
            True,
        ),
    ),
)
def _update_artifact(client, p):
    artifact = client.get_artifact(p["artifact_id"])
    _replace_raw(artifact.get_definition(), p["definition"]).save()
    return artifact.get_definition().get_raw()


@_register(
    "update_artifact_fields",
    domain="artifacts",
    kind="write",
    description="Merge field values (and optionally the name) into an artifact, preserving the rest.",
    sdk="GovernArtifactDefinition.save",
    params=(
        ARTIFACT_ID,
        _p("fields", "object", "Field values to set, keyed by field ID.", True),
        _p("name", "string", "New artifact name."),
    ),
)
def _update_artifact_fields(client, p):
    artifact = client.get_artifact(p["artifact_id"])
    definition = artifact.get_definition()
    raw = definition.get_raw()
    raw.setdefault("fields", {}).update(p["fields"])
    if p.get("name"):
        raw["name"] = p["name"]
    definition.save()
    return artifact.get_definition().get_raw()


@_register(
    "delete_artifact",
    domain="artifacts",
    kind="delete",
    description="Delete an artifact.",
    sdk="GovernArtifact.delete",
    params=(ARTIFACT_ID,),
)
def _delete_artifact(client, p):
    client.get_artifact(p["artifact_id"]).delete()
    return {"deleted": p["artifact_id"]}


# ---------------------------------------------------------------------------
# signoffs
# ---------------------------------------------------------------------------


@_register(
    "list_signoffs",
    domain="signoffs",
    kind="read",
    description="List the signoffs of an artifact with their step and status.",
    sdk="GovernArtifact.list_signoffs",
    params=(ARTIFACT_ID,),
)
def _list_signoffs(client, p):
    return [
        item.get_raw() for item in client.get_artifact(p["artifact_id"]).list_signoffs()
    ]


@_register(
    "get_signoff",
    domain="signoffs",
    kind="read",
    description="Get a signoff definition: status, feedback responses and approver response.",
    sdk="GovernArtifactSignoff.get_definition",
    params=(ARTIFACT_ID, STEP_ID),
)
def _get_signoff(client, p):
    return _signoff(client, p).get_definition().get_raw()


@_register(
    "get_signoff_details",
    domain="signoffs",
    kind="read",
    description="Get a signoff with reviewer and approver membership resolved to users.",
    sdk="GovernArtifactSignoff.get_details",
    params=(ARTIFACT_ID, STEP_ID),
)
def _get_signoff_details(client, p):
    return _signoff(client, p).get_details().get_raw()


@_register(
    "create_signoff",
    domain="signoffs",
    kind="write",
    description="Create the signoff of an ONGOING step whose blueprint version has a signoff configuration.",
    sdk="GovernArtifact.create_signoff",
    params=(ARTIFACT_ID, STEP_ID),
)
def _create_signoff(client, p):
    artifact = client.get_artifact(p["artifact_id"])
    return artifact.create_signoff(p["step_id"]).get_definition().get_raw()


@_register(
    "update_signoff_status",
    domain="signoffs",
    kind="write",
    description="Move a signoff to NOT_STARTED, WAITING_FOR_FEEDBACK, WAITING_FOR_APPROVAL, APPROVED, REJECTED or ABANDONED.",
    sdk="GovernArtifactSignoff.update_status",
    params=(
        ARTIFACT_ID,
        STEP_ID,
        _p("status", "string", "Target signoff status.", True),
        _p(
            "users_to_notify",
            "list",
            "Users to email, each {userLogin, groupId}; omit to notify every configured reviewer or approver; pass [] to notify nobody.",
        ),
        _p(
            "reload_conf_for_reset",
            "boolean",
            "On NOT_STARTED, reload the configuration from the blueprint version and drop delegations.",
        ),
    ),
)
def _update_signoff_status(client, p):
    signoff = _signoff(client, p)
    signoff.update_status(
        p["status"],
        users_to_notify=p.get("users_to_notify"),
        reload_conf_for_reset=bool(p.get("reload_conf_for_reset", False)),
    )
    return signoff.get_definition().get_raw()


@_register(
    "list_signoff_feedbacks",
    domain="signoffs",
    kind="read",
    description="List the feedback responses recorded on a signoff.",
    sdk="GovernArtifactSignoff.list_feedbacks",
    params=(ARTIFACT_ID, STEP_ID),
)
def _list_signoff_feedbacks(client, p):
    return [item.get_raw() for item in _signoff(client, p).list_feedbacks()]


FEEDBACK_ID = _p("feedback_id", "string", "Feedback response ID.", True)
FEEDBACK_STATUS = _p(
    "status", "string", "Feedback status: APPROVED, MINOR_ISSUE or MAJOR_ISSUE.", True
)
APPROVAL_STATUS = _p(
    "status", "string", "Approval status: APPROVED, REJECTED or ABANDONED.", True
)


@_register(
    "get_signoff_feedback",
    domain="signoffs",
    kind="read",
    description="Get one feedback response of a signoff.",
    sdk="GovernArtifactSignoffFeedback.get_definition",
    params=(ARTIFACT_ID, STEP_ID, FEEDBACK_ID),
)
def _get_signoff_feedback(client, p):
    return _signoff(client, p).get_feedback(p["feedback_id"]).get_definition().get_raw()


@_register(
    "add_signoff_feedback",
    domain="signoffs",
    kind="write",
    description="Record a feedback response as the authenticated user, in a feedback group.",
    sdk="GovernArtifactSignoff.add_feedback",
    params=(
        ARTIFACT_ID,
        STEP_ID,
        _p(
            "group_id",
            "string",
            "Feedback group ID from the signoff configuration.",
            True,
        ),
        FEEDBACK_STATUS,
        COMMENT,
    ),
)
def _add_signoff_feedback(client, p):
    feedback = _signoff(client, p).add_feedback(
        p["group_id"], p["status"], comment=p.get("comment")
    )
    return feedback.get_definition().get_raw()


@_register(
    "update_signoff_feedback",
    domain="signoffs",
    kind="write",
    description="Change the status or comment of an existing feedback response.",
    sdk="GovernArtifactSignoffFeedbackDefinition.save",
    params=(ARTIFACT_ID, STEP_ID, FEEDBACK_ID, FEEDBACK_STATUS, COMMENT),
)
def _update_signoff_feedback(client, p):
    definition = _signoff(client, p).get_feedback(p["feedback_id"]).get_definition()
    raw = definition.get_raw()
    raw["status"] = p["status"]
    if p.get("comment") is not None:
        raw["comment"] = p["comment"]
    definition.save()
    return definition.get_raw()


@_register(
    "delete_signoff_feedback",
    domain="signoffs",
    kind="delete",
    description="Delete a feedback response.",
    sdk="GovernArtifactSignoffFeedback.delete",
    params=(ARTIFACT_ID, STEP_ID, FEEDBACK_ID),
)
def _delete_signoff_feedback(client, p):
    _signoff(client, p).get_feedback(p["feedback_id"]).delete()
    return {"deleted": p["feedback_id"]}


@_register(
    "delegate_signoff_feedback",
    domain="signoffs",
    kind="write",
    description="Add a delegated reviewer to a feedback group of a signoff.",
    sdk="GovernArtifactSignoff.delegate_feedback",
    params=(
        ARTIFACT_ID,
        STEP_ID,
        _p("group_id", "string", "Feedback group ID.", True),
        USERS_CONTAINER,
    ),
)
def _delegate_signoff_feedback(client, p):
    signoff = _signoff(client, p)
    signoff.delegate_feedback(p["group_id"], _users_container(p["users_container"]))
    return signoff.get_details().get_raw()


@_register(
    "get_signoff_approval",
    domain="signoffs",
    kind="read",
    description="Get the approver response of a signoff.",
    sdk="GovernArtifactSignoffApproval.get_definition",
    params=(ARTIFACT_ID, STEP_ID),
)
def _get_signoff_approval(client, p):
    return _signoff(client, p).get_approval().get_definition().get_raw()


@_register(
    "add_signoff_approval",
    domain="signoffs",
    kind="write",
    description="Record the final approval decision as the authenticated user.",
    sdk="GovernArtifactSignoff.add_approval",
    params=(ARTIFACT_ID, STEP_ID, APPROVAL_STATUS, COMMENT),
)
def _add_signoff_approval(client, p):
    signoff = _signoff(client, p)
    signoff.add_approval(p["status"], comment=p.get("comment"))
    return signoff.get_approval().get_definition().get_raw()


@_register(
    "update_signoff_approval",
    domain="signoffs",
    kind="write",
    description="Change the status or comment of the recorded approval.",
    sdk="GovernArtifactSignoffApprovalDefinition.save",
    params=(ARTIFACT_ID, STEP_ID, APPROVAL_STATUS, COMMENT),
)
def _update_signoff_approval(client, p):
    definition = _signoff(client, p).get_approval().get_definition()
    raw = definition.get_raw()
    raw["status"] = p["status"]
    if p.get("comment") is not None:
        raw["comment"] = p["comment"]
    definition.save()
    return definition.get_raw()


@_register(
    "delete_signoff_approval",
    domain="signoffs",
    kind="delete",
    description="Delete the recorded approval of a signoff.",
    sdk="GovernArtifactSignoffApproval.delete",
    params=(ARTIFACT_ID, STEP_ID),
)
def _delete_signoff_approval(client, p):
    _signoff(client, p).get_approval().delete()
    return {
        "deleted": "approval",
        "artifact_id": p["artifact_id"],
        "step_id": p["step_id"],
    }


@_register(
    "delegate_signoff_approval",
    domain="signoffs",
    kind="write",
    description="Add a delegated approver to a signoff.",
    sdk="GovernArtifactSignoff.delegate_approval",
    params=(ARTIFACT_ID, STEP_ID, USERS_CONTAINER),
)
def _delegate_signoff_approval(client, p):
    signoff = _signoff(client, p)
    signoff.delegate_approval(_users_container(p["users_container"]))
    return signoff.get_details().get_raw()


@_register(
    "get_signoff_recurrence",
    domain="signoffs",
    kind="read",
    description="Get the recurrence (scheduled reset) configuration of a signoff.",
    sdk="GovernArtifactSignoff.get_recurrence_configuration",
    params=(ARTIFACT_ID, STEP_ID),
)
def _get_signoff_recurrence(client, p):
    return _signoff(client, p).get_recurrence_configuration().get_raw()


@_register(
    "update_signoff_recurrence",
    domain="signoffs",
    kind="write",
    description="Replace the recurrence configuration of a signoff: {activated, days, weeks, months, years, reloadConf}.",
    sdk="GovernArtifactSignoffRecurrenceConfiguration.save",
    params=(
        ARTIFACT_ID,
        STEP_ID,
        _p("configuration", "object", "Complete recurrence configuration.", True),
    ),
)
def _update_signoff_recurrence(client, p):
    recurrence = _signoff(client, p).get_recurrence_configuration()
    _replace_raw(recurrence, p["configuration"]).save()
    return recurrence.get_raw()


# ---------------------------------------------------------------------------
# blueprints
# ---------------------------------------------------------------------------


@_register(
    "list_blueprints",
    domain="blueprints",
    kind="read",
    description="List readable blueprints; each item nests the blueprint under 'blueprint'.",
    sdk="GovernClient.list_blueprints",
)
def _list_blueprints(client, p):
    return [item.get_raw() for item in client.list_blueprints()]


@_register(
    "get_blueprint",
    domain="blueprints",
    kind="read",
    description="Get a blueprint: name, icon and colors.",
    sdk="GovernBlueprint.get_definition",
    params=(BLUEPRINT_ID,),
)
def _get_blueprint(client, p):
    return client.get_blueprint(p["blueprint_id"]).get_definition().get_raw()


@_register(
    "list_blueprint_versions",
    domain="blueprints",
    kind="read",
    description="List the versions of a blueprint with their status.",
    sdk="GovernBlueprint.list_versions",
    params=(BLUEPRINT_ID,),
)
def _list_blueprint_versions(client, p):
    return [
        item.get_raw()
        for item in client.get_blueprint(p["blueprint_id"]).list_versions()
    ]


@_register(
    "get_blueprint_version",
    domain="blueprints",
    kind="read",
    description="Get a blueprint version definition (fields, workflow, views, hooks) and its trace (status, origin).",
    sdk="GovernBlueprintVersion.get_definition",
    params=(BLUEPRINT_ID, VERSION_ID),
)
def _get_blueprint_version(client, p):
    version = client.get_blueprint(p["blueprint_id"]).get_version(p["version_id"])
    return _version_state(version)


@_register(
    "create_blueprint",
    domain="blueprints",
    kind="write",
    description="Create a blueprint (designer). The body holds name, icon, color and backgroundColor, no id.",
    sdk="GovernAdminBlueprintDesigner.create_blueprint",
    params=(NEW_IDENTIFIER, _p("blueprint", "object", "Blueprint metadata.", True)),
)
def _create_blueprint(client, p):
    designer = client.get_blueprint_designer()
    blueprint = designer.create_blueprint(p["new_identifier"], p["blueprint"])
    return blueprint.get_definition().get_raw()


@_register(
    "update_blueprint",
    domain="blueprints",
    kind="write",
    description="Replace the blueprint metadata (name, icon, colors); versions are edited separately.",
    sdk="GovernAdminBlueprintDefinition.save",
    params=(
        BLUEPRINT_ID,
        _p("blueprint", "object", "Complete blueprint metadata.", True),
    ),
)
def _update_blueprint(client, p):
    blueprint = _admin_blueprint(client, p)
    _replace_raw(blueprint.get_definition(), p["blueprint"]).save()
    return blueprint.get_definition().get_raw()


@_register(
    "delete_blueprint",
    domain="blueprints",
    kind="delete",
    description="Delete a blueprint; its versions must hold no artifacts.",
    sdk="GovernAdminBlueprint.delete",
    params=(BLUEPRINT_ID,),
)
def _delete_blueprint(client, p):
    _admin_blueprint(client, p).delete()
    return {"deleted": p["blueprint_id"]}


@_register(
    "create_blueprint_version",
    domain="blueprints",
    kind="write",
    description="Create a DRAFT blueprint version, optionally forked from an origin version.",
    sdk="GovernAdminBlueprint.create_version",
    params=(
        BLUEPRINT_ID,
        NEW_IDENTIFIER,
        _p("name", "string", "Display name of the version."),
        _p(
            "origin_version_id",
            "string",
            "Version to copy fields, workflow and views from.",
        ),
    ),
)
def _create_blueprint_version(client, p):
    version = _admin_blueprint(client, p).create_version(
        p["new_identifier"],
        name=p.get("name"),
        origin_version_id=p.get("origin_version_id"),
    )
    return _version_state(version)


@_register(
    "update_blueprint_version",
    domain="blueprints",
    kind="write",
    description="Replace a blueprint version definition; danger_zone_accepted lets a field removal or type change discard artifact data.",
    sdk="GovernAdminBlueprintVersionDefinition.save",
    params=(
        BLUEPRINT_ID,
        VERSION_ID,
        _p(
            "definition",
            "object",
            "Complete version definition from get_blueprint_version.",
            True,
        ),
        _p(
            "danger_zone_accepted",
            "boolean",
            "Accept data loss on artifacts of this version.",
        ),
    ),
)
def _update_blueprint_version(client, p):
    version = _admin_version(client, p)
    definition = _replace_raw(version.get_definition(), p["definition"])
    definition.save(danger_zone_accepted=p.get("danger_zone_accepted"))
    return _version_state(version)


@_register(
    "set_blueprint_version_status",
    domain="blueprints",
    kind="write",
    description="Set a blueprint version status: DRAFT, ACTIVE or ARCHIVED.",
    sdk="GovernAdminBlueprintVersionTrace.set_status",
    params=(BLUEPRINT_ID, VERSION_ID, _p("status", "string", "Target status.", True)),
)
def _set_blueprint_version_status(client, p):
    version = _admin_version(client, p)
    version.get_trace().set_status(p["status"])
    return version.get_trace().get_raw()


@_register(
    "delete_blueprint_version",
    domain="blueprints",
    kind="delete",
    description="Delete a blueprint version; it must hold no artifacts.",
    sdk="GovernAdminBlueprintVersion.delete",
    params=(BLUEPRINT_ID, VERSION_ID),
)
def _delete_blueprint_version(client, p):
    _admin_version(client, p).delete()
    return {"deleted": p["version_id"], "blueprint_id": p["blueprint_id"]}


@_register(
    "list_signoff_configurations",
    domain="blueprints",
    kind="read",
    description="List the signoff configurations (review gates) of a blueprint version.",
    sdk="GovernAdminBlueprintVersion.list_signoff_configurations",
    params=(BLUEPRINT_ID, VERSION_ID),
)
def _list_signoff_configurations(client, p):
    return [
        item.get_raw()
        for item in _admin_version(client, p).list_signoff_configurations()
    ]


@_register(
    "get_signoff_configuration",
    domain="blueprints",
    kind="read",
    description="Get the signoff configuration of one workflow step.",
    sdk="GovernAdminSignoffConfiguration.get_definition",
    params=(BLUEPRINT_ID, VERSION_ID, STEP_ID),
)
def _get_signoff_configuration(client, p):
    configuration = _admin_version(client, p).get_signoff_configuration(p["step_id"])
    return configuration.get_definition().get_raw()


@_register(
    "create_signoff_configuration",
    domain="blueprints",
    kind="write",
    description="Create a review gate on a workflow step: {title, mandatory, feedbackUsersGroups, approvers, recurrenceConfiguration}, no id.",
    sdk="GovernAdminBlueprintVersion.create_signoff_configuration",
    params=(
        BLUEPRINT_ID,
        VERSION_ID,
        STEP_ID,
        _p("configuration", "object", "Signoff configuration without an id.", True),
    ),
)
def _create_signoff_configuration(client, p):
    configuration = _admin_version(client, p).create_signoff_configuration(
        p["step_id"], p["configuration"]
    )
    return configuration.get_definition().get_raw()


@_register(
    "update_signoff_configuration",
    domain="blueprints",
    kind="write",
    description="Replace the signoff configuration of a workflow step.",
    sdk="GovernAdminSignoffConfigurationDefinition.save",
    params=(
        BLUEPRINT_ID,
        VERSION_ID,
        STEP_ID,
        _p("configuration", "object", "Complete signoff configuration.", True),
    ),
)
def _update_signoff_configuration(client, p):
    configuration = _admin_version(client, p).get_signoff_configuration(p["step_id"])
    _replace_raw(configuration.get_definition(), p["configuration"]).save()
    return configuration.get_definition().get_raw()


@_register(
    "delete_signoff_configuration",
    domain="blueprints",
    kind="delete",
    description="Delete the signoff configuration of a workflow step.",
    sdk="GovernAdminSignoffConfiguration.delete",
    params=(BLUEPRINT_ID, VERSION_ID, STEP_ID),
)
def _delete_signoff_configuration(client, p):
    _admin_version(client, p).get_signoff_configuration(p["step_id"]).delete()
    return {
        "deleted": p["step_id"],
        "blueprint_id": p["blueprint_id"],
        "version_id": p["version_id"],
    }


# ---------------------------------------------------------------------------
# roles
# ---------------------------------------------------------------------------


@_register(
    "list_roles",
    domain="roles",
    kind="read",
    description="List roles.",
    sdk="GovernAdminRolesPermissionsHandler.list_roles",
)
def _list_roles(client, p):
    return [item.get_raw() for item in _roles(client).list_roles()]


@_register(
    "get_role",
    domain="roles",
    kind="read",
    description="Get a role definition.",
    sdk="GovernAdminRole.get_definition",
    params=(ROLE_ID,),
)
def _get_role(client, p):
    return _roles(client).get_role(p["role_id"]).get_definition().get_raw()


@_register(
    "create_role",
    domain="roles",
    kind="write",
    description="Create a role: {label, description}.",
    sdk="GovernAdminRolesPermissionsHandler.create_role",
    params=(
        NEW_IDENTIFIER,
        _p("role", "object", "Role definition without an id.", True),
    ),
)
def _create_role(client, p):
    return (
        _roles(client)
        .create_role(p["new_identifier"], p["role"])
        .get_definition()
        .get_raw()
    )


@_register(
    "update_role",
    domain="roles",
    kind="write",
    description="Replace a role definition.",
    sdk="GovernAdminRoleDefinition.save",
    params=(ROLE_ID, _p("role", "object", "Complete role definition.", True)),
)
def _update_role(client, p):
    role = _roles(client).get_role(p["role_id"])
    _replace_raw(role.get_definition(), p["role"]).save()
    return role.get_definition().get_raw()


@_register(
    "delete_role",
    domain="roles",
    kind="delete",
    description="Delete a role.",
    sdk="GovernAdminRole.delete",
    params=(ROLE_ID,),
)
def _delete_role(client, p):
    _roles(client).get_role(p["role_id"]).delete()
    return {"deleted": p["role_id"]}


@_register(
    "list_role_assignments",
    domain="roles",
    kind="read",
    description="List the role assignments of every blueprint.",
    sdk="GovernAdminRolesPermissionsHandler.list_role_assignments",
)
def _list_role_assignments(client, p):
    return [item.get_raw() for item in _roles(client).list_role_assignments()]


@_register(
    "get_role_assignments",
    domain="roles",
    kind="read",
    description="Get the role assignments of a blueprint: roleAssignmentsRules keyed by role ID.",
    sdk="GovernAdminBlueprintRoleAssignments.get_definition",
    params=(BLUEPRINT_ID,),
)
def _get_role_assignments(client, p):
    return (
        _roles(client)
        .get_role_assignments(p["blueprint_id"])
        .get_definition()
        .get_raw()
    )


@_register(
    "create_role_assignments",
    domain="roles",
    kind="write",
    description="Create the role assignments of a blueprint: {blueprintId, roleAssignmentsRules}.",
    sdk="GovernAdminRolesPermissionsHandler.create_role_assignments",
    params=(
        _p(
            "role_assignments",
            "object",
            "Role assignments including blueprintId.",
            True,
        ),
    ),
)
def _create_role_assignments(client, p):
    assignments = _roles(client).create_role_assignments(p["role_assignments"])
    return assignments.get_definition().get_raw()


@_register(
    "update_role_assignments",
    domain="roles",
    kind="write",
    description="Replace the role assignments of a blueprint; preserve the other roles' rules.",
    sdk="GovernAdminBlueprintRoleAssignmentsDefinition.save",
    params=(
        BLUEPRINT_ID,
        _p("role_assignments", "object", "Complete role assignments.", True),
    ),
)
def _update_role_assignments(client, p):
    assignments = _roles(client).get_role_assignments(p["blueprint_id"])
    _replace_raw(assignments.get_definition(), p["role_assignments"]).save()
    return assignments.get_definition().get_raw()


@_register(
    "delete_role_assignments",
    domain="roles",
    kind="delete",
    description="Delete every role assignment of a blueprint.",
    sdk="GovernAdminBlueprintRoleAssignments.delete",
    params=(BLUEPRINT_ID,),
)
def _delete_role_assignments(client, p):
    _roles(client).get_role_assignments(p["blueprint_id"]).delete()
    return {"deleted": "role_assignments", "blueprint_id": p["blueprint_id"]}


@_register(
    "get_default_blueprint_permissions",
    domain="roles",
    kind="read",
    description="Get the default permissions applied to blueprints without their own.",
    sdk="GovernAdminRolesPermissionsHandler.get_default_permissions_definition",
)
def _get_default_blueprint_permissions(client, p):
    return _roles(client).get_default_permissions_definition().get_raw()


@_register(
    "update_default_blueprint_permissions",
    domain="roles",
    kind="write",
    description="Replace the default blueprint permissions.",
    sdk="GovernAdminDefaultPermissionsDefinition.save",
    params=(_p("permissions", "object", "Complete default permissions.", True),),
)
def _update_default_blueprint_permissions(client, p):
    definition = _roles(client).get_default_permissions_definition()
    _replace_raw(definition, p["permissions"]).save()
    return _roles(client).get_default_permissions_definition().get_raw()


@_register(
    "list_blueprint_permissions",
    domain="roles",
    kind="read",
    description="List the blueprints that carry their own permissions.",
    sdk="GovernAdminRolesPermissionsHandler.list_blueprint_permissions",
)
def _list_blueprint_permissions(client, p):
    return [item.get_raw() for item in _roles(client).list_blueprint_permissions()]


@_register(
    "get_blueprint_permissions",
    domain="roles",
    kind="read",
    description="Get the permissions of a blueprint.",
    sdk="GovernAdminBlueprintPermissions.get_definition",
    params=(BLUEPRINT_ID,),
)
def _get_blueprint_permissions(client, p):
    return (
        _roles(client)
        .get_blueprint_permissions(p["blueprint_id"])
        .get_definition()
        .get_raw()
    )


@_register(
    "create_blueprint_permissions",
    domain="roles",
    kind="write",
    description="Create the permissions of a blueprint: {blueprintId, permissions}.",
    sdk="GovernAdminRolesPermissionsHandler.create_blueprint_permissions",
    params=(
        _p(
            "blueprint_permissions",
            "object",
            "Permissions including blueprintId.",
            True,
        ),
    ),
)
def _create_blueprint_permissions(client, p):
    permissions = _roles(client).create_blueprint_permissions(
        p["blueprint_permissions"]
    )
    return permissions.get_definition().get_raw()


@_register(
    "update_blueprint_permissions",
    domain="roles",
    kind="write",
    description="Replace the permissions of a blueprint.",
    sdk="GovernAdminBlueprintPermissionsDefinition.save",
    params=(
        BLUEPRINT_ID,
        _p("blueprint_permissions", "object", "Complete permissions.", True),
    ),
)
def _update_blueprint_permissions(client, p):
    permissions = _roles(client).get_blueprint_permissions(p["blueprint_id"])
    _replace_raw(permissions.get_definition(), p["blueprint_permissions"]).save()
    return permissions.get_definition().get_raw()


@_register(
    "delete_blueprint_permissions",
    domain="roles",
    kind="delete",
    description="Delete the permissions of a blueprint so the defaults apply again.",
    sdk="GovernAdminBlueprintPermissions.delete",
    params=(BLUEPRINT_ID,),
)
def _delete_blueprint_permissions(client, p):
    _roles(client).get_blueprint_permissions(p["blueprint_id"]).delete()
    return {"deleted": "blueprint_permissions", "blueprint_id": p["blueprint_id"]}


# ---------------------------------------------------------------------------
# custom pages
# ---------------------------------------------------------------------------


@_register(
    "list_custom_pages",
    domain="custom_pages",
    kind="read",
    description="List the custom pages visible to the authenticated user.",
    sdk="GovernClient.list_custom_pages",
)
def _list_custom_pages(client, p):
    return [item.get_raw() for item in client.list_custom_pages()]


@_register(
    "get_custom_page",
    domain="custom_pages",
    kind="read",
    description="Get a custom page as the authenticated user sees it.",
    sdk="GovernCustomPage.get_definition",
    params=(CUSTOM_PAGE_ID,),
)
def _get_custom_page(client, p):
    return client.get_custom_page(p["custom_page_id"]).get_definition().get_raw()


@_register(
    "get_custom_page_definition",
    domain="custom_pages",
    kind="read",
    description="Get the editable definition of a custom page (designer).",
    sdk="GovernAdminCustomPage.get_definition",
    params=(CUSTOM_PAGE_ID,),
)
def _get_custom_page_definition(client, p):
    return (
        _pages(client).get_custom_page(p["custom_page_id"]).get_definition().get_raw()
    )


@_register(
    "create_custom_page",
    domain="custom_pages",
    kind="write",
    description="Create a custom page; copy the definition shape from an existing page of the same type.",
    sdk="GovernAdminCustomPagesHandler.create_custom_page",
    params=(
        NEW_IDENTIFIER,
        _p("custom_page", "object", "Custom page definition without an id.", True),
    ),
)
def _create_custom_page(client, p):
    page = _pages(client).create_custom_page(p["new_identifier"], p["custom_page"])
    return page.get_definition().get_raw()


@_register(
    "update_custom_page",
    domain="custom_pages",
    kind="write",
    description="Replace a custom page definition.",
    sdk="GovernAdminCustomPageDefinition.save",
    params=(
        CUSTOM_PAGE_ID,
        _p("custom_page", "object", "Complete custom page definition.", True),
    ),
)
def _update_custom_page(client, p):
    page = _pages(client).get_custom_page(p["custom_page_id"])
    _replace_raw(page.get_definition(), p["custom_page"]).save()
    return page.get_definition().get_raw()


@_register(
    "delete_custom_page",
    domain="custom_pages",
    kind="delete",
    description="Delete a custom page.",
    sdk="GovernAdminCustomPage.delete",
    params=(CUSTOM_PAGE_ID,),
)
def _delete_custom_page(client, p):
    _pages(client).get_custom_page(p["custom_page_id"]).delete()
    return {"deleted": p["custom_page_id"]}


@_register(
    "get_custom_pages_order",
    domain="custom_pages",
    kind="read",
    description="Get the display order of the custom pages as a list of IDs.",
    sdk="GovernAdminCustomPagesHandler.get_custom_pages_order",
)
def _get_custom_pages_order(client, p):
    return _pages(client).get_custom_pages_order()


@_register(
    "update_custom_pages_order",
    domain="custom_pages",
    kind="write",
    description="Set the display order of the custom pages; the list must contain every page ID.",
    sdk="GovernAdminCustomPagesHandler.save_custom_pages_order",
    params=(_p("order", "list", "Custom page IDs in display order.", True),),
)
def _update_custom_pages_order(client, p):
    return _pages(client).save_custom_pages_order(list(p["order"]))


# ---------------------------------------------------------------------------
# time series
# ---------------------------------------------------------------------------

DATAPOINTS = _p(
    "datapoints",
    "list",
    "Datapoints, each {timestamp: epoch milliseconds, value: number}.",
)
MIN_TIMESTAMP = _p("min_timestamp", "integer", "Lower bound, epoch milliseconds.")
MAX_TIMESTAMP = _p("max_timestamp", "integer", "Upper bound, epoch milliseconds.")


@_register(
    "create_time_series",
    domain="time_series",
    kind="write",
    description="Create a time series, optionally with initial datapoints; returns its ID.",
    sdk="GovernClient.create_time_series",
    params=(DATAPOINTS,),
)
def _create_time_series(client, p):
    datapoints = list(p.get("datapoints") or [])
    time_series = client.create_time_series(datapoints=datapoints)
    return {"time_series_id": time_series.time_series_id, "datapoints": len(datapoints)}


@_register(
    "get_time_series_values",
    domain="time_series",
    kind="read",
    description="Get the datapoints of a time series, optionally within a timestamp window.",
    sdk="GovernTimeSeries.get_values",
    params=(TIME_SERIES_ID, MIN_TIMESTAMP, MAX_TIMESTAMP),
)
def _get_time_series_values(client, p):
    return client.get_time_series(p["time_series_id"]).get_values(
        min_timestamp=p.get("min_timestamp"), max_timestamp=p.get("max_timestamp")
    )


@_register(
    "push_time_series_values",
    domain="time_series",
    kind="write",
    description="Push datapoints into a time series; upsert overwrites existing timestamps.",
    sdk="GovernTimeSeries.push_values",
    params=(
        TIME_SERIES_ID,
        _p("datapoints", "list", "Datapoints, each {timestamp, value}.", True),
        _p("upsert", "boolean", "Overwrite existing timestamps (default true)."),
    ),
)
def _push_time_series_values(client, p):
    datapoints = list(p["datapoints"])
    client.get_time_series(p["time_series_id"]).push_values(
        datapoints, upsert=bool(p.get("upsert", True))
    )
    return {"time_series_id": p["time_series_id"], "pushed": len(datapoints)}


@_register(
    "delete_time_series_values",
    domain="time_series",
    kind="delete",
    description="Delete datapoints of a time series within a window, or all of them without bounds.",
    sdk="GovernTimeSeries.delete",
    params=(TIME_SERIES_ID, MIN_TIMESTAMP, MAX_TIMESTAMP),
)
def _delete_time_series_values(client, p):
    client.get_time_series(p["time_series_id"]).delete(
        min_timestamp=p.get("min_timestamp"), max_timestamp=p.get("max_timestamp")
    )
    return {
        "time_series_id": p["time_series_id"],
        "deleted": True,
        "min_timestamp": p.get("min_timestamp"),
        "max_timestamp": p.get("max_timestamp"),
    }


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------


@_register(
    "upload_file",
    domain="files",
    kind="write",
    description="Upload a local file; attach the returned ID to an UPLOADED_FILE field afterwards.",
    sdk="GovernClient.upload_file",
    params=(
        _p("file_path", "string", "Local path of the file to upload.", True),
        _p(
            "file_name",
            "string",
            "Name stored in Govern (default: the local file name).",
        ),
    ),
)
def _upload_file(client, p):
    path = os.path.realpath(
        os.path.expanduser(require_non_empty_string(p["file_path"], "file_path"))
    )
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")
    file_name = p.get("file_name") or os.path.basename(path)
    with open(path, "rb") as handle:
        uploaded = client.upload_file(file_name, handle)
    return uploaded.get_description()


@_register(
    "get_uploaded_file",
    domain="files",
    kind="read",
    description="Get the description (name, size, type) of an uploaded file.",
    sdk="GovernUploadedFile.get_description",
    params=(UPLOADED_FILE_ID,),
)
def _get_uploaded_file(client, p):
    return client.get_uploaded_file(p["uploaded_file_id"]).get_description()


@_register(
    "download_uploaded_file",
    domain="files",
    kind="read",
    description="Download an uploaded file to a local path; never overwrites unless overwrite is true.",
    sdk="GovernUploadedFile.download",
    params=(
        UPLOADED_FILE_ID,
        _p("output_path", "string", "Local destination path.", True),
        _p("overwrite", "boolean", "Replace an existing destination file."),
    ),
)
def _download_uploaded_file(client, p):
    output_path = require_non_empty_string(p["output_path"], "output_path")
    overwrite = bool(p.get("overwrite", False))
    absolute_path = os.path.realpath(os.path.expanduser(output_path))
    parent = os.path.dirname(absolute_path)
    if not os.path.isdir(parent):
        raise FileNotFoundError(f"Destination directory does not exist: {parent}")
    if os.path.lexists(absolute_path) and not overwrite:
        raise FileExistsError(
            f"Destination already exists: {absolute_path}. Set overwrite=true to replace it."
        )
    uploaded = client.get_uploaded_file(p["uploaded_file_id"])
    description = uploaded.get_description()
    stream = uploaded.download()
    temporary_path = None
    digest = hashlib.sha256()
    size = 0
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".govern-file-", suffix=".tmp", dir=parent, delete=False
        ) as handle:
            temporary_path = handle.name
            while True:
                chunk = stream.read(_CHUNK_SIZE)
                if not chunk:
                    break
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
        close = getattr(stream, "close", None)
        if close is not None:
            close()
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
    return {
        "uploaded_file_id": p["uploaded_file_id"],
        "output_path": absolute_path,
        "size_bytes": size,
        "sha256": digest.hexdigest(),
        "description": description,
    }


@_register(
    "delete_uploaded_file",
    domain="files",
    kind="delete",
    description="Delete an uploaded file.",
    sdk="GovernUploadedFile.delete",
    params=(UPLOADED_FILE_ID,),
)
def _delete_uploaded_file(client, p):
    client.get_uploaded_file(p["uploaded_file_id"]).delete()
    return {"deleted": p["uploaded_file_id"]}


# ---------------------------------------------------------------------------
# users and groups
# ---------------------------------------------------------------------------


@_register(
    "list_users",
    domain="users",
    kind="read",
    description="List Govern users; include_settings adds each user's full settings.",
    sdk="GovernClient.list_users",
    params=(_p("include_settings", "boolean", "Include full settings per user."),),
)
def _list_users(client, p):
    return client.list_users(
        as_objects=False, include_settings=bool(p.get("include_settings", False))
    )


@_register(
    "get_user",
    domain="users",
    kind="read",
    description="Get a user's settings (admin).",
    sdk="GovernUser.get_settings",
    params=(LOGIN,),
)
def _get_user(client, p):
    return client.get_user(p["login"]).get_settings().get_raw()


@_register(
    "create_user",
    domain="users",
    kind="write",
    description="Create a Govern user (admin).",
    sdk="GovernClient.create_user",
    params=(
        LOGIN,
        _p("password", "string", "Password; required for LOCAL users."),
        _p("display_name", "string", "Display name."),
        _p(
            "source_type",
            "string",
            "LOCAL (default), LDAP, or another identity source.",
        ),
        _p("groups", "list", "Group names."),
        _p("profile", "string", "User profile; leave empty for the server default."),
        _p("email", "string", "Email address."),
    ),
)
def _create_user(client, p):
    kwargs: dict[str, Any] = {}
    for key in ("display_name", "source_type", "groups", "profile", "email"):
        if p.get(key) is not None:
            kwargs[key] = p[key]
    user = client.create_user(p["login"], p.get("password"), **kwargs)
    return user.get_settings().get_raw()


@_register(
    "update_user",
    domain="users",
    kind="write",
    description="Merge top-level keys (displayName, email, groups, enabled, userProfile, ...) into a user's settings.",
    sdk="GovernUserSettings.save",
    params=(LOGIN, _p("settings", "object", "Settings keys to set.", True)),
)
def _update_user(client, p):
    user = client.get_user(p["login"])
    settings = user.get_settings()
    settings.get_raw().update(p["settings"])
    settings.save()
    return user.get_settings().get_raw()


@_register(
    "delete_user",
    domain="users",
    kind="delete",
    description="Delete a Govern user (admin).",
    sdk="GovernUser.delete",
    params=(
        LOGIN,
        _p("allow_self_deletion", "boolean", "Allow deleting the authenticated user."),
    ),
)
def _delete_user(client, p):
    client.get_user(p["login"]).delete(
        allow_self_deletion=bool(p.get("allow_self_deletion", False))
    )
    return {"deleted": p["login"]}


@_register(
    "get_own_user",
    domain="users",
    kind="read",
    description="Get the settings of the authenticated user.",
    sdk="GovernOwnUser.get_settings",
)
def _get_own_user(client, p):
    return client.get_own_user().get_settings().get_raw()


@_register(
    "list_groups",
    domain="users",
    kind="read",
    description="List Govern groups (admin).",
    sdk="GovernClient.list_groups",
)
def _list_groups(client, p):
    return client.list_groups()


@_register(
    "get_group",
    domain="users",
    kind="read",
    description="Get a group definition (admin).",
    sdk="GovernGroup.get_definition",
    params=(GROUP_NAME,),
)
def _get_group(client, p):
    return client.get_group(p["name"]).get_definition()


@_register(
    "create_group",
    domain="users",
    kind="write",
    description="Create a Govern group (admin).",
    sdk="GovernClient.create_group",
    params=(
        GROUP_NAME,
        _p("description", "string", "Group description."),
        _p("source_type", "string", "LOCAL (default) or LDAP."),
    ),
)
def _create_group(client, p):
    kwargs: dict[str, Any] = {}
    for key in ("description", "source_type"):
        if p.get(key) is not None:
            kwargs[key] = p[key]
    return client.create_group(p["name"], **kwargs).get_definition()


@_register(
    "update_group",
    domain="users",
    kind="write",
    description="Merge top-level keys (description, isGovernArchitect, ...) into a group definition.",
    sdk="GovernGroup.set_definition",
    params=(GROUP_NAME, _p("definition", "object", "Definition keys to set.", True)),
)
def _update_group(client, p):
    group = client.get_group(p["name"])
    definition = group.get_definition()
    definition.update(p["definition"])
    group.set_definition(definition)
    return group.get_definition()


@_register(
    "delete_group",
    domain="users",
    kind="delete",
    description="Delete a Govern group (admin).",
    sdk="GovernGroup.delete",
    params=(GROUP_NAME,),
)
def _delete_group(client, p):
    client.get_group(p["name"]).delete()
    return {"deleted": p["name"]}


# ---------------------------------------------------------------------------
# instance
# ---------------------------------------------------------------------------


@_register(
    "get_instance_info",
    domain="instance",
    kind="read",
    description="Get the Govern node identity and version; confirms the URL targets a GOVERN node.",
    sdk="GovernClient.get_instance_info",
)
def _get_instance_info(client, p):
    return client.get_instance_info().raw


@_register(
    "get_auth_info",
    domain="instance",
    kind="read",
    description="Get the identity behind the configured API key.",
    sdk="GovernClient.get_auth_info",
)
def _get_auth_info(client, p):
    return client.get_auth_info()


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------

_KIND_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: isinstance(value, bool),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "object": lambda value: isinstance(value, dict),
    "list": lambda value: isinstance(value, list),
    "any": lambda value: True,
}


def _validate_params(
    operation_id: str, operation: GovernOperation, params: dict[str, Any]
) -> None:
    declared = {param.name: param for param in operation.params}
    unexpected = sorted(set(params) - set(declared))
    if unexpected:
        raise ValueError(
            f"Unexpected params for '{operation_id}': {unexpected}. "
            f"Allowed: {list(declared)}"
        )
    missing = [
        param.name
        for param in operation.params
        if param.required and params.get(param.name) in (None, "")
    ]
    if missing:
        raise ValueError(f"Missing required params for '{operation_id}': {missing}")
    for name, value in params.items():
        if value is None:
            continue
        param = declared[name]
        if not _KIND_CHECKS[param.kind](value):
            raise ValueError(f"Param '{name}' must be a {param.kind}")
        if param.kind == "string" and param.required:
            require_non_empty_string(value, name)


def _operation_summary(operation_id: str, operation: GovernOperation) -> dict[str, Any]:
    return {
        "operation": operation_id,
        "domain": operation.domain,
        "kind": operation.kind,
        "description": operation.description,
        "sdk": operation.sdk,
        "params": [
            {
                "name": param.name,
                "kind": param.kind,
                "required": param.required,
                "description": param.description,
            }
            for param in operation.params
        ],
    }


def _catalog(domain: str) -> str:
    if domain and domain not in DOMAINS:
        raise ValueError(
            f"Unknown Govern domain '{domain}'. Available: {list(DOMAINS)}"
        )
    operations = [
        _operation_summary(operation_id, operation)
        for operation_id, operation in GOVERN_OPERATIONS.items()
        if not domain or operation.domain == domain
    ]
    return compact_json(
        {"count": len(operations), "domains": list(DOMAINS), "operations": operations}
    )


_verified_hosts: set[str] = set()


def _require_govern_node(client) -> None:
    """Check once per host that the URL targets a GOVERN node.

    `/instance-info` is permission-gated, so an unreadable answer is not an
    error; the node type is then trusted as configured.
    """
    host = getattr(client, "host", "")
    if host in _verified_hosts:
        return
    try:
        node_type = client.get_instance_info().node_type
    except Exception:
        _verified_hosts.add(host)
        return
    if node_type != "GOVERN":
        raise ValueError(
            f"The configured Govern URL {host} points to a {node_type} node, not a "
            "Govern node. Check DKU_GOVERN_URL or the Govern URL of the active instance."
        )
    _verified_hosts.add(host)


@mcp.tool(
    title="Govern",
    description="Single entry point to Dataiku Govern. Leave operation empty to list the catalog; otherwise run one catalog operation through the Govern Python SDK.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def govern(
    ctx: Context,
    operation: str = "",
    params: dict[str, Any] | None = None,
    domain: str = "",
) -> str:
    """Run one Govern operation, or list the catalog when ``operation`` is empty.

    Args:
        operation: Operation id from the catalog, for example ``get_artifact``.
            Leave empty to get the catalog.
        params: Flat JSON object with the operation's parameters: identifiers,
            payloads and options, as listed in the catalog.
        domain: Optional catalog filter: artifacts, signoffs, blueprints, roles,
            custom_pages, time_series, files, users or instance.
    """
    operation = (operation or "").strip()
    domain = (domain or "").strip()
    params = dict(params or {})
    if not operation:
        if params:
            raise ValueError("params are only valid with an operation")
        return _catalog(domain)
    if domain:
        raise ValueError("domain is only valid when listing the catalog")
    try:
        spec = GOVERN_OPERATIONS[operation]
    except KeyError:
        raise ValueError(
            f"Unknown Govern operation '{operation}'. Call govern with an empty "
            "operation to list the catalog."
        ) from None
    _validate_params(operation, spec, params)
    await ctx.info(f"Running Govern operation '{operation}'...")

    def _run():
        client = get_govern_client()
        _require_govern_node(client)
        return spec.run(client, params)

    return compact_json(await run_blocking(_run))

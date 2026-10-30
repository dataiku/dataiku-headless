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

"""Audited operation declarations for Deployer, Govern and Agent Management."""

from .operation_registry import Operation, arguments_for, make_catalog
from .tools import deployer, govern, agent_management
from .operation_schemas import govern_arguments


def _deployer(
    name: str, example: dict, *, effect="read", destructive=False, idempotent=False
):
    handler = getattr(deployer, name)
    return Operation(
        operation_id="deployer." + name.replace("_deployer", ""),
        domain="deployer",
        description=handler.__doc__,
        effect=effect,
        allowed_instance_types=("deployer",),
        arguments=arguments_for(handler),
        handler=handler,
        requirements="Selected node must expose Project/API Deployer. The configured type does not verify feature availability or permissions.",
        response_contract="Selected operational fields; credentials, raw settings, free-text diagnostics and update logs are omitted. Configuration saves do not apply deployments; start_update returns a future_id for deployer.get_future_status on the same instance.",
        example=example,
        destructive=destructive,
        idempotent=idempotent,
    )


_DEPLOYER_OPERATIONS = list(
    [
        _deployer("list_deployer_stages", {"deployer_type": "project"}),
        _deployer("list_deployer_infrastructures", {"deployer_type": "project"}),
        _deployer(
            "get_deployer_infrastructure",
            {"deployer_type": "project", "infra_id": "discovered-infra"},
        ),
        _deployer("list_deployer_published_items", {"deployer_type": "api"}),
        _deployer(
            "get_deployer_published_item",
            {"deployer_type": "api", "source_id": "discovered-service"},
        ),
        _deployer("list_deployer_deployments", {"deployer_type": "project"}),
        _deployer(
            "get_deployer_deployment",
            {"deployer_type": "project", "deployment_id": "discovered-deployment"},
        ),
        _deployer(
            "list_deployer_updates",
            {"deployer_type": "project", "deployment_id": "discovered-deployment"},
        ),
        _deployer(
            "get_deployer_update",
            {"deployer_type": "project", "deployment_id": "discovered-deployment"},
        ),
        _deployer(
            "create_deployer_deployment",
            {
                "deployer_type": "project",
                "deployment_id": "requested-deployment",
                "infra_id": "discovered-infra",
                "source_id": "discovered-project",
                "version": "discovered-bundle",
            },
            effect="write",
        ),
        _deployer(
            "update_deployer_deployment",
            {
                "deployer_type": "api",
                "deployment_id": "discovered-deployment",
                "version": "discovered-version",
            },
            effect="write",
            destructive=True,
            idempotent=True,
        ),
        _deployer(
            "start_deployer_update",
            {"deployer_type": "project", "deployment_id": "discovered-deployment"},
            effect="write",
            destructive=True,
        ),
        _deployer("get_deployer_future_status", {"future_id": "returned-future"}),
    ]
)


def _agent_management_operation(name, spec):
    arguments = (
        agent_management.AlertEvaluationArguments
        if name == "evaluate_alerts"
        else arguments_for(spec.handler, exclude=("client",))
    )
    return Operation(
        operation_id="agent-management." + name,
        domain="agent-management",
        category=spec.domain,
        description=spec.handler.__doc__,
        effect=spec.effect,
        allowed_instance_types=("agent-management",),
        arguments=arguments,
        handler=agent_management.operation_handler(spec),
        requirements="Requires dataiku-api-client 15.2.0 or newer and a compatible Agent Management release. Uses public SDK methods only. Nested settings are backend-defined. Catalog presence does not verify live permissions or server features.",
        response_contract="Public SDK JSON with credentials recursively redacted. Save inspected fetchedRevision as expected_revision for writes. Async starts return platform_id, agent_id and operation_id for polling without waiting. No automatic retries. Alert evaluation returns queued_agent_count, not newly created alerts. Local-file transfers require stdio.",
        example=spec.example,
        destructive=spec.destructive,
        transports=("stdio",)
        if "output_path" in spec.local_file_fields
        else ("stdio", "http"),
        local_file_fields=spec.local_file_fields,
    )


def _govern_operation(name, spec):
    arguments = govern_arguments(name, spec)
    example = {}
    for param in spec.params:
        if param.required:
            example[param.name] = {
                "string": "discovered-" + param.name.replace("_", "-"),
                "object": {},
                "list": [],
                "boolean": False,
                "integer": 1,
                "any": "value",
            }[param.kind]
    if name == "delete_time_series_values":
        example["delete_all"] = True
    if "status" in example and name in {
        "update_signoff_status",
        "add_signoff_feedback",
        "update_signoff_feedback",
        "add_signoff_approval",
        "update_signoff_approval",
    }:
        example["status"] = "APPROVED"
    if "users_container" in example:
        example["users_container"] = {"type": "user", "login": "discovered-user"}
    return Operation(
        operation_id="govern." + name,
        domain="govern",
        category=spec.domain,
        description=spec.description,
        effect="read" if spec.kind == "read" else "write",
        allowed_instance_types=("govern",),
        arguments=arguments,
        handler=govern.operation_handler(spec),
        backend="govern",
        transports=("stdio",),
        requirements="Requires a compatible Govern release and a configured Govern profile with stdio credentials. Govern HTTP authentication is unsupported. Blueprint-specific definitions remain backend-defined; inspect current definitions before replacing them.",
        response_contract="Public Govern SDK JSON with credential fields recursively redacted. Write and delete actions operate on Govern records, not DSS projects. Definition replacements require preserving unrelated fields; inspect and re-read after mutations. No retry on uncertain outcome.",
        example=example,
        destructive=spec.kind != "read" and not name.startswith("create_"),
        local_file_fields=("file_path", "output_path"),
    )


OPERATIONS = make_catalog(
    [
        *_DEPLOYER_OPERATIONS,
        *[
            _agent_management_operation(name, spec)
            for name, spec in agent_management.AGENT_MANAGEMENT_OPERATIONS.items()
        ],
        *[
            _govern_operation(name, spec)
            for name, spec in govern.GOVERN_OPERATIONS.items()
        ],
    ]
)
